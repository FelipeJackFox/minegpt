"""
finetune.py — Instruction tuning de MineGPT
=============================================

¿QUÉ ES INSTRUCTION TUNING?
=============================
Después del pre-training, el modelo sabe "hablar" y sabe sobre Minecraft,
pero NO sabe seguir instrucciones. Si le preguntas algo, solo completa texto.

Instruction tuning es una SEGUNDA FASE de entrenamiento, más corta, donde
el modelo aprende a RESPONDER preguntas usando pares instrucción→respuesta.

Antes de instruction tuning:
  Input: "How do I craft a sword?"
  Output: "How do I craft a shield? How do I craft a..."  (solo completa texto)

Después de instruction tuning:
  Input: "How do I craft a sword?"
  Output: "Place 2 iron ingots and 1 stick in the crafting grid."  (responde!)

FORMATO DE ENTRENAMIENTO:
  ### Instruction:
  How do I craft a Diamond Sword in Minecraft?

  ### Response:
  To craft a Diamond Sword, place 2 diamonds vertically above 1 stick
  in the crafting table. This requires a 3x3 crafting grid.

El modelo aprende que después de "### Response:" debe dar una respuesta útil.

Uso:
    python -m model.finetune
    python -m model.finetune --resume
"""

import json
import time
import logging
import argparse
from pathlib import Path

try:
    import mlx.core as mx
    import mlx.nn as nn
    import mlx.optimizers as optim
    HAS_MLX = True
except ImportError:
    HAS_MLX = False

import sentencepiece as spm
from tqdm import tqdm

from model.gpt import MineGPT, create_model_from_config
from model.train import save_checkpoint, load_checkpoint, get_lr, compute_loss
from utils.config import CONFIG

