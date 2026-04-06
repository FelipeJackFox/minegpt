"""
train_tokenizer.py — Entrenamiento de tokenizer BPE para MineGPT
=================================================================

¿QUÉ ES UN TOKENIZER?
Un tokenizer convierte texto en números (tokens) que el modelo puede procesar.
Los modelos de lenguaje no leen texto — leen secuencias de números.

Ejemplo:
  "A Creeper explodes near the player"
  → [45, 892, 3, 67, 234, 12]  (cada número es un "token")

¿QUÉ ES BPE (BYTE PAIR ENCODING)?
BPE es el algoritmo de tokenización más usado en LLMs (GPT, LLaMA, etc.).

Funciona así:
1. Empieza con un vocabulario de caracteres individuales: {a, b, c, ..., z, A, ...}
2. Busca el par de tokens más frecuente en el corpus (ej: "e" + "r" → "er")
3. Fusiona ese par en un nuevo token y lo agrega al vocabulario
4. Repite hasta alcanzar el tamaño de vocabulario deseado

Resultado: palabras comunes se convierten en 1-2 tokens, palabras raras en más.

¿POR QUÉ UN TOKENIZER CUSTOM?
Con un tokenizer genérico (como el de GPT-2), palabras de Minecraft se fragmentan:
  "Enderman" → ["End", "erman"]   (2 tokens)
  "Redstone" → ["Red", "stone"]   (2 tokens)
  "Netherite" → ["N", "ether", "ite"]  (3 tokens)

Con un tokenizer entrenado en nuestro corpus:
  "Enderman" → ["Enderman"]   (1 token!)
  "Redstone" → ["Redstone"]   (1 token!)
  "Netherite" → ["Netherite"]  (1 token!)

Esto es más eficiente: el modelo usa menos tokens para la misma información,
puede procesar más contexto, y aprende estas palabras como unidades atómicas.

Uso:
    python -m tokenizer.train_tokenizer
    python -m tokenizer.train_tokenizer --vocab-size 16000
    python -m tokenizer.train_tokenizer --validate
"""

import json
import logging
import argparse
from pathlib import Path

import sentencepiece as spm

PROCESSED_DIR = Path(__file__).parent.parent / "processed_data"
TOKENIZER_DIR = Path(__file__).parent
OUTPUT_PREFIX = TOKENIZER_DIR / "minecraft_bpe"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ============================================================
# Vocabulario de referencia de Minecraft
# ============================================================
# Estas son palabras que DEBEN ser tokens únicos en nuestro tokenizer.
# Si alguna se fragmenta, el vocab_size es muy pequeño o el corpus es insuficiente.
#
# Esta lista se puede expandir scrapeando la lista de items/mobs/bloques del wiki.

MINECRAFT_VOCABULARY = [
    # Mobs
    "Creeper", "Enderman", "Zombie", "Skeleton", "Spider", "Blaze",
    "Ghast", "Wither", "Ender", "Piglin", "Villager", "Pillager",
    "Ravager", "Phantom", "Drowned", "Husk", "Stray", "Warden",
    "Allay", "Sniffer", "Breeze", "Bogged",
    # Bloques y materiales
    "Redstone", "Netherite", "Obsidian", "Bedrock", "Glowstone",
    "Deepslate", "Amethyst", "Terracotta", "Prismarine", "Purpur",
    "Shulker", "Sculk", "Dripstone", "Tuff", "Calcite",
    # Items
    "Elytra", "Trident", "Totem", "Ender Pearl",
    # Biomas y dimensiones
    "Nether", "Overworld", "biome", "Savanna", "Taiga",
    "Badlands", "Mangrove",
    # Mecánicas
    "crafting", "smelting", "enchanting", "brewing", "smithing",
    "spawner", "hopper", "piston", "comparator", "repeater",
    # Estructuras
    "Stronghold", "Mineshaft", "Bastion", "Fortress",
]


def prepare_training_text(output_file: Path) -> Path:
    """
    Prepara un archivo de texto plano con todo el corpus para entrenar el tokenizer.

    SentencePiece espera un archivo de texto plano (una línea por documento).
    Tomamos el corpus mezclado y lo convertimos.

    Returns:
        Path al archivo de texto generado
    """
    corpus_file = PROCESSED_DIR / "train_corpus.jsonl"

    if not corpus_file.exists():
        log.error(f"No encontrado: {corpus_file}. Ejecuta data.mixer primero.")
        raise FileNotFoundError(corpus_file)

    log.info(f"Preparando texto de entrenamiento desde {corpus_file}...")

    count = 0
    with open(corpus_file, "r", encoding="utf-8") as fin, \
         open(output_file, "w", encoding="utf-8") as fout:
        for line in fin:
            entry = json.loads(line)
            text = entry.get("text", "").strip()
            if text:
                # SentencePiece espera una oración/línea
                # Reemplazar newlines internos por espacio
                text = text.replace("\n", " ")
                fout.write(text + "\n")
                count += 1

    log.info(f"Preparados {count:,} textos para entrenamiento del tokenizer")
    return output_file


