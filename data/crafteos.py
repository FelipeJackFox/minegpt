"""
crafteos.py — Extracción de recetas de crafting del wiki
==========================================================

Este script toma las tablas de crafting extraídas por wiki_scraper.py
y las convierte en datos estructurados para entrenamiento.

¿POR QUÉ DATOS ESTRUCTURADOS DE CRAFTEOS?
Los crafteos son uno de los casos de uso más pedidos: "¿Cómo crafteo X?"
Si el modelo aprende esto bien, ya tiene un caso de uso útil desde el día 1.

El formato final es instrucción→respuesta, listo para instruction tuning:
{
    "instruction": "How do I craft a Diamond Sword?",
    "input": "",
    "output": "Place 2 diamonds and 1 stick vertically in the crafting grid..."
}

Uso:
    python -m data.crafteos
"""

import json
import logging
import re
from pathlib import Path

RAW_DIR = Path(__file__).parent.parent / "raw_data" / "wiki"
OUTPUT_DIR = Path(__file__).parent.parent / "processed_data"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def extract_crafting_from_articles():
    """
    Busca patrones de crafting en el texto de los artículos del wiki.

    Como el scraper limpia HTML y pierde las tablas visuales de crafting,
    buscamos patrones textuales comunes en los artículos:
    - "X is crafted using..."
    - "To craft X, place..."
    - "The recipe requires..."
    """
    articles_file = RAW_DIR / "articles.jsonl"
    if not articles_file.exists():
        log.error(f"No encontrado: {articles_file}. Ejecuta wiki_scraper.py primero.")
        return []

    crafting_entries = []

    with open(articles_file, "r", encoding="utf-8") as f:
        for line in f:
            article = json.loads(line)
            title = article["title"]
            text = article["text"]

            # Buscar párrafos que hablen de crafting
            paragraphs = text.split("\n")
            for para in paragraphs:
                para_lower = para.lower()
                if any(kw in para_lower for kw in ["craft", "recipe", "ingredient", "smelting", "brewing"]):
                    if len(para) > 30:  # Párrafo sustancial
                        crafting_entries.append({
                            "instruction": f"How do I craft or obtain {title} in Minecraft?",
                            "input": "",
                            "output": para.strip(),
                            "source": "wiki_crafting",
                            "article": title,
                        })

    return crafting_entries


def run():
    """Extrae datos de crafting y los guarda."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / "crafting_qa.jsonl"

    entries = extract_crafting_from_articles()

    with open(output_file, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    log.info(f"Extraídas {len(entries)} entradas de crafting → {output_file}")


if __name__ == "__main__":
    run()
