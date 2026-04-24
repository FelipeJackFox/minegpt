"""
regex_clean.py — Limpieza de articulos y changelogs con regex (sin LLM)
========================================================================

Fase 2 del pipeline de limpieza de WIKI_DATA_CLEANING.md.

Aplica transformaciones regex en ORDEN ESPECIFICO sobre el texto de cada
registro. El orden importa: URLs antes de cleanup de puntuacion, wiki markup
antes de cite artifacts, etc.

Reglas descubiertas por los agentes de investigacion:

1. WIKI LINKS [[x]] y [[x|y]] — preservar el texto, no strippear
   - [[File:...]] → strip completo (imagen no deseada)
   - [[x|y]] → reemplazar por "y" (display text)
   - [[x]] → reemplazar por "x"

2. WIKI TEMPLATES {{...}} — strip completo (46 articulos)

3. URLS — reemplazar por "" (66 articulos tienen URLs en prosa)

4. CITE ARTIFACTS [N] — con regex PROTEGIDA:
   (?<![A-Za-z0-9_\\]])\\[(\\d+)\\](?!\\w)
   Preserva NBT paths como ArmorItems[3], Pos[1], Inventory[0]

5. NAVIGATION LINES — strip lineas que contienen ◄ o ► (2,498 articulos)

6. BOILERPLATE — strip frases de template wiki:
   - Stubs, maintenance notices, image/sound requests
   - Disambiguation boilerplate
   - Subpage headers (Java Edition block render history subpage, etc.)
   - Lost version notices
   - Naming-origin tags
   - Table artifacts (vtestone, "correct tool" legend)

7. CHANGELOG HEADERS — solo para changelogs:
   - Strip lineas "Key: value" del header tecnico
   - Strip "Other editions with a version ..." block
   - Strip "There is a guide for this update!" block
   - April Fools disambiguation notes

8. HATNOTES — KEEP (por decision de Felipe):
   - "For other uses, see X" — mantener (contexto)
   - "Not to be confused with X" — mantener
   - "Main article: X" — mantener (pero strippear /Blueprints/ noise)
   - Edition exclusivity (Java only / Bedrock only) — mantener (hechos de dominio)
   - April Fools, DLC tags, removed content — mantener

9. FINAL PASS — despues de todo lo anterior:
   - Whitespace normalization
   - Space-before-punctuation cleanup

Produce:
- articles_cleaned.jsonl
- changelogs_cleaned.jsonl
- clean_diffs.jsonl (top 100 articulos por word-loss ratio, para audit)
- clean_flagged.jsonl (articulos con >30% word-loss, requieren review)
- clean_report.json (stats agregadas, hash sha256 de inputs)

Uso:
    python -m scraper.regex_clean
    python -m scraper.regex_clean --force
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
from pathlib import Path

# ============================================================
# Configuracion
# ============================================================

OUTPUT_DIR = Path(__file__).parent.parent / "raw_data" / "wiki"

ARTICLES_IN = OUTPUT_DIR / "articles_filtered.jsonl"
CHANGELOGS_IN = OUTPUT_DIR / "changelogs_filtered.jsonl"

ARTICLES_OUT = OUTPUT_DIR / "articles_cleaned.jsonl"
CHANGELOGS_OUT = OUTPUT_DIR / "changelogs_cleaned.jsonl"

DIFFS_OUT = OUTPUT_DIR / "clean_diffs.jsonl"
FLAGGED_OUT = OUTPUT_DIR / "clean_flagged.jsonl"
REPORT_OUT = OUTPUT_DIR / "clean_report.json"

# Threshold: articulos que pierdan mas de este % de palabras son flagged
FLAG_WORD_LOSS_RATIO = 0.30

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ============================================================
# Regex compilados (para performance)
# ============================================================

# Paso 1: wiki links
RE_FILE_LINK = re.compile(r"\[\[File:[^\]]*\]\]")
RE_PIPED_LINK = re.compile(r"\[\[[^\]]*\|([^\]]+)\]\]")
RE_PLAIN_LINK = re.compile(r"\[\[([^\]]+)\]\]")

# Paso 2: wiki templates
RE_TEMPLATE = re.compile(r"\{\{[^{}]*\}\}")

# Paso 3: URLs
RE_URL = re.compile(r"https?://\S+")

# Paso 4: cite artifacts — regex PROTEGIDA contra NBT paths
# Matches [N] solo si NO esta pegado a identificador o cierre de bracket
RE_CITE = re.compile(r"(?<![A-Za-z0-9_\]])\[(\d+)\](?!\w)")

# Paso 9: espacio antes de puntuacion (final pass)
RE_SPACE_PUNCT = re.compile(r" +([.,;:!?])")
RE_MULTI_SPACE = re.compile(r"  +")
RE_MULTI_NEWLINE = re.compile(r"\n{3,}")

# Deteccion de lineas de navegacion
RE_NAV_CHARS = re.compile(r"[◄►]")

# ============================================================
# Boilerplate a strippear (frases completas con regex de linea)
# ============================================================

# Frases que aparecen como lineas enteras o al inicio de lineas y deben
# eliminarse porque son templates de mantenimiento de wiki.
# Compiladas como regex para flexibilidad con whitespace.

BOILERPLATE_PATTERNS = [
    # Stub/maintenance
    r"This template is used to categorize the article\.",
    r"This article is a stub\s*\.",
    r"This tutorial page is a stub\s*\.",
    r"This tutorial page is a work in progress\.",
    r"This article is a work in progress\.",
    r"This section is a work in progress\.",
    r"You can help by expanding it\s*\.",
    r"The talk page may contain suggestions\.",
    r"Please help expand and improve it\s*\.",
    r"Please help improve this page\.",
    r"Please expand the (section|article) to include this information\.",
    r"Further details may exist on the talk page\s*\.",
    r"This section of the article is empty\.",
    r"This section needs expansion\.",
    r"This (section|article) needs to be updated\.",
    r"Please update this (section|article) to reflect recent updates or newly available information\.",
    r"This section is missing information about:",
    r"This list is incomplete\s*;\s*you can help by expanding it\s*\.",
    r"This (article|tutorial page) needs cleanup to comply with the style guide\s*\.\s*\[\s*discuss\s*\]",
    # Image/render/sound notices
    r"This (article|section) would benefit from the addition of more images\.",
    r"Please remove this notice once you have added suitable images to the (article|section)\.",
    r"This (article|section) would benefit from the addition of isometric renders\s*\.",
    r"Please remove this notice once you have added suitable isometric renders to the (article|section)\.",
    r"This (article|section) would benefit from the addition of more sounds\.",
    r"Please remove this notice once you have added suitable sounds to the (article|section)\.",
    r"Instructions: Needs images and fill empty sections\.",
    # Subpage headers de render/texture history
    r"This article is a (Java Edition|Bedrock Edition|Legacy Console Edition) (block|item|entity|mob) (render|texture) history subpage\.",
    r"This article is a texture history subpage\.",
    r"This article is a dynamic list\s*\.",
    r"Its subject matter requires frequent updates to remain current and complete[^.]*\.",
    # Disambiguation
    r"This disambiguation page lists articles associated with the same (title|version number)\.\s*If an internal link led you here, you may wish to change the link to point directly to the intended article\.",
    r"This disambiguation page lists achievements and advancements associated with the same title\.\s*If an internal link led you here[^.]*\.",
    r"This is an index of related pages that share a common conceptual attribute\.\s*Unlike disambiguation pages[^.]*\.",
    # Lost version boilerplate
    r"This version is currently lost\.",
    r"While this version is known to exist, it has not been archived(, and is therefore considered lost| in the launcher or elsewhere, and is therefore considered lost)\s*\.",
    r"If you believe you have a copy of this version, please post it on the talk page\s*\.",
    r"This version does not have an official title\.",
    r"Please update the name if confirmed by reliable sources, such as in the launcher\s*\.",
    # Naming-origin tags (meta, no dicen nada del articulo)
    r"This topic is named from the game code\.",
    r"This topic is named based on the topic's music track and game code\.",
    r"This topic is named by the community\.",
    # Table artifacts (mis-scraped templates)
    r"correct tool, drops the block itself",
    r"correct tool, drops nothing or something other than the block itself",
    r"italicized can be instant mined",
    r"Listed difficulties are considered to be the minimum difficulty the item is obtainable on unless stated otherwise\.",
    r"Tags common to all entities see Template:Nbt inherit/entity/template",
    # Sound table headers (repetidos verbatim 400+ veces)
    r"Sounds: Sound, Closed captions, Source, Description, Identifier, Translation key, Volume, Pitch(, Attenuationdistance)?",
    # Achievement table header (529 veces)
    r"Icon, Achievement, In-game description, Actual requirements \(if different\), Gamerscore earned, Trophy type \(PS\)",
]

RE_BOILERPLATE = re.compile(
    "|".join(BOILERPLATE_PATTERNS), re.IGNORECASE
)

# Main article que apunta a blueprints — strippear estos noise references
RE_MAIN_ARTICLE_BLUEPRINT = re.compile(
    r"^Main article:\s*[^\n]*/(Structure|Blueprints)/[^\n]*$", re.MULTILINE
)

# ============================================================
# Boilerplate adicional para changelogs
# ============================================================

# Keys del header tecnico de changelogs (strip lineas Key: value)
CHANGELOG_HEADER_KEYS = [
    "Edition",
    "Release date",
    "Type",
    "Downloads",
    "Obfuscation maps",
    "Protocol version",
    "Data version",
    "Resource pack format",
    "Data pack format",
    "Minimum Java version",
    "Server version",
    "Internal version",
    "Version code",
    "Build version",
    "Cache ID",
    "Old ID",
    "Old file name",
    "Official name",
    "Snapshot for",
    "Release Candidate for",
    "Editor version",
    "Compilation date",
]

RE_CHANGELOG_HEADER = re.compile(
    r"^(" + "|".join(re.escape(k) for k in CHANGELOG_HEADER_KEYS) + r")\s*:\s*.*$",
    re.MULTILINE,
)

# "Other editions with a version X" — bloque multilinea
# Solo consume lineas siguientes que empiezan con nombres conocidos de ediciones.
# Si aparece cualquier otra cosa, el bloque termina (evita comerse el resto del changelog).
RE_OTHER_EDITIONS_BLOCK = re.compile(
    r"^Other editions with a version [^\n]*\n"
    r"(?:(?:Java Edition|Bedrock Edition|Bedrock Preview|Bedrock Editor|Pocket Edition|"
    r"Legacy Console Edition|New Nintendo 3DS Edition|Minecraft China|Minecraft Education|"
    r"Xbox One|Xbox 360|PlayStation\s*(?:3|4|Vita)|Wii U|Nintendo Switch|PS3|PS4|PS Vita)"
    r"[^\n]*\n)+",
    re.MULTILINE,
)

# "There is a guide for this update!"
RE_GUIDE_NOTICE = re.compile(
    r"^There is a guide for this update!\s*\n(?:See [^\n]+\n)?",
    re.MULTILINE,
)

# Leading disambig/April Fools
RE_APRIL_FOOLS_LEAD = re.compile(
    r"^This article (documents an April Fools' Day joke version|is about the April Fool's joke snapshot)\.[^\n]*\n",
    re.MULTILINE,
)

RE_NO_PROPER_RELEASE = re.compile(
    r"^There is no proper release version or development version[^\n]*\n",
    re.MULTILINE,
)

# Lua error lines (templates rotos)
RE_LUA_ERROR = re.compile(r"^Lua error:[^\n]*$", re.MULTILINE)

# Detector de si un registro es changelog (por title prefix o por header key)
RE_IS_CHANGELOG_TITLE = re.compile(
    r"^(Java Edition|Bedrock Edition|Pocket Edition|Legacy Console Edition)\s+[\d\w.]",
    re.IGNORECASE,
)


# ============================================================
# Pipeline de transformacion
# ============================================================


def clean_text(text: str, is_changelog: bool = False) -> str:
    """
    Aplica todas las transformaciones regex en orden.
    is_changelog activa reglas adicionales especificas de changelogs.
    """
    t = text

    # Paso 1: wiki links — preservar texto
    t = RE_FILE_LINK.sub("", t)
    t = RE_PIPED_LINK.sub(r"\1", t)
    t = RE_PLAIN_LINK.sub(r"\1", t)

    # Paso 2: wiki templates
    # Loop para templates anidados (aunque nuestra regex ya es non-greedy)
    prev = None
    while prev != t:
        prev = t
        t = RE_TEMPLATE.sub("", t)

    # Paso 3: URLs
    t = RE_URL.sub("", t)

    # Paso 4: cite artifacts (con proteccion)
    t = RE_CITE.sub("", t)

    # Paso 5: navigation lines (strip linea completa si contiene ◄ o ►)
    t = "\n".join(line for line in t.split("\n") if not RE_NAV_CHARS.search(line))

    # Paso 6: boilerplate general
    t = RE_BOILERPLATE.sub("", t)

    # Main article noise references
    t = RE_MAIN_ARTICLE_BLUEPRINT.sub("", t)

    # Paso 7: reglas especificas de changelog
    if is_changelog:
        # CHANGELOG_HEADER solo aplica a las primeras 30 lineas (zona de header tecnico).
        # Si se aplica globalmente, strippea tablas de contenido como "Old file name: X"
        # en paginas "Resource pack changes".
        lines = t.split("\n")
        header_zone = "\n".join(lines[:30])
        rest = "\n".join(lines[30:])
        header_zone = RE_CHANGELOG_HEADER.sub("", header_zone)
        t = header_zone + ("\n" + rest if rest else "")

        t = RE_OTHER_EDITIONS_BLOCK.sub("", t)
        t = RE_GUIDE_NOTICE.sub("", t)
        t = RE_APRIL_FOOLS_LEAD.sub("", t)
        t = RE_NO_PROPER_RELEASE.sub("", t)
        t = RE_LUA_ERROR.sub("", t)

    # Paso 8: final pass — whitespace y puntuacion
    # IMPORTANTE: rstrip per-line ANTES de colapsar newlines, de lo contrario
    # lineas con solo espacios introducen newlines que la segunda pasada
    # colapsaria (no-idempotente).
    t = "\n".join(line.rstrip() for line in t.split("\n"))
    t = RE_SPACE_PUNCT.sub(r"\1", t)
    t = RE_MULTI_SPACE.sub(" ", t)
    t = RE_MULTI_NEWLINE.sub("\n\n", t)
    t = t.strip()

    return t


def word_count(text: str) -> int:
    """Conteo simple de palabras (whitespace-split)."""
    return len(text.split())


def is_changelog(record: dict) -> bool:
    """
    Detecta si un registro es changelog por:
    1. Prefijo del titulo (Java/Bedrock/Pocket/Legacy Console Edition + version)
    2. Presencia de "Protocol version:" en los primeros 1000 chars del texto
    """
    title = record.get("title", "")
    if RE_IS_CHANGELOG_TITLE.match(title):
        return True
    text = record.get("text", "")
    if "Protocol version:" in text[:1000]:
        return True
    return False


# ============================================================
# I/O helpers
# ============================================================


def iter_jsonl(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def sha256_file(path: Path) -> str:
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
    output_path: Path,
    force_changelog: bool,
    label: str,
) -> dict:
    """
    Procesa un jsonl aplicando clean_text a cada registro.
    Devuelve stats incluyendo lista de diffs ordenada por word-loss ratio.
    """
    total_in_words = 0
    total_out_words = 0
    processed = 0
    diffs: list[dict] = []
    flagged: list[dict] = []
    empty_after: list[dict] = []

    with open(output_path, "w", encoding="utf-8") as out_f:
        for rec in iter_jsonl(input_path):
            original = rec.get("text", "")
            wc_in = word_count(original)

            use_changelog_rules = force_changelog or is_changelog(rec)
            cleaned = clean_text(original, is_changelog=use_changelog_rules)
            wc_out = word_count(cleaned)

            total_in_words += wc_in
            total_out_words += wc_out
            processed += 1

            # Track diffs
            loss = wc_in - wc_out
            loss_ratio = loss / wc_in if wc_in > 0 else 0.0

            # Actualizar el registro
            new_rec = {**rec, "text": cleaned, "word_count": wc_out}
            out_f.write(json.dumps(new_rec, ensure_ascii=False) + "\n")

            # Diff data para audit
            diff_info = {
                "title": rec.get("title", ""),
                "words_before": wc_in,
                "words_after": wc_out,
                "loss": loss,
                "loss_ratio": round(loss_ratio, 4),
            }
            diffs.append(diff_info)

            if loss_ratio > FLAG_WORD_LOSS_RATIO and wc_in >= 50:
                flagged.append(
                    {
                        **diff_info,
                        "text_before_head": original[:300],
                        "text_after_head": cleaned[:300],
                    }
                )

            if wc_out == 0 and wc_in > 0:
                empty_after.append(diff_info)

    # Top 100 diffs por loss ratio
    diffs_sorted = sorted(diffs, key=lambda d: d["loss_ratio"], reverse=True)[:100]

    stats = {
        "label": label,
        "processed": processed,
        "words_in": total_in_words,
        "words_out": total_out_words,
        "words_lost": total_in_words - total_out_words,
        "pct_loss": round(
            (total_in_words - total_out_words) / total_in_words * 100, 2
        )
        if total_in_words > 0
        else 0.0,
        "flagged_count": len(flagged),
        "empty_after_count": len(empty_after),
        "top_diffs_sample": diffs_sorted[:10],
    }

    log.info("=" * 60)
    log.info(f"{label.upper()} LIMPIEZA COMPLETADA")
    log.info(f"  Procesados:      {stats['processed']:>7}")
    log.info(f"  Words in:        {stats['words_in']:>10,}")
    log.info(f"  Words out:       {stats['words_out']:>10,}")
    log.info(
        f"  Lost:            {stats['words_lost']:>10,} ({stats['pct_loss']}%)"
    )
    log.info(f"  Flagged (>30%):  {stats['flagged_count']:>7}")
    log.info(f"  Empty after:     {stats['empty_after_count']:>7}")
    log.info("=" * 60)

    return {**stats, "diffs": diffs_sorted, "flagged": flagged}


def verify_idempotence(output_path: Path, is_changelog_file: bool) -> bool:
    """
    Verifica que aplicar clean_text sobre el output NO cambie nada.
    Sample 20 registros al azar.
    """
    import random

    random.seed(42)

    with open(output_path, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]

    samples = random.sample(records, min(20, len(records)))
    differences = 0
    for rec in samples:
        original = rec.get("text", "")
        re_cleaned = clean_text(original, is_changelog=is_changelog_file)
        if re_cleaned != original:
            differences += 1

    if differences > 0:
        log.warning(
            f"Idempotence check FALLO en {differences}/{len(samples)} registros de {output_path.name}"
        )
        return False
    log.info(f"Idempotence check OK para {output_path.name}")
    return True


def run(force: bool = False) -> None:
    # Inputs
    if not ARTICLES_IN.exists():
        log.error(f"Input no encontrado: {ARTICLES_IN}. Correr filter.py primero.")
        sys.exit(1)
    if not CHANGELOGS_IN.exists():
        log.error(f"Input no encontrado: {CHANGELOGS_IN}. Correr filter.py primero.")
        sys.exit(1)

    # Outputs check
    outputs = [ARTICLES_OUT, CHANGELOGS_OUT, DIFFS_OUT, FLAGGED_OUT, REPORT_OUT]
    existing = [p for p in outputs if p.exists()]
    if existing and not force:
        log.error(
            f"Outputs ya existen: {[p.name for p in existing]}. Usar --force para sobreescribir."
        )
        sys.exit(1)

    # Hash inputs
    log.info("Calculando sha256 de inputs...")
    articles_hash = sha256_file(ARTICLES_IN)
    changelogs_hash = sha256_file(CHANGELOGS_IN)
    log.info(f"  articles_filtered.jsonl:   {articles_hash[:16]}...")
    log.info(f"  changelogs_filtered.jsonl: {changelogs_hash[:16]}...")

    # Procesar articles (detecta changelogs individualmente por si hay alguno mezclado)
    log.info("Procesando articles...")
    articles_stats = process(
        ARTICLES_IN, ARTICLES_OUT, force_changelog=False, label="articles"
    )

    # Procesar changelogs (todos con reglas de changelog)
    log.info("Procesando changelogs...")
    changelogs_stats = process(
        CHANGELOGS_IN, CHANGELOGS_OUT, force_changelog=True, label="changelogs"
    )

    # Idempotence checks
    log.info("Verificando idempotencia...")
    idem_articles = verify_idempotence(ARTICLES_OUT, is_changelog_file=False)
    idem_changelogs = verify_idempotence(CHANGELOGS_OUT, is_changelog_file=True)

    # Audit files
    with open(DIFFS_OUT, "w", encoding="utf-8") as f:
        for d in articles_stats["diffs"] + changelogs_stats["diffs"]:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    with open(FLAGGED_OUT, "w", encoding="utf-8") as f:
        for d in articles_stats["flagged"] + changelogs_stats["flagged"]:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    # Report (sin los blobs gigantes)
    report = {
        "input_hashes": {
            "articles_filtered.jsonl": articles_hash,
            "changelogs_filtered.jsonl": changelogs_hash,
        },
        "articles": {
            k: v for k, v in articles_stats.items() if k not in ("diffs", "flagged")
        },
        "changelogs": {
            k: v for k, v in changelogs_stats.items() if k not in ("diffs", "flagged")
        },
        "idempotence": {
            "articles_ok": idem_articles,
            "changelogs_ok": idem_changelogs,
        },
    }
    with open(REPORT_OUT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    log.info(f"Reporte guardado en {REPORT_OUT}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Limpia articulos y changelogs con regex."
    )
    parser.add_argument(
        "--force", action="store_true", help="Sobreescribe outputs existentes."
    )
    args = parser.parse_args()
    run(force=args.force)
