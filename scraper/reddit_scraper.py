"""
reddit_scraper.py — Descarga de r/Minecraft via Arctic Shift
=============================================================

Descarga posts y comentarios de r/Minecraft usando la API de Arctic Shift.
Filosofía: obtener TODO, limpiar después.

FEATURES:
- Checkpointing granular: escribe incrementalmente, resume desde último timestamp
- Filtra bots conocidos
- Guarda TODO (incluidos posts sin texto) — el filtrado se hace en limpieza

Uso:
    python -m scraper.reddit_scraper
    python -m scraper.reddit_scraper --resume
    python -m scraper.reddit_scraper --after 2020-01-01 --before 2026-04-01
"""

import json
import time
import argparse
import logging
from pathlib import Path

import requests

# ============================================================
# Configuración
# ============================================================

API_BASE = "https://arctic-shift.photon-reddit.com/api"
SUBREDDIT = "Minecraft"
RATE_LIMIT = 0.5

OUTPUT_DIR = Path(__file__).parent.parent / "raw_data" / "reddit"

# Bots conocidos a filtrar
BOTS = {
    "[deleted]", "AutoModerator", "RemindMeBot",
    "WikiTextBot", "SaveVideo", "Sneakpeekbot",
    "RepostSleuthBot", "GifReversingBot", "haikusbot",
    "sub_doesnt_exist_bot", "LinkifyBot", "HelperBot_",
    "TotesMessenger", "BotDefense", "B0tRank",
    "DownloadVideo", "savevideobot", "VideoTrim",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ============================================================
# Checkpointing
# ============================================================

def load_progress(progress_file: Path) -> str | None:
    """Lee el último timestamp procesado."""
    if progress_file.exists():
        return progress_file.read_text(encoding="utf-8").strip()
    return None


def save_progress(progress_file: Path, timestamp: str):
    """Guarda el último timestamp procesado."""
    progress_file.write_text(str(timestamp), encoding="utf-8")


# ============================================================
# Descarga de posts
# ============================================================

def fetch_posts(after: str, before: str, resume: bool = False):
    """
    Descarga TODOS los posts de r/Minecraft incrementalmente.
    Escribe directamente al archivo JSONL sin acumular en memoria.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    posts_file = OUTPUT_DIR / "posts.jsonl"
    progress_file = OUTPUT_DIR / ".progress_posts"

    # Resume: leer último timestamp
    current_after = after
    mode = "w"
    if resume:
        saved = load_progress(progress_file)
        if saved:
            current_after = saved
            mode = "a"
            log.info(f"Resumiendo posts desde {current_after}")

    page = 0
    total = 0
    total_saved = 0

    with open(posts_file, mode, encoding="utf-8") as f:
        while True:
            time.sleep(RATE_LIMIT)

            params = {
                "subreddit": SUBREDDIT,
                "after": current_after,
                "before": before,
                "sort": "asc",
                "limit": 100,
            }

            try:
                resp = requests.get(f"{API_BASE}/posts/search", params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()
            except (requests.RequestException, json.JSONDecodeError) as e:
                log.warning(f"Error (page {page}): {e}. Reintentando en 5s...")
                time.sleep(5)
                continue

            batch = data.get("data", [])
            if not batch:
                break

            for post in batch:
                author = post.get("author", "")
                if author in BOTS:
                    continue

                entry = {
                    "title": post.get("title", ""),
                    "text": post.get("selftext", "") or "",
                    "score": post.get("score", 0),
                    "created_utc": post.get("created_utc"),
                    "num_comments": post.get("num_comments", 0),
                    "flair": post.get("link_flair_text", ""),
                    "author": author,
                    "id": post.get("id"),
                    "url": post.get("url", ""),
                    "is_self": post.get("is_self", False),
                }
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                total_saved += 1

            total += len(batch)

            # Checkpoint: guardar último timestamp
            last_utc = batch[-1].get("created_utc")
            if last_utc:
                current_after = last_utc
                save_progress(progress_file, str(last_utc))
            else:
                break

            page += 1
            if page % 50 == 0:
                log.info(f"  Posts: página {page} | {total_saved:,} guardados de {total:,} vistos")

    log.info(f"Posts completados: {total_saved:,} guardados de {total:,} vistos")
    return total_saved


# ============================================================
# Descarga de comentarios
# ============================================================

def fetch_comments(after: str, before: str, resume: bool = False):
    """
    Descarga comentarios de r/Minecraft incrementalmente.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    comments_file = OUTPUT_DIR / "comments.jsonl"
    progress_file = OUTPUT_DIR / ".progress_comments"

    current_after = after
    mode = "w"
    if resume:
        saved = load_progress(progress_file)
        if saved:
            current_after = saved
            mode = "a"
            log.info(f"Resumiendo comentarios desde {current_after}")

    page = 0
    total = 0
    total_saved = 0

    with open(comments_file, mode, encoding="utf-8") as f:
        while True:
            time.sleep(RATE_LIMIT)

            params = {
                "subreddit": SUBREDDIT,
                "after": current_after,
                "before": before,
                "sort": "asc",
                "limit": 100,
            }

            try:
                resp = requests.get(f"{API_BASE}/comments/search", params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()
            except (requests.RequestException, json.JSONDecodeError) as e:
                log.warning(f"Error (page {page}): {e}. Reintentando en 5s...")
                time.sleep(5)
                continue

            batch = data.get("data", [])
            if not batch:
                break

            for comment in batch:
                author = comment.get("author", "")
                if author in BOTS:
                    continue

                entry = {
                    "text": comment.get("body", "") or "",
                    "score": comment.get("score", 0),
                    "created_utc": comment.get("created_utc"),
                    "author": author,
                    "id": comment.get("id"),
                    "link_id": comment.get("link_id"),
                    "parent_id": comment.get("parent_id"),
                }
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                total_saved += 1

            total += len(batch)

            last_utc = batch[-1].get("created_utc")
            if last_utc:
                current_after = last_utc
                save_progress(progress_file, str(last_utc))
            else:
                break

            page += 1
            if page % 100 == 0:
                log.info(f"  Comentarios: página {page} | {total_saved:,} guardados de {total:,} vistos")

    log.info(f"Comentarios completados: {total_saved:,} guardados de {total:,} vistos")
    return total_saved


# ============================================================
# Orquestación
# ============================================================

def run(after: str = "2015-01-01", before: str = "2026-04-01", resume: bool = False):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    log.info(f"Descargando r/{SUBREDDIT} ({after} → {before})")

    n_posts = fetch_posts(after, before, resume)
    n_comments = fetch_comments(after, before, resume)

    stats = {"posts": n_posts, "comments": n_comments}

    log.info("=" * 60)
    log.info("DESCARGA COMPLETADA")
    log.info(f"  Posts: {n_posts:,}")
    log.info(f"  Comentarios: {n_comments:,}")
    log.info("=" * 60)

    stats_file = OUTPUT_DIR / "reddit_stats.json"
    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Descarga r/Minecraft de Arctic Shift")
    parser.add_argument("--after", default="2015-01-01")
    parser.add_argument("--before", default="2026-04-01")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    run(after=args.after, before=args.before, resume=args.resume)