def train(vocab_size: int = 8000):
    """
    Entrena el tokenizer BPE con SentencePiece.

    Args:
        vocab_size: Tamaño del vocabulario.
            - Muy pequeño (<4000): muchas palabras se fragmentan
            - Muy grande (>32000): el modelo necesita más params para la capa de embedding
            - 8000-16000: buen rango para corpus especializado con modelo chico
    """
    TOKENIZER_DIR.mkdir(parents=True, exist_ok=True)

    # Paso 1: Preparar texto plano
    train_text = TOKENIZER_DIR / "train_text.txt"
    prepare_training_text(train_text)

    # Paso 2: Entrenar SentencePiece
    log.info(f"Entrenando tokenizer BPE (vocab_size={vocab_size})...")

    spm.SentencePieceTrainer.train(
        input=str(train_text),
        model_prefix=str(OUTPUT_PREFIX),
        vocab_size=vocab_size,
        model_type="bpe",

        # Tokens especiales que el modelo necesita:
        # <pad> = padding (rellenar secuencias cortas)
        # <unk> = desconocido (caracteres no vistos)
        # <s> = inicio de secuencia
        # </s> = fin de secuencia
        pad_id=0,
        unk_id=1,
        bos_id=2,
        eos_id=3,

        # Normalización mínima (ya limpiamos los datos)
        normalization_rule_name="identity",

        # Byte fallback: si un carácter no está en el vocab,
        # se descompone en bytes. Esto garantiza que CUALQUIER
        # texto se puede tokenizar (nunca hay <unk>).
        byte_fallback=True,

        # Limitar tamaño del input para velocidad
        input_sentence_size=1_000_000,
        shuffle_input_sentence=True,
    )

    log.info(f"Tokenizer entrenado: {OUTPUT_PREFIX}.model ({OUTPUT_PREFIX}.vocab)")

    # Limpiar archivo temporal
    train_text.unlink(missing_ok=True)


def validate():
    """
    Valida que el tokenizer maneja bien el vocabulario de Minecraft.

    Verifica que las palabras clave de Minecraft son tokens únicos
    (no se fragmentan en sub-tokens).
    """
    model_file = f"{OUTPUT_PREFIX}.model"
    if not Path(model_file).exists():
        log.error(f"Tokenizer no encontrado: {model_file}. Entrénalo primero.")
        return

    sp = spm.SentencePieceProcessor()
    sp.load(model_file)

    log.info(f"Validando tokenizer (vocab_size={sp.get_piece_size()})...")
    log.info(f"Verificando {len(MINECRAFT_VOCABULARY)} palabras de Minecraft...")

    fragmented = []
    single_token = []

    for word in MINECRAFT_VOCABULARY:
        tokens = sp.encode(word, out_type=str)
        if len(tokens) == 1:
            single_token.append(word)
        else:
            fragmented.append((word, tokens))

    log.info(f"\nResultados:")
    log.info(f"  Tokens únicos (OK): {len(single_token)}/{len(MINECRAFT_VOCABULARY)}")
    log.info(f"  Fragmentados: {len(fragmented)}/{len(MINECRAFT_VOCABULARY)}")

    if fragmented:
        log.info(f"\nPalabras fragmentadas (considerar aumentar vocab_size):")
        for word, tokens in fragmented:
            log.info(f"  {word:20s} → {tokens}")

    if single_token:
        log.info(f"\nPalabras como token único (OK):")
        for word in single_token[:20]:  # Mostrar primeras 20
            log.info(f"  {word}")
        if len(single_token) > 20:
            log.info(f"  ... y {len(single_token) - 20} más")

    # Ejemplo de tokenización completa
    log.info("\nEjemplos de tokenización:")
    examples = [
        "A Creeper explodes near the player dealing damage",
        "How do I craft a Diamond Sword in Minecraft?",
        "The Nether is a dangerous dimension full of hostile mobs",
        "Redstone can be used to create complex circuits and machines",
    ]
    for text in examples:
        tokens = sp.encode(text, out_type=str)
        ids = sp.encode(text)
        log.info(f"  \"{text}\"")
        log.info(f"    Tokens ({len(tokens)}): {tokens}")
        log.info(f"    IDs: {ids}")

    return len(fragmented) == 0  # True si todo es token único


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tokenizer BPE para MineGPT")
    parser.add_argument("--vocab-size", type=int, default=8000)
    parser.add_argument("--validate", action="store_true", help="Solo validar tokenizer existente")
    args = parser.parse_args()

    if args.validate:
        validate()
    else:
        train(vocab_size=args.vocab_size)
        validate()
