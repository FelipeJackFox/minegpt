"""
filter.py — Filtro de articulos y changelogs por reglas de titulo/metadata
===========================================================================

Fase 1 del pipeline de limpieza de WIKI_DATA_CLEANING.md.

Aplica reglas sobre title, categories y word_count para descartar articulos
que no aportan valor a un LM entrenado desde cero:

- Render/texture/asset history (metadatos de versiones visuales)
- Debug mode (listas de 29,873 block states = ruido)
- Empty/tiny (<10 palabras)
- Paginas meta de la wiki (Category:, User:, Template:, Minecraft Wiki:)
- Blueprints y renders de estructuras
- Disambiguations de solo numeros de version

Produce:
- articles_filtered.jsonl  → articulos conservados
- articles_removed.jsonl   → articulos descartados con campo "removal_reason"
- changelogs_filtered.jsonl → changelogs conservados
- changelogs_removed.jsonl  → changelogs descartados
- filter_report.json       → stats + hash sha256 de inputs

No sobreescribe outputs: aborta si existen (usar --force para forzar).

Uso:
    python -m scraper.filter
    python -m scraper.filter --force
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
from collections import Counter
from pathlib import Path

# ============================================================
# Configuracion
# ============================================================

OUTPUT_DIR = Path(__file__).parent.parent / "raw_data" / "wiki"

ARTICLES_IN = OUTPUT_DIR / "articles.jsonl"
CHANGELOGS_IN = OUTPUT_DIR / "changelogs.jsonl"

ARTICLES_KEEP = OUTPUT_DIR / "articles_filtered.jsonl"
ARTICLES_DROP = OUTPUT_DIR / "articles_removed.jsonl"
CHANGELOGS_KEEP = OUTPUT_DIR / "changelogs_filtered.jsonl"
CHANGELOGS_DROP = OUTPUT_DIR / "changelogs_removed.jsonl"
REPORT = OUTPUT_DIR / "filter_report.json"

# Regex para detectar titles de disambiguation que son puramente versiones
# Matches: "0.0", "0.30", "1.22", "20100617", "0.31_01", "a1.0", "b1.5"
# NO matches: "Level.dat", "Function", "API", "Beta 1.9 Prerelease (disambiguation)"
VERSION_ONLY_RE = re.compile(
    r"^(\d+(\.\d+)+[a-z0-9_\-]*|\d{6,8}|0\.\d+[a-z0-9_\-]*|[ab]\d[\d.a-z_\-]*)$",
    re.IGNORECASE,
)

# Deteccion de texto que indica que un articulo es disambiguation
DISAMBIG_MARKERS = (
    "This disambiguation page lists articles associated with the same title",
    "This disambiguation page lists articles associated with the same version number",
    "This disambiguation page lists achievements and advancements",
    "This is an index of related pages",
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ============================================================
# Reglas de filtrado
# ============================================================


def classify_article(article: dict) -> str | None:
    """
    Devuelve la razon de descarte si el articulo debe eliminarse, o None para
    mantenerlo. Retornar la razon permite auditar despues.
    """
    title = article.get("title", "")
    wc = article.get("word_count", 0)
    text = article.get("text", "")

    title_lower = title.lower()

    # Palabras muy cortas (sin contenido util)
    if wc < 10:
        return "empty_or_tiny"

    # Meta-pages de la wiki
    if title.startswith("Category:"):
        return "category_page"
    if title.startswith("User:"):
        return "user_page"
    if title.startswith("Template:"):
        return "template_page"
    if title.startswith("Minecraft Wiki:"):
        return "meta_wiki_page"

    # Historia de assets/textures/renders (metadata sin contenido narrativo)
    if "render history" in title_lower:
        return "render_history"
    if "texture history" in title_lower:
        return "texture_history"
    if title.endswith("/Asset history"):
        return "asset_history"

    # Debug mode (listas gigantes de block states)
    if title.startswith("Debug mode"):
        return "debug_mode"

    # Blueprints y renders de estructuras
    if "/Structure/" in title:
        return "structure_blueprint"
    if title.endswith("/Renders"):
        return "structure_renders"
    if "/development gallery/" in title:
        return "development_gallery"

    # Disambiguations de solo version number
    # Solo aplicar si realmente es disambiguation (no otras paginas con titulo numerico)
    if is_disambiguation(text) and VERSION_ONLY_RE.match(title):
        return "version_disambiguation"

    return None


def classify_changelog(changelog: dict) -> str | None:
    """
    Reglas de descarte para changelogs. Son menos estrictas que articles:
    solo descartamos los obviamente vacios o rotos.
    """
    wc = changelog.get("word_count", 0)
    text = changelog.get("text", "")

    if wc < 30:
        return "empty_or_tiny"

    # Changelogs con errores de Lua (templates rotos en la wiki)
    if text.strip().startswith("Lua error:"):
        return "lua_error"

    return None


def is_disambiguation(text: str) -> bool:
    """Detecta si un articulo es una pagina de disambiguation por marker en texto."""
    head = text[:500]
    return any(marker in head for marker in DISAMBIG_MARKERS)


# ============================================================
# I/O helpers
# ============================================================


def iter_jsonl(path: Path):
    """Generator que yield-ea un dict por cada linea del archivo JSONL."""
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def write_jsonl(path: Path, records):
    """Escribe lista/generator de dicts a JSONL (ensure_ascii=False para unicode)."""
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def sha256_file(path: Path) -> str:
    """Calcula sha256 de un archivo para audit trail."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# ============================================================
