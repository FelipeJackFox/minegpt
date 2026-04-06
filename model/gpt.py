"""
gpt.py — Arquitectura GPT para MineGPT (MLX)
================================================

Este archivo implementa un modelo GPT (Generative Pre-trained Transformer)
desde cero usando MLX, el framework de ML de Apple optimizado para Apple Silicon.

FLUJO DE DATOS DEL MODELO:
==========================

  Input: "How do I craft a sword"
    │
    ▼
  ┌─────────────────────────────────────────┐
  │  Token Embedding                         │  Convierte cada token (número) en un vector
  │  + Positional Embedding                  │  + agrega información de posición
  └─────────────────────────────────────────┘
    │
    ▼ (repite N veces)
  ┌─────────────────────────────────────────┐
  │  Transformer Block                       │
  │  ┌───────────────────────────────────┐  │
  │  │  LayerNorm                         │  │  Normaliza las activaciones
  │  │  → Multi-Head Self-Attention       │  │  El modelo "mira" todos los tokens anteriores
  │  │  → Residual Connection (+)         │  │  Suma la entrada original (evita degradación)
  │  │  → LayerNorm                       │  │
  │  │  → Feed-Forward Network (FFN)      │  │  Procesa cada posición independientemente
  │  │  → Residual Connection (+)         │  │  Otra suma con la entrada
  │  └───────────────────────────────────┘  │
  └─────────────────────────────────────────┘
    │
    ▼
  ┌─────────────────────────────────────────┐
  │  LayerNorm final                         │
  │  → Linear (vocab_size)                   │  Proyecta a probabilidades de cada token
  └─────────────────────────────────────────┘
    │
    ▼
  Output: probabilidades del siguiente token
          → "?" (siguiente token más probable)

¿QUÉ HACE CADA COMPONENTE?
============================

MULTI-HEAD SELF-ATTENTION:
  El mecanismo central de los Transformers. Para cada token, calcula cuánto
  "atención" debería prestar a cada token anterior.

  Ejemplo: en "The Creeper that spawned in the cave exploded"
  - Para predecir "exploded", el modelo necesita atender a "Creeper" (quién explota)
  - Self-Attention permite que "exploded" "mire hacia atrás" a "Creeper"

  "Multi-Head" significa que hay varias "cabezas" de atención en paralelo,
  cada una aprendiendo a buscar diferentes patrones (sujeto, verbo, contexto, etc.)

FEED-FORWARD NETWORK (FFN):
  Una red neuronal simple (2 capas lineales con activación) que procesa
  cada posición de forma independiente. Aquí es donde se almacena el
  "conocimiento" del modelo — los facts sobre Minecraft.

  La FFN es mucho más grande que la atención (4x d_model típicamente),
  porque necesita almacenar más información.

LAYER NORM:
  Normaliza las activaciones para que el entrenamiento sea estable.
  Sin esto, los gradientes explotan o desaparecen en modelos profundos.

RESIDUAL CONNECTIONS:
  output = input + layer(input)
  Esto permite que los gradientes fluyan directamente a través de las capas,
  resolviendo el problema de "vanishing gradients" en redes profundas.
  Inventado en ResNet (2015), ahora estándar en todos los Transformers.

REFERENCIAS:
  - "Attention Is All You Need" (Vaswani et al., 2017) — paper original del Transformer
  - "Language Models are Unsupervised Multitask Learners" (Radford et al., 2019) — GPT-2
  - "Improving Language Understanding by Generative Pre-Training" (Radford et al., 2018) — GPT-1
"""

import math

# MLX: framework de Apple para ML en Apple Silicon
# Si estás en Windows/Linux, esto no se puede importar.
# El modelo solo se puede entrenar en Mac.
try:
    import mlx.core as mx
    import mlx.nn as nn
    HAS_MLX = True
