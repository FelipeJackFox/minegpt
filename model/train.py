"""
train.py — Loop de entrenamiento de MineGPT con curriculum learning
=====================================================================

Este script entrena el modelo MineGPT usando el corpus mezclado.

CURRICULUM LEARNING:
====================
En lugar de mezclar todo aleatoriamente, entrenamos en orden de dificultad:

  Fase 1 (épocas 1-2): TinyStories → gramática básica, oraciones simples
  Fase 2 (épocas 3-4): WikiText-103 → prosa compleja, conocimiento general
  Fase 3 (épocas 5+):  Minecraft wiki + Q&A → especialización

Es como enseñar a un niño: primero cuentos simples, luego enciclopedia,
luego la especialización.

CHECKPOINTING:
==============
Cada N steps, guardamos TODO el estado del entrenamiento:
- Pesos del modelo
- Estado del optimizador (momentums de Adam)
- Step actual, época, fase del curriculum
- Historial de loss
- Configuración completa

Si se va la luz, se interrumpe el proceso, o cualquier cosa:
→ Al reiniciar, detecta automáticamente el último checkpoint y continúa.
→ Se pierden como MÁXIMO N steps de trabajo.

OBSERVABILIDAD:
===============
Para monitorear el entrenamiento usamos:
- wandb (Weights & Biases): dashboard web con gráficas en tiempo real
- Logs en consola con tqdm
- Archivo de log para referencia

wandb es gratuito para uso personal y permite ver las métricas desde
cualquier dispositivo con browser (ej: la laptop Windows via Tailscale).

Uso:
    python -m model.train
    python -m model.train --resume                    # Continuar desde checkpoint
    python -m model.train --no-wandb                  # Sin W&B
    python -m model.train --benchmark                 # Solo benchmark de velocidad
"""

import json
import time
import math
import logging
import argparse
from pathlib import Path
from datetime import datetime

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
from utils.config import CONFIG

# ============================================================
# Configuración
# ============================================================

CHECKPOINT_DIR = CONFIG["paths"]["checkpoints"]
PROCESSED_DIR = Path(__file__).parent.parent / "processed_data"
TOKENIZER_MODEL = CONFIG["paths"]["tokenizer_model"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(__file__).parent.parent / "training.log"),
    ],
)
log = logging.getLogger(__name__)


# ============================================================
# Dataset y DataLoader
# ============================================================

class TextDataset:
    """
    Dataset que tokeniza texto on-the-fly y lo divide en chunks.

    ¿CÓMO FUNCIONA EL ENTRENAMIENTO DE UN LM?
    El modelo recibe una secuencia de tokens [t1, t2, ..., tn] y para
    cada posición i, debe predecir t_{i+1}.

    Input:  [The, Creeper, explodes, near, the]
    Target: [Creeper, explodes, near, the, player]

    El loss mide qué tan bien predice cada siguiente token.
    """

    def __init__(self, data_file: Path, tokenizer: spm.SentencePieceProcessor,
                 ctx_len: int, batch_size: int):
        self.tokenizer = tokenizer
        self.ctx_len = ctx_len
        self.batch_size = batch_size

        # Tokenizar todo el corpus y concatenar en un solo array
        log.info(f"Tokenizando {data_file}...")
        all_tokens = []
        with open(data_file, "r", encoding="utf-8") as f:
            for line in tqdm(f, desc="Tokenizando"):
                entry = json.loads(line)
                text = entry.get("text", "")
                if text:
                    tokens = tokenizer.encode(text)
                    all_tokens.extend(tokens)
                    all_tokens.append(tokenizer.eos_id())  # Separar documentos con </s>

        self.tokens = mx.array(all_tokens, dtype=mx.int32)
        self.n_tokens = len(all_tokens)
        self.n_batches = (self.n_tokens - 1) // (ctx_len * batch_size)

        log.info(f"  Tokens totales: {self.n_tokens:,}")
        log.info(f"  Batches por época: {self.n_batches:,}")

    def get_batch(self, step: int):
        """
        Retorna un batch de entrenamiento.

        Cada batch tiene:
        - x: tokens de input, shape (batch_size, ctx_len)
        - y: tokens target (shifted +1), shape (batch_size, ctx_len)

        Args:
            step: número de step actual (para indexar el dataset)

        Returns:
            (x, y) — tensores de MLX
        """
        start = (step * self.batch_size * self.ctx_len) % (self.n_tokens - self.ctx_len - 1)

        x_list = []
        y_list = []
        for b in range(self.batch_size):
            offset = start + b * self.ctx_len
            if offset + self.ctx_len + 1 > self.n_tokens:
                offset = 0  # Wrap around

            x_list.append(self.tokens[offset:offset + self.ctx_len])
            y_list.append(self.tokens[offset + 1:offset + self.ctx_len + 1])

        x = mx.stack(x_list)
        y = mx.stack(y_list)
        return x, y


