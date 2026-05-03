"""
wikipedia_bio_scraper.py — Bios de personalidades Minecraft desde Wikipedia EN.

Output: raw_data/external/wikipedia_bios.jsonl
Cada línea: {title, text, categories, source: "wikipedia_en", url, word_count, scraped_at}

Licencia de los textos: CC BY-SA 4.0 (Wikipedia). Atribución en LEGAL.md.

Uso:
    python -m scraper.wikipedia_bio_scraper
    python -m scraper.wikipedia_bio_scraper --force        # re-scrape
    python -m scraper.wikipedia_bio_scraper --only Notch   # solo un target
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "raw_data" / "external" / "wikipedia_bios.jsonl"

API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "MineGPT-research/0.1 (educational, non-commercial; contact: github.com/FelipeJackFox/minegpt)"

# Targets — comprehensive list of Minecraft personalities + companies + game.
# Format: (Wikipedia title, our friendly title, role)
TARGETS: list[tuple[str, str, str]] = [
    # Core developers
    ("Markus Persson",        "Markus Persson (Notch)",         "Founder of Mojang, original creator of Minecraft"),
    ("Jens Bergensten",       "Jens Bergensten (Jeb)",           "Lead developer of Minecraft after Notch"),
    ("Daniel Rosenfeld",      "Daniel Rosenfeld (C418)",         "Original Minecraft composer (2009-2020)"),
    ("Lena Raine",            "Lena Raine",                       "Composer (Caves & Cliffs, Nether Update, Tricky Trials)"),
    ("Julian Gough",          "Julian Gough",                     "Author of the Minecraft End Poem"),

    # Companies
    ("Mojang Studios",        "Mojang Studios",                   "Game studio behind Minecraft"),
    ("Microsoft",             "Microsoft",                        "Owner of Mojang Studios since 2014"),
    # ("2 Player Productions",  "2 Player Productions",             "Producers of 'The Story of Mojang' documentary"),  # Removed 2026-04-26 — Felipe: not useful
    ("Bukkit (software)",     "Bukkit",                           "Modding API; controversy over Notch ownership"),

    # Game
    ("Minecraft",             "Minecraft (game)",                 "Main game article with development history"),
    ("History of Minecraft",  "History of Minecraft",             "Standalone history article (if exists)"),
    ("Development of Minecraft", "Development of Minecraft",      "Standalone dev history (if exists)"),

    # Events
    ("Minecon",               "Minecon",                          "Yearly Minecraft convention"),
    ("Minecraft Live",        "Minecraft Live",                   "Annual live-stream event"),

    # Other personalities — likely some won't have own page; will skip with warning
    ("Carl Manneh",           "Carl Manneh",                      "Co-founder of Mojang, former CEO"),
    ("Daniel Kaplan",         "Daniel Kaplan (game developer)",   "Mojang business developer"),
    ("Aron Nieminen",         "Aron Nieminen",                    "Early Mojang dev (if exists)"),

    # Cultural / spinoffs
    ("Minecraft: Story Mode", "Minecraft: Story Mode",            "Telltale spinoff (history context)"),
    ("Minecraft Dungeons",    "Minecraft Dungeons",               "Spinoff dungeon-crawler"),
    ("Minecraft Legends",     "Minecraft Legends",                "Spinoff RTS"),
    ("Minecraft Earth",       "Minecraft Earth",                  "AR spinoff (discontinued)"),

    # Documental
    ("Minecraft: The Story of Mojang", "Minecraft: The Story of Mojang", "Documentary film 2012"),

    # Movie
    ("A Minecraft Movie",     "A Minecraft Movie",                "2025 live-action film"),
]


def fetch_extract(title: str) -> dict | None:
    """Fetch plain-text extract + categories of a Wikipedia article."""
    params = {
        "action": "query",
        "format": "json",
        "titles": title,
        "prop": "extracts|categories|info",
        "explaintext": "true",
        "exsectionformat": "plain",
        "cllimit": 50,
        "inprop": "url",
        "redirects": 1,
    }
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    r = requests.get(API, params=params, headers=headers, timeout=30)
    if r.status_code != 200:
        return None
    data = r.json()
    pages = data.get("query", {}).get("pages", {})
    if not pages:
        return None
    page = next(iter(pages.values()))
    if page.get("missing") is not None or "extract" not in page:
        return None
    cats = [c["title"].replace("Category:", "") for c in (page.get("categories") or [])]
    return {
        "title": page["title"],
        "text": page["extract"],
        "categories": cats,
        "url": page.get("fullurl") or f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--only", help="Substring to filter targets")
    args = parser.parse_args()

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    # Resume support
    already: set[str] = set()
    if OUTPUT.exists() and not args.force:
        with OUTPUT.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        already.add(json.loads(line)["our_title"])
                    except Exception:
                        pass

    targets = TARGETS
    if args.only:
        q = args.only.lower()
        targets = [t for t in targets if q in t[0].lower() or q in t[1].lower()]

    # Track Wikipedia canonical titles (post-redirects) to avoid duplicates
    seen_canonical: set[str] = set()
    if OUTPUT.exists() and not args.force:
        with OUTPUT.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        seen_canonical.add(json.loads(line)["title"])
                    except Exception:
                        pass

    mode = "w" if args.force else "a"
    n_ok, n_skip, n_miss, n_dup = 0, 0, 0, 0
    with OUTPUT.open(mode, encoding="utf-8") as f:
        for wp_title, our_title, role in targets:
            if our_title in already:
                print(f"  SKIP  {our_title} (already saved)")
                n_skip += 1
                continue
            print(f"  ...   {wp_title}", end=" ")
            try:
                extract = fetch_extract(wp_title)
            except Exception as e:
                print(f"ERROR: {e}")
                n_miss += 1
                continue
            if not extract or not extract["text"].strip():
                print("MISSING")
                n_miss += 1
                continue
            if extract["title"] in seen_canonical:
                print(f"DUPE (redirect to '{extract['title']}')")
                n_dup += 1
                continue
            seen_canonical.add(extract["title"])
            wc = len(extract["text"].split())
            entry = {
                "title": extract["title"],
                "our_title": our_title,
                "role": role,
                "text": extract["text"],
                "categories": extract["categories"],
                "source": "wikipedia_en",
                "license": "CC BY-SA 4.0",
                "url": extract["url"],
                "word_count": wc,
                "scraped_at": datetime.utcnow().isoformat(timespec="seconds"),
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            f.flush()
            n_ok += 1
            print(f"OK ({wc:,}w)")
            time.sleep(1.0)  # rate limit polite to Wikipedia
    print(f"  ({n_dup} duplicates removed via redirect canonicalization)") if n_dup else None

    print()
    print(f"Done. {n_ok} new, {n_skip} skipped, {n_miss} missing/failed.")
    print(f"Output: {OUTPUT}")


if __name__ == "__main__":
    main()
