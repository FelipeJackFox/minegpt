"""
_hardening_audit.py - Produce before/after samples from hardening_v2.

Picks N articles spanning each detected family + each route, shows the head
and tail of cleaned vs hardened text. Output is markdown for easy review.

Usage:
  python -m scraper._hardening_audit
  python -m scraper._hardening_audit --n-per-family 3 --output audit.md
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
CLEANED = ROOT / "raw_data" / "wiki" / "articles_cleaned.jsonl"
HARDENED = ROOT / "raw_data" / "wiki" / "articles_hardened.jsonl"
DEFAULT_OUT = ROOT / ".tmp_audit" / "hardening_before_after.md"


def load_index(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            out[rec.get("title", "")] = rec
    return out


def main(n_per_family: int, output_path: Path) -> None:
    cleaned = load_index(CLEANED)
    hardened_index: dict[str, list[dict]] = defaultdict(list)
    with open(HARDENED, encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            family = rec.get("hardening_meta", {}).get("family") or "none"
            hardened_index[family].append(rec)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# Hardening v2 - Before/After audit\n\n")
        for family in sorted(hardened_index.keys()):
            recs = hardened_index[family][:n_per_family]
            if not recs:
                continue
            f.write(f"## Family: `{family}` ({len(hardened_index[family])} total)\n\n")
            for rec in recs:
                title = rec.get("title", "")
                meta = rec.get("hardening_meta", {})
                wc_before = meta.get("original_word_count") or 0
                wc_after = rec.get("word_count") or 0
                section_drops = meta.get("section_drops") or []
                warnings = meta.get("warnings") or []
                cleaned_rec = cleaned.get(title)
                if not cleaned_rec:
                    continue

                f.write(f"### `{title}`\n\n")
                f.write(
                    f"- **WC**: {wc_before:,} -> {wc_after:,} "
                    f"({(wc_before - wc_after) / max(wc_before, 1) * 100:.1f}% loss)\n"
                )
                f.write(f"- **Route**: {rec.get('route')}\n")
                if section_drops:
                    f.write(f"- **Section drops**: {', '.join(section_drops)}\n")
                if warnings:
                    f.write(f"- **Warnings**: {', '.join(warnings)}\n")
                f.write("\n")

                f.write("**Before (cleaned, head 800 chars):**\n\n")
                f.write("```\n")
                f.write(cleaned_rec.get("text", "")[:800])
                f.write("\n```\n\n")

                f.write("**After (hardened, head 800 chars):**\n\n")
                f.write("```\n")
                f.write(rec.get("text", "")[:800])
                f.write("\n```\n\n")

                f.write("---\n\n")

    print(f"Wrote audit to {output_path}")
    print(f"Families covered: {sorted(hardened_index.keys())}")
    for family, recs in sorted(hardened_index.items()):
        print(f"  {family}: {len(recs)} total, sampled {min(n_per_family, len(recs))}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-per-family", type=int, default=2)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    main(args.n_per_family, args.output)
