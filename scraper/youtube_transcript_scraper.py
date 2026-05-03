"""
youtube_transcript_scraper.py — Transcripts de videos sobre Minecraft.

Descarga captions/subtitles oficiales (o auto-generated as fallback) de videos
seleccionados: documental "The Story of Mojang", GDC talks de Notch/Jeb,
retrospectivas oficiales de Mojang.

Output: raw_data/external/youtube_transcripts.jsonl
Cada línea: {video_id, title, our_title, role, text, source: "youtube_captions",
             url, language, is_generated, word_count, scraped_at}

Uso:
    python -m scraper.youtube_transcript_scraper
    python -m scraper.youtube_transcript_scraper --force
    python -m scraper.youtube_transcript_scraper --only mojang

Notas legales:
- Los videos están públicamente disponibles en YouTube subidos por sus creadores.
- Captions son metadata accesible vía YouTube. Para uso educativo no-comercial.
- Cada entry incluye URL para atribución.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "raw_data" / "external" / "youtube_transcripts.jsonl"

# Video IDs + metadata.
#
# IMPORTANT: This list starts EMPTY. Add real video IDs by:
#   1. Visiting the channel (e.g. https://www.youtube.com/@2PlayerProductions)
#   2. Finding the target video
#   3. Copying the video ID from the URL (the bit after watch?v=)
#   4. Adding an entry below
#
# Suggested videos to look up:
#   - "Minecraft: The Story of Mojang" full doc on the 2 Player Productions channel
#     (uploaded Nov 2013, free)
#   - Notch GDC 2011 postmortem talk
#   - Notch GDC Vault talks (some require search)
#   - Mojang official "10 years of Minecraft" retrospectives
#   - Mojang official annual Minecon/Minecraft Live opening keynotes
#
# Each entry needs: video_id, our_title, channel, role. The scraper will pull
# manual EN captions if available, falling back to auto-generated EN.
VIDEOS: list[dict] = [
    # Verified IDs (2026-04-26 via web search) — official uploads
    {
        "video_id": "6dfncxXtH_o",
        "our_title": "Minecraft: The Story of Mojang (full documentary)",
        "channel": "Various / mirror upload",
        "role": "Full feature-length 104min documentary by 2 Player Productions about Mojang's first year (2010-2012). Features Notch, Jeb, Daniel Kaplan, Carl Manneh, Junkboy, plus interviews with Tim Schafer, Peter Molyneux, Chris Hecker. (Original 2 Player Productions Kotaku upload `ySRgVo1X_18` is now private; this mirror has captions.)",
    },
    {
        "video_id": "cBF2ugTzXqQ",
        "our_title": "Minecraft: The Story of Mojang — Proof of Concept (Pt. 1/2)",
        "channel": "2 Player Productions",
        "role": "20-minute proof-of-concept short used to launch the Kickstarter for the feature-length documentary. Earlier interviews with Notch and Mojang from 2010-2011.",
    },
    {
        "video_id": "qe6r4jSup6c",
        "our_title": "Minecraft: The Story of Mojang — 20 Minute Short",
        "channel": "2 Player Productions",
        "role": "Original 20-minute short version of the documentary.",
    },
    {
        "video_id": "Oudi5XUDLtA",
        "our_title": "GDC 11 Multiple Award Winner — Notch Minecraft Interview",
        "channel": "GDC / 2011 coverage",
        "role": "Notch interviewed at GDC 2011 after Minecraft swept multiple Independent Games Festival awards.",
    },
]


def fetch_transcript(video_id: str) -> dict | None:
    """Try to fetch English captions (manual first, auto-gen fallback)."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api._errors import (
            TranscriptsDisabled, NoTranscriptFound, VideoUnavailable
        )
    except ImportError:
        print("  ERROR: youtube_transcript_api not installed (pip install youtube-transcript-api)")
        return None

    api = YouTubeTranscriptApi()
    try:
        transcript_list = api.list(video_id)
    except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable) as e:
        print(f"NO CAPTIONS ({type(e).__name__})")
        return None
    except Exception as e:
        print(f"ERROR ({type(e).__name__}: {e})")
        return None

    # Prefer manually-created EN captions, fallback to auto-generated EN, then any EN-translation
    transcript = None
    is_generated = False
    try:
        transcript = transcript_list.find_manually_created_transcript(["en", "en-US", "en-GB"])
    except Exception:
        try:
            transcript = transcript_list.find_generated_transcript(["en", "en-US", "en-GB"])
            is_generated = True
        except Exception:
            try:
                # Last resort: take any transcript and translate to en
                for t in transcript_list:
                    if t.is_translatable:
                        transcript = t.translate("en")
                        is_generated = True
                        break
            except Exception:
                pass
    if not transcript:
        return None

    try:
        snippets = transcript.fetch()
    except Exception as e:
        print(f"FETCH ERROR ({e})")
        return None

    # snippets is list of objects with .text, .start, .duration
    text = " ".join(s.text for s in snippets if s.text and s.text.strip())
    return {
        "text": text,
        "language": transcript.language_code,
        "is_generated": is_generated,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--only", help="Substring to filter our_title")
    args = parser.parse_args()

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    already: set[str] = set()
    if OUTPUT.exists() and not args.force:
        with OUTPUT.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        already.add(json.loads(line)["video_id"])
                    except Exception:
                        pass

    videos = VIDEOS
    if args.only:
        q = args.only.lower()
        videos = [v for v in videos if q in v["our_title"].lower() or q in v["channel"].lower()]

    mode = "w" if args.force else "a"
    n_ok, n_skip, n_miss = 0, 0, 0
    with OUTPUT.open(mode, encoding="utf-8") as f:
        for v in videos:
            vid = v["video_id"]
            if vid in already:
                print(f"  SKIP  {v['our_title']}")
                n_skip += 1
                continue
            print(f"  ...   {v['our_title']}", end=" ")
            t = fetch_transcript(vid)
            if not t:
                n_miss += 1
                continue
            wc = len(t["text"].split())
            entry = {
                "video_id": vid,
                "title": v["our_title"],
                "our_title": v["our_title"],
                "channel": v["channel"],
                "role": v["role"],
                "text": t["text"],
                "categories": [],
                "source": "youtube_captions",
                "license": "captions metadata; uploader retains video copyright; educational fair-use",
                "url": f"https://www.youtube.com/watch?v={vid}",
                "language": t["language"],
                "is_generated": t["is_generated"],
                "word_count": wc,
                "scraped_at": datetime.utcnow().isoformat(timespec="seconds"),
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            f.flush()
            tag = "auto-gen" if t["is_generated"] else "manual"
            print(f"OK ({wc:,}w, {tag})")
            n_ok += 1
            time.sleep(1.5)

    print()
    print(f"Done. {n_ok} new, {n_skip} skipped, {n_miss} missing/failed.")
    print(f"Output: {OUTPUT}")


if __name__ == "__main__":
    main()
