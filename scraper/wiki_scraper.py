"""
wiki_scraper.py — Scraper de minecraft.wiki
=============================================

Este script extrae artículos de la Minecraft Wiki (minecraft.wiki) usando
la API de MediaWiki. MediaWiki es el software que usa Wikipedia y muchas
wikis — expone una API JSON que permite obtener contenido sin parsear HTML.

CÓMO FUNCIONA:
1. Pedimos la lista de TODOS los artículos via la API (allpages)
2. Para cada artículo, pedimos su contenido en texto plano (extracts)
3. Guardamos todo en formato JSONL (un JSON por línea)

NOTA SOBRE LEGALIDAD:
- El contenido está bajo CC BY-NC-SA 3.0
- El sitio bloquea bots de IA en robots.txt
- Este scraper es para uso educativo personal únicamente
- Respetamos rate limits (1 req/seg mínimo)

Uso:
    python -m scraper.wiki_scraper
    python -m scraper.wiki_scraper --resume    # Continúa desde donde quedó
"""

import json
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
RATE_LIMIT = 1.0  # Segundos entre requests

# Carpeta donde se guardan los datos crudos
OUTPUT_DIR = Path(__file__).parent.parent / "raw_data" / "wiki"

# User-Agent identificándose honestamente
USER_AGENT = "MineGPT-Educational-Scraper/1.0 (personal ML learning project; contact: github.com/minegpt)"

# Headers para todas las requests
HEADERS = {"User-Agent": USER_AGENT}

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ============================================================
# Paso 1: Obtener lista de todos los artículos
# ============================================================
# La API de MediaWiki tiene el módulo "allpages" que lista todos
# los artículos del wiki. Devuelve máximo 500 por request, así que
# hay que paginar usando el token "apcontinue".

