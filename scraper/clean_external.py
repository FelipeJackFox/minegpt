"""
clean_external.py — Limpieza de fuentes externas (Wikipedia + Word of Notch + YouTube).

Cada fuente tiene patterns de ruido distintos. Genera archivos paralelos *_cleaned.jsonl
sin destruir los originales.

Uso:
    python -m scraper.clean_external
    python -m scraper.clean_external --only wikipedia
    python -m scraper.clean_external --force
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "raw_data" / "external"

# ============================================================
# WIKIPEDIA cleanup
# ============================================================

# Footer sections to strip (everything from this header to end of article)
WIKIPEDIA_FOOTER_HEADERS = [
    "References", "External links", "Notes", "Bibliography", "Further reading",
    "See also", "Citations", "Sources", "Footnotes", "Awards",
]
# IPA pronunciation patterns: "[ˈmǎrːkɵs ˈpæ̌ːʂɔn]" or "(  PEER-sən, Swedish: [...])"
IPA_PATTERNS = [
    re.compile(r"\[[ˈˌːː'ˑ̀-ͯɐ-ʯʰ-˿\s\w]+\]"),  # IPA inside brackets
    re.compile(r"\(\s*[A-Z][A-Za-z\-]+,?\s*[A-Za-z\s]*:\s*\[[^\]]+\][;,]?\s*"),  # "(PEER-sən, Swedish: [...])"
]


def clean_wikipedia(text: str) -> str:
    # Strip footer sections
    for header in WIKIPEDIA_FOOTER_HEADERS:
        # Headers in plaintext extract appear on their own line, often surrounded by blank lines
        pattern = re.compile(rf"\n\n{re.escape(header)}\s*\n.*", re.DOTALL)
        text = pattern.sub("", text)

    # Strip IPA pronunciation guides
    text = re.sub(r"\(\s*[A-Z]+-?[a-zəɛɪʊɔæʌɑːˌˈ]+,\s*[A-Z][a-z]+:\s*\[[^\]]+\]\s*[;,]?\s*",
                  "", text)
    # Remove standalone IPA brackets like [ˈmǎrːkɵs ˈpæ̌ːʂɔn]
    text = re.sub(r"\[[\sɐ-˿̀-ͯʰ-˿À-ɏ\w'ːˈˌ\-]+\]", "", text)

    # Normalize whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" +", " ", text)
    text = text.strip()
    return text


# ============================================================
# WORD OF NOTCH cleanup
# ============================================================

NOTCH_NOISE_LINES = {
    "← last post", "next post →", "Archive", "Random Post", "tumblrist",
    "theme", "by", "topherchris", ".", "powered by", "Tumblr",
    "Opinions, rants, screenshots and demos from an up and coming indie game developer.",
}
NOTCH_NOISE_PATTERNS = [
    re.compile(r"^posted\s+\d+\s+(week|day|hour|minute|month|year)s?\s+ago\.?$", re.IGNORECASE),
    re.compile(r"^posted\s+\d+\s+(week|day|hour|minute|month|year)s?\s+ago\.?\s*$", re.IGNORECASE),
    re.compile(r"^\d+\s*(notes?|likes?|reblogs?)$", re.IGNORECASE),
]
# Date split across 3 lines: "May", "22", "2009"
MONTH_RE = re.compile(r"^(January|February|March|April|May|June|July|August|"
                      r"September|October|November|December|"
                      r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)$",
                      re.IGNORECASE)
DAY_RE = re.compile(r"^\d{1,2}$")
YEAR_RE = re.compile(r"^(19|20)\d{2}$")
MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _parse_date(month: str, day: str, year: str) -> str | None:
    """Convert split month/day/year into ISO format like '2009-05-22'."""
    try:
        m = MONTH_MAP.get(month.lower()[:3])
        d = int(day)
        y = int(year)
        if not m or not (1 <= d <= 31) or not (1990 <= y <= 2030):
            return None
        return f"{y:04d}-{m:02d}-{d:02d}"
    except Exception:
        return None


def _format_human_date(iso: str) -> str:
    """ISO '2009-05-22' -> 'May 22, 2009'."""
    months = ["", "January", "February", "March", "April", "May", "June",
              "July", "August", "September", "October", "November", "December"]
    try:
        y, m, d = iso.split("-")
        return f"{months[int(m)]} {int(d)}, {y}"
    except Exception:
        return iso


def clean_notch_post(title: str, text: str) -> tuple[str, str, str | None]:
    # Remove "The Word of Notch :" prefix from title
    title = re.sub(r"^The Word of Notch\s*[:|-]\s*", "", title).strip()
    if not title or title.lower().startswith("the word of notch"):
        title = ""

    lines = [ln.strip() for ln in text.splitlines()]
    cleaned: list[str] = []
    post_date: str | None = None
    i = 0
    while i < len(lines):
        ln = lines[i]
        if not ln:
            i += 1
            continue
        # 3-line date pattern (Month / Day / Year) — capture, don't drop
        if (i + 2 < len(lines)
                and MONTH_RE.match(ln)
                and DAY_RE.match(lines[i + 1].strip())
                and YEAR_RE.match(lines[i + 2].strip())):
            if post_date is None:  # keep first occurrence (the post's own date)
                d = _parse_date(ln, lines[i + 1].strip(), lines[i + 2].strip())
                if d:
                    post_date = d
            i += 3
            continue
        # Skip noise lines
        if ln in NOTCH_NOISE_LINES:
            i += 1
            continue
        if any(p.match(ln) for p in NOTCH_NOISE_PATTERNS):
            i += 1
            continue
        # Skip lines that are just punctuation
        if re.fullmatch(r"[\W_]+", ln):
            i += 1
            continue
        cleaned.append(ln)
        i += 1

    body = "\n".join(cleaned).strip()

    # If the title appears as the first body line, drop it (it's redundant after cleanup)
    if title and body.startswith(title):
        body = body[len(title):].lstrip("\n").strip()

    # Prepend a human-readable date line so the temporal context survives in the text.
    if post_date:
        body = f"Posted {_format_human_date(post_date)}.\n\n{body}"

    # Collapse multi-newlines
    body = re.sub(r"\n{3,}", "\n\n", body)
    return title, body, post_date


# ============================================================
# YOUTUBE cleanup
# ============================================================

YOUTUBE_TAG_RE = re.compile(r"\[(Music|Applause|Laughter|Cheering|Cheers|Inaudible|"
                            r"Crowd|Chuckles|Sigh|Sighs|Pause|Silence|Crowd noise|"
                            r"upbeat music|Dramatic music|Speaker \d+)\]",
                            re.IGNORECASE)


def clean_youtube(text: str) -> str:
    text = YOUTUBE_TAG_RE.sub("", text)
    text = re.sub(r"\s+", " ", text)
    text = text.strip()
    return text


# ============================================================
# Main
# ============================================================

def process_file(input_path: Path, output_path: Path,
                 cleaner_fn, min_words: int = 30) -> tuple[int, int, int]:
    """Run cleaner, write _cleaned file. Returns (kept, dropped_short, total)."""
    kept = 0
    dropped = 0
    total = 0
    with output_path.open("w", encoding="utf-8") as out:
        with input_path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                d = json.loads(line)
                total += 1
                cleaned = cleaner_fn(d)
                if not cleaned:
                    dropped += 1
                    continue
                wc = len(cleaned["text"].split())
                if wc < min_words:
                    dropped += 1
                    continue
                cleaned["word_count"] = wc
                cleaned["cleaned_at"] = datetime.utcnow().isoformat(timespec="seconds")
                out.write(json.dumps(cleaned, ensure_ascii=False) + "\n")
                kept += 1
    return kept, dropped, total


def clean_wiki_entry(d: dict) -> dict | None:
    text = clean_wikipedia(d["text"])
    if not text:
        return None
    d2 = dict(d)
    d2["text"] = text
    return d2


def clean_notch_entry(d: dict) -> dict | None:
    title, text, post_date = clean_notch_post(d.get("title", ""), d["text"])
    if not text:
        return None
    d2 = dict(d)
    d2["title"] = title or d.get("slug", "").replace("-", " ").title()
    d2["text"] = text
    if post_date:
        d2["post_date"] = post_date
    return d2


def clean_youtube_entry(d: dict) -> dict | None:
    text = clean_youtube(d["text"])
    if not text:
        return None
    d2 = dict(d)
    d2["text"] = text
    return d2


SOURCES = [
    ("wikipedia", "wikipedia_bios.jsonl",      "wikipedia_bios_cleaned.jsonl",      clean_wiki_entry,    50),
    ("notch",     "word_of_notch.jsonl",        "word_of_notch_cleaned.jsonl",       clean_notch_entry,   30),
    ("youtube",   "youtube_transcripts.jsonl",  "youtube_transcripts_cleaned.jsonl", clean_youtube_entry, 100),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=[s[0] for s in SOURCES])
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    todo = [s for s in SOURCES if not args.only or s[0] == args.only]
    for name, in_name, out_name, fn, min_w in todo:
        in_p = EXT / in_name
        out_p = EXT / out_name
        if not in_p.exists():
            print(f"  [{name}] input missing: {in_p}")
            continue
        if out_p.exists() and not args.force:
            print(f"  [{name}] output exists, use --force to overwrite: {out_p}")
            continue
        kept, dropped, total = process_file(in_p, out_p, fn, min_words=min_w)
        in_words = sum(json.loads(line)["word_count"] for line in in_p.open(encoding="utf-8") if line.strip())
        out_words = sum(json.loads(line)["word_count"] for line in out_p.open(encoding="utf-8") if line.strip())
        delta_pct = 100 * (in_words - out_words) / max(in_words, 1)
        print(f"  [{name}] {total} entries -> {kept} kept ({dropped} dropped <{min_w}w)")
        print(f"           words: {in_words:,} -> {out_words:,}  (-{delta_pct:.1f}%)")


if __name__ == "__main__":
    main()
