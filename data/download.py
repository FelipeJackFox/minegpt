"""
download.py — Descarga de datasets generales desde HuggingFace
===============================================================

Este script descarga los datasets de texto general que el modelo necesita
para aprender a "hablar" antes de especializarse en Minecraft.

DATASETS Y SU PROPÓSITO:
=========================

1. WikiText-103 (~500MB)
   ¿Qué es? Artículos completos de Wikipedia en inglés, verificados
   y de alta calidad. Es uno de los benchmarks clásicos de language modeling.

   ¿Para qué sirve en MineGPT? Le enseña al modelo:
   - Prosa formal y bien estructurada
   - Conocimiento general del mundo
   - Vocabulario amplio y variado
   - Cómo escribir artículos informativos

   Analogía: Es como darle al modelo una "educación general" antes de
   especializarlo. Sin esto, el modelo solo sabría palabras de Minecraft
   pero no podría construir oraciones coherentes sobre temas complejos.

2. TinyStories (~2GB, usamos un subset)
   ¿Qué es? Historias cortas generadas por GPT-3.5/4, diseñadas específicamente
   para entrenar modelos de lenguaje pequeños. Creado por Microsoft Research.

   ¿Para qué sirve en MineGPT? Le enseña al modelo:
   - Gramática básica y estructura de oraciones
   - Narrativa simple y coherente
   - Lenguaje natural fluido
   - Relaciones causa-efecto en texto

   Analogía: Es como enseñarle a un niño a hablar con cuentos simples
   antes de darle una enciclopedia. Los modelos pequeños (~50-100M params)
   se benefician enormemente de empezar con texto simple.

   Paper original: "TinyStories: How Small Can Language Models Be and Still
   Speak Coherent English?" (Eldan & Li, 2023)

3. Alpaca (~24MB, 52,000 instrucciones)
   ¿Qué es? Un dataset de pares instrucción→respuesta creado por Stanford.
   Cada entrada tiene una instrucción (como "Explain photosynthesis") y
   una respuesta esperada.

   ¿Para qué sirve en MineGPT? Se usa en la SEGUNDA FASE de entrenamiento
   (instruction tuning, Paso 9) para que el modelo aprenda a:
   - Seguir instrucciones del usuario
   - Responder preguntas directamente
   - Formatear respuestas de manera útil

   Sin Alpaca, el modelo solo "completa texto" (predice la siguiente palabra).
   Con Alpaca, el modelo "responde preguntas" (entiende qué se le pide).

   Analogía: Pre-training = enseñarle a leer. Instruction tuning = enseñarle
   a responder cuando le preguntan algo.

Uso:
    python -m data.download
    python -m data.download --dataset wikitext    # Solo uno
    python -m data.download --dataset tinystories
    python -m data.download --dataset alpaca
"""

import json
import logging
import argparse
from pathlib import Path

from datasets import load_dataset
from tqdm import tqdm

# ============================================================
# Configuración
# ============================================================

OUTPUT_DIR = Path(__file__).parent.parent / "raw_data" / "general"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ============================================================
# Funciones de descarga
# ============================================================

def download_wikitext():
    """
    Descarga WikiText-103.

    Es un dataset de artículos de Wikipedia curados, sin tablas ni listas
    de navegación. Viene ya limpio y es uno de los estándares en NLP.

    En HuggingFace: wikitext / wikitext-103-raw-v1
    """
    log.info("Descargando WikiText-103...")
    output_file = OUTPUT_DIR / "wikitext103.jsonl"

    if output_file.exists():
        log.info(f"  Ya existe {output_file}, saltando.")
        return

    # "wikitext-103-raw-v1" es la versión sin tokenizar (texto crudo)
    dataset = load_dataset("wikitext", "wikitext-103-raw-v1", split="train")

    count = 0
    total_words = 0
    with open(output_file, "w", encoding="utf-8") as f:
        for item in tqdm(dataset, desc="WikiText-103"):
            text = item["text"].strip()
            if len(text) < 50:  # Ignorar líneas vacías o muy cortas
                continue
            f.write(json.dumps({"text": text, "source": "wikitext-103"}, ensure_ascii=False) + "\n")
            count += 1
            total_words += len(text.split())

    log.info(f"WikiText-103: {count:,} documentos, {total_words:,} palabras → {output_file}")


def download_tinystories():
    """
    Descarga TinyStories (subset).

    El dataset completo es ~2GB. Para un modelo de ~50-100M params,
    usar todo puede ser excesivo — tomamos un subset.

    En HuggingFace: roneneldan/TinyStories
    """
    log.info("Descargando TinyStories...")
    output_file = OUTPUT_DIR / "tinystories.jsonl"

    if output_file.exists():
        log.info(f"  Ya existe {output_file}, saltando.")
        return

    dataset = load_dataset("roneneldan/TinyStories", split="train")

    # Tomamos un subset: las primeras 500,000 historias (~500MB de texto)
    max_stories = 500_000

    count = 0
    total_words = 0
    with open(output_file, "w", encoding="utf-8") as f:
        for item in tqdm(dataset, desc="TinyStories", total=min(max_stories, len(dataset))):
            if count >= max_stories:
                break
            text = item["text"].strip()
            if len(text) < 50:
                continue
            f.write(json.dumps({"text": text, "source": "tinystories"}, ensure_ascii=False) + "\n")
            count += 1
            total_words += len(text.split())

    log.info(f"TinyStories: {count:,} historias, {total_words:,} palabras → {output_file}")


def download_alpaca():
    """
    Descarga Stanford Alpaca (52k instrucciones).

    Este dataset se usa en la fase de INSTRUCTION TUNING (no en pre-training).
    Cada entrada tiene:
    - instruction: qué se le pide al modelo
    - input: contexto adicional (opcional)
    - output: respuesta esperada

    En HuggingFace: tatsu-lab/alpaca
    """
    log.info("Descargando Alpaca...")
    output_file = OUTPUT_DIR / "alpaca.jsonl"

    if output_file.exists():
        log.info(f"  Ya existe {output_file}, saltando.")
        return

    dataset = load_dataset("tatsu-lab/alpaca", split="train")

    count = 0
    with open(output_file, "w", encoding="utf-8") as f:
        for item in tqdm(dataset, desc="Alpaca"):
            entry = {
                "instruction": item["instruction"],
                "input": item.get("input", ""),
                "output": item["output"],
                "source": "alpaca",
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            count += 1

    log.info(f"Alpaca: {count:,} instrucciones → {output_file}")


# ============================================================
# Orquestación
# ============================================================

DATASETS = {
    "wikitext": download_wikitext,
    "tinystories": download_tinystories,
    "alpaca": download_alpaca,
}


def run(dataset: str | None = None):
    """Descarga datasets."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if dataset:
        if dataset not in DATASETS:
            log.error(f"Dataset '{dataset}' no reconocido. Opciones: {list(DATASETS.keys())}")
            return
        DATASETS[dataset]()
    else:
        for name, func in DATASETS.items():
            func()

    log.info("Descarga completada.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Descarga de datasets generales")
    parser.add_argument("--dataset", choices=list(DATASETS.keys()), help="Descargar solo un dataset")
    args = parser.parse_args()

    run(dataset=args.dataset)
