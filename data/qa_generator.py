"""
qa_generator.py — Generación de Q&A sintético para instruction tuning
=======================================================================

Este script genera pares pregunta→respuesta a partir del corpus del wiki.
Hay dos modos:

1. HEURÍSTICO (gratis, calidad media):
   Usa reglas simples para convertir artículos en Q&A.
   Ej: Título "Creeper" + primer párrafo → "What is a Creeper in Minecraft?"

2. IA SOTA (costo de API, alta calidad):
   Envía artículos a Claude/GPT-4 para generar Q&A de calidad profesional.
   Esto es EXACTAMENTE lo que hacen los laboratorios grandes: usan modelos
   enormes para generar datos de entrenamiento para modelos pequeños.
   Se llama "knowledge distillation" o "synthetic data generation".

¿POR QUÉ GENERAR Q&A?
Sin Q&A: el modelo aprende a completar texto ("A Creeper is a...")
Con Q&A: el modelo aprende a RESPONDER ("Q: What is a Creeper? A: A Creeper is...")

La diferencia es enorme en usabilidad. Un modelo entrenado solo con texto plano
no sabe qué hacer cuando le preguntas algo — solo continúa el texto.

Uso:
    python -m data.qa_generator                     # Modo heurístico
    python -m data.qa_generator --mode ai           # Modo IA SOTA
    python -m data.qa_generator --mode ai --limit 100  # Solo 100 artículos con IA
"""

import json
import logging
import argparse
import re
from pathlib import Path

PROCESSED_DIR = Path(__file__).parent.parent / "processed_data"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ============================================================
# Modo 1: Heurístico (gratis)
# ============================================================

# Templates de preguntas basadas en categorías comunes del wiki
QUESTION_TEMPLATES = [
    "What is {title} in Minecraft?",
    "Tell me about {title} in Minecraft.",
    "Explain {title} in the context of Minecraft.",
    "How does {title} work in Minecraft?",
    "Describe {title} from Minecraft.",
]

SPECIFIC_TEMPLATES = {
    # Si el artículo menciona ciertas keywords, usar preguntas más específicas
    "craft": "How do I craft {title} in Minecraft?",
    "spawn": "Where does {title} spawn in Minecraft?",
    "drop": "What does {title} drop in Minecraft?",
    "damage": "How much damage does {title} do in Minecraft?",
    "biome": "In which biome can I find {title} in Minecraft?",
    "breed": "How do I breed {title} in Minecraft?",
    "tame": "How do I tame {title} in Minecraft?",
    "enchant": "What enchantments can be applied to {title} in Minecraft?",
    "smelt": "How do I smelt {title} in Minecraft?",
    "potion": "How do I brew {title} in Minecraft?",
}


def generate_heuristic_qa(articles: list[dict]) -> list[dict]:
    """
    Genera Q&A usando reglas heurísticas.

    Para cada artículo:
    1. El título se convierte en la pregunta
    2. El primer párrafo sustancial se convierte en la respuesta
    3. Si el texto menciona keywords específicas, se generan preguntas adicionales

    Args:
        articles: Lista de artículos del wiki (con title y text)

    Returns:
        Lista de pares {instruction, input, output}
    """
    qa_pairs = []

    for article in articles:
        title = article.get("title", "")
        text = article.get("text", "")

        if not title or not text:
            continue

        # Dividir en párrafos y tomar los sustanciales
        paragraphs = [p.strip() for p in text.split("\n") if len(p.strip()) > 50]

        if not paragraphs:
            continue

        # --- Q&A general (primer párrafo como respuesta) ---
        first_para = paragraphs[0]

        # Pregunta general
        qa_pairs.append({
            "instruction": f"What is {title} in Minecraft?",
            "input": "",
            "output": first_para,
            "source": "heuristic_qa",
        })

        # Si hay suficiente contenido, generar "Tell me about..."
        if len(paragraphs) > 1:
            combined = "\n".join(paragraphs[:3])  # Primeros 3 párrafos
            qa_pairs.append({
                "instruction": f"Tell me everything about {title} in Minecraft.",
                "input": "",
                "output": combined,
                "source": "heuristic_qa",
            })

        # --- Q&A específicas basadas en keywords ---
        text_lower = text.lower()
        for keyword, template in SPECIFIC_TEMPLATES.items():
            if keyword in text_lower:
                # Buscar el párrafo más relevante
                relevant_paras = [p for p in paragraphs if keyword in p.lower()]
                if relevant_paras:
                    qa_pairs.append({
                        "instruction": template.format(title=title),
                        "input": "",
                        "output": relevant_paras[0],
                        "source": "heuristic_qa",
                    })

    return qa_pairs


# ============================================================
# Modo 2: IA SOTA (Claude/GPT-4)
# ============================================================

