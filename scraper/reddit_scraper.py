"""
reddit_scraper.py — Descarga de r/Minecraft via Arctic Shift
=============================================================

Arctic Shift es un proyecto comunitario que mantiene dumps históricos
de Reddit. Expone una API pública que permite buscar posts y comentarios
por subreddit, fecha, y otros filtros.

CÓMO FUNCIONA:
1. Usamos la API de Arctic Shift (NO la API oficial de Reddit)
2. Paginamos cronológicamente (sort=asc, after=last_created_utc)
3. Descargamos tanto posts (submissions) como comentarios
4. Filtramos por calidad (score > threshold, texto suficiente)
5. Guardamos en JSONL

¿POR QUÉ ARCTIC SHIFT Y NO LA API DE REDDIT?
- Reddit cobra por su API y prohíbe uso para ML training
- Arctic Shift tiene datos históricos gratuitos para uso científico
- La API es más simple y no requiere autenticación

Uso:
    python -m scraper.reddit_scraper
    python -m scraper.reddit_scraper --resume
    python -m scraper.reddit_scraper --after 2023-01-01 --before 2025-01-01
"""

import json
import time
import argparse
import logging
from pathlib import Path
from datetime import datetime

import requests

# ============================================================
# Configuración
# ============================================================

API_BASE = "https://arctic-shift.photon-reddit.com/api"
SUBREDDIT = "Minecraft"

# Filtros de calidad
MIN_SCORE_POSTS = 10        # Solo posts con al menos 10 upvotes
MIN_SCORE_COMMENTS = 10     # Solo comentarios con al menos 10 upvotes
MIN_TEXT_LENGTH = 50         # Mínimo 50 caracteres de texto

# Rate limiting (Arctic Shift es gratuito, sé respetuoso)
RATE_LIMIT = 0.5  # Segundos entre requests

# Output
OUTPUT_DIR = Path(__file__).parent.parent / "raw_data" / "reddit"

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ============================================================
# Funciones de descarga
# ============================================================

def fetch_posts(after: str = "2015-01-01", before: str = "2026-04-01") -> list[dict]:
    """
    Descarga TODOS los posts de r/Minecraft en un rango de fechas.

    Usa paginación cronológica: sort=asc, y el created_utc del último
    resultado como cursor para la siguiente página.

    Args:
        after: Fecha de inicio (YYYY-MM-DD)
        before: Fecha de fin (YYYY-MM-DD)

    Returns:
        Lista de posts filtrados
    """
    posts = []
    current_after = after
    page = 0

    log.info(f"Descargando posts de r/{SUBREDDIT} ({after} → {before})...")

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
            log.warning(f"Error en request (page {page}): {e}. Reintentando en 5s...")
            time.sleep(5)
            continue

        batch = data.get("data", [])
        if not batch:
            break

        # Filtrar por calidad
        for post in batch:
            score = post.get("score", 0)
            selftext = post.get("selftext", "") or ""
            title = post.get("title", "") or ""

            # Queremos posts con texto sustancial (no solo links/imágenes)
            if score >= MIN_SCORE_POSTS and len(selftext) >= MIN_TEXT_LENGTH:
                posts.append({
                    "title": title,
                    "text": selftext,
                    "score": score,
                    "created_utc": post.get("created_utc"),
                    "num_comments": post.get("num_comments", 0),
                    "flair": post.get("link_flair_text", ""),
                    "author": post.get("author", "[deleted]"),
                    "id": post.get("id"),
                })

        # Paginar: usar created_utc del último resultado como cursor
        last_utc = batch[-1].get("created_utc")
        if last_utc:
            current_after = last_utc
        else:
            break

        page += 1
        if page % 10 == 0:
            log.info(f"  Página {page}: {len(posts)} posts filtrados hasta ahora")

    log.info(f"Posts descargados: {len(posts)} (filtrados de r/{SUBREDDIT})")
    return posts


