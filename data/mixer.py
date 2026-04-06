"""
mixer.py — Mezcla de datasets para entrenamiento
===================================================

Este script combina todos los datasets (generales + Minecraft) en un
solo corpus de entrenamiento, con ratios configurables.

¿POR QUÉ MEZCLAR?
Un modelo entrenado SOLO en Minecraft wiki sabe mucho de Minecraft pero
no puede hablar coherentemente. Uno entrenado SOLO en texto general habla
bien pero no sabe nada de Minecraft. La mezcla le da ambas capacidades.

¿QUÉ SON LOS RATIOS?
Los ratios controlan cuánto de cada fuente ve el modelo durante el entrenamiento:
- 70% texto general → el modelo aprende gramática, estructura, vocabulario
- 20% Minecraft wiki → el modelo aprende conocimiento de Minecraft
- 10% Minecraft (oversampled) → repite datos de Minecraft para reforzar el aprendizaje

¿QUÉ ES OVERSAMPLING?
Repetir datos de una fuente minoritaria para que el modelo los vea más veces.
Sin oversampling, con una mezcla 90/10, el modelo vería texto general 9 veces
por cada vez que ve Minecraft → aprendería más general que Minecraft.

El output es un archivo JSONL mezclado y shuffleado, listo para tokenizar.

Uso:
    python -m data.mixer
    python -m data.mixer --general-ratio 0.60 --minecraft-ratio 0.30 --oversample 0.10
"""

import json
import logging
import random
import argparse
from pathlib import Path

PROCESSED_DIR = Path(__file__).parent.parent / "processed_data"
RAW_DIR = Path(__file__).parent.parent / "raw_data"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def load_jsonl(path: Path) -> list[dict]:
    """Carga JSONL, retorna lista vacía si no existe."""
    if not path.exists():
        log.warning(f"No encontrado: {path}")
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def normalize_to_text(entry: dict) -> str:
    """
    Extrae texto plano de una entrada, sin importar su formato.

    Los datasets vienen en diferentes formatos:
    - Wiki: {"title": ..., "text": ...}
    - Reddit: {"title": ..., "text": ...}
    - WikiText: {"text": ...}
    - TinyStories: {"text": ...}
    - Alpaca: {"instruction": ..., "output": ...}  ← se guarda aparte

    Esta función normaliza todo a texto plano para pre-training.
    """
    if "instruction" in entry:
        # Formato Alpaca → se usa en instruction tuning, no aquí
        return ""

    parts = []
    if entry.get("title"):
        parts.append(entry["title"])
    if entry.get("text"):
        parts.append(entry["text"])

    return "\n".join(parts).strip()


def run(general_ratio: float = 0.70, minecraft_ratio: float = 0.20, oversample_ratio: float = 0.10):
    """
    Mezcla todos los datasets con los ratios especificados.

    Args:
        general_ratio: Proporción de texto general (WikiText + TinyStories)
        minecraft_ratio: Proporción de Minecraft wiki + Reddit
        oversample_ratio: Proporción extra de Minecraft (repetido)
    """
    assert abs(general_ratio + minecraft_ratio + oversample_ratio - 1.0) < 0.01, \
        f"Los ratios deben sumar 1.0, suman {general_ratio + minecraft_ratio + oversample_ratio}"

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    # --- Cargar datasets ---
    log.info("Cargando datasets...")

    # General
    wikitext = load_jsonl(RAW_DIR / "general" / "wikitext103.jsonl")
    tinystories = load_jsonl(RAW_DIR / "general" / "tinystories.jsonl")
    general = wikitext + tinystories

    # Minecraft
    wiki_mc = load_jsonl(PROCESSED_DIR / "wiki_clean.jsonl")
    reddit_mc = load_jsonl(PROCESSED_DIR / "reddit_clean.jsonl")
    minecraft = wiki_mc + reddit_mc

    log.info(f"General: {len(general):,} textos ({len(wikitext):,} WikiText + {len(tinystories):,} TinyStories)")
    log.info(f"Minecraft: {len(minecraft):,} textos ({len(wiki_mc):,} wiki + {len(reddit_mc):,} Reddit)")

    if not general or not minecraft:
        log.error("Faltan datasets. Ejecuta download.py y clean.py primero.")
        return

    # --- Convertir a texto plano ---
    general_texts = [normalize_to_text(e) for e in general if normalize_to_text(e)]
    minecraft_texts = [normalize_to_text(e) for e in minecraft if normalize_to_text(e)]

    log.info(f"Textos válidos: {len(general_texts):,} general, {len(minecraft_texts):,} Minecraft")

    # --- Calcular cuántos textos de cada fuente ---
    # El total lo determina la fuente más grande escalada por su ratio
    total_target = max(
        int(len(general_texts) / general_ratio),
        int(len(minecraft_texts) / minecraft_ratio),
    )

    n_general = int(total_target * general_ratio)
    n_minecraft = int(total_target * minecraft_ratio)
    n_oversample = int(total_target * oversample_ratio)

    log.info(f"Target de mezcla:")
    log.info(f"  General: {n_general:,} textos ({general_ratio*100:.0f}%)")
    log.info(f"  Minecraft: {n_minecraft:,} textos ({minecraft_ratio*100:.0f}%)")
    log.info(f"  Minecraft oversample: {n_oversample:,} textos ({oversample_ratio*100:.0f}%)")

    # --- Samplear con los ratios ---
    # Si hay más textos de los necesarios, samplear aleatoriamente
    # Si hay menos, repetir (oversamplear)
    def sample_or_repeat(texts: list[str], n: int) -> list[str]:
        if len(texts) >= n:
            return random.sample(texts, n)
        else:
            # Repetir hasta llenar
            repeated = texts * (n // len(texts) + 1)
            return random.sample(repeated, n)

    random.seed(42)  # Reproducibilidad

    sampled_general = sample_or_repeat(general_texts, n_general)
    sampled_minecraft = sample_or_repeat(minecraft_texts, n_minecraft)
    sampled_oversample = sample_or_repeat(minecraft_texts, n_oversample)

    # --- Combinar y shufflear ---
    mixed = sampled_general + sampled_minecraft + sampled_oversample
    random.shuffle(mixed)

    # --- Guardar ---
    output_file = PROCESSED_DIR / "train_corpus.jsonl"
    with open(output_file, "w", encoding="utf-8") as f:
        for text in mixed:
            f.write(json.dumps({"text": text}, ensure_ascii=False) + "\n")

    # --- Stats ---
    total_words = sum(len(t.split()) for t in mixed)
    log.info("=" * 60)
    log.info("MIXING COMPLETADO")
    log.info(f"  Total textos: {len(mixed):,}")
    log.info(f"  Total palabras: {total_words:,}")
    log.info(f"  Ratios: {general_ratio*100:.0f}% general / {minecraft_ratio*100:.0f}% MC / {oversample_ratio*100:.0f}% MC oversample")
    log.info(f"  Output: {output_file}")
    log.info(f"  Tamaño: {output_file.stat().st_size / 1024 / 1024:.1f} MB")
    log.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mixer de datasets para MineGPT")
    parser.add_argument("--general-ratio", type=float, default=0.70)
    parser.add_argument("--minecraft-ratio", type=float, default=0.20)
    parser.add_argument("--oversample", type=float, default=0.10)
    args = parser.parse_args()

    run(
        general_ratio=args.general_ratio,
        minecraft_ratio=args.minecraft_ratio,
        oversample_ratio=args.oversample,
    )