def generate_ai_qa(articles: list[dict], limit: int = 100) -> list[dict]:
    """
    Genera Q&A usando una IA SOTA (Claude API).

    Este es el mismo approach que usan OpenAI, Anthropic, y otros labs:
    - Toman texto de alta calidad
    - Lo pasan a un modelo grande para generar datos de entrenamiento
    - Usan esos datos para entrenar modelos más pequeños

    Se llama "knowledge distillation" cuando el modelo grande "enseña"
    al modelo pequeño a través de datos generados.

    NOTA: Requiere API key de Anthropic o OpenAI configurada como
    variable de entorno (ANTHROPIC_API_KEY o OPENAI_API_KEY).

    Args:
        articles: Lista de artículos del wiki
        limit: Máximo de artículos a procesar (para controlar costos)

    Returns:
        Lista de pares {instruction, input, output}
    """
    try:
        import anthropic
        client = anthropic.Anthropic()  # Usa ANTHROPIC_API_KEY del env
        use_claude = True
    except (ImportError, Exception):
        log.warning("anthropic no instalado o no configurado. Intentando openai...")
        try:
            import openai
            client = openai.OpenAI()  # Usa OPENAI_API_KEY del env
            use_claude = False
        except (ImportError, Exception):
            log.error(
                "No se pudo conectar a ninguna API de IA. "
                "Instala 'anthropic' o 'openai' y configura la API key. "
                "Usando modo heurístico como fallback."
            )
            return generate_heuristic_qa(articles[:limit])

    qa_pairs = []
    articles_to_process = articles[:limit]

    log.info(f"Generando Q&A con IA SOTA para {len(articles_to_process)} artículos...")

    SYSTEM_PROMPT = """You are a Minecraft expert creating training data for a small language model.
Given a Minecraft wiki article, generate 3-5 diverse question-answer pairs that cover the key information.

Rules:
- Questions should be natural, like a player would ask
- Answers should be concise but complete (1-3 sentences)
- Include a mix of: factual, how-to, and comparison questions
- Only use information from the provided article
- Format as JSON array: [{"q": "...", "a": "..."}]"""

    for i, article in enumerate(articles_to_process):
        title = article.get("title", "")
        text = article.get("text", "")[:3000]  # Truncar para no exceder tokens

        user_msg = f"Article title: {title}\n\nContent:\n{text}"

        try:
            if use_claude:
                response = client.messages.create(
                    model="claude-haiku-4-5-20251001",  # Haiku es barato y suficiente
                    max_tokens=1024,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_msg}],
                )
                raw = response.content[0].text
            else:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    max_tokens=1024,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                )
                raw = response.choices[0].message.content

            # Parsear JSON de la respuesta
            # Buscar el array JSON en la respuesta
            json_match = re.search(r'\[.*\]', raw, re.DOTALL)
            if json_match:
                pairs = json.loads(json_match.group())
                for pair in pairs:
                    qa_pairs.append({
                        "instruction": pair["q"],
                        "input": "",
                        "output": pair["a"],
                        "source": "ai_generated",
                        "article": title,
                    })

        except Exception as e:
            log.warning(f"Error generando Q&A para '{title}': {e}")
            continue

        if (i + 1) % 10 == 0:
            log.info(f"  Procesados {i + 1}/{len(articles_to_process)} artículos ({len(qa_pairs)} Q&A generados)")

    return qa_pairs


# ============================================================
# Orquestación
# ============================================================

def run(mode: str = "heuristic", limit: int = 100):
    """Genera Q&A y los guarda."""
    # Cargar artículos limpios
    wiki_file = PROCESSED_DIR / "wiki_clean.jsonl"
    if not wiki_file.exists():
        log.error(f"No encontrado: {wiki_file}. Ejecuta scraper.clean primero.")
        return

    articles = []
    with open(wiki_file, "r", encoding="utf-8") as f:
        for line in f:
            articles.append(json.loads(line))

    log.info(f"Cargados {len(articles)} artículos limpios")

    # Generar Q&A
    if mode == "ai":
        qa_pairs = generate_ai_qa(articles, limit=limit)
    else:
        qa_pairs = generate_heuristic_qa(articles)

    # Guardar
    output_file = PROCESSED_DIR / f"minecraft_qa_{mode}.jsonl"
    with open(output_file, "w", encoding="utf-8") as f:
        for pair in qa_pairs:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")

    log.info(f"Generados {len(qa_pairs)} pares Q&A ({mode}) → {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generador de Q&A para MineGPT")
    parser.add_argument("--mode", choices=["heuristic", "ai"], default="heuristic")
    parser.add_argument("--limit", type=int, default=100, help="Máx artículos para modo AI")
    args = parser.parse_args()

    run(mode=args.mode, limit=args.limit)
