"""
generate.py — Inferencia y generación de texto con MineGPT
============================================================

Este script carga el modelo entrenado y genera texto.
Soporta dos modos:

1. Modo completar: dado un prompt, genera la continuación
2. Modo chat: formato instrucción→respuesta interactivo

¿CÓMO GENERA TEXTO UN LLM?
============================
El modelo predice UN token a la vez. Para generar texto:

1. Tokenizar el prompt: "How do I" → [45, 12, 89]
2. Pasar por el modelo → obtener probabilidades del siguiente token
3. Samplear un token de esas probabilidades → 234 ("craft")
4. Agregar al input: [45, 12, 89, 234]
5. Repetir desde paso 2

¿QUÉ ES TEMPERATURE?
La temperature controla qué tan "creativo" o "determinístico" es el sampling:
- temperature=0: siempre elige el token más probable (determinístico, repetitivo)
- temperature=0.7: un buen balance (creativo pero coherente)
- temperature=1.5: muy creativo (puede ser incoherente)

Matemáticamente: divide los logits por temperature antes de softmax.
Temperature baja → distribución más peaked → menos variedad
Temperature alta → distribución más plana → más variedad

¿QUÉ ES TOP-K?
Solo considerar los K tokens más probables. Los demás se descartan.
- top_k=50: elige entre los 50 tokens más probables
- Evita que el modelo genere tokens muy improbables (basura)

¿QUÉ ES TOP-P (NUCLEUS SAMPLING)?
Considerar los tokens cuya probabilidad acumulada suma ≤ p.
- top_p=0.9: tomar los tokens que juntos suman 90% de probabilidad
- Más adaptativo que top-k (a veces 5 tokens cubren el 90%, a veces 200)

Uso:
    python -m model.generate "How do I craft a diamond sword?"
    python -m model.generate --chat          # Modo interactivo
    python -m model.generate --temperature 0.5 --top-k 30
"""

import argparse
import logging
from pathlib import Path

try:
    import mlx.core as mx
    import mlx.nn as nn
    HAS_MLX = True
except ImportError:
    HAS_MLX = False

import sentencepiece as spm

from model.gpt import MineGPT, create_model_from_config
from model.train import load_checkpoint
from utils.config import CONFIG

CHECKPOINT_DIR = CONFIG["paths"]["checkpoints"]
TOKENIZER_MODEL = CONFIG["paths"]["tokenizer_model"]

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)


def generate(
    model: MineGPT,
    tokenizer: spm.SentencePieceProcessor,
    prompt: str,
    max_tokens: int = 256,
    temperature: float = 0.7,
    top_k: int = 50,
    top_p: float = 0.9,
    stream: bool = True,
) -> str:
    """
    Genera texto dado un prompt.

    Args:
        model: Modelo MineGPT cargado
        tokenizer: SentencePiece tokenizer
        prompt: Texto de entrada
        max_tokens: Máximo de tokens a generar
        temperature: Control de creatividad (0.0-2.0)
        top_k: Número de tokens candidatos
        top_p: Nucleus sampling threshold
        stream: Si True, imprime token por token

    Returns:
        Texto generado completo
    """
    # Tokenizar prompt
    tokens = tokenizer.encode(prompt)
    tokens = mx.array([tokens], dtype=mx.int32)  # Agregar dimensión de batch

    generated_tokens = []

    for _ in range(max_tokens):
        # Truncar al contexto máximo si es necesario
        if tokens.shape[1] > model.ctx_len:
            tokens = tokens[:, -model.ctx_len:]

        # Forward pass: obtener logits del último token
        logits = model(tokens)
        logits = logits[:, -1, :]  # Solo el último token: (1, vocab_size)

        # Aplicar temperature
        if temperature > 0:
            logits = logits / temperature
        else:
            # temperature=0: greedy (siempre el más probable)
            next_token = mx.argmax(logits, axis=-1)
            generated_tokens.append(next_token.item())
            tokens = mx.concatenate([tokens, next_token.reshape(1, 1)], axis=1)

            if next_token.item() == tokenizer.eos_id():
                break
            if stream:
                print(tokenizer.decode([next_token.item()]), end="", flush=True)
            continue

        # Top-K filtering
        if top_k > 0:
            top_k_values = mx.topk(logits, k=min(top_k, logits.shape[-1]))
            min_value = top_k_values[0, -1]
            logits = mx.where(logits < min_value, float('-inf'), logits)

        # Softmax → probabilidades
        probs = mx.softmax(logits, axis=-1)

        # Top-P (nucleus) filtering
        if top_p < 1.0:
            sorted_indices = mx.argsort(probs, axis=-1)[:, ::-1]
            sorted_probs = mx.take_along_axis(probs, sorted_indices, axis=-1)
            cumulative_probs = mx.cumsum(sorted_probs, axis=-1)

            # Crear mask para tokens fuera del nucleus
            mask = cumulative_probs - sorted_probs > top_p
            sorted_probs = mx.where(mask, 0.0, sorted_probs)

            # Renormalizar
            sorted_probs = sorted_probs / mx.sum(sorted_probs, axis=-1, keepdims=True)
            probs = mx.zeros_like(probs)
            probs = probs.at[mx.arange(probs.shape[0]).reshape(-1, 1), sorted_indices].set(sorted_probs)

        # Samplear
        next_token = mx.random.categorical(mx.log(probs + 1e-10))
        generated_tokens.append(next_token.item())

        # Agregar al input para la siguiente iteración
        tokens = mx.concatenate([tokens, next_token.reshape(1, 1)], axis=1)

        # Parar si generamos end-of-sequence
        if next_token.item() == tokenizer.eos_id():
            break

        # Stream: imprimir token por token
        if stream:
            piece = tokenizer.decode([next_token.item()])
            print(piece, end="", flush=True)

    if stream:
        print()  # Newline final

    return tokenizer.decode(generated_tokens)


