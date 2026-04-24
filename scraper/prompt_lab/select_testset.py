"""
select_testset.py — Selecciona samples balanceados para prompt engineering
============================================================================

Crea un test set de ~50 articulos de spin-offs (Dungeons, Legends, Earth,
Story Mode) con un mix balanceado de categorias para iterar el prompt de
clasificacion KEEP/DISCARD.

Asigna un "expected" tentativo basado en heuristicas. Felipe puede ajustarlos
manualmente en la UI.

Heuristicas para expected:
- DISCARD: items (weapons, armor, enchantments), version numbers, patches,
  mobs/creatures genericos del spin-off
- KEEP: personajes narrativos (Gender/Species/Actor in infobox), niveles con
  lore (Episode/Season/Chapter), descripciones generales del juego

Uso:
    python -m scraper.prompt_lab.select_testset
    python -m scraper.prompt_lab.select_testset --seed 42 --size 50
"""

from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent.parent.parent / "raw_data" / "wiki"
ARTICLES_IN = OUTPUT_DIR / "articles_cleaned.jsonl"
TESTSET_OUT = Path(__file__).parent / "testsets" / "spinoff_classifier.jsonl"

SPINOFF_PREFIXES = ("Dungeons:", "Legends:", "Earth:", "Story Mode:", "MCD:")

# Heuristicas para pre-clasificar (expected tentativo)
ITEM_KEYWORDS = (
    "Sword", "Bow", "Crossbow", "Arrow", "Axe", "Pickaxe", "Shovel",
    "Armor", "Shield", "Helmet", "Chestplate", "Leggings", "Boots",
    "Staff", "Wand", "Rod", "Spear", "Sickle", "Daggers", "Glaive",
    "Hammer", "Mace", "Scythe", "Whip",
    "Banner", "Tower", "Chest", "Pickaxe",
)

ENCHANT_MARKERS = ("Enchantment", "Applicable to:")

# Regex para detectar version numbers en titulos de spinoffs
VERSION_SUFFIX_RE = re.compile(r":[\d.]+[\w\-]*$")


def classify_expected(record: dict) -> str:
    """Heuristica para pre-asignar KEEP/DISCARD. Felipe ajusta en UI."""
    title = record["title"]
    text = record["text"][:800]

    # strip prefijo para analisis
    for prefix in SPINOFF_PREFIXES:
        if title.startswith(prefix):
            name = title[len(prefix):]
            break
    else:
        name = title

    # Version numbers / patches
    if VERSION_SUFFIX_RE.search(title):
        return "DISCARD"

    # Characters (narrativa): infobox con Gender/Species/Actor
    if re.search(r"^(Gender|Species|Actor|Aliases|First appearance):", text, re.MULTILINE):
        return "KEEP"

    # Episodes/levels (narrativa): infobox con Episode/Season/Chapter/Boss
    if re.search(r"^(Episode|Season|Chapter|Written by|Directed by|Boss):", text, re.MULTILINE):
        return "KEEP"

    # Enchantments
    if any(m in text[:300] for m in ENCHANT_MARKERS):
        return "DISCARD"

    # Items con keywords en titulo o infobox "Rarity: UNIQUE/Common/Rare"
    if any(kw in name for kw in ITEM_KEYWORDS):
        return "DISCARD"
    if re.search(r"^Rarity:\s*(UNIQUE|Common|Rare|Uncommon|Legendary|Deluxe)", text, re.MULTILINE):
        # Podria ser item o skin
        if re.search(r"^Type:\s*(Horse|Hero|Weapon|Armor|Skin|Mount)", text, re.MULTILINE):
            return "DISCARD"

    # Mobs del spinoff (tienen infobox con Health points)
    if re.search(r"^Health points:", text, re.MULTILINE):
        return "DISCARD"

    # Default: unknown — marcar para revisar
    return "UNKNOWN"


def iter_jsonl(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def select_balanced(articles: list[dict], size: int, seed: int) -> list[dict]:
    """
    Selecciona un subset balanceado por spin-off y por KEEP/DISCARD.
    Target: 15 Dungeons, 15 Legends, 10 Earth, 10 Story Mode = 50.
    """
    random.seed(seed)

    # Group by spinoff
    by_spinoff: dict[str, list[dict]] = {"Dungeons": [], "Legends": [], "Earth": [], "Story Mode": []}
    for a in articles:
        title = a["title"]
        for key in by_spinoff.keys():
            if title.startswith(key + ":") or (key == "Dungeons" and title.startswith("MCD:")):
                by_spinoff[key].append(a)
                break

    # Target distribution
    targets = {"Dungeons": 15, "Legends": 15, "Earth": 10, "Story Mode": 10}
    if size != 50:
        # Re-scale proportionally
        total = sum(targets.values())
        targets = {k: round(v * size / total) for k, v in targets.items()}

    selected: list[dict] = []
    for spinoff, n in targets.items():
        pool = by_spinoff[spinoff]
        if not pool:
            continue

        # Split by expected (pre-classified) for balance within spinoff
        keeps = [a for a in pool if classify_expected(a) == "KEEP"]
        discards = [a for a in pool if classify_expected(a) == "DISCARD"]
        unknowns = [a for a in pool if classify_expected(a) == "UNKNOWN"]

        # For Dungeons/Legends: target 1/3 KEEP, 2/3 DISCARD (mas items que narrativa)
        # For Story Mode: target 90% KEEP (casi todo es narrativa)
        # For Earth: target 20% KEEP (mayoria items/mobs)
        if spinoff == "Story Mode":
            n_keep = min(int(n * 0.9), len(keeps))
        elif spinoff == "Earth":
            n_keep = min(int(n * 0.2), len(keeps))
        else:
            n_keep = min(int(n / 3), len(keeps))

        n_discard = min(n - n_keep, len(discards))
        n_unknown = n - n_keep - n_discard

        picks = (
            random.sample(keeps, n_keep) +
            random.sample(discards, n_discard) +
            random.sample(unknowns, min(n_unknown, len(unknowns)))
        )
        selected.extend(picks)

    return selected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if TESTSET_OUT.exists() and not args.force:
        print(f"Ya existe: {TESTSET_OUT}. Usar --force para regenerar.")
        return

    # Cargar articulos
    print(f"Leyendo {ARTICLES_IN}...")
    articles = []
    for a in iter_jsonl(ARTICLES_IN):
        if any(a["title"].startswith(p) for p in SPINOFF_PREFIXES):
            articles.append(a)
    print(f"  {len(articles)} articulos de spin-offs encontrados")

    # Seleccionar
    selected = select_balanced(articles, args.size, args.seed)
    print(f"  {len(selected)} seleccionados")

    # Asignar expected y guardar
    distribution = {"KEEP": 0, "DISCARD": 0, "UNKNOWN": 0}
    with open(TESTSET_OUT, "w", encoding="utf-8") as f:
        for a in selected:
            expected = classify_expected(a)
            distribution[expected] += 1
            record = {
                "title": a["title"],
                "text": a["text"],
                "word_count": a["word_count"],
                "expected": expected,  # Felipe ajusta en UI
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"\nGuardado en {TESTSET_OUT}")
    print(f"Distribucion expected (heuristico):")
    for k, v in distribution.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
