"""
clean.py — Limpieza y deduplicación de datos scrapeados
=========================================================

Este script toma los datos crudos (wiki + reddit) y los limpia para
entrenamiento. La filosofía es: EVALUAR antes de descartar.

PROCESO:
1. Normalizar unicode y whitespace
2. Deduplicar textos similares con MinHash (LSH)
3. Analizar artículos cortos (stubs) y decidir qué hacer con ellos
4. Analizar contenido con muchos caracteres especiales
5. Generar reporte detallado de qué se descartó y por qué

¿QUÉ ES MINHASH?
MinHash es un algoritmo para estimar la similitud entre textos sin
compararlos todos contra todos (que sería O(n²) y muy lento).

Funciona así:
1. Cada texto se convierte en un conjunto de "shingles" (n-gramas de palabras)
2. Se aplican funciones hash al conjunto para crear una "firma" compacta
3. Textos con firmas similares probablemente tienen contenido similar
4. Con LSH (Locality-Sensitive Hashing) agrupamos textos similares eficientemente

Esto es clave porque el wiki de Minecraft repite mucho texto entre artículos
(ej: "Creeper" y "List of Mobs" pueden compartir párrafos enteros).

Uso:
    python -m scraper.clean
    python -m scraper.clean --report-only    # Solo genera reporte, no limpia
"""

import json
import re
import unicodedata
import logging
import argparse
from pathlib import Path
from collections import Counter

from datasketch import MinHash, MinHashLSH

# ============================================================
# Configuración
# ============================================================

RAW_DIR = Path(__file__).parent.parent / "raw_data"
CLEAN_DIR = Path(__file__).parent.parent / "processed_data"

# MinHash: umbral de similitud para considerar duplicados
# 0.8 = 80% similar → probablemente contenido repetido
SIMILARITY_THRESHOLD = 0.8
NUM_PERM = 128  # Número de permutaciones para MinHash (más = más preciso pero más lento)

# Umbrales para análisis (NO para eliminación automática)
SPECIAL_CHAR_THRESHOLD = 0.30  # 30% caracteres especiales → revisar

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ============================================================
# Normalización de texto
# ============================================================

def normalize_text(text: str) -> str:
    """
    Normaliza texto para consistencia.

    - Unicode NFC (forma canónica compuesta)
    - Reemplaza múltiples espacios/newlines por uno solo
    - Strip de whitespace al inicio y final

    NO elimina contenido — solo normaliza formato.
    """
    # Normalizar unicode (ej: é como un solo codepoint, no e + acento)
    text = unicodedata.normalize("NFC", text)

    # Colapsar whitespace múltiple
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


# ============================================================
# Deduplicación con MinHash
# ============================================================

def create_minhash(text: str, num_perm: int = NUM_PERM) -> MinHash:
    """
    Crea un MinHash para un texto.

    Proceso:
    1. Dividir en "shingles" (trigramas de palabras)
       Ej: "the quick brown fox" → {"the quick brown", "quick brown fox"}
    2. Aplicar hash a cada shingle
    3. El MinHash resultante es una firma compacta del texto

    Args:
        text: Texto a hashear
        num_perm: Número de permutaciones (mayor = más preciso)

    Returns:
        Objeto MinHash
    """
    m = MinHash(num_perm=num_perm)

    # Crear shingles (trigramas de palabras)
    words = text.lower().split()
    for i in range(len(words) - 2):
        shingle = " ".join(words[i:i + 3])
        m.update(shingle.encode("utf-8"))

    return m


