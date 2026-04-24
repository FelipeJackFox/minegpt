"""
ollama_client.py — Cliente minimo para Ollama via SSH tunnel
=============================================================

Asume tunnel abierto: `ssh -L 11434:localhost:11434 felipe@mini-fzamorano`.
Llama http://localhost:11434/api/generate.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import requests

OLLAMA_URL = "http://localhost:11434/api/generate"


@dataclass
class GenResult:
    response: str
    eval_count: int
    prompt_eval_count: int
    total_duration_s: float


def generate(
    prompt: str,
    model: str = "qwen3:8b",
    num_ctx: int = 4096,
    temperature: float = 0.1,
    timeout: int = 240,
) -> GenResult:
    """
    Llama Ollama y devuelve la respuesta. Lanza excepcion si falla.
    """
    start = time.time()
    resp = requests.post(
        OLLAMA_URL,
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_ctx": num_ctx,
                "temperature": temperature,
            },
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    return GenResult(
        response=data.get("response", "").strip(),
        eval_count=data.get("eval_count", 0),
        prompt_eval_count=data.get("prompt_eval_count", 0),
        total_duration_s=time.time() - start,
    )


def check_connection() -> tuple[bool, str]:
    """Quick health check del tunnel SSH."""
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        return True, f"OK. Modelos: {', '.join(models)}"
    except requests.exceptions.ConnectionError:
        return False, "Conexion rechazada. Abrir tunnel: ssh -L 11434:localhost:11434 felipe@mini-fzamorano"
    except Exception as e:
        return False, f"Error: {e}"