def chat_mode(model, tokenizer, **kwargs):
    """
    Modo chat interactivo en terminal.

    Usa el formato de instruction tuning:
    ### Instruction:
    {user_input}

    ### Response:
    {model_output}
    """
    print("=" * 50)
    print("MineGPT — Chat Mode")
    print("Escribe tu pregunta sobre Minecraft.")
    print("Escribe 'quit' para salir.")
    print("=" * 50)

    while True:
        try:
            user_input = input("\nTú: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if user_input.lower() in ("quit", "exit", "q"):
            break

        if not user_input:
            continue

        # Formatear como instrucción
        prompt = f"### Instruction:\n{user_input}\n\n### Response:\n"

        print("\nMineGPT: ", end="")
        generate(model, tokenizer, prompt, **kwargs)


def main():
    if not HAS_MLX:
        print("MLX no disponible. Solo funciona en macOS con Apple Silicon.")
        return

    parser = argparse.ArgumentParser(description="Generación de texto con MineGPT")
    parser.add_argument("prompt", nargs="?", default=None, help="Texto de entrada")
    parser.add_argument("--chat", action="store_true", help="Modo chat interactivo")
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--top-k", type=int, default=50)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--checkpoint", default=None, help="Path a checkpoint específico")
    args = parser.parse_args()

    # Cargar tokenizer
    sp = spm.SentencePieceProcessor()
    sp.load(str(TOKENIZER_MODEL))

    # Cargar modelo
    model = create_model_from_config(CONFIG["model"], sp.get_piece_size())

    # Intentar cargar checkpoint de finetune primero, luego pre-training
    ft_dir = CHECKPOINT_DIR / "finetune"
    if ft_dir.exists():
        load_checkpoint(model, ft_dir)
        log.info("Modelo cargado desde checkpoint de finetune")
    else:
        load_checkpoint(model, CHECKPOINT_DIR)
        log.info("Modelo cargado desde checkpoint de pre-training (sin finetune)")

    gen_kwargs = {
        "max_tokens": args.max_tokens,
        "temperature": args.temperature,
        "top_k": args.top_k,
        "top_p": args.top_p,
    }

    if args.chat:
        chat_mode(model, sp, **gen_kwargs)
    elif args.prompt:
        generate(model, sp, args.prompt, **gen_kwargs)
    else:
        # Default: modo chat
        chat_mode(model, sp, **gen_kwargs)


if __name__ == "__main__":
    main()
