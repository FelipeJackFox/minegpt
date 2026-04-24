"""
Agrega ~20 items NUEVOS al testset (no vistos previamente) para evitar
overfitting al iterar el prompt.

Heuristica: selecciona items balanceados por spin-off y por KEEP/DISCARD
esperado segun patterns simples. Felipe ajusta expected en la UI si hay
errores.
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

TESTSET_PATH = Path(__file__).parent / "testsets" / "spinoff_classifier.jsonl"
ARTICLES_PATH = Path(__file__).parent.parent.parent / "raw_data" / "wiki" / "articles_cleaned.jsonl"

SPINOFF_PREFIXES = ("Dungeons:", "Legends:", "Earth:", "Story Mode:", "MCD:")

# Heuristica para pre-asignar expected. Se basa en señales fuertes en titulo/infobox.
def heuristic_expected(record: dict) -> str:
    title = record["title"]
    text = record["text"][:1000]

    # Version numbers (muy claros)
    name = title.split(":", 1)[1] if ":" in title else title
    if re.match(r"^[\d.]+[\w\-]*$", name):
        return "DISCARD"
    if re.match(r"^\d+\.\d+", name):
        return "DISCARD"

    # Personajes narrativos: infobox Gender/Species/Actor + narrative descriptors
    has_character_box = bool(re.search(
        r"^(Gender|Species|Actor|Aliases|First appearance):", text, re.MULTILINE
    ))
    mentions_story_role = any(
        kw in text.lower() for kw in [
            "main character", "protagonist", "antagonist", "main villain",
            "named boss", "chapter boss", "storyline", "cutscene",
            "is a character", "is the villain", "is a hero", "is the leader",
        ]
    )

    if has_character_box and mentions_story_role:
        return "KEEP"

    # Episodes/levels
    if re.search(r"^(Episode|Season|Chapter|Written by|Directed by):", text, re.MULTILINE):
        return "KEEP"

    # Items con rarity + type (claramente gear)
    if re.search(r"^Rarity:\s*(UNIQUE|Common|Rare|Uncommon|Legendary|Deluxe)", text, re.MULTILINE):
        if re.search(r"^Type:\s*(Armor|Melee Weapon|Ranged Weapon|Horse|Hero|Skin|Mount|Banner|Tower|Structure|Artifact|Enchantment|Currency)", text, re.MULTILINE):
            return "DISCARD"

    # Mobs genericos (tienen Health points pero no story role)
    if re.search(r"^Health points:", text, re.MULTILINE) and not mentions_story_role:
        return "DISCARD"

    return "UNKNOWN"


def main(n_new: int = 20, seed: int = 123):
    # Cargar testset actual
    with open(TESTSET_PATH, "r", encoding="utf-8") as f:
        records = [json.loads(l) for l in f if l.strip()]
    existing_titles = {r["title"] for r in records}
    print(f"Testset actual: {len(records)} items")

    # Cargar articles candidatos (spin-offs no en testset)
    candidates = []
    with open(ARTICLES_PATH, "r", encoding="utf-8") as f:
        for line in f:
            a = json.loads(line)
            t = a["title"]
            if not any(t.startswith(p) for p in SPINOFF_PREFIXES):
                continue
            if t in existing_titles:
                continue
            if a.get("word_count", 0) < 50:
                continue  # skip articulos muy cortos (ruido)
            candidates.append(a)

    print(f"Candidatos disponibles (no vistos): {len(candidates)}")

    # Seleccionar aleatoriamente balanceado por prefijo
    random.seed(seed)
    by_prefix = {p: [] for p in SPINOFF_PREFIXES}
    for a in candidates:
        for p in SPINOFF_PREFIXES:
            if a["title"].startswith(p):
                by_prefix[p].append(a)
                break

    # Target: ~5 Dungeons, ~5 Legends, ~3 Earth, ~5 Story Mode, ~2 MCD
    targets = {
        "Dungeons:": 6,
        "Legends:": 5,
        "Earth:": 3,
        "Story Mode:": 5,
        "MCD:": 1,
    }

    selected = []
    for prefix, n in targets.items():
        pool = by_prefix.get(prefix, [])
        if not pool:
            continue
        picks = random.sample(pool, min(n, len(pool)))
        selected.extend(picks)

    print(f"Seleccionados: {len(selected)}")
    print()

    # Asignar expected heuristico
    new_records = []
    dist = {"KEEP": 0, "DISCARD": 0, "UNKNOWN": 0}
    for a in selected:
        expected = heuristic_expected(a)
        dist[expected] += 1
        new_records.append({
            "title": a["title"],
            "text": a["text"],
            "word_count": a["word_count"],
            "expected": expected,
        })
        print(f"  [{expected:8s}] {a['title']}")

    print()
    print(f"Distribucion nuevos: {dist}")

    # Guardar
    all_records = records + new_records
    with open(TESTSET_PATH, "w", encoding="utf-8") as f:
        for r in all_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Stats finales
    final_dist = {}
    for r in all_records:
        e = r["expected"]
        final_dist[e] = final_dist.get(e, 0) + 1
    print(f"\nTestset final: {len(all_records)} items")
    for k, v in sorted(final_dist.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