def deduplicate(articles: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Elimina artículos duplicados o casi-duplicados usando MinHash LSH.

    Returns:
        (artículos_únicos, artículos_duplicados)
    """
    log.info(f"Deduplicando {len(articles)} artículos (threshold={SIMILARITY_THRESHOLD})...")

    # Crear índice LSH
    lsh = MinHashLSH(threshold=SIMILARITY_THRESHOLD, num_perm=NUM_PERM)

    unique = []
    duplicates = []

    for i, article in enumerate(articles):
        text = article.get("text", "")
        if len(text.split()) < 10:  # Muy corto para deduplicar
            unique.append(article)
            continue

        mh = create_minhash(text)
        key = f"doc_{i}"

        # ¿Hay algún documento similar ya en el índice?
        result = lsh.query(mh)

        if result:
            # Este texto es similar a algo que ya tenemos
            duplicates.append({
                **article,
                "_duplicate_of": result[0],  # Referencia al original
            })
        else:
            # Texto nuevo, agregarlo al índice
            lsh.insert(key, mh)
            unique.append(article)

        if (i + 1) % 1000 == 0:
            log.info(f"  Procesados {i + 1}/{len(articles)} | Únicos: {len(unique)} | Duplicados: {len(duplicates)}")

    log.info(f"Deduplicación completa: {len(unique)} únicos, {len(duplicates)} duplicados")
    return unique, duplicates


# ============================================================
# Análisis de contenido problemático
# ============================================================

def analyze_special_chars(text: str) -> float:
    """
    Calcula el porcentaje de caracteres especiales en un texto.

    Caracteres "normales": letras, números, espacios, puntuación básica.
    Caracteres "especiales": todo lo demás (símbolos, unicode raro, etc.)

    Returns:
        Ratio de caracteres especiales (0.0 a 1.0)
    """
    if not text:
        return 0.0

    normal_chars = sum(1 for c in text if c.isalnum() or c.isspace() or c in ".,;:!?'-\"()")
    return 1.0 - (normal_chars / len(text))


def analyze_content(articles: list[dict]) -> dict:
    """
    Genera un análisis detallado del corpus para tomar decisiones informadas.

    NO elimina nada — solo reporta.

    Returns:
        Dict con categorías de contenido y sus estadísticas
    """
    report = {
        "total": len(articles),
        "by_word_count": Counter(),
        "high_special_chars": [],
        "short_articles": [],
        "categories": Counter(),
        "total_words": 0,
    }

    for article in articles:
        text = article.get("text", "")
        word_count = len(text.split())
        title = article.get("title", "unknown")

        report["total_words"] += word_count

        # Distribución por longitud
        if word_count < 50:
            report["by_word_count"]["<50 palabras"] += 1
        elif word_count < 100:
            report["by_word_count"]["50-100 palabras"] += 1
        elif word_count < 500:
            report["by_word_count"]["100-500 palabras"] += 1
        elif word_count < 2000:
            report["by_word_count"]["500-2000 palabras"] += 1
        else:
            report["by_word_count"][">2000 palabras"] += 1

        # Artículos con muchos caracteres especiales
        special_ratio = analyze_special_chars(text)
        if special_ratio > SPECIAL_CHAR_THRESHOLD:
            report["high_special_chars"].append({
                "title": title,
                "special_ratio": round(special_ratio, 3),
                "word_count": word_count,
                "preview": text[:200],  # Primeros 200 chars para evaluar
            })

        # Artículos cortos
        if word_count < 100:
            report["short_articles"].append({
                "title": title,
                "word_count": word_count,
                "preview": text[:200],
            })

        # Categorías
        for cat in article.get("categories", []):
            report["categories"][cat] += 1

    return report


# ============================================================
# Pipeline principal
# ============================================================

def load_jsonl(filepath: Path) -> list[dict]:
    """Carga un archivo JSONL."""
    if not filepath.exists():
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def save_jsonl(articles: list[dict], filepath: Path):
    """Guarda artículos en JSONL."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        for article in articles:
            f.write(json.dumps(article, ensure_ascii=False) + "\n")


def run(report_only: bool = False):
    """Ejecuta el pipeline de limpieza."""

    # --- Cargar datos crudos ---
    wiki_articles = load_jsonl(RAW_DIR / "wiki" / "articles.jsonl")
    wiki_stubs = load_jsonl(RAW_DIR / "wiki" / "stubs.jsonl")
    reddit_posts = load_jsonl(RAW_DIR / "reddit" / "posts.jsonl")
    reddit_comments = load_jsonl(RAW_DIR / "reddit" / "comments.jsonl")

    log.info(f"Datos cargados:")
    log.info(f"  Wiki artículos: {len(wiki_articles)}")
    log.info(f"  Wiki stubs: {len(wiki_stubs)}")
    log.info(f"  Reddit posts: {len(reddit_posts)}")
    log.info(f"  Reddit comentarios: {len(reddit_comments)}")

    # --- Paso 1: Normalizar texto ---
    log.info("Normalizando texto...")
    for article in wiki_articles + wiki_stubs:
        article["text"] = normalize_text(article.get("text", ""))
    for post in reddit_posts:
        post["text"] = normalize_text(post.get("text", ""))
    for comment in reddit_comments:
        comment["text"] = normalize_text(comment.get("text", ""))

    # --- Paso 2: Análisis del corpus ---
    log.info("Analizando corpus del wiki...")
    wiki_report = analyze_content(wiki_articles + wiki_stubs)

    log.info("=" * 60)
    log.info("REPORTE DE ANÁLISIS DEL WIKI")
    log.info(f"  Total artículos: {wiki_report['total']}")
    log.info(f"  Total palabras: {wiki_report['total_words']:,}")
    log.info(f"  Distribución por longitud:")
    for bucket, count in sorted(wiki_report["by_word_count"].items()):
        log.info(f"    {bucket}: {count}")
    log.info(f"  Artículos con >30% chars especiales: {len(wiki_report['high_special_chars'])}")
    if wiki_report["high_special_chars"][:5]:
        log.info(f"  Ejemplos (primeros 5):")
        for item in wiki_report["high_special_chars"][:5]:
            log.info(f"    '{item['title']}' — {item['special_ratio']*100:.1f}% especiales, {item['word_count']} palabras")
            log.info(f"      Preview: {item['preview'][:100]}...")
    log.info(f"  Top 10 categorías:")
    for cat, count in wiki_report["categories"].most_common(10):
        log.info(f"    {cat}: {count}")
    log.info("=" * 60)

    # Guardar reporte completo
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    report_file = CLEAN_DIR / "analysis_report.json"
    # Convertir Counters a dicts para JSON
    wiki_report["by_word_count"] = dict(wiki_report["by_word_count"])
    wiki_report["categories"] = dict(wiki_report["categories"].most_common(50))
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(wiki_report, f, indent=2, ensure_ascii=False)
    log.info(f"Reporte guardado en {report_file}")

    if report_only:
        log.info("Modo --report-only: no se realizaron cambios.")
        return

    # --- Paso 3: Deduplicar wiki ---
    unique_wiki, duplicated_wiki = deduplicate(wiki_articles)

    # Guardar duplicados para revisión
    save_jsonl(duplicated_wiki, CLEAN_DIR / "wiki_duplicates.jsonl")

    # --- Paso 4: Deduplicar Reddit ---
    # Combinar posts y comentarios como textos individuales
    reddit_all = []
    for post in reddit_posts:
        reddit_all.append({"text": f"{post['title']}\n{post['text']}", "source": "post", **post})
    for comment in reddit_comments:
        reddit_all.append({"text": comment["text"], "source": "comment", **comment})

    unique_reddit, duplicated_reddit = deduplicate(reddit_all)

    # --- Paso 5: Guardar datos limpios ---
    save_jsonl(unique_wiki, CLEAN_DIR / "wiki_clean.jsonl")
    save_jsonl(wiki_stubs, CLEAN_DIR / "wiki_stubs_for_review.jsonl")  # Stubs sin tocar, para decisión manual
    save_jsonl(unique_reddit, CLEAN_DIR / "reddit_clean.jsonl")

    # --- Reporte final ---
    log.info("=" * 60)
    log.info("LIMPIEZA COMPLETADA")
    log.info(f"  Wiki: {len(wiki_articles)} → {len(unique_wiki)} (removidos {len(duplicated_wiki)} duplicados)")
    log.info(f"  Wiki stubs: {len(wiki_stubs)} guardados para revisión manual")
    log.info(f"  Reddit: {len(reddit_all)} → {len(unique_reddit)} (removidos {len(duplicated_reddit)} duplicados)")
    log.info(f"  Archivos en {CLEAN_DIR}/:")
    log.info(f"    wiki_clean.jsonl — artículos limpios y deduplicados")
    log.info(f"    wiki_stubs_for_review.jsonl — artículos cortos para evaluar")
    log.info(f"    wiki_duplicates.jsonl — duplicados removidos (para auditoría)")
    log.info(f"    reddit_clean.jsonl — posts+comentarios limpios")
    log.info(f"    analysis_report.json — reporte detallado del corpus")
    log.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Limpieza de datos para MineGPT")
    parser.add_argument("--report-only", action="store_true", help="Solo genera reporte, no limpia")
    args = parser.parse_args()

    run(report_only=args.report_only)