# Orchestrator
# ============================================================


def process(
    input_path: Path,
    keep_path: Path,
    drop_path: Path,
    classifier,
    label: str,
) -> dict:
    """Aplica classifier a cada registro y escribe outputs. Devuelve stats."""
    kept: list[dict] = []
    dropped: list[dict] = []
    reasons: Counter = Counter()

    total_words_in = 0
    total_words_kept = 0

    for rec in iter_jsonl(input_path):
        wc = rec.get("word_count", 0)
        total_words_in += wc

        reason = classifier(rec)
        if reason is None:
            kept.append(rec)
            total_words_kept += wc
        else:
            rec_with_reason = {**rec, "removal_reason": reason}
            dropped.append(rec_with_reason)
            reasons[reason] += 1

    write_jsonl(keep_path, kept)
    write_jsonl(drop_path, dropped)

    stats = {
        "label": label,
        "total_input": len(kept) + len(dropped),
        "kept": len(kept),
        "dropped": len(dropped),
        "total_words_in": total_words_in,
        "total_words_kept": total_words_kept,
        "total_words_dropped": total_words_in - total_words_kept,
        "reasons": dict(reasons.most_common()),
    }

    log.info("=" * 60)
    log.info(f"{label.upper()} FILTRO COMPLETADO")
    log.info(f"  Input:           {stats['total_input']:>7}")
    log.info(f"  Kept:            {stats['kept']:>7}")
    log.info(f"  Dropped:         {stats['dropped']:>7}")
    log.info(f"  Words in:        {stats['total_words_in']:>10,}")
    log.info(f"  Words kept:      {stats['total_words_kept']:>10,}")
    log.info(f"  Words dropped:   {stats['total_words_dropped']:>10,}")
    log.info(f"  Razones:")
    for reason, count in reasons.most_common():
        log.info(f"    {reason:30s} {count:>6}")
    log.info("=" * 60)

    return stats


def run(force: bool = False) -> None:
    # Verificar inputs
    if not ARTICLES_IN.exists():
        log.error(f"Input no encontrado: {ARTICLES_IN}")
        sys.exit(1)
    if not CHANGELOGS_IN.exists():
        log.error(f"Input no encontrado: {CHANGELOGS_IN}")
        sys.exit(1)

    # Verificar si outputs ya existen
    outputs = [ARTICLES_KEEP, ARTICLES_DROP, CHANGELOGS_KEEP, CHANGELOGS_DROP, REPORT]
    existing = [p for p in outputs if p.exists()]
    if existing and not force:
        log.error(
            f"Outputs ya existen: {[p.name for p in existing]}. Usar --force para sobreescribir."
        )
        sys.exit(1)

    # Hash de inputs (audit trail)
    log.info("Calculando sha256 de inputs...")
    articles_hash = sha256_file(ARTICLES_IN)
    changelogs_hash = sha256_file(CHANGELOGS_IN)
    log.info(f"  articles.jsonl:   {articles_hash[:16]}...")
    log.info(f"  changelogs.jsonl: {changelogs_hash[:16]}...")

    # Procesar articles
    log.info("Procesando articles...")
    articles_stats = process(
        ARTICLES_IN, ARTICLES_KEEP, ARTICLES_DROP, classify_article, "articles"
    )

    # Procesar changelogs
    log.info("Procesando changelogs...")
    changelogs_stats = process(
        CHANGELOGS_IN,
        CHANGELOGS_KEEP,
        CHANGELOGS_DROP,
        classify_changelog,
        "changelogs",
    )

    # Guardar reporte
    report = {
        "input_hashes": {
            "articles.jsonl": articles_hash,
            "changelogs.jsonl": changelogs_hash,
        },
        "articles": articles_stats,
        "changelogs": changelogs_stats,
    }
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    log.info(f"Reporte guardado en {REPORT}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Filtra articulos y changelogs por reglas.")
    parser.add_argument(
        "--force", action="store_true", help="Sobreescribe outputs existentes."
    )
    args = parser.parse_args()
    run(force=args.force)