except ImportError:
    HAS_MLX = False
    # Placeholder para que el archivo sea importable en cualquier OS
    # (útil para tests, linting, etc.)
    class _FakeModule:
        def __getattr__(self, name):
            raise RuntimeError(
                "MLX no está disponible en este sistema. "
                "El modelo solo puede ejecutarse en macOS con Apple Silicon (M1/M2/M3)."
            )
    mx = _FakeModule()
    nn = type('nn', (), {'Module': object, 'Linear': object, 'Embedding': object,
                          'LayerNorm': object, 'Dropout': object})()


# ============================================================
# Multi-Head Self-Attention
# ============================================================

class MultiHeadAttention(nn.Module):
    """
    Multi-Head Self-Attention con causal masking.

    "Self-Attention" = cada token atiende a otros tokens de la MISMA secuencia
    "Causal" = cada token solo puede ver tokens ANTERIORES (no el futuro)
    "Multi-Head" = múltiples mecanismos de atención en paralelo

    Matemáticamente:
      Q = input @ W_q   (Query: "¿qué estoy buscando?")
      K = input @ W_k   (Key: "¿qué información tengo?")
      V = input @ W_v   (Value: "¿qué información devuelvo?")

      Attention(Q, K, V) = softmax(Q @ K^T / sqrt(d_k)) @ V

    La división por sqrt(d_k) es para estabilidad numérica.
    El softmax convierte los scores en probabilidades.
    """

    def __init__(self, d_model: int, n_heads: int):
        super().__init__()

        assert d_model % n_heads == 0, \
            f"d_model ({d_model}) debe ser divisible por n_heads ({n_heads})"

        self.n_heads = n_heads
        self.d_head = d_model // n_heads  # Dimensión por cabeza
        self.scale = math.sqrt(self.d_head)  # Factor de escalado

        # Proyecciones lineales para Q, K, V y output
        # Cada una transforma el input a un espacio diferente
        self.W_q = nn.Linear(d_model, d_model, bias=False)
        self.W_k = nn.Linear(d_model, d_model, bias=False)
        self.W_v = nn.Linear(d_model, d_model, bias=False)
        self.W_o = nn.Linear(d_model, d_model, bias=False)

    def __call__(self, x: "mx.array") -> "mx.array":
        """
        Forward pass de Multi-Head Attention.

        Args:
            x: tensor de shape (batch, seq_len, d_model)

        Returns:
            tensor de shape (batch, seq_len, d_model)
        """
        B, T, C = x.shape  # Batch, Time (seq_len), Channels (d_model)

        # Proyectar a Q, K, V
        q = self.W_q(x)  # (B, T, d_model)
        k = self.W_k(x)
        v = self.W_v(x)

        # Reshape para múltiples cabezas: (B, T, d_model) → (B, n_heads, T, d_head)
        q = q.reshape(B, T, self.n_heads, self.d_head).transpose(0, 2, 1, 3)
        k = k.reshape(B, T, self.n_heads, self.d_head).transpose(0, 2, 1, 3)
        v = v.reshape(B, T, self.n_heads, self.d_head).transpose(0, 2, 1, 3)

        # Calcular scores de atención: Q @ K^T / sqrt(d_k)
        # Shape: (B, n_heads, T, T) — cada token tiene un score con cada otro token
        scores = (q @ k.transpose(0, 1, 3, 2)) / self.scale

        # Causal mask: poner -infinito en posiciones futuras
        # Esto hace que softmax les asigne probabilidad ~0
        # Un token en posición i solo puede atender a tokens 0..i
        mask = mx.triu(mx.full((T, T), float('-inf')), k=1)
        scores = scores + mask

        # Softmax: convertir scores en probabilidades (suman 1.0 por fila)
        weights = mx.softmax(scores, axis=-1)

        # Multiplicar por V: ponderar los valores por las probabilidades de atención
        out = weights @ v  # (B, n_heads, T, d_head)

        # Re-concatenar cabezas: (B, n_heads, T, d_head) → (B, T, d_model)
        out = out.transpose(0, 2, 1, 3).reshape(B, T, -1)

        # Proyección final de output
        return self.W_o(out)


