"""
explore_sample.py — Test exploratorio de fuentes de datos
==========================================================

Descarga un sample diverso de artículos del wiki y posts de Reddit
para analizar qué tipo de contenido llega ANTES de lanzar el scraping completo.

Esto permite:
- Ver el formato real del HTML/texto
- Detectar contenido problemático
- Anticipar qué hay que limpiar
- Decidir qué se quita en scraping vs en limpieza

Uso:
    python -m scraper.explore_sample
"""

import json
import time
import logging
from pathlib import Path
from collections import Counter

import requests
from bs4 import BeautifulSoup

# ============================================================
# Configuración
# ============================================================

WIKI_API = "https://minecraft.wiki/api.php"
ARCTIC_API = "https://arctic-shift.photon-reddit.com/api"
RATE_LIMIT = 1.0
OUTPUT_DIR = Path(__file__).parent.parent / "raw_data" / "_exploration"
HEADERS = {"User-Agent": "MineGPT-Educational-Scraper/1.0 (exploration sample)"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ============================================================
# Sample de artículos del wiki
# ============================================================

# Artículos variados para cubrir diferentes tipos de contenido
WIKI_SAMPLE_TITLES = [
    # Mobs
    "Creeper", "Enderman", "Warden", "Villager",
    # Bloques
    "Redstone Dust", "Obsidian", "Deepslate",
    # Items
    "Diamond Sword", "Elytra", "Totem of Undying",
    # Biomas
    "Plains", "Nether Wastes", "Deep Dark",
    # Mecánicas
    "Crafting", "Enchanting", "Brewing",
    # Estructuras
    "Stronghold", "Ancient City",
    # Probablemente cortos/stubs
    "Dandelion", "Dead Bush",
    # Versiones/changelog
    "Java Edition 1.21", "Java Edition version history",
]


def fetch_wiki_sample():
    """Descarga sample de artículos del wiki con HTML raw + texto limpio."""
    log.info(f"Descargando {len(WIKI_SAMPLE_TITLES)} artículos del wiki...")
    articles = []

    for title in WIKI_SAMPLE_TITLES:
        time.sleep(RATE_LIMIT)
        log.info(f"  Descargando: {title}")

        params = {
            "action": "parse",
            "page": title,
            "prop": "text|categories|properties",
            "format": "json",
            "disabletoc": "true",
            "disableeditsection": "true",
        }

        try:
            resp = requests.get(WIKI_API, params=params, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.warning(f"  Error: {e}")
            continue

        if "error" in data:
            log.warning(f"  API error: {data['error'].get('info')}")
            continue

        parse_data = data.get("parse", {})
        html = parse_data.get("text", {}).get("*", "")
        categories = [c["*"] for c in parse_data.get("categories", []) if not c.get("hidden")]

        # Análisis del HTML
        soup = BeautifulSoup(html, "lxml")

        # Encontrar todas las clases CSS usadas
        css_classes = Counter()
        for el in soup.find_all(True):
            for cls in el.get("class", []):
                css_classes[cls] += 1

        # Contar tablas
        tables = soup.find_all("table")
        table_classes = Counter()
        for t in tables:
            for cls in t.get("class", []):
                table_classes[cls] += 1

        # Encontrar infoboxes
        infoboxes = soup.find_all(class_="infobox")

        # Texto plano (sin limpiar — queremos ver qué hay)
        raw_text = soup.get_text(separator="\n")

        articles.append({
            "title": title,
            "html_length": len(html),
            "text_length": len(raw_text),
            "word_count": len(raw_text.split()),
            "categories": categories,
            "num_tables": len(tables),
            "table_classes": dict(table_classes),
            "num_infoboxes": len(infoboxes),
            "top_css_classes": dict(css_classes.most_common(20)),
            "html_raw": html,  # Guardar HTML completo para inspección
            "text_raw": raw_text,  # Guardar texto sin limpiar
        })

    return articles


# ============================================================
# Sample de Reddit
# ============================================================

def fetch_reddit_sample():
    """Descarga sample de posts de Reddit de diferentes años."""
    log.info("Descargando sample de r/Minecraft...")
    all_posts = []

    # Diferentes períodos para ver evolución del contenido
    periods = [
        ("2015-01-01", "2015-07-01", "2015 H1"),
        ("2018-01-01", "2018-07-01", "2018 H1"),
        ("2020-01-01", "2020-07-01", "2020 H1"),
        ("2023-01-01", "2023-07-01", "2023 H1"),
        ("2025-01-01", "2025-07-01", "2025 H1"),
    ]

    for after, before, label in periods:
        time.sleep(0.5)
        log.info(f"  Período: {label}")

        params = {
            "subreddit": "Minecraft",
            "after": after,
            "before": before,
            "sort": "desc",  # Más populares primero
            "limit": 10,
        }

        try:
            resp = requests.get(f"{ARCTIC_API}/posts/search", params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.warning(f"  Error: {e}")
            continue

        for post in data.get("data", []):
            all_posts.append({
                "title": post.get("title", ""),
                "selftext": post.get("selftext", ""),
                "score": post.get("score", 0),
                "created_utc": post.get("created_utc"),
                "num_comments": post.get("num_comments", 0),
                "flair": post.get("link_flair_text", ""),
                "author": post.get("author", ""),
                "url": post.get("url", ""),
                "is_self": post.get("is_self", False),
                "period": label,
            })

    # También descargar algunos comentarios
    log.info("  Descargando sample de comentarios...")
    time.sleep(0.5)
    try:
        resp = requests.get(f"{ARCTIC_API}/comments/search", params={
            "subreddit": "Minecraft",
            "after": "2024-01-01",
            "before": "2024-07-01",
            "sort": "desc",
            "limit": 20,
        }, timeout=30)
        resp.raise_for_status()
        comments = resp.json().get("data", [])
    except Exception as e:
        log.warning(f"  Error con comentarios: {e}")
        comments = []

    return all_posts, comments


# ============================================================
# Generación de reporte
# ============================================================

def generate_report(wiki_articles: list, reddit_posts: list, reddit_comments: list):
    """Genera un reporte de análisis del sample."""
    report_lines = []
    report_lines.append("=" * 70)
    report_lines.append("REPORTE DE EXPLORACIÓN — MineGPT Scraping Sample")
    report_lines.append("=" * 70)

    # --- WIKI ---
    report_lines.append("\n" + "=" * 70)
    report_lines.append("WIKI — minecraft.wiki")
    report_lines.append("=" * 70)

    report_lines.append(f"\nArtículos descargados: {len(wiki_articles)}")

    # Distribución de longitudes
    report_lines.append("\nDistribución de longitud (palabras):")
    for article in sorted(wiki_articles, key=lambda a: a["word_count"]):
        report_lines.append(
            f"  {article['title']:30s} | {article['word_count']:>6,} palabras | "
            f"{article['num_tables']} tablas | {article['num_infoboxes']} infoboxes"
        )

    # Clases CSS más comunes (para decidir qué quitar)
    all_classes = Counter()
    for article in wiki_articles:
        for cls, count in article["top_css_classes"].items():
            all_classes[cls] += count

    report_lines.append("\nTop 30 clases CSS encontradas en el HTML:")
    for cls, count in all_classes.most_common(30):
        report_lines.append(f"  .{cls:30s} — {count} apariciones")

    # Clases de tablas
    all_table_classes = Counter()
    for article in wiki_articles:
        for cls, count in article["table_classes"].items():
            all_table_classes[cls] += count

    report_lines.append("\nClases de tablas:")
    for cls, count in all_table_classes.most_common(10):
        report_lines.append(f"  .{cls:30s} — {count} tablas")

    # Muestra de texto de artículos cortos
    report_lines.append("\n--- Artículos más cortos (posibles stubs) ---")
    for article in sorted(wiki_articles, key=lambda a: a["word_count"])[:5]:
        preview = article["text_raw"][:300].replace("\n", " ")
        report_lines.append(f"\n  [{article['title']}] ({article['word_count']} palabras)")
        report_lines.append(f"  Preview: {preview}...")

    # Muestra de texto de artículos largos
    report_lines.append("\n--- Primeros 300 chars de artículos largos ---")
    for article in sorted(wiki_articles, key=lambda a: -a["word_count"])[:3]:
        preview = article["text_raw"][:300].replace("\n", " ")
        report_lines.append(f"\n  [{article['title']}] ({article['word_count']} palabras)")
        report_lines.append(f"  Preview: {preview}...")

    # --- REDDIT ---
    report_lines.append("\n\n" + "=" * 70)
    report_lines.append("REDDIT — r/Minecraft (Arctic Shift)")
    report_lines.append("=" * 70)

    report_lines.append(f"\nPosts descargados: {len(reddit_posts)}")
    report_lines.append(f"Comentarios descargados: {len(reddit_comments)}")

    # Posts por período
    report_lines.append("\nPosts por período:")
    period_counts = Counter(p["period"] for p in reddit_posts)
    for period, count in sorted(period_counts.items()):
        report_lines.append(f"  {period}: {count} posts")

    # Flairs
    report_lines.append("\nFlairs encontrados:")
    flair_counts = Counter(p["flair"] for p in reddit_posts if p["flair"])
    for flair, count in flair_counts.most_common(15):
        report_lines.append(f"  {flair}: {count}")

    # Posts con texto vs sin texto
    with_text = sum(1 for p in reddit_posts if p["selftext"] and len(p["selftext"]) > 50)
    report_lines.append(f"\nPosts con texto sustancial (>50 chars): {with_text}/{len(reddit_posts)}")

    # Score distribution
    scores = [p["score"] for p in reddit_posts]
    if scores:
        report_lines.append(f"Score: min={min(scores)}, max={max(scores)}, median={sorted(scores)[len(scores)//2]}")

    # Muestra de posts
    report_lines.append("\n--- Sample de posts con texto ---")
    for post in reddit_posts:
        if post["selftext"] and len(post["selftext"]) > 50:
            preview = post["selftext"][:200].replace("\n", " ")
            report_lines.append(
                f"\n  [{post['period']}] score={post['score']} flair={post['flair']}"
            )
            report_lines.append(f"  Title: {post['title']}")
            report_lines.append(f"  Text: {preview}...")
            break  # Solo 1 ejemplo por brevedad en consola

    # Muestra de posts SIN texto (solo título + link)
    no_text_posts = [p for p in reddit_posts if not p["selftext"] or len(p["selftext"]) < 10]
    report_lines.append(f"\nPosts SIN texto (solo título/link): {len(no_text_posts)}/{len(reddit_posts)}")
    for post in no_text_posts[:3]:
        report_lines.append(f"  [{post['period']}] score={post['score']} | {post['title']}")
        report_lines.append(f"    URL: {post['url']}")

    # Muestra de comentarios
    report_lines.append("\n--- Sample de comentarios ---")
    for comment in reddit_comments[:3]:
        body = comment.get("body", "")[:200].replace("\n", " ")
        report_lines.append(f"  score={comment.get('score', 0)} | {body}")

    return "\n".join(report_lines)


# ============================================================
# Main
# ============================================================

def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Descargar samples
    wiki_articles = fetch_wiki_sample()
    reddit_posts, reddit_comments = fetch_reddit_sample()

    # Guardar datos raw
    with open(OUTPUT_DIR / "wiki_sample.json", "w", encoding="utf-8") as f:
        # Guardar sin HTML para que sea legible (HTML va aparte)
        sample_no_html = [{k: v for k, v in a.items() if k != "html_raw"} for a in wiki_articles]
        json.dump(sample_no_html, f, indent=2, ensure_ascii=False)

    # Guardar HTML raw por separado para inspección
    for article in wiki_articles:
        safe_title = article["title"].replace("/", "_").replace(" ", "_")
        html_file = OUTPUT_DIR / "wiki_html" / f"{safe_title}.html"
        html_file.parent.mkdir(parents=True, exist_ok=True)
        html_file.write_text(article["html_raw"], encoding="utf-8")

    with open(OUTPUT_DIR / "reddit_sample.json", "w", encoding="utf-8") as f:
        json.dump({"posts": reddit_posts, "comments": reddit_comments}, f, indent=2, ensure_ascii=False)

    # Generar y mostrar reporte
    report = generate_report(wiki_articles, reddit_posts, reddit_comments)
    print(report)

    # Guardar reporte
    report_file = OUTPUT_DIR / "exploration_report.txt"
    report_file.write_text(report, encoding="utf-8")
    log.info(f"\nReporte guardado en: {report_file}")
    log.info(f"HTML de artículos en: {OUTPUT_DIR / 'wiki_html'}/")
    log.info(f"Datos raw en: {OUTPUT_DIR}/")


if __name__ == "__main__":
    run()