def get_all_page_titles() -> list[str]:
    """
    Obtiene los títulos de TODOS los artículos del wiki.

    Usa el endpoint allpages de la API MediaWiki.
    Pagina automáticamente hasta obtener todos los títulos.

    Returns:
        Lista de títulos de artículos (strings)
    """
    titles = []
    params = {
        "action": "query",
        "list": "allpages",
        "aplimit": "500",       # Máximo por request
        "apnamespace": "0",     # Namespace 0 = artículos (no talk pages, no user pages)
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
        batch_titles = [p["title"] for p in pages]
        titles.extend(batch_titles)

        page_count += 1
        log.info(f"  Página {page_count}: +{len(batch_titles)} artículos (total: {len(titles)})")

        # ¿Hay más páginas? MediaWiki pone "continue" si hay más resultados
        if "continue" in data:
            params["apcontinue"] = data["continue"]["apcontinue"]
        else:
            break

    log.info(f"Total de artículos encontrados: {len(titles)}")
    return titles


# ============================================================
# Paso 2: Obtener contenido de un artículo
# ============================================================
# Usamos el endpoint "parse" que devuelve el HTML renderizado del artículo.
# Luego limpiamos el HTML con BeautifulSoup para quedarnos solo con texto.
#
# ¿Por qué no usar "extracts" (texto plano directo)?
# Porque extracts trunca el contenido y pierde estructura.
# Con "parse" obtenemos el artículo completo.

def get_article_content(title: str) -> dict | None:
    """
    Obtiene el contenido completo de un artículo.

    Usa el endpoint "parse" de MediaWiki que devuelve HTML,
    luego lo limpia a texto plano con BeautifulSoup.

    Args:
        title: Título del artículo

    Returns:
        Dict con title, text, categories, word_count, o None si falla
    """
    params = {
        "action": "parse",
        "page": title,
        "prop": "text|categories",
        "format": "json",
        "disabletoc": "true",      # No queremos la tabla de contenidos
        "disableeditsection": "true",  # No queremos los links de [edit]
    }

    try:
        resp = requests.get(WIKI_API, params=params, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, json.JSONDecodeError) as e:
        log.warning(f"Error obteniendo '{title}': {e}")
        return None

    # La API puede devolver error si la página no existe o es redirect
    if "error" in data:
        log.debug(f"API error para '{title}': {data['error'].get('info', 'unknown')}")
        return None

    parse_data = data.get("parse", {})

    # --- Extraer HTML y limpiarlo ---
    html = parse_data.get("text", {}).get("*", "")
    text = clean_html(html)

    # --- Extraer categorías ---
    categories = [
        cat["*"] for cat in parse_data.get("categories", [])
        if not cat.get("hidden")  # Ignorar categorías ocultas (de mantenimiento)
    ]

    word_count = len(text.split())

    return {
        "title": title,
        "text": text,
        "categories": categories,
        "word_count": word_count,
        "scraped_at": datetime.now().isoformat(),
    }


def clean_html(html: str) -> str:
    """
    Convierte HTML del wiki a texto plano limpio.

    Proceso:
    1. Parsear HTML con BeautifulSoup
    2. Eliminar elementos que no aportan contenido textual
       (tablas de navegación, infoboxes, scripts, estilos)
    3. Extraer texto plano
    4. Limpiar whitespace

    Args:
        html: HTML crudo del artículo

    Returns:
        Texto plano limpio
    """
    soup = BeautifulSoup(html, "lxml")

    # Eliminar elementos que no son contenido útil para entrenamiento
    for element in soup.find_all([
        "script", "style",          # Código
        "sup",                       # Notas al pie / referencias
        "table",                     # Tablas (se procesan aparte en crafteos.py)
    ]):
        element.decompose()

    # Eliminar elementos por clase CSS (navegación, avisos, etc.)
    for class_name in [
        "navbox",           # Cajas de navegación al final
        "mw-editsection",   # Links de [edit]
        "reference",        # Referencias
        "noprint",          # Elementos ocultos en impresión
        "mbox",             # Message boxes (avisos, stubs, etc.)
        "hatnote",          # "For other uses, see..."
        "toc",              # Tabla de contenidos
        "infobox",          # Infoboxes laterales
        "sidebar",          # Barras laterales
    ]:
        for el in soup.find_all(class_=class_name):
            el.decompose()

    # Extraer texto plano
    text = soup.get_text(separator="\n")

    # Limpiar whitespace excesivo
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if line:
            lines.append(line)

    return "\n".join(lines)


# ============================================================
# Paso 3: Extraer tablas de crafting (para crafteos.py)
# ============================================================

def extract_crafting_tables(html: str, title: str) -> list[dict]:
    """
    Extrae tablas de crafting del HTML de un artículo.
    Estas se guardan por separado para generar datos estructurados.

    Args:
        html: HTML crudo del artículo
        title: Título del artículo (para contexto)

    Returns:
        Lista de dicts con datos de crafting encontrados
    """
    soup = BeautifulSoup(html, "lxml")
    crafting_data = []

    # Buscar tablas con clase "wikitable" que contengan info de crafting
    for table in soup.find_all("table", class_="wikitable"):
        # Extraer texto de cada celda
        rows = []
        for tr in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if cells:
                rows.append(cells)

        if rows:
            crafting_data.append({
                "article": title,
                "table_rows": rows,
            })

    return crafting_data


# ============================================================
# Orquestación principal
# ============================================================

def load_progress(progress_file: Path) -> set[str]:
    """Carga títulos ya scrapeados (para resume)."""
    if progress_file.exists():
        return set(progress_file.read_text(encoding="utf-8").strip().split("\n"))
    return set()


def save_progress(progress_file: Path, title: str):
    """Registra un título como scrapeado."""
    with open(progress_file, "a", encoding="utf-8") as f:
        f.write(title + "\n")


def run(resume: bool = False):
    """
    Ejecuta el scraping completo.

    Args:
        resume: Si True, continúa desde donde se quedó la última vez
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    articles_file = OUTPUT_DIR / "articles.jsonl"
    crafting_file = OUTPUT_DIR / "crafting_tables.jsonl"
    progress_file = OUTPUT_DIR / ".progress"
    stubs_file = OUTPUT_DIR / "stubs.jsonl"  # Artículos cortos, para evaluar después

    # --- Obtener lista de artículos ---
    titles = get_all_page_titles()

    # --- Filtrar ya scrapeados si es resume ---
    done = load_progress(progress_file) if resume else set()
    if done:
        log.info(f"Resumiendo: {len(done)} artículos ya scrapeados, {len(titles) - len(done)} pendientes")

    # --- Stats ---
    stats = {
        "total_titles": len(titles),
        "scraped": len(done),
        "errors": 0,
        "stubs": 0,
        "total_words": 0,
    }

    # --- Abrir archivos de salida ---
    mode = "a" if resume else "w"
    with (
        open(articles_file, mode, encoding="utf-8") as f_articles,
        open(crafting_file, mode, encoding="utf-8") as f_crafting,
        open(stubs_file, mode, encoding="utf-8") as f_stubs,
    ):
        for i, title in enumerate(titles):
            if title in done:
                continue

            # Rate limiting
            time.sleep(RATE_LIMIT)

            # Obtener contenido
            article = get_article_content(title)

            if article is None:
                stats["errors"] += 1
                save_progress(progress_file, title)
                continue

            # Clasificar: stub o artículo completo
            if article["word_count"] < 100:
                # Guardar en archivo de stubs para evaluar después
                # (NO descartamos — los evaluamos en la fase de limpieza)
                f_stubs.write(json.dumps(article, ensure_ascii=False) + "\n")
                stats["stubs"] += 1
            else:
                f_articles.write(json.dumps(article, ensure_ascii=False) + "\n")
                stats["total_words"] += article["word_count"]

            # Registrar progreso
            save_progress(progress_file, title)
            stats["scraped"] += 1

            # Log periódico
            if stats["scraped"] % 100 == 0:
                log.info(
                    f"Progreso: {stats['scraped']}/{stats['total_titles']} artículos | "
                    f"{stats['total_words']:,} palabras | "
                    f"{stats['stubs']} stubs | "
                    f"{stats['errors']} errores"
                )

    # --- Reporte final ---
    log.info("=" * 60)
    log.info("SCRAPING COMPLETADO")
    log.info(f"  Artículos scrapeados: {stats['scraped']}")
    log.info(f"  Artículos completos:  {stats['scraped'] - stats['stubs'] - stats['errors']}")
    log.info(f"  Stubs (< 100 palabras): {stats['stubs']} (guardados en stubs.jsonl para revisión)")
    log.info(f"  Errores:              {stats['errors']}")
    log.info(f"  Total de palabras:    {stats['total_words']:,}")
    log.info(f"  Archivos generados:")
    log.info(f"    {articles_file}")
    log.info(f"    {stubs_file}")
    log.info(f"    {crafting_file}")
    log.info("=" * 60)

    # Guardar stats como JSON
    stats_file = OUTPUT_DIR / "scraping_stats.json"
    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scraper de minecraft.wiki")
    parser.add_argument("--resume", action="store_true", help="Continuar desde donde se quedó")
    args = parser.parse_args()

    run(resume=args.resume)