# ============================================================
# Feed-Forward Network
# ============================================================

class FeedForward(nn.Module):
    """
    Feed-Forward Network (FFN) con activación GELU.

    Es una red neuronal simple de 2 capas que procesa cada posición
    de la secuencia de forma independiente.

    Aquí se almacena el "conocimiento" del modelo:
    - Los facts sobre crafteos, mobs, biomas
    - Patrones gramaticales y semánticos

    GELU (Gaussian Error Linear Unit) es la activación usada en GPT-2.
    Es similar a ReLU pero más suave, lo que ayuda al entrenamiento.

    d_ff típicamente es 4x d_model (ej: d_model=512 → d_ff=2048).
    """

    def __init__(self, d_model: int, d_ff: int):
        super().__init__()
        self.fc1 = nn.Linear(d_model, d_ff, bias=False)
        self.fc2 = nn.Linear(d_ff, d_model, bias=False)

    def __call__(self, x: "mx.array") -> "mx.array":
        x = self.fc1(x)
        x = nn.gelu(x)  # Activación no-lineal
        x = self.fc2(x)
        return x


# ============================================================
# Transformer Block
# ============================================================

class TransformerBlock(nn.Module):
    """
    Un bloque Transformer completo (Pre-Norm variant).

    Pre-Norm (lo que usamos): LayerNorm → Attention/FFN → Residual
    Post-Norm (original):     Attention/FFN → Residual → LayerNorm

    Pre-Norm es más estable para entrenar y es lo que usan GPT-2, LLaMA, etc.
    """

    def __init__(self, d_model: int, n_heads: int, d_ff: int):
        super().__init__()
        self.ln1 = nn.LayerNorm(d_model)
        self.attn = MultiHeadAttention(d_model, n_heads)
        self.ln2 = nn.LayerNorm(d_model)
        self.ffn = FeedForward(d_model, d_ff)

    def __call__(self, x: "mx.array") -> "mx.array":
        # Attention con residual connection
        # x = x + Attention(LayerNorm(x))
        x = x + self.attn(self.ln1(x))

        # FFN con residual connection
        # x = x + FFN(LayerNorm(x))
        x = x + self.ffn(self.ln2(x))

        return x


# ============================================================
# Modelo GPT completo
# ============================================================

