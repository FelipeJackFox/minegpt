"""
expand_testset.py — Agrega casos edge al testset existente + corrige expecteds

Propósito: cubrir mejor el caso "unique named entity with story role"
(bosses nombrados, artifacts narrativos, antagonistas) que son KEEP aunque
tengan infobox de stats.
"""

from __future__ import annotations

import json
from pathlib import Path

TESTSET_PATH = Path(__file__).parent / "testsets" / "spinoff_classifier.jsonl"
ARTICLES_PATH = Path(__file__).parent.parent.parent / "raw_data" / "wiki" / "articles_cleaned.jsonl"

# Casos adicionales curados manualmente (edge cases)
# Formato: (title, expected)
NEW_CASES = [
    # Dungeons: bosses nombrados con stats (KEEP — narrativa)
    ("Dungeons:Arch-Illager", "KEEP"),
    ("Dungeons:Orb of Dominance", "KEEP"),
    ("Dungeons:Mooshroom Monstrosity", "KEEP"),
    ("Dungeons:Nameless One", "KEEP"),
    ("Dungeons:Tempest Golem", "KEEP"),
    ("Dungeons:Redstone Monstrosity", "KEEP"),
    # Dungeons: weapons/armor NO narrative (DISCARD)
    ("Dungeons:Battle Robe", "DISCARD"),
    ("Dungeons:Golem Kit", "DISCARD"),
    # Legends: hordes/bosses (KEEP)
    ("Legends:Horde of the Bastion", "KEEP"),
    ("Legends:Horde of the Hunt", "KEEP"),
    # Story Mode: personajes principales y antagonistas
    ("Story Mode:Reuben", "KEEP"),
    ("Story Mode:PAMA", "KEEP"),
    ("Story Mode:Ivor", "KEEP"),
    ("Story Mode:Cassie Rose", "KEEP"),
    ("Story Mode:Giant Magma Golem", "KEEP"),
]

# Correcciones de expecteds del testset actual (bugs de la heurística)
CORRECTIONS = {
    "Earth:Peanut Butter": "DISCARD",          # item de Earth, no narrativa
    "Story Mode:Soren's Books": "KEEP",        # Soren es personaje principal
    "Story Mode:Icy Spider": "KEEP",           # antagonista de episodio (ya lo tenía)
    "Story Mode:Icy Golem": "KEEP",            # antagonista de episodio (ya lo tenía)
}


def main():
    # Leer testset actual
    with open(TESTSET_PATH, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]

    existing_titles = {r["title"] for r in records}
    by_title = {r["title"]: r for r in records}

    # Aplicar correcciones
    print("=== Correcciones ===")
    for title, new_expected in CORRECTIONS.items():
        if title in by_title:
            old = by_title[title]["expected"]
            by_title[title]["expected"] = new_expected
            print(f"  {title}: {old} -> {new_expected}")
        else:
            print(f"  (no encontrado) {title}")

    # Leer articles_cleaned para recuperar texto de los nuevos casos
    needed = {title for title, _ in NEW_CASES if title not in existing_titles}
    found = {}
    if needed:
        with open(ARTICLES_PATH, "r", encoding="utf-8") as f:
            for line in f:
                a = json.loads(line)
                if a["title"] in needed:
                    found[a["title"]] = a
                    if len(found) == len(needed):
                        break

    # Agregar nuevos casos
    print("\n=== Nuevos casos agregados ===")
    for title, expected in NEW_CASES:
        if title in existing_titles:
            print(f"  (ya existe) {title}")
            continue
        if title not in found:
            print(f"  (NO encontrado en articles) {title}")
            continue
        a = found[title]
        record = {
            "title": a["title"],
            "text": a["text"],
            "word_count": a["word_count"],
            "expected": expected,
        }
        records.append(record)
        print(f"  [{expected}] {title}")

    # Guardar
    with open(TESTSET_PATH, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Stats
    dist = {}
    for r in records:
        e = r["expected"]
        dist[e] = dist.get(e, 0) + 1

    print(f"\n=== Total testset: {len(records)} items ===")
    for k, v in sorted(dist.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
