"""
wiki_scraper.py — Scraper de minecraft.wiki
=============================================

Extrae artículos de la Minecraft Wiki usando la API de MediaWiki.

FILOSOFÍA: Obtener TODO, limpiar después.
El scraper solo quita navegación web (navbox, toc, edit links).
Todo el contenido informativo se mantiene para procesamiento posterior.

FEATURES:
- Maneja redirects (ej: "Enchanting" → "Enchantment")
- Extrae tablas como texto natural + raw por separado
- Extrae nombres de sonidos como metadata
- Separa changelogs en archivo aparte con secciones marcadas
- Resume: puede continuar si se interrumpe
- Rate limiting respetuoso (1 req/seg)

Uso:
    python -m scraper.wiki_scraper
    python -m scraper.wiki_scraper --resume
"""

from __future__ import annotations

import json
import re
import time
import argparse
import logging
from pathlib import Path
from datetime import datetime

import requests
from bs4 import BeautifulSoup

# ============================================================
# Configuración
# ============================================================

WIKI_API = "https://minecraft.wiki/api.php"
RATE_LIMIT = 1.0

OUTPUT_DIR = Path(__file__).parent.parent / "raw_data" / "wiki"

USER_AGENT = "MineGPT-Educational-Scraper/1.0 (personal ML learning project)"
HEADERS = {"User-Agent": USER_AGENT}