PROCESSED_DIR = Path(__file__).parent.parent / "processed_data"
RAW_DIR = Path(__file__).parent.parent / "raw_data"
CHECKPOINT_DIR = CONFIG["paths"]["checkpoints"]
TOKENIZER_MODEL = CONFIG["paths"]["tokenizer_model"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# Formato de instrucción
INSTRUCTION_TEMPLATE = "### Instruction:\n{instruction}\n\n### Response:\n{response}"


def prepare_instruction_data(tokenizer: spm.SentencePieceProcessor,
                             ctx_len: int) -> list:
    """
    Prepara datos de instruction tuning de todas las fuentes.

    Fuentes:
    1. Alpaca (52k instrucciones generales)
    2. Q&A de Minecraft (heurístico y/o generado por IA)
    3. Crafteos estructurados
    """
    all_tokens = []

    # Alpaca
    alpaca_file = RAW_DIR / "general" / "alpaca.jsonl"
    if alpaca_file.exists():
        log.info("Cargando Alpaca...")
        with open(alpaca_file, "r", encoding="utf-8") as f:
            for line in f:
                entry = json.loads(line)
                instruction = entry["instruction"]
                if entry.get("input"):
                    instruction += f"\n{entry['input']}"
                text = INSTRUCTION_TEMPLATE.format(
                    instruction=instruction,
                    response=entry["output"],
                )
                tokens = tokenizer.encode(text)
                if len(tokens) <= ctx_len:
                    all_tokens.append(tokens)
        log.info(f"  Alpaca: {len(all_tokens)} ejemplos")

    # Q&A Minecraft
    for qa_file in PROCESSED_DIR.glob("minecraft_qa_*.jsonl"):
        count_before = len(all_tokens)
        with open(qa_file, "r", encoding="utf-8") as f:
            for line in f:
                entry = json.loads(line)
                text = INSTRUCTION_TEMPLATE.format(
                    instruction=entry["instruction"],
                    response=entry["output"],
                )
                tokens = tokenizer.encode(text)
                if len(tokens) <= ctx_len:
                    all_tokens.append(tokens)
        log.info(f"  {qa_file.name}: {len(all_tokens) - count_before} ejemplos")

    # Crafteos
    crafting_file = PROCESSED_DIR / "crafting_qa.jsonl"
    if crafting_file.exists():
        count_before = len(all_tokens)
        with open(crafting_file, "r", encoding="utf-8") as f:
            for line in f:
                entry = json.loads(line)
                text = INSTRUCTION_TEMPLATE.format(
                    instruction=entry["instruction"],
                    response=entry["output"],
                )
                tokens = tokenizer.encode(text)
                if len(tokens) <= ctx_len:
                    all_tokens.append(tokens)
        log.info(f"  Crafteos: {len(all_tokens) - count_before} ejemplos")

    log.info(f"Total ejemplos de instruction tuning: {len(all_tokens)}")
    return all_tokens


def train_finetune(resume: bool = False, use_wandb: bool = True):
    """Ejecuta instruction tuning."""
    if not HAS_MLX:
        log.error("MLX no disponible.")
        return

    # Cargar tokenizer
    sp = spm.SentencePieceProcessor()
    sp.load(str(TOKENIZER_MODEL))

    # Cargar modelo pre-entrenado desde checkpoint
    model = create_model_from_config(CONFIG["model"], sp.get_piece_size())
    step, _, _ = load_checkpoint(model, CHECKPOINT_DIR)
    if step == 0:
        log.warning("No se encontró checkpoint de pre-training. El modelo no está pre-entrenado.")

    # Preparar datos
    all_sequences = prepare_instruction_data(sp, CONFIG["model"]["ctx_len"])
    if not all_sequences:
        log.error("No hay datos de instruction tuning.")
        return

    # Optimizer con lr más bajo
    optimizer = optim.AdamW(learning_rate=CONFIG["finetune"]["learning_rate"])

    # wandb
    if use_wandb:
        try:
            import wandb
            wandb.init(project="minegpt-finetune", config=CONFIG["finetune"])
        except ImportError:
            use_wandb = False

    # Training loop
    batch_size = CONFIG["finetune"]["batch_size"]
    max_epochs = CONFIG["finetune"]["max_epochs"]
    loss_and_grad_fn = nn.value_and_grad(model, compute_loss)

    ft_step = 0
    for epoch in range(max_epochs):
        log.info(f"\n--- Finetune Epoch {epoch + 1}/{max_epochs} ---")

        # Shuffle
        import random
        random.shuffle(all_sequences)

        for i in tqdm(range(0, len(all_sequences) - batch_size, batch_size),
                      desc=f"FT Epoch {epoch+1}"):
            # Crear batch (pad a ctx_len)
            batch = all_sequences[i:i + batch_size]
            padded = []
            for seq in batch:
                if len(seq) < CONFIG["model"]["ctx_len"]:
                    seq = seq + [sp.pad_id()] * (CONFIG["model"]["ctx_len"] - len(seq))
                else:
                    seq = seq[:CONFIG["model"]["ctx_len"]]
                padded.append(seq)

            tokens = mx.array(padded, dtype=mx.int32)
            x = tokens[:, :-1]
            y = tokens[:, 1:]

            loss, grads = loss_and_grad_fn(model, x, y)
            grads, _ = optim.clip_grad_norm(grads, max_norm=1.0)
            optimizer.update(model, grads)
            mx.eval(model.parameters(), optimizer.state)

            if ft_step % 50 == 0:
                log.info(f"  FT Step {ft_step}: loss={loss.item():.4f}")
                if use_wandb:
                    import wandb
                    wandb.log({"ft_loss": loss.item(), "ft_step": ft_step})

            ft_step += 1

    # Guardar checkpoint de finetune
    ft_checkpoint_dir = CHECKPOINT_DIR / "finetune"
    save_checkpoint(model, optimizer, ft_step, max_epochs, [],
                    CONFIG["finetune"], ft_checkpoint_dir)

    log.info("Instruction tuning completado.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Instruction tuning de MineGPT")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--no-wandb", action="store_true")
    args = parser.parse_args()

    train_finetune(resume=args.resume, use_wandb=not args.no_wandb)