class MineGPT(nn.Module):
    """
    MineGPT — Modelo GPT completo para generación de texto sobre Minecraft.

    Parámetros:
        vocab_size: Tamaño del vocabulario del tokenizer
        n_layers: Número de bloques Transformer apilados
        n_heads: Número de cabezas de atención por bloque
        d_model: Dimensión de los embeddings y hidden states
        d_ff: Dimensión de la FFN (típicamente 4x d_model)
        ctx_len: Longitud máxima de contexto (en tokens)

    Para estimar el número de parámetros:
        ~= vocab_size * d_model  (embeddings)
         + n_layers * (4 * d_model² + 2 * d_model * d_ff)  (transformer blocks)
         + vocab_size * d_model  (head de salida)
    """

    def __init__(
        self,
        vocab_size: int,
        n_layers: int = 6,
        n_heads: int = 8,
        d_model: int = 512,
        d_ff: int = 2048,
        ctx_len: int = 512,
    ):
        super().__init__()

        self.ctx_len = ctx_len

        # Token embedding: convierte IDs de tokens en vectores
        # Cada token tiene su propio vector de d_model dimensiones
        self.token_embed = nn.Embedding(vocab_size, d_model)

        # Positional embedding: codifica la POSICIÓN de cada token
        # Sin esto, el modelo no sabe si "Creeper" está al inicio o al final
        # (la atención es invariante al orden sin positional encoding)
        self.pos_embed = nn.Embedding(ctx_len, d_model)

        # Stack de bloques Transformer
        self.blocks = [
            TransformerBlock(d_model, n_heads, d_ff)
            for _ in range(n_layers)
        ]

        # LayerNorm final antes de la proyección a vocabulario
        self.ln_final = nn.LayerNorm(d_model)

        # Head de salida: proyecta de d_model → vocab_size
        # Produce un score (logit) para cada token del vocabulario
        # El token con el logit más alto es la predicción
        self.head = nn.Linear(d_model, vocab_size, bias=False)

        # Weight tying: compartir pesos entre token_embed y head
        # Esto reduce parámetros y mejora generalización
        # (paper: "Using the Output Embedding to Improve Language Models", Press & Wolf 2017)
        self.head.weight = self.token_embed.weight

    def __call__(self, tokens: "mx.array") -> "mx.array":
        """
        Forward pass del modelo.

        Args:
            tokens: tensor de shape (batch, seq_len) con IDs de tokens

        Returns:
            logits: tensor de shape (batch, seq_len, vocab_size)
                    Scores para cada token del vocabulario en cada posición.
                    Para obtener probabilidades: softmax(logits)
                    Para obtener predicción: argmax(logits)
        """
        B, T = tokens.shape
        assert T <= self.ctx_len, \
            f"Secuencia de {T} tokens excede ctx_len={self.ctx_len}"

        # Crear posiciones: [0, 1, 2, ..., T-1]
        positions = mx.arange(T)

        # Embeddings: token + posición
        x = self.token_embed(tokens) + self.pos_embed(positions)

        # Pasar por todos los bloques Transformer
        for block in self.blocks:
            x = block(x)

        # Normalización final
        x = self.ln_final(x)

        # Proyectar a logits del vocabulario
        logits = self.head(x)

        return logits

    def count_parameters(self) -> int:
        """Cuenta el número total de parámetros del modelo."""
        total = 0
        for name, param in self.parameters().items():
            total += param.size
        return total


# ============================================================
# Utilidades
# ============================================================

def create_model_from_config(config: dict, vocab_size: int) -> MineGPT:
    """
    Crea una instancia del modelo desde un dict de configuración.

    Args:
        config: Dict con keys n_layers, n_heads, d_model, d_ff, ctx_len
        vocab_size: Tamaño del vocabulario (del tokenizer)

    Returns:
        Instancia de MineGPT
    """
    model = MineGPT(
        vocab_size=vocab_size,
        n_layers=config.get("n_layers", 6),
        n_heads=config.get("n_heads", 8),
        d_model=config.get("d_model", 512),
        d_ff=config.get("d_ff", 2048),
        ctx_len=config.get("ctx_len", 512),
    )

    n_params = model.count_parameters()
    print(f"MineGPT creado:")
    print(f"  Capas: {config.get('n_layers', 6)}")
    print(f"  Cabezas: {config.get('n_heads', 8)}")
    print(f"  d_model: {config.get('d_model', 512)}")
    print(f"  d_ff: {config.get('d_ff', 2048)}")
    print(f"  ctx_len: {config.get('ctx_len', 512)}")
    print(f"  Vocab size: {vocab_size}")
    print(f"  Parámetros totales: {n_params:,} ({n_params / 1e6:.1f}M)")

    return model


if __name__ == "__main__":
    if not HAS_MLX:
        print("MLX no disponible. Este modelo solo corre en macOS con Apple Silicon.")
    else:
        # Quick test: crear modelo y verificar shapes
        model = create_model_from_config(
            {"n_layers": 6, "n_heads": 8, "d_model": 512, "d_ff": 2048, "ctx_len": 512},
            vocab_size=8000,
        )

        # Test forward pass
        dummy_input = mx.zeros((2, 128), dtype=mx.int32)  # batch=2, seq_len=128
        logits = model(dummy_input)
        print(f"\nTest forward pass:")
        print(f"  Input shape: {dummy_input.shape}")
        print(f"  Output shape: {logits.shape}")  # Debería ser (2, 128, 8000)
        print(f"  OK!")
