"""
app.py — API backend para MineGPT chat UI
============================================

Sirve el modelo via FastAPI con streaming de tokens.
El frontend (Next.js + shadcn) se conecta a estos endpoints.

Endpoints:
  POST /api/chat     — Genera respuesta (streaming SSE)
  GET  /api/health   — Health check
  GET  /api/config   — Configuración del modelo (params, etc.)

Uso:
    python -m web.app
    # o
    uvicorn web.app:app --host 0.0.0.0 --port 8000
"""

import json
import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

try:
    import mlx.core as mx
    HAS_MLX = True
except ImportError:
    HAS_MLX = False

import sentencepiece as spm

from utils.config import CONFIG

app = FastAPI(title="MineGPT", version="0.1.0")

# CORS para desarrollo local (Next.js corre en otro puerto)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción: restringir a la IP de Tailscale
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Modelo y tokenizer (se cargan al iniciar)
model = None
tokenizer = None


@app.on_event("startup")
async def load_model():
    """Carga modelo y tokenizer al iniciar el servidor."""
    global model, tokenizer

    if not HAS_MLX:
        log.warning("MLX no disponible. El endpoint /api/chat no funcionará.")
        return

    from model.gpt import create_model_from_config
    from model.train import load_checkpoint

    # Tokenizer
    sp = spm.SentencePieceProcessor()
    tokenizer_path = CONFIG["paths"]["tokenizer_model"]
    if tokenizer_path.exists():
        sp.load(str(tokenizer_path))
        tokenizer = sp
        log.info(f"Tokenizer cargado: vocab_size={sp.get_piece_size()}")
    else:
        log.error(f"Tokenizer no encontrado: {tokenizer_path}")
        return

    # Modelo
    model = create_model_from_config(CONFIG["model"], sp.get_piece_size())

    # Intentar cargar finetune, luego pre-training
    ft_dir = CONFIG["paths"]["checkpoints"] / "finetune"
    if ft_dir.exists():
        load_checkpoint(model, ft_dir)
        log.info("Modelo finetune cargado")
    else:
        step, _, _ = load_checkpoint(model, CONFIG["paths"]["checkpoints"])
        if step > 0:
            log.info(f"Modelo pre-training cargado (step {step})")
        else:
            log.warning("No hay checkpoints. Modelo con pesos aleatorios.")


@app.get("/api/health")
async def health():
    return {"status": "ok", "model_loaded": model is not None}


@app.get("/api/config")
async def get_config():
    """Retorna info del modelo para mostrar en la UI."""
    n_params = model.count_parameters() if model else 0
    return {
        "model": CONFIG["model"],
        "parameters": n_params,
        "parameters_human": f"{n_params / 1e6:.1f}M" if n_params else "N/A",
        "vocab_size": tokenizer.get_piece_size() if tokenizer else 0,
    }


@app.post("/api/chat")
async def chat(request: Request):
    """
    Genera respuesta con streaming SSE (Server-Sent Events).

    El frontend recibe tokens uno por uno, permitiendo ver
    la respuesta mientras se genera (como ChatGPT).

    Body:
        {
            "message": "How do I craft a diamond sword?",
            "temperature": 0.7,
            "top_k": 50,
            "top_p": 0.9,
            "max_tokens": 256
        }
    """
    if not model or not tokenizer:
        return JSONResponse(
            status_code=503,
            content={"error": "Modelo no cargado"},
        )

    body = await request.json()
    message = body.get("message", "")
    temperature = body.get("temperature", CONFIG["web"]["default_temperature"])
    top_k = body.get("top_k", CONFIG["web"]["default_top_k"])
    top_p = body.get("top_p", CONFIG["web"]["default_top_p"])
    max_tokens = body.get("max_tokens", 256)

    # Formatear como instrucción
    prompt = f"### Instruction:\n{message}\n\n### Response:\n"

    async def generate_stream():
        """Generador asíncrono que yield tokens uno por uno."""
        tokens = tokenizer.encode(prompt)
        tokens_mx = mx.array([tokens], dtype=mx.int32)

        import math
        import time
        start_time = time.time()
        token_count = 0

        for _ in range(max_tokens):
            if tokens_mx.shape[1] > model.ctx_len:
                tokens_mx = tokens_mx[:, -model.ctx_len:]

            logits = model(tokens_mx)
            logits = logits[:, -1, :]

            if temperature > 0:
                logits = logits / temperature

                if top_k > 0:
                    top_k_vals = mx.topk(logits, k=min(top_k, logits.shape[-1]))
                    min_val = top_k_vals[0, -1]
                    logits = mx.where(logits < min_val, float('-inf'), logits)

                probs = mx.softmax(logits, axis=-1)
                next_token = mx.random.categorical(mx.log(probs + 1e-10))
            else:
                next_token = mx.argmax(logits, axis=-1)

            token_id = next_token.item()
            token_count += 1

            if token_id == tokenizer.eos_id():
                break

            piece = tokenizer.decode([token_id])
            tokens_mx = mx.concatenate([tokens_mx, next_token.reshape(1, 1)], axis=1)

            # SSE format
            elapsed = time.time() - start_time
            tps = token_count / elapsed if elapsed > 0 else 0

            data = json.dumps({
                "token": piece,
                "tokens_per_second": round(tps, 1),
            })
            yield f"data: {data}\n\n"

            # Yield control para no bloquear el event loop
            await asyncio.sleep(0)

        # Signal de fin
        yield f"data: {json.dumps({'done': True, 'total_tokens': token_count})}\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "web.app:app",
        host=CONFIG["web"]["host"],
        port=CONFIG["web"]["port"],
        reload=False,  # No reload en producción
    )
