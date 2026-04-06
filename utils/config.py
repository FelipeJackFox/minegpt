"""
config.py — Configuración centralizada de MineGPT
==================================================

Todos los hiperparámetros y rutas del proyecto están aquí.
Esto permite cambiar configuraciones sin tocar el código de cada módulo.

Uso:
    from utils.config import CONFIG
    print(CONFIG["model"]["n_layers"])
"""

from pathlib import Path

# Raíz del proyecto (donde está este archivo, 2 niveles arriba)
PROJECT_ROOT = Path(__file__).parent.parent

CONFIG = {
    # --------------------------------------------------------
    # Rutas de datos
    # --------------------------------------------------------
    "paths": {
        "raw_data": PROJECT_ROOT / "raw_data",          # Datos crudos del scraping
        "processed_data": PROJECT_ROOT / "processed_data",  # Datos limpios y mezclados
        "checkpoints": PROJECT_ROOT / "checkpoints",     # Checkpoints del modelo
        "tokenizer_model": PROJECT_ROOT / "tokenizer" / "minecraft_bpe.model",
    },

    # --------------------------------------------------------
    # Scraping
    # --------------------------------------------------------
    "scraper": {
        "wiki_base_url": "https://minecraft.wiki",
        "rate_limit_seconds": 1.0,  # Mínimo 1 segundo entre requests
        "min_article_words": 100,   # Umbral para evaluar artículos cortos
    },

    # --------------------------------------------------------
    # Tokenizer
    # --------------------------------------------------------
    "tokenizer": {
        "vocab_size": 8000,     # Vocabulario pequeño para corpus especializado
        "model_type": "bpe",    # Byte Pair Encoding
    },

    # --------------------------------------------------------
    # Modelo GPT
    # Estos valores son INICIALES — se ajustan tras el benchmark
    # en el Mac Mini M2 (Paso 7 del plan)
    # --------------------------------------------------------
    "model": {
        "n_layers": 6,          # Bloques transformer
        "n_heads": 8,           # Cabezas de atención
        "d_model": 512,         # Dimensión de embeddings
        "d_ff": 2048,           # Dimensión de la FFN (típicamente 4x d_model)
        "ctx_len": 512,         # Longitud de contexto en tokens
        "dropout": 0.1,
    },

    # --------------------------------------------------------
    # Entrenamiento
    # --------------------------------------------------------
    "training": {
        "batch_size": 32,
        "learning_rate": 3e-4,
        "warmup_steps": 1000,
        "checkpoint_every_steps": 500,  # Guardar checkpoint cada N steps
        "max_epochs": 10,
        "grad_clip": 1.0,
    },

    # --------------------------------------------------------
    # Instruction tuning
    # --------------------------------------------------------
    "finetune": {
        "learning_rate": 1e-5,
        "max_epochs": 3,
        "batch_size": 16,
    },

    # --------------------------------------------------------
    # Data mixing
    # Ratios se determinan tras tener todos los datasets.
    # Estos son valores iniciales para experimentar.
    # --------------------------------------------------------
    "mixing": {
        "general_ratio": 0.70,      # WikiText + TinyStories
        "minecraft_ratio": 0.20,    # Wiki de Minecraft
        "minecraft_oversample": 0.10,  # Repetición extra de Minecraft
    },

    # --------------------------------------------------------
    # UI Web
    # --------------------------------------------------------
    "web": {
        "host": "0.0.0.0",     # Accesible via Tailscale
        "port": 8000,
        "default_temperature": 0.7,
        "default_top_k": 50,
        "default_top_p": 0.9,
    },
}