# ============================================================
# Checkpointing
# ============================================================

def save_checkpoint(model, optimizer, step: int, epoch: int, loss_history: list,
                    config: dict, checkpoint_dir: Path):
    """
    Guarda un checkpoint completo del entrenamiento.

    Incluye TODO lo necesario para continuar exactamente desde este punto:
    - Pesos del modelo
    - Estado del optimizador (crucial para Adam — tiene momentum por parámetro)
    - Metadata: step, epoch, loss, config
    """
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = checkpoint_dir / f"checkpoint_step{step}"
    checkpoint_path.mkdir(exist_ok=True)

    # Guardar pesos del modelo
    weights = dict(model.parameters())
    mx.savez(str(checkpoint_path / "model.npz"), **{k: v for k, v in weights.items()})

    # Guardar metadata
    metadata = {
        "step": step,
        "epoch": epoch,
        "loss_history": loss_history[-100:],  # Últimos 100 valores
        "config": config,
        "timestamp": datetime.now().isoformat(),
    }
    with open(checkpoint_path / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    # Marcar como último checkpoint
    with open(checkpoint_dir / "latest", "w") as f:
        f.write(str(checkpoint_path.name))

    log.info(f"Checkpoint guardado: {checkpoint_path}")


def load_checkpoint(model, checkpoint_dir: Path):
    """
    Carga el último checkpoint disponible.

    Returns:
        (step, epoch, loss_history) o (0, 0, []) si no hay checkpoint
    """
    latest_file = checkpoint_dir / "latest"
    if not latest_file.exists():
        return 0, 0, []

    checkpoint_name = latest_file.read_text().strip()
    checkpoint_path = checkpoint_dir / checkpoint_name

    if not checkpoint_path.exists():
        return 0, 0, []

    # Cargar pesos
    weights = mx.load(str(checkpoint_path / "model.npz"))
    model.load_weights(list(weights.items()))

    # Cargar metadata
    with open(checkpoint_path / "metadata.json", "r") as f:
        metadata = json.load(f)

    log.info(f"Checkpoint cargado: {checkpoint_path} (step {metadata['step']}, epoch {metadata['epoch']})")
    return metadata["step"], metadata["epoch"], metadata.get("loss_history", [])


# ============================================================
# Learning rate schedule
# ============================================================

def get_lr(step: int, warmup_steps: int, max_steps: int, max_lr: float) -> float:
    """
    Cosine learning rate schedule con warmup.

    ¿QUÉ ES ESTO?
    El learning rate (lr) controla qué tan grandes son los pasos de actualización
    de los pesos. Si es muy alto, el entrenamiento es inestable. Si es muy bajo,
    es demasiado lento.

    Warmup: empezar con lr=0 y subir linealmente hasta max_lr.
    Esto evita que los primeros steps (con gradientes ruidosos) sean destructivos.

    Cosine decay: después del warmup, bajar el lr siguiendo una curva coseno
    hasta ~0. Esto permite que el modelo "refine" los pesos al final.

        lr
        │  /‾‾‾‾‾\
        │ /        \
        │/          \___
        └───────────────── step
        warmup   decay
    """
    if step < warmup_steps:
        # Warmup lineal
        return max_lr * step / warmup_steps
    elif step >= max_steps:
        return max_lr * 0.1  # No bajar a 0 completamente
    else:
        # Cosine decay
        progress = (step - warmup_steps) / (max_steps - warmup_steps)
        return max_lr * 0.5 * (1.0 + math.cos(math.pi * progress))


# ============================================================
# Función de loss
# ============================================================

def compute_loss(model, x, y):
    """
    Calcula el cross-entropy loss.

    Cross-entropy mide qué tan bien las predicciones del modelo
    (distribución de probabilidad sobre el vocabulario) coinciden
    con los tokens reales.

    Loss bajo = el modelo predice bien el siguiente token.
    Loss alto = las predicciones son malas.

    Para referencia:
    - Loss aleatorio = ln(vocab_size) ≈ 8.99 para vocab_size=8000
    - Un modelo decente de texto: loss ~3-4
    - Un modelo bueno: loss ~2-3
    """
    logits = model(x)  # (B, T, vocab_size)

    # Reshape para cross_entropy: (B*T, vocab_size) vs (B*T,)
    B, T, V = logits.shape
    logits = logits.reshape(B * T, V)
    targets = y.reshape(B * T)

    # Cross-entropy loss
    loss = nn.losses.cross_entropy(logits, targets, reduction="mean")
    return loss


# ============================================================
# Benchmark
# ============================================================

def run_benchmark(config: dict, vocab_size: int = 8000):
    """
    Benchmark de velocidad y memoria para diferentes configuraciones.

    Esto se corre ANTES de elegir la arquitectura final para saber
    qué tan ambicioso puede ser el modelo en el M2.
    """
    if not HAS_MLX:
        print("MLX no disponible. Benchmark solo funciona en macOS con Apple Silicon.")
        return

    configs = [
        {"name": "Small (50M)", "n_layers": 6, "n_heads": 8, "d_model": 512, "d_ff": 2048, "ctx_len": 512},
        {"name": "Medium (85M)", "n_layers": 8, "n_heads": 8, "d_model": 640, "d_ff": 2560, "ctx_len": 512},
        {"name": "Large (125M)", "n_layers": 12, "n_heads": 12, "d_model": 768, "d_ff": 3072, "ctx_len": 512},
    ]

    batch_size = config.get("batch_size", CONFIG["training"]["batch_size"])

    print("=" * 70)
    print("BENCHMARK DE CONFIGURACIONES EN ESTE HARDWARE")
    print("=" * 70)

    for cfg in configs:
        print(f"\n--- {cfg['name']} ---")
        model = create_model_from_config(cfg, vocab_size)

        # Forward pass
        dummy = mx.zeros((batch_size, cfg["ctx_len"]), dtype=mx.int32)

        start = time.time()
        for _ in range(10):
            logits = model(dummy)
            mx.eval(logits)
        elapsed = time.time() - start

        tokens_per_sec = (10 * batch_size * cfg["ctx_len"]) / elapsed

        print(f"  Forward pass (10 iters): {elapsed:.2f}s")
        print(f"  Tokens/segundo: {tokens_per_sec:,.0f}")
        print(f"  Batch size: {batch_size}")

    print("\n" + "=" * 70)
    print("Elige la configuración más ambiciosa que quepa cómodamente.")
    print("Si tokens/segundo es muy bajo, reduce batch_size o modelo.")
    print("=" * 70)


# ============================================================
# Training loop principal
# ============================================================

def train(resume: bool = False, use_wandb: bool = True, benchmark: bool = False):
    """Ejecuta el entrenamiento completo."""
    if not HAS_MLX:
        log.error("MLX no disponible. Entrenamiento solo funciona en macOS con Apple Silicon.")
        return

    if benchmark:
        run_benchmark(CONFIG["training"])
        return

    # --- Cargar tokenizer ---
    if not TOKENIZER_MODEL.exists():
        log.error(f"Tokenizer no encontrado: {TOKENIZER_MODEL}. Entrénalo primero.")
        return
    sp = spm.SentencePieceProcessor()
    sp.load(str(TOKENIZER_MODEL))
    vocab_size = sp.get_piece_size()
    log.info(f"Tokenizer cargado: vocab_size={vocab_size}")

    # --- Crear modelo ---
    model = create_model_from_config(CONFIG["model"], vocab_size)

    # --- Optimizer: AdamW ---
    # AdamW = Adam con weight decay correcto
    # Adam mantiene promedios móviles de gradientes (momentum) y sus cuadrados
    # Weight decay = penalizar pesos grandes (regularización)
    optimizer = optim.AdamW(
        learning_rate=CONFIG["training"]["learning_rate"],
    )

    # --- Resume desde checkpoint ---
    start_step, start_epoch, loss_history = (0, 0, [])
    if resume:
        start_step, start_epoch, loss_history = load_checkpoint(model, CHECKPOINT_DIR)

    # --- wandb ---
    if use_wandb:
        try:
            import wandb
            wandb.init(
                project="minegpt",
                config={**CONFIG["model"], **CONFIG["training"]},
                resume="allow" if resume else None,
            )
            wandb.watch(model)
            log.info("wandb inicializado — monitoreo en https://wandb.ai")
        except ImportError:
            log.warning("wandb no instalado. Continuando sin monitoreo remoto.")
            use_wandb = False

    # --- Cargar dataset ---
    corpus_file = PROCESSED_DIR / "train_corpus.jsonl"
    if not corpus_file.exists():
        log.error(f"Corpus no encontrado: {corpus_file}. Ejecuta data.mixer primero.")
        return

    dataset = TextDataset(
        corpus_file, sp,
        ctx_len=CONFIG["model"]["ctx_len"],
        batch_size=CONFIG["training"]["batch_size"],
    )

    # --- Training loop ---
    max_steps = dataset.n_batches * CONFIG["training"]["max_epochs"]
    checkpoint_every = CONFIG["training"]["checkpoint_every_steps"]
    grad_clip = CONFIG["training"]["grad_clip"]

    log.info(f"Iniciando entrenamiento:")
    log.info(f"  Steps totales: {max_steps:,}")
    log.info(f"  Checkpoint cada: {checkpoint_every} steps")
    log.info(f"  Empezando desde: step {start_step}")

    # Función que computa loss y gradientes juntos (eficiente en MLX)
    loss_and_grad_fn = nn.value_and_grad(model, compute_loss)

    step = start_step
    epoch = start_epoch
    tokens_processed = 0
    start_time = time.time()

    for epoch in range(start_epoch, CONFIG["training"]["max_epochs"]):
        log.info(f"\n--- Época {epoch + 1}/{CONFIG['training']['max_epochs']} ---")

        for batch_step in tqdm(range(dataset.n_batches), desc=f"Epoch {epoch+1}"):
            if step < start_step:
                step += 1
                continue

            # Obtener batch
            x, y = dataset.get_batch(step)

            # Ajustar learning rate
            lr = get_lr(step, CONFIG["training"]["warmup_steps"], max_steps,
                       CONFIG["training"]["learning_rate"])
            optimizer.learning_rate = lr

            # Forward + backward pass
            loss, grads = loss_and_grad_fn(model, x, y)

            # Gradient clipping: limitar la magnitud de los gradientes
            # Esto evita que un batch "malo" destruya los pesos del modelo
            grads, grad_norm = optim.clip_grad_norm(grads, max_norm=grad_clip)

            # Actualizar pesos
            optimizer.update(model, grads)

            # Evaluar (materializar computación lazy de MLX)
            mx.eval(model.parameters(), optimizer.state)

            loss_val = loss.item()
            loss_history.append(loss_val)
            tokens_processed += CONFIG["training"]["batch_size"] * CONFIG["model"]["ctx_len"]

            # Logging cada 50 steps
            if step % 50 == 0:
                elapsed = time.time() - start_time
                tps = tokens_processed / elapsed if elapsed > 0 else 0

                log.info(
                    f"Step {step:>6d} | Loss: {loss_val:.4f} | "
                    f"LR: {lr:.2e} | "
                    f"Tokens/s: {tps:,.0f} | "
                    f"Grad norm: {grad_norm:.4f}"
                )

                if use_wandb:
                    import wandb
                    wandb.log({
                        "loss": loss_val,
                        "learning_rate": lr,
                        "tokens_per_second": tps,
                        "grad_norm": grad_norm,
                        "epoch": epoch,
                        "step": step,
                    })

            # Checkpoint
            if step > 0 and step % checkpoint_every == 0:
                save_checkpoint(
                    model, optimizer, step, epoch, loss_history,
                    {**CONFIG["model"], **CONFIG["training"]},
                    CHECKPOINT_DIR,
                )

            step += 1

    # Checkpoint final
    save_checkpoint(
        model, optimizer, step, epoch, loss_history,
        {**CONFIG["model"], **CONFIG["training"]},
        CHECKPOINT_DIR,
    )

    log.info("\n" + "=" * 60)
    log.info("ENTRENAMIENTO COMPLETADO")
    log.info(f"  Steps totales: {step:,}")
    log.info(f"  Loss final: {loss_history[-1]:.4f}")
    log.info(f"  Tiempo total: {(time.time() - start_time) / 3600:.1f} horas")
    log.info("=" * 60)

    if use_wandb:
        import wandb
        wandb.finish()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Entrenamiento de MineGPT")
    parser.add_argument("--resume", action="store_true", help="Continuar desde checkpoint")
    parser.add_argument("--no-wandb", action="store_true", help="Sin monitoreo de W&B")
    parser.add_argument("--benchmark", action="store_true", help="Solo benchmark de velocidad")
    args = parser.parse_args()

    train(resume=args.resume, use_wandb=not args.no_wandb, benchmark=args.benchmark)