# Patrón para detectar changelogs
CHANGELOG_PATTERN = re.compile(
    r"^(Java Edition|Bedrock Edition|Pocket Edition|Legacy Console Edition)\s+[\d.]",
    re.IGNORECASE,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ============================================================
# Obtener lista de todos los artículos
# ============================================================

def get_all_page_titles() -> list[str]:
    """Obtiene títulos de TODOS los artículos via API allpages."""
    titles = []
    params = {
        "action": "query",
        "list": "allpages",
        "aplimit": "500",
        "apnamespace": "0",
        "format": "json",
    }

    log.info("Obteniendo lista de todos los artículos...")
    page_count = 0

    while True:
        time.sleep(RATE_LIMIT)
        resp = requests.get(WIKI_API, params=params, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        pages = data.get("query", {}).get("allpages", [])
        titles.extend(p["title"] for p in pages)

        page_count += 1
        log.info(f"  Página {page_count}: +{len(pages)} artículos (total: {len(titles)})")

        if "continue" in data:
            params["apcontinue"] = data["continue"]["apcontinue"]
        else:
            break

    log.info(f"Total de artículos encontrados: {len(titles)}")
    return titles


# ============================================================
# Obtener contenido de un artículo
# ============================================================

def fetch_article_html(title: str) -> tuple[str, list[dict], bool] | None:
    """
    Obtiene el HTML de un artículo.

    Returns:
        (html, categories, is_redirect) o None si falla
    """
    params = {
        "action": "parse",
        "page": title,
        "prop": "text|categories",
        "format": "json",
        "disabletoc": "true",
        "disableeditsection": "true",
    }

    try:
        resp = requests.get(WIKI_API, params=params, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, json.JSONDecodeError) as e:
        log.warning(f"Error obteniendo '{title}': {e}")
        return None

    if "error" in data:
        log.debug(f"API error para '{title}': {data['error'].get('info')}")
        return None

    parse_data = data.get("parse", {})
    html = parse_data.get("text", {}).get("*", "")
    categories = [
        cat["*"] for cat in parse_data.get("categories", [])
        if not cat.get("hidden")
    ]

    # Detectar redirects
    is_redirect = 'class="redirectMsg"' in html

    return html, categories, is_redirect


def resolve_redirect(html: str) -> str | None:
    """Extrae el título destino de un redirect."""
    soup = BeautifulSoup(html, "lxml")
    redirect_div = soup.find(class_="redirectMsg")
    if redirect_div:
        link = redirect_div.find("a")
        if link and link.get("title"):
            return link["title"]
    return None


# ============================================================
# Procesamiento de HTML
# ============================================================

def extract_tables_raw(soup: BeautifulSoup, title: str) -> list[dict]:
    """Extrae tablas wikitable como datos raw."""
    tables = []
    for table in soup.find_all("table", class_="wikitable"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if cells:
                rows.append(cells)
        if rows:
            tables.append({"article": title, "rows": rows})
    return tables


def table_to_text(table_tag) -> str:
    """Convierte una tabla HTML a texto natural."""
    rows = []
    for tr in table_tag.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
        if cells:
            rows.append(cells)

    if not rows:
        return ""

    # Si tiene header row, usarla como contexto
    if len(rows) >= 2:
        headers = rows[0]
        lines = []
        for row in rows[1:]:
            parts = []
            for i, cell in enumerate(row):
                if cell and i < len(headers) and headers[i]:
                    parts.append(f"{headers[i]}: {cell}")
                elif cell:
                    parts.append(cell)
            if parts:
                lines.append(", ".join(parts))
        return "\n".join(lines)
    else:
        return " | ".join(rows[0])


def extract_sounds(soup: BeautifulSoup) -> list[str]:
    """Extrae nombres de archivos de audio."""
    sounds = []
    for audio in soup.find_all("audio"):
        title = audio.get("data-mwtitle", "")
        if title:
            # "Creeper_death.ogg" → "Creeper death"
            name = title.replace(".ogg", "").replace("_", " ")
            sounds.append(name)
    return sounds


def infobox_to_text(infobox_tag) -> str:
    """Convierte un infobox HTML a texto estructurado legible."""
    rows = []
    for tr in infobox_tag.find_all("tr"):
        # Usar get_text con separador para no juntar todo
        cells = [td.get_text(separator=" ", strip=True) for td in tr.find_all(["td", "th"])]
        cells = [c for c in cells if c]
        if len(cells) == 2:
            rows.append(f"{cells[0]}: {cells[1]}")
        elif len(cells) == 1:
            rows.append(cells[0])
        elif len(cells) > 2:
            rows.append(" | ".join(cells))

    parts = [r for r in rows if r]
    return "\n".join(parts)


def process_html(html: str, title: str) -> tuple[str, list[dict], list[str]]:
    """
    Procesa HTML del wiki. Obtiene contenido informativo, limpia artefactos web.

    Returns:
        (texto_limpio, tablas_raw, sonidos)
    """
    soup = BeautifulSoup(html, "lxml")

    # --- Extraer datos ANTES de modificar el DOM ---
    tables_raw = extract_tables_raw(soup, title)
    sounds = extract_sounds(soup)

    # --- QUITAR: navegación y artefactos web ---
    for element in soup.find_all(["script", "style"]):
        element.decompose()

    for class_name in [
        "navbox",           # Navegación entre artículos
        "mw-editsection",   # Links de [edit]
        "toc",              # Tabla de contenidos
        "navigation-not-searchable",
        "mw-cite-backlink",  # Flechas ↑ de referencias
        "reference",         # Números de referencia [1][2]
        "reference-text",    # Texto de referencias al pie
    ]:
        for el in soup.find_all(class_=class_name):
            el.decompose()

    # Eliminar navbox tables
    for table in soup.find_all("table", class_="navbox"):
        table.decompose()

    # --- Convertir infoboxes a texto legible ---
    for infobox in soup.find_all(class_="infobox"):
        text = infobox_to_text(infobox)
        if text:
            new_tag = soup.new_tag("p")
            new_tag.string = text
            infobox.replace_with(new_tag)
        else:
            infobox.decompose()

    # --- Convertir wikitables a texto natural ---
    for table in soup.find_all("table", class_="wikitable"):
        text = table_to_text(table)
        if text:
            new_tag = soup.new_tag("p")
            new_tag.string = text
            table.replace_with(new_tag)
        else:
            table.decompose()

    # --- Limpiar sprites/imágenes que no aportan texto ---
    for el in soup.find_all(class_="sprite-file"):
        el.decompose()
    for el in soup.find_all(class_="pixel-image"):
        if not el.get_text(strip=True):
            el.decompose()

    # --- Quitar audio players (ya extrajimos los nombres) ---
    for el in soup.find_all(class_="sound"):
        el.decompose()

    # --- Unir texto inline (no fragmentar en los links) ---
    # Reemplazar <br> y block elements con newlines, pero <a>, <b>, <i> son inline
    for br in soup.find_all("br"):
        br.replace_with("\n")

    # Extraer texto: usar " " como separator para que los links no fragmenten
    # y luego restaurar párrafos donde había block elements
    text = soup.get_text(separator=" ")

    # --- Limpiar artefactos del footer ---
    lines = []
    # Secciones de footer que no son contenido informativo
    footer_markers = {
        "Navigation", "External links", "References",
        "This was a featured article",
    }
    in_footer = False

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue

        # Detectar inicio de secciones de footer
        if any(line.startswith(marker) for marker in footer_markers):
            in_footer = True
            continue

        # "See also" es una sección legítima — mantener los items pero no URLs
        if line == "See also":
            lines.append(line)
            continue

        if in_footer:
            continue

        # Quitar URLs raw sueltas
        if re.match(r'^https?://', line):
            continue

        # Quitar flechas de referencia sueltas
        if line == "↑":
            continue

        # Quitar bug tracker IDs sueltos (MC-12345)
        if re.match(r'^MC-\d+$', line):
            continue

        lines.append(line)

    text = "\n".join(lines)

    # Colapsar whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Limpiar edition markers fragmentados: "‌\n[\nJE\nonly\n]" → "[JE only]"
    text = re.sub(r'‌?\s*\[\s*(JE|BE)\s+only\s*\]', r' [\1 only]', text)

    return text.strip(), tables_raw, sounds


def detect_changelog_sections(text: str) -> dict:
    """
    Para artículos de changelog, marca las secciones.

    Returns:
        {"player_facing": "...", "technical": "...", "full": "..."}
    """
    lines = text.split("\n")
    sections = {"player_facing": [], "technical": [], "current": "player_facing"}

    for line in lines:
        lower = line.lower().strip()
        if lower in ("technical", "technical changes", "technical additions"):
            sections["current"] = "technical"
        elif lower in ("fixes", "video", "trivia", "references", "navigation"):
            sections["current"] = "other"

        if sections["current"] == "player_facing":
            sections["player_facing"].append(line)
        elif sections["current"] == "technical":
            sections["technical"].append(line)

    return {
        "player_facing": "\n".join(sections["player_facing"]).strip(),
        "technical": "\n".join(sections["technical"]).strip(),
        "full": text,
    }


# ============================================================
# Orquestación principal
# ============================================================

def load_progress(progress_file: Path) -> set[str]:
    if progress_file.exists():
        lines = progress_file.read_text(encoding="utf-8").strip().split("\n")
        return set(l for l in lines if l)
    return set()


def save_progress(progress_file: Path, title: str):
    with open(progress_file, "a", encoding="utf-8") as f:
        f.write(title + "\n")


def run(resume: bool = False):
    """Ejecuta el scraping completo."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    articles_file = OUTPUT_DIR / "articles.jsonl"
    tables_file = OUTPUT_DIR / "tables_raw.jsonl"
    changelogs_file = OUTPUT_DIR / "changelogs.jsonl"
    redirects_file = OUTPUT_DIR / "redirects.jsonl"
    progress_file = OUTPUT_DIR / ".progress"

    # Obtener lista de artículos
    titles = get_all_page_titles()

    # Resume
    done = load_progress(progress_file) if resume else set()
    if done:
        log.info(f"Resumiendo: {len(done)} ya procesados, {len(titles) - len(done)} pendientes")

    stats = {
        "total_titles": len(titles),
        "processed": len(done),
        "articles": 0,
        "changelogs": 0,
        "redirects": 0,
        "errors": 0,
        "total_words": 0,
        "total_tables": 0,
    }

    mode = "a" if resume else "w"
    with (
        open(articles_file, mode, encoding="utf-8") as f_articles,
        open(tables_file, mode, encoding="utf-8") as f_tables,
        open(changelogs_file, mode, encoding="utf-8") as f_changelogs,
        open(redirects_file, mode, encoding="utf-8") as f_redirects,
    ):
        for title in titles:
            if title in done:
                continue

            time.sleep(RATE_LIMIT)

            result = fetch_article_html(title)
            if result is None:
                stats["errors"] += 1
                save_progress(progress_file, title)
                continue

            html, categories, is_redirect = result

            # Manejar redirects
            if is_redirect:
                redirect_target = resolve_redirect(html)
                f_redirects.write(json.dumps({
                    "from": title,
                    "to": redirect_target,
                }, ensure_ascii=False) + "\n")
                stats["redirects"] += 1
                save_progress(progress_file, title)

                # Descargar el artículo destino si no lo hemos visto
                if redirect_target and redirect_target not in done:
                    time.sleep(RATE_LIMIT)
                    result2 = fetch_article_html(redirect_target)
                    if result2:
                        html, categories, _ = result2
                        title = redirect_target  # Usar el título real
                    else:
                        stats["processed"] += 1
                        continue
                else:
                    stats["processed"] += 1
                    continue

            # Procesar HTML
            text, tables_raw, sounds = process_html(html, title)

            # Guardar tablas raw
            for table in tables_raw:
                f_tables.write(json.dumps(table, ensure_ascii=False) + "\n")
                stats["total_tables"] += 1

            # Armar artículo
            article = {
                "title": title,
                "text": text,
                "categories": categories,
                "sounds": sounds if sounds else None,
                "word_count": len(text.split()),
                "scraped_at": datetime.now().isoformat(),
            }

            # Separar changelogs
            if CHANGELOG_PATTERN.match(title):
                sections = detect_changelog_sections(text)
                article["changelog_sections"] = {
                    "player_facing": sections["player_facing"],
                    "technical": sections["technical"],
                }
                f_changelogs.write(json.dumps(article, ensure_ascii=False) + "\n")
                stats["changelogs"] += 1
            else:
                f_articles.write(json.dumps(article, ensure_ascii=False) + "\n")
                stats["articles"] += 1

            stats["total_words"] += article["word_count"]
            save_progress(progress_file, title)
            stats["processed"] += 1

            if stats["processed"] % 100 == 0:
                log.info(
                    f"Progreso: {stats['processed']}/{stats['total_titles']} | "
                    f"{stats['articles']} artículos | {stats['changelogs']} changelogs | "
                    f"{stats['redirects']} redirects | {stats['errors']} errores | "
                    f"{stats['total_words']:,} palabras"
                )

    # Reporte final
    log.info("=" * 60)
    log.info("SCRAPING COMPLETADO")
    log.info(f"  Artículos: {stats['articles']}")
    log.info(f"  Changelogs: {stats['changelogs']}")
    log.info(f"  Redirects: {stats['redirects']}")
    log.info(f"  Errores: {stats['errors']}")
    log.info(f"  Tablas extraídas: {stats['total_tables']}")
    log.info(f"  Total palabras: {stats['total_words']:,}")
    log.info("=" * 60)

    stats_file = OUTPUT_DIR / "scraping_stats.json"
    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scraper de minecraft.wiki")
    parser.add_argument("--resume", action="store_true", help="Continuar desde donde se quedó")
    args = parser.parse_args()

    run(resume=args.resume)