def fetch_comments(after: str = "2015-01-01", before: str = "2026-04-01") -> list[dict]:
    """
    Descarga comentarios de r/Minecraft filtrados por calidad.

    Misma lógica de paginación que fetch_posts.

    Args:
        after: Fecha de inicio (YYYY-MM-DD)
        before: Fecha de fin (YYYY-MM-DD)

    Returns:
        Lista de comentarios filtrados
    """
    comments = []
    current_after = after
    page = 0

    log.info(f"Descargando comentarios de r/{SUBREDDIT} ({after} → {before})...")

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
            log.warning(f"Error en request (page {page}): {e}. Reintentando en 5s...")
            time.sleep(5)
            continue

        batch = data.get("data", [])
        if not batch:
            break

        for comment in batch:
            score = comment.get("score", 0)
            body = comment.get("body", "") or ""

            if score >= MIN_SCORE_COMMENTS and len(body) >= MIN_TEXT_LENGTH:
                # Filtrar bots y contenido eliminado
                author = comment.get("author", "")
                if author in ("[deleted]", "AutoModerator", "RemindMeBot"):
                    continue

                comments.append({
                    "text": body,
                    "score": score,
                    "created_utc": comment.get("created_utc"),
                    "author": author,
                    "id": comment.get("id"),
                    "link_id": comment.get("link_id"),  # ID del post padre
                })

        last_utc = batch[-1].get("created_utc")
        if last_utc:
            current_after = last_utc
        else:
            break

        page += 1
        if page % 50 == 0:
            log.info(f"  Página {page}: {len(comments)} comentarios filtrados hasta ahora")

    log.info(f"Comentarios descargados: {len(comments)} (filtrados de r/{SUBREDDIT})")
    return comments


# ============================================================
# Orquestación
# ============================================================

def run(after: str = "2015-01-01", before: str = "2026-04-01", resume: bool = False):
    """Ejecuta la descarga completa."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    posts_file = OUTPUT_DIR / "posts.jsonl"
    comments_file = OUTPUT_DIR / "comments.jsonl"

    # --- Descargar posts ---
    if resume and posts_file.exists():
        log.info(f"Posts ya descargados ({posts_file}), saltando...")
    else:
        posts = fetch_posts(after=after, before=before)
        with open(posts_file, "w", encoding="utf-8") as f:
            for post in posts:
                f.write(json.dumps(post, ensure_ascii=False) + "\n")
        log.info(f"Posts guardados en {posts_file}")

    # --- Descargar comentarios ---
    if resume and comments_file.exists():
        log.info(f"Comentarios ya descargados ({comments_file}), saltando...")
    else:
        comments = fetch_comments(after=after, before=before)
        with open(comments_file, "w", encoding="utf-8") as f:
            for comment in comments:
                f.write(json.dumps(comment, ensure_ascii=False) + "\n")
        log.info(f"Comentarios guardados en {comments_file}")

    # --- Stats ---
    stats = {}
    if posts_file.exists():
        post_count = sum(1 for _ in open(posts_file, encoding="utf-8"))
        stats["posts"] = post_count
    if comments_file.exists():
        comment_count = sum(1 for _ in open(comments_file, encoding="utf-8"))
        stats["comments"] = comment_count

    log.info("=" * 60)
    log.info("DESCARGA COMPLETADA")
    log.info(f"  Posts: {stats.get('posts', 0):,}")
    log.info(f"  Comentarios: {stats.get('comments', 0):,}")
    log.info(f"  Archivos: {posts_file}, {comments_file}")
    log.info("=" * 60)

    stats_file = OUTPUT_DIR / "reddit_stats.json"
    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Descarga r/Minecraft de Arctic Shift")
    parser.add_argument("--after", default="2015-01-01", help="Fecha inicio (YYYY-MM-DD)")
    parser.add_argument("--before", default="2026-04-01", help="Fecha fin (YYYY-MM-DD)")
    parser.add_argument("--resume", action="store_true", help="Saltear archivos ya descargados")
    args = parser.parse_args()

    run(after=args.after, before=args.before, resume=args.resume)
