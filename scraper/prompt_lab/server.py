"""
server.py — FastAPI backend para el Prompt Lab
================================================

Sirve la UI estatica y provee API para correr prompts contra Qwen3:8b
via SSH tunnel.

Endpoints:
- GET  /                        → sirve static/index.html
- GET  /api/connection          → health check del tunnel SSH
- GET  /api/tasks               → lista tasks disponibles (basado en testsets)
- GET  /api/task/{task}         → detalle de la task: testset + prompt
- POST /api/task/{task}/prompt  → guarda prompt como final
- POST /api/run                 → inicia un run, devuelve run_id
- GET  /api/run/{run_id}/events → SSE stream con eventos item-por-item

Uso:
    # 1. Abrir tunnel SSH:
    ssh -L 11434:localhost:11434 felipe@mini-fzamorano

    # 2. Lanzar server:
    python -m scraper.prompt_lab.server

    # 3. Abrir http://127.0.0.1:7860
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from datetime import datetime
from pathlib import Path

import requests as _requests

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from scraper.prompt_lab.ollama_client import check_connection, generate

# ============================================================
# SSH tunnel management
# ============================================================

TUNNEL_HOST = "felipe@mini-fzamorano"
TUNNEL_LOCAL_PORT = 11434
TUNNEL_REMOTE_PORT = 11434


def ensure_tunnel() -> tuple[bool, str]:
    """
    Verifica si el tunnel SSH esta vivo. Si no, lo abre automaticamente.
    Devuelve (ok, msg).
    """
    import subprocess
    import socket

    # Quick port check
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    try:
        sock.connect(("127.0.0.1", TUNNEL_LOCAL_PORT))
        sock.close()
        return True, "Tunnel already active"
    except (ConnectionRefusedError, socket.timeout, OSError):
        pass

    # Open tunnel
    try:
        subprocess.Popen(
            [
                "ssh", "-f", "-N",
                "-o", "StrictHostKeyChecking=no",
                "-o", "ServerAliveInterval=30",
                "-o", "ServerAliveCountMax=3",
                "-L", f"{TUNNEL_LOCAL_PORT}:localhost:{TUNNEL_REMOTE_PORT}",
                TUNNEL_HOST,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return False, "ssh not found in PATH"

    # Wait for tunnel to be ready
    import time
    for _ in range(10):
        time.sleep(0.5)
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect(("127.0.0.1", TUNNEL_LOCAL_PORT))
            sock.close()
            return True, "Tunnel opened successfully"
        except (ConnectionRefusedError, socket.timeout, OSError):
            continue

    return False, "Tunnel failed to open after 5s"

# ============================================================
# Input preparation — strip hatnotes/notices del inicio
# ============================================================

# Patterns de lineas "noise" que aparecen al inicio de articulos wiki.
# Se aplican en orden: mientras una linea del inicio matche alguno, se
# descarta. Al encontrar la primera linea que NO matche, se detiene.
HATNOTE_PATTERNS = [
    # Hatnotes de disambiguation
    re.compile(r"^For other uses,?\s*see .+$", re.IGNORECASE),
    re.compile(r"^Not to be confused with .+$", re.IGNORECASE),
    re.compile(r"^This article is about .+?(\.\s*For .+, see .+\.?)?$", re.IGNORECASE),
    re.compile(r'^".+" redirects here\.\s*(For .+, see .+\.?)?$', re.IGNORECASE),
    re.compile(r'^".+" may refer to:?$', re.IGNORECASE),
    # DLC / edition notices
    re.compile(r"^This page describes content that is (a part|part) of the .+ DLC\.?$", re.IGNORECASE),
    re.compile(r"^This feature is exclusive to .+$", re.IGNORECASE),
    re.compile(r"^This article documents an April Fools?'?.+$", re.IGNORECASE),
    re.compile(r"^This article is about the .+?(\.\s*For .+, see .+\.?)?$", re.IGNORECASE),
    # Maintenance notes/instructions residuales
    re.compile(r"^Instructions:\s*$", re.IGNORECASE),
    re.compile(r"^Note:\s*$", re.IGNORECASE),
    re.compile(r"^Verify the plot.+$", re.IGNORECASE),
    re.compile(r"^Expand on .+$", re.IGNORECASE),
    re.compile(r"^Find out from the developers.+$", re.IGNORECASE),
    re.compile(r"^An official name.+$", re.IGNORECASE),
    re.compile(r"^Please update the name.+$", re.IGNORECASE),
    re.compile(r"^This article has no navigation boxes\.$", re.IGNORECASE),
    re.compile(r"^Please add one or more navigation box templates.+$", re.IGNORECASE),
    re.compile(r"^Add data values section\.?$", re.IGNORECASE),
    re.compile(r"^Add sounds,? if there is any\.?$", re.IGNORECASE),
    re.compile(r"^Missing information$", re.IGNORECASE),
    re.compile(r"^Empty sections$", re.IGNORECASE),
    # Blank / whitespace-only
    re.compile(r"^\s*$"),
]


def strip_leading_hatnotes(text: str) -> str:
    """
    Elimina lineas iniciales que son hatnotes, templates o notes.
    Se detiene al encontrar la primera linea de contenido real.
    """
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if any(p.match(line) for p in HATNOTE_PATTERNS):
            i += 1
            continue
        break
    return "\n".join(lines[i:])


def prepare_input(text: str, max_words: int = 800) -> str:
    """
    Prepara el texto de un articulo para pasar a Qwen:
    1. Strippea hatnotes/notes/templates del inicio
    2. Trunca a max_words palabras
    """
    cleaned = strip_leading_hatnotes(text)
    words = cleaned.split()
    if len(words) > max_words:
        return " ".join(words[:max_words])
    return cleaned

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
TESTSETS_DIR = BASE_DIR / "testsets"
PROMPTS_DIR = BASE_DIR / "prompts"
HISTORY_DIR = BASE_DIR / "history"

# ============================================================
# Config por task
# ============================================================

TASK_CONFIG = {
    "spinoff_classifier": {
        "mode": "classify",
        "classes": ["KEEP", "DISCARD"],
        "default_prompt": """/no_think
You are classifying Minecraft spin-off wiki articles (from Dungeons, Legends, Earth, Story Mode) for a small LLM training dataset. The dataset must not be saturated with generic spin-off items that would confuse the model about vanilla Minecraft, but must keep the narrative content that teaches players about the spin-off games' stories.

CLASSIFY BY ASKING: "What IS this article about?"

KEEP if the article IS about:
- A named character (protagonist, ally, villain, NPC, mascot)
- A specific named boss or antagonistic entity with a unique role in the story
- A specific plot item or artifact that drives the narrative (an artifact owned by a named character, a cursed object central to the plot)
- A named location with narrative significance (a specific town, dungeon, palace that appears in cutscenes/episodes)
- An episode, chapter, mission, or major cutscene
- A general concept describing the game, its world, its factions, or its lore

DISCARD if the article IS about:
- A generic player-obtainable item, weapon, armor, enchantment, artifact, kit, or skin (one of many in the gear pool)
- A generic mob, enemy, passive creature, or mob variant
- A version number, patch, build, or update
- A gameplay mechanic, currency, stat system, crafting recipe, or drop table
- A generic player-built structure, tower, unit, or construct
- A cosmetic mob variant (recolored cow, themed chicken)

CRITICAL RULE — avoid the "named character in flavor text" trap:
An article can MENTION a named character in its description without being ABOUT that character. If the article is about a piece of gear or a generic structure, but its flavor text references a famous character (e.g. "crafted by the Arch-Illager", "built by Knowledge"), it is still DISCARD. The test: remove the mention of the named character from the article — is there still a reason to keep this specific article in a narrative dataset? If no, DISCARD.

Only KEEP if the article's SUBJECT (what the article is ABOUT) is itself a narrative element, not if it merely references one.

ANOTHER TEST: Would this article plausibly appear in a "story summary" or "characters and locations" wiki section? If yes, KEEP. Would it appear in a "gear list" or "mob catalog" section? If yes, DISCARD.

SPECIAL CASES:
- Mascot characters (even pets or companions introduced as official mascots) → KEEP
- Generic infobox fields (Health points, Damage, Rarity) do NOT decide classification — a boss has HP but is KEEP, a generic mob also has HP but is DISCARD
- A type/category of entity (e.g. "a type of piglin that did X") is usually DISCARD unless it has a unique named role — BUT if the article describes a specific narrative event involving that type (e.g. a specific injured piglin with a biography), then KEEP
- Structures or buildings with dedicated Lore sections explaining their narrative origin (e.g. built by a Host, ancient relic) → KEEP — their worldbuilding value justifies inclusion

CRITICAL — distinguish "loot/collectibles" from "plot devices":
An item that "can be found within the various missions" as random loot or gear is DISCARD (generic collectible). But an item that appears across MULTIPLE episodes as a recurring narrative thread — created or owned by named characters, actively sought by the protagonist, connecting story arcs — is KEEP. The test: does this item drive or connect the plot? If the item appears in a list of "found in: Episode X, Episode Y, Episode Z" with different named owners in each, it's a plot device, not loot.

CRITICAL — "appearing" is NOT "relevant":
If an article says an entity "appears in Episode X" or "is found in Location Y" but the article contains NO actual narrative content (no biography, no plot event, no character interaction described), it is DISCARD. The article itself must DESCRIBE narrative content, not merely state that the entity exists in a narrative context. A mob variant that just spawns in a story level without any described story role is DISCARD.

Article title: {title}
Article text:
{text}

Reply in this exact format (one line):
KEEP: <one-sentence reason>
or
DISCARD: <one-sentence reason>""",
    },
    # Futuros tasks:
    # "short_classifier": {"mode": "classify", "classes": ["KEEP", "DISCARD"], ...}
    # "changelog_transformer": {"mode": "transform", ...}
    # "core_transformer": {"mode": "transform", ...}
    # "qa_generator": {"mode": "transform", ...}
}

# ============================================================
# FastAPI app
# ============================================================

app = FastAPI(title="MineGPT Prompt Lab")

# In-memory run state
RUNS: dict[str, dict] = {}

# Estado del job de produccion (uno solo a la vez)
PROD_JOB: dict = {
    "state": "idle",       # idle | running | paused | done | error
    "job_id": None,
    "model": "qwen3:8b",
    "prompt": "",
    "input_file": "",
    "output_file": "",
    "num_ctx": 4096,
    "temperature": 0.1,
    "start_time": None,
    "total": 0,
    "processed": 0,
    "results": [],          # ultimos 50 para live feed
    "all_results_count": 0,
    "distribution": {"KEEP": 0, "DISCARD": 0, "UNPARSEABLE": 0},
    "errors": {"timeout": 0, "unparseable": 0, "connection": 0, "details": []},
    "paused_event": None,   # asyncio.Event para pause/resume
    "cancelled": False,
    "item_times": [],       # timestamps de ultimos 20 items (para ETA)
}

RAW_DATA_DIR = Path(__file__).parents[2] / "raw_data" / "wiki"


# ----- Models -----


class RunRequest(BaseModel):
    task: str
    prompt: str
    model: str = "qwen3:8b"
    num_ctx: int = 4096
    temperature: float = 0.1


class SavePromptRequest(BaseModel):
    prompt: str
    accuracy: float | None = None


# ----- Helpers -----


def load_testset(task: str) -> list[dict]:
    path = TESTSETS_DIR / f"{task}.jsonl"
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_prompt(task: str) -> str:
    path = PROMPTS_DIR / f"{task}.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return TASK_CONFIG.get(task, {}).get("default_prompt", "")


def parse_classification(response: str, classes: list[str]) -> tuple[str, str]:
    """
    Parser tolerante: busca la clase en la respuesta y extrae la razon.
    Devuelve (classification, reason).

    Formatos aceptados:
    - "KEEP: This is a named character."
    - "KEEP — This is a named character."
    - "KEEP\nThis is a named character."
    - "KEEP" (sin razon)
    """
    r = response.strip()
    r_upper = r.upper()

    # Intentar parse estructurado: "CLASS: reason" o "CLASS — reason"
    for cls in classes:
        # Match "KEEP: reason" or "KEEP — reason" or "KEEP - reason"
        pattern = re.compile(
            rf"^{cls}\s*[:—\-–]\s*(.+)", re.IGNORECASE | re.DOTALL
        )
        m = pattern.match(r)
        if m:
            reason = m.group(1).strip().split("\n")[0].strip()  # primera linea
            return cls, reason

    # Fallback: busca clase en respuesta, usa el resto como razon
    found = [c for c in classes if c in r_upper]
    if len(found) == 1:
        # Extraer todo despues de la clase como razon
        idx = r_upper.index(found[0])
        after = r[idx + len(found[0]):].strip().lstrip(":—-–").strip()
        reason = after.split("\n")[0].strip() if after else ""
        return found[0], reason
    if len(found) > 1:
        positions = [(r_upper.index(c), c) for c in found]
        positions.sort()
        cls = positions[0][1]
        idx = r_upper.index(cls)
        after = r[idx + len(cls):].strip().lstrip(":—-–").strip()
        reason = after.split("\n")[0].strip() if after else ""
        return cls, reason

    return "UNPARSEABLE", r[:100]


# ----- API Endpoints -----


@app.get("/api/mac/stats")
def api_mac_stats():
    """Stats de la Mac Mini via SSH (RAM, CPU, swap)."""
    import subprocess
    try:
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=3", TUNNEL_HOST,
             "vm_stat | head -10; echo '---'; sysctl vm.swapusage; echo '---'; "
             "ps -A -o %cpu | awk '{s+=$1} END {printf \"cpu_total: %.0f\\n\", s}'; "
             "top -l 1 -n 0 | grep 'CPU usage'; "
             "sudo powermetrics --samplers thermal -i 1 -n 1 2>/dev/null | grep 'pressure level'"],
            capture_output=True, text=True, timeout=10,
        )
        lines = result.stdout.strip().split("\n")

        # Parse vm_stat
        page_size = 16384
        stats = {}
        for line in lines:
            if "Pages free" in line:
                stats["free_mb"] = int(line.split(":")[1].strip().rstrip(".")) * page_size // (1024 * 1024)
            elif "Pages active" in line:
                stats["active_mb"] = int(line.split(":")[1].strip().rstrip(".")) * page_size // (1024 * 1024)
            elif "Pages inactive" in line:
                stats["inactive_mb"] = int(line.split(":")[1].strip().rstrip(".")) * page_size // (1024 * 1024)
            elif "Pages wired" in line:
                stats["wired_mb"] = int(line.split(":")[1].strip().rstrip(".")) * page_size // (1024 * 1024)
            elif "swapusage" in line:
                # "vm.swapusage: total = 0.00M  used = 0.00M  free = 0.00M"
                parts = line.split()
                for j, p in enumerate(parts):
                    if p == "used":
                        stats["swap_used_mb"] = float(parts[j + 2].rstrip("M"))
            elif "CPU usage" in line:
                stats["cpu_line"] = line.strip()
            elif "pressure level" in line:
                # "Current pressure level: Nominal"
                level = line.split(":")[-1].strip()
                stats["thermal"] = level

        total = 16 * 1024  # 16GB
        used = stats.get("active_mb", 0) + stats.get("wired_mb", 0)
        available = stats.get("free_mb", 0) + stats.get("inactive_mb", 0)
        stats["used_mb"] = used
        stats["available_mb"] = available
        stats["total_mb"] = total
        stats["used_pct"] = round(used / total * 100, 1)
        stats["swap_used_mb"] = stats.get("swap_used_mb", 0)

        return stats
    except Exception as e:
        return {"error": str(e)}


@app.on_event("startup")
def on_startup():
    """Auto-open SSH tunnel on server start."""
    ok, msg = ensure_tunnel()
    if ok:
        log = __import__("logging").getLogger(__name__)
        log.info(f"SSH tunnel: {msg}")
    else:
        log = __import__("logging").getLogger(__name__)
        log.warning(f"SSH tunnel failed: {msg}")


@app.get("/api/connection")
def api_connection():
    ok, msg = check_connection()
    if not ok:
        # Try to open/reopen tunnel automatically
        tok, tmsg = ensure_tunnel()
        if tok:
            # Re-check after tunnel opened
            ok, msg = check_connection()
            if ok:
                msg += " (tunnel reopened)"
    return {"ok": ok, "msg": msg}


@app.get("/api/tasks")
def api_tasks():
    """Lista tasks con su config basica."""
    tasks = []
    for name, cfg in TASK_CONFIG.items():
        testset = load_testset(name)
        tasks.append(
            {
                "name": name,
                "mode": cfg["mode"],
                "classes": cfg.get("classes"),
                "testset_size": len(testset),
            }
        )
    return tasks


@app.get("/api/task/{task}")
def api_task(task: str):
    if task not in TASK_CONFIG:
        raise HTTPException(404, f"Task '{task}' not found")
    cfg = TASK_CONFIG[task]
    testset = load_testset(task)
    prompt = load_prompt(task)

    # Distribution
    dist: dict[str, int] = {}
    for item in testset:
        e = item.get("expected", "UNKNOWN")
        dist[e] = dist.get(e, 0) + 1

    return {
        "name": task,
        "mode": cfg["mode"],
        "classes": cfg.get("classes"),
        "prompt": prompt,
        "testset": testset,
        "distribution": dist,
    }


@app.post("/api/task/{task}/prompt")
def api_save_prompt(task: str, body: SavePromptRequest):
    if task not in TASK_CONFIG:
        raise HTTPException(404)
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    path = PROMPTS_DIR / f"{task}.txt"
    path.write_text(body.prompt, encoding="utf-8")

    # Also history
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    hist = HISTORY_DIR / f"{task}_{ts}.json"
    hist.write_text(
        json.dumps(
            {"timestamp": ts, "prompt": body.prompt, "accuracy": body.accuracy},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return {"saved_to": str(path)}


@app.get("/api/ollama/models")
def api_ollama_models():
    """Lista modelos disponibles en Ollama."""
    try:
        import requests as req
        r = req.get("http://localhost:11434/api/tags", timeout=5)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        return {"models": models}
    except Exception as e:
        return {"models": [], "error": str(e)}


@app.post("/api/run")
async def api_run(body: RunRequest):
    if body.task not in TASK_CONFIG:
        raise HTTPException(404)

    testset = load_testset(body.task)
    if not testset:
        raise HTTPException(400, "Testset vacio")

    run_id = uuid.uuid4().hex[:8]
    RUNS[run_id] = {
        "task": body.task,
        "prompt": body.prompt,
        "model": body.model,
        "num_ctx": body.num_ctx,
        "temperature": body.temperature,
        "items": [],
        "done": False,
        "cancelled": False,
        "start_time": time.time(),
        "end_time": None,
        "total": len(testset),
        "testset": testset,
        "current_idx": -1,
    }

    # Spawn background task
    asyncio.create_task(execute_run(run_id))

    return {"run_id": run_id, "total": len(testset)}


@app.post("/api/run/{run_id}/cancel")
def api_cancel(run_id: str):
    if run_id not in RUNS:
        raise HTTPException(404)
    RUNS[run_id]["cancelled"] = True
    return {"ok": True}


async def execute_run(run_id: str):
    """Corre el prompt sobre el testset, secuencial o paralelo."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    state = RUNS[run_id]
    cfg = TASK_CONFIG[state["task"]]
    testset = state["testset"]
    model = state.get("model", "qwen3:8b")
    parallel = max(1, state.get("parallel_workers", 1))

    def process_item(i: int, item: dict) -> dict:
        """Procesa un item. Thread-safe."""
        if state["cancelled"]:
            return None

        text_truncated = prepare_input(item.get("text", ""), max_words=800)
        prompt_rendered = state["prompt"].format(
            title=item.get("title", ""), text=text_truncated
        )

        item_start = time.time()
        try:
            result = generate(
                prompt_rendered,
                model=model,
                num_ctx=state["num_ctx"],
                temperature=state["temperature"],
            )
            raw = result.response
            duration = result.total_duration_s
            eval_count = result.eval_count
            error = None
        except Exception as e:
            raw = ""
            duration = time.time() - item_start
            eval_count = 0
            error = str(e)

        reason = ""
        if cfg["mode"] == "classify":
            actual, reason = parse_classification(raw, cfg["classes"])
            expected = item.get("expected", "")
            if not expected or expected.upper() == "UNKNOWN":
                match = None
            else:
                match = actual == expected.upper()
        else:
            actual = raw
            expected = item.get("expected", "")
            match = None

        return {
            "idx": i,
            "title": item.get("title", ""),
            "input_preview": text_truncated,
            "expected": expected,
            "actual": actual,
            "reason": reason,
            "raw_response": raw,
            "match": match,
            "duration": duration,
            "eval_count": eval_count,
            "error": error,
        }

    for i, item in enumerate(testset):
        if state["cancelled"]:
            break
        state["current_idx"] = i
        result = await asyncio.to_thread(process_item, i, item)
        state["current_idx"] = -1
        if result is not None:
            state["items"].append(result)

    state["done"] = True
    state["end_time"] = time.time()

    # Auto-persist last_run
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    last_path = HISTORY_DIR / f"{state['task']}_last_run.json"
    evaluated = [it for it in state["items"] if it.get("match") is not None]
    correct = sum(1 for it in evaluated if it["match"])
    total_evaluated = len(evaluated)
    last_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "task": state["task"],
                "timestamp": datetime.now().isoformat(),
                "model": state.get("model", "qwen3:8b"),
                "prompt": state["prompt"],
                "num_ctx": state["num_ctx"],
                "temperature": state["temperature"],
                "duration_total": state["end_time"] - state["start_time"],
                "accuracy": {
                    "correct": correct,
                    "total": total_evaluated,
                    "pct": correct / total_evaluated * 100 if total_evaluated > 0 else 0,
                },
                "items": state["items"],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


@app.get("/api/run/{run_id}/state")
def api_run_state(run_id: str):
    """
    Devuelve el estado actual del run (para reanudar UI despues de refresh).
    """
    state = RUNS.get(run_id)
    if not state:
        raise HTTPException(404, f"Run {run_id} not found")
    return {
        "run_id": run_id,
        "task": state["task"],
        "prompt": state["prompt"],
        "num_ctx": state["num_ctx"],
        "temperature": state["temperature"],
        "total": state["total"],
        "done": state["done"],
        "cancelled": state["cancelled"],
        "start_time": state["start_time"],
        "end_time": state["end_time"],
        "items": state["items"],
    }


@app.get("/api/run/{run_id}/events")
async def api_events(run_id: str, request: Request):
    if run_id not in RUNS:
        raise HTTPException(404)

    async def event_stream():
        last_idx = 0
        last_running = -1
        while True:
            if await request.is_disconnected():
                return
            state = RUNS.get(run_id)
            if state is None:
                yield 'event: error\ndata: {"error":"run not found"}\n\n'
                return

            # Stream current processing item
            cur = state.get("current_idx", -1)
            if cur != last_running:
                if cur >= 0:
                    payload = json.dumps({"idx": cur})
                    yield f"event: running\ndata: {payload}\n\n"
                last_running = cur

            # Stream new items
            while last_idx < len(state["items"]):
                item = state["items"][last_idx]
                payload = {
                    "idx": item["idx"],
                    "total": state["total"],
                    "title": item["title"],
                    "expected": item["expected"],
                    "actual": item["actual"],
                    "reason": item.get("reason", ""),
                    "raw_response": item["raw_response"],
                    "input_preview": item["input_preview"],
                    "match": item["match"],
                    "duration": item["duration"],
                    "error": item["error"],
                    "elapsed_total": time.time() - state["start_time"],
                }
                yield f"event: item\ndata: {json.dumps(payload)}\n\n"
                last_idx += 1

            if state["done"]:
                yield f'event: done\ndata: {json.dumps({"duration":state["end_time"]-state["start_time"]})}\n\n'
                return

            await asyncio.sleep(0.1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ============================================================
# Production job endpoints
# ============================================================


class ProdStartRequest(BaseModel):
    model: str = "qwen3:8b"
    prompt: str
    input_file: str = "articles_cleaned.jsonl"   # relativo a raw_data/wiki/
    output_file: str = "spinoffs_classified.jsonl"  # relativo a raw_data/wiki/
    num_ctx: int = 4096
    temperature: float = 0.1


def _reset_prod_job():
    """Resetea PROD_JOB a estado idle."""
    PROD_JOB.update({
        "state": "idle",
        "job_id": None,
        "model": "qwen3:8b",
        "prompt": "",
        "input_file": "",
        "output_file": "",
        "num_ctx": 4096,
        "temperature": 0.1,
        "start_time": None,
        "total": 0,
        "processed": 0,
        "results": [],
        "all_results_count": 0,
        "distribution": {"KEEP": 0, "DISCARD": 0, "UNPARSEABLE": 0},
        "errors": {"timeout": 0, "unparseable": 0, "connection": 0, "details": []},
        "paused_event": None,
        "cancelled": False,
        "item_times": [],
    })


@app.post("/api/prod/start")
async def api_prod_start(body: ProdStartRequest):
    if PROD_JOB["state"] == "running":
        raise HTTPException(409, "Ya hay un job en ejecucion")

    input_path = RAW_DATA_DIR / body.input_file
    output_path = RAW_DATA_DIR / body.output_file

    if not input_path.exists():
        raise HTTPException(404, f"Input file not found: {input_path}")

    # Leer items del JSONL — filtrar solo spin-offs
    SPINOFF_PREFIXES = ("Dungeons:", "MCD:", "Legends:", "Earth:", "Story Mode:")
    with open(input_path, "r", encoding="utf-8") as f:
        all_items = [json.loads(line) for line in f if line.strip()]
    items = [it for it in all_items if any(it.get("title", "").startswith(p) for p in SPINOFF_PREFIXES)]
    import logging
    log = logging.getLogger(__name__)
    log.info("Prod: %d spinoff items de %d total en %s", len(items), len(all_items), input_path.name)

    if not items:
        raise HTTPException(400, "Input file vacio")

    # Resume: contar lineas ya procesadas en output
    already_done = 0
    if output_path.exists():
        with open(output_path, "r", encoding="utf-8") as f:
            already_done = sum(1 for line in f if line.strip())

    _reset_prod_job()
    job_id = uuid.uuid4().hex[:8]
    PROD_JOB.update({
        "state": "running",
        "job_id": job_id,
        "model": body.model,
        "prompt": body.prompt,
        "input_file": body.input_file,
        "output_file": body.output_file,
        "num_ctx": body.num_ctx,
        "temperature": body.temperature,
        "start_time": time.time(),
        "total": len(items),
        "processed": already_done,
        "all_results_count": already_done,
        "paused_event": asyncio.Event(),
        "cancelled": False,
    })
    # Event empieza en "set" (no pausado)
    PROD_JOB["paused_event"].set()

    # Reconstruir distribucion de items ya procesados
    if already_done > 0:
        with open(output_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    row = json.loads(line)
                    cls = row.get("classification", "UNPARSEABLE")
                    if cls in PROD_JOB["distribution"]:
                        PROD_JOB["distribution"][cls] += 1

    asyncio.create_task(_execute_prod_job(items, already_done, output_path))

    return {
        "job_id": job_id,
        "total": len(items),
        "resuming_from": already_done,
    }


async def _execute_prod_job(items: list[dict], skip: int, output_path: Path):
    """Procesa items secuencialmente, escribiendo resultados al JSONL."""
    import logging
    log = logging.getLogger(__name__)

    # Determinar clases del task (usamos spinoff_classifier por defecto)
    classes = ["KEEP", "DISCARD"]
    for cfg in TASK_CONFIG.values():
        if cfg.get("classes"):
            classes = cfg["classes"]
            break

    # Cola de eventos SSE para broadcast
    PROD_JOB.setdefault("_event_queue", [])

    for i in range(skip, len(items)):
        # Check cancel
        if PROD_JOB["cancelled"]:
            PROD_JOB["state"] = "idle"
            log.info("Prod job cancelado en item %d/%d", i, len(items))
            return

        # Check pause — bloquea hasta que se haga resume
        await PROD_JOB["paused_event"].wait()

        item = items[i]
        text_truncated = prepare_input(item.get("text", ""), max_words=800)
        prompt_rendered = PROD_JOB["prompt"].format(
            title=item.get("title", ""), text=text_truncated
        )

        item_start = time.time()
        error = None
        raw = ""
        duration = 0
        MAX_RETRIES = 3

        for attempt in range(MAX_RETRIES):
            try:
                result = await asyncio.to_thread(
                    generate,
                    prompt_rendered,
                    model=PROD_JOB["model"],
                    num_ctx=PROD_JOB["num_ctx"],
                    temperature=PROD_JOB["temperature"],
                )
                raw = result.response
                duration = result.total_duration_s
                error = None
                break  # exito
            except _requests.exceptions.ConnectionError:
                error = "connection"
                # Intentar reabrir tunnel y reintentar
                import logging as _log
                _log.getLogger(__name__).warning(
                    "Prod item %d: connection error (attempt %d/%d), reopening tunnel...",
                    i, attempt + 1, MAX_RETRIES,
                )
                ensure_tunnel()
                await asyncio.sleep(5)  # esperar a que tunnel se estabilice
            except _requests.exceptions.Timeout:
                error = "timeout"
                _log_mod = __import__("logging")
                _log_mod.getLogger(__name__).warning(
                    "Prod item %d: timeout (attempt %d/%d)", i, attempt + 1, MAX_RETRIES,
                )
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(3)
            except Exception as e:
                error = str(e)
                break  # error desconocido, no reintentar

        duration = duration or (time.time() - item_start)

        if error == "connection":
            PROD_JOB["errors"]["connection"] += 1
        elif error == "timeout":
            PROD_JOB["errors"]["timeout"] += 1

        classification, reason = parse_classification(raw, classes)

        if classification == "UNPARSEABLE" and error is None:
            PROD_JOB["errors"]["unparseable"] += 1

        # Tracking de errores detallados (ultimos 20)
        if error:
            PROD_JOB["errors"]["details"].append({
                "idx": i, "title": item.get("title", ""), "error": error,
            })
            if len(PROD_JOB["errors"]["details"]) > 20:
                PROD_JOB["errors"]["details"] = PROD_JOB["errors"]["details"][-20:]

        # Actualizar distribucion
        if classification in PROD_JOB["distribution"]:
            PROD_JOB["distribution"][classification] += 1

        # Resultado para archivo y feed
        row = {
            "idx": i,
            "title": item.get("title", ""),
            "classification": classification,
            "reason": reason,
            "duration": round(duration, 2),
            "error": error,
            "input_preview": text_truncated,
            "raw_response": raw,
        }

        # Solo escribir al JSONL si la clasificacion es valida (no UNPARSEABLE)
        if classification in ("KEEP", "DISCARD"):
            with open(output_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

            if classification == "DISCARD":
                discard_path = output_path.parent / (output_path.stem + "_discarded.jsonl")
                with open(discard_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
        else:
            # UNPARSEABLE: loggear pero NO escribir al output (se reintentara en resume)
            import logging as _log_mod
            _log_mod.getLogger(__name__).warning(
                "Prod item %d UNPARSEABLE (no escrito al output, se reintentara): %s",
                i, item.get("title", ""),
            )

        # Actualizar estado en memoria
        PROD_JOB["processed"] = i + 1
        PROD_JOB["all_results_count"] = i + 1
        PROD_JOB["results"].append(row)
        if len(PROD_JOB["results"]) > 50:
            PROD_JOB["results"] = PROD_JOB["results"][-50:]

        # Tracking de tiempos para ETA (ultimos 20)
        PROD_JOB["item_times"].append(time.time())
        if len(PROD_JOB["item_times"]) > 20:
            PROD_JOB["item_times"] = PROD_JOB["item_times"][-20:]

        # Eventos SSE
        evt_item = {
            "type": "item",
            "data": {
                "idx": i, "title": item.get("title", ""),
                "classification": classification, "reason": reason,
                "duration": round(duration, 2), "error": error,
                "input_preview": text_truncated[:500],  # truncado para SSE
                "raw_response": raw[:500],
            },
        }
        PROD_JOB.setdefault("_events", []).append(evt_item)

        # Persistir metricas cada 10 items (para graficas post-mortem)
        if (i + 1) % 10 == 0:
            try:
                import subprocess
                mac_result = subprocess.run(
                    ["ssh", "-o", "ConnectTimeout=3", TUNNEL_HOST,
                     "vm_stat | head -6; echo '---'; sysctl vm.swapusage"],
                    capture_output=True, text=True, timeout=8,
                )
                mac_lines = mac_result.stdout
            except Exception:
                mac_lines = ""

            metrics_path = HISTORY_DIR / f"prod_metrics_{PROD_JOB['job_id']}.jsonl"
            metric = {
                "ts": time.time(),
                "elapsed": round(time.time() - PROD_JOB["start_time"], 1),
                "processed": PROD_JOB["processed"],
                "items_per_min": round(_calc_items_per_min() or 0, 2),
                "distribution": dict(PROD_JOB["distribution"]),
                "errors_total": sum(v for k, v in PROD_JOB["errors"].items() if k != "details"),
                "mac_stats_raw": mac_lines[:500],
            }
            with open(metrics_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(metric, ensure_ascii=False) + "\n")

        # Progreso cada 5 items
        if (i + 1) % 5 == 0 or i == len(items) - 1:
            elapsed = time.time() - PROD_JOB["start_time"]
            eta = _calc_eta()
            ipm = _calc_items_per_min()
            evt_progress = {
                "type": "progress",
                "data": {
                    "processed": PROD_JOB["processed"],
                    "total": PROD_JOB["total"],
                    "elapsed": round(elapsed, 1),
                    "eta": round(eta, 1) if eta else None,
                    "items_per_min": round(ipm, 2) if ipm else None,
                },
            }
            PROD_JOB.setdefault("_events", []).append(evt_progress)

    # Job completado
    PROD_JOB["state"] = "done"
    total_duration = time.time() - PROD_JOB["start_time"]
    log.info("Prod job completado: %d items en %.1fs", PROD_JOB["total"], total_duration)

    evt_done = {
        "type": "done",
        "data": {
            "total_duration": round(total_duration, 1),
            "distribution": PROD_JOB["distribution"],
            "errors": {k: v for k, v in PROD_JOB["errors"].items() if k != "details"},
        },
    }
    PROD_JOB.setdefault("_events", []).append(evt_done)

    # Guardar metadata en history/
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    meta_path = HISTORY_DIR / f"prod_{PROD_JOB['job_id']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    meta_path.write_text(
        json.dumps({
            "job_id": PROD_JOB["job_id"],
            "model": PROD_JOB["model"],
            "input_file": PROD_JOB["input_file"],
            "output_file": PROD_JOB["output_file"],
            "num_ctx": PROD_JOB["num_ctx"],
            "temperature": PROD_JOB["temperature"],
            "total": PROD_JOB["total"],
            "processed": PROD_JOB["processed"],
            "duration": round(total_duration, 1),
            "distribution": PROD_JOB["distribution"],
            "errors": {k: v for k, v in PROD_JOB["errors"].items() if k != "details"},
            "timestamp": datetime.now().isoformat(),
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _calc_eta() -> float | None:
    """ETA basado en rolling average de ultimos 20 items."""
    times = PROD_JOB["item_times"]
    if len(times) < 2:
        return None
    window = times[-20:]
    avg_per_item = (window[-1] - window[0]) / (len(window) - 1)
    remaining = PROD_JOB["total"] - PROD_JOB["processed"]
    return avg_per_item * remaining


def _calc_items_per_min() -> float | None:
    """Items/min basado en los ultimos 5 minutos."""
    now = time.time()
    times = PROD_JOB["item_times"]
    if not times:
        return None
    cutoff = now - 300  # 5 minutos
    recent = [t for t in times if t > cutoff]
    if len(recent) < 2:
        # Fallback: usar todos los tiempos disponibles
        if len(times) < 2:
            return None
        elapsed = times[-1] - times[0]
        if elapsed <= 0:
            return None
        return (len(times) - 1) / (elapsed / 60)
    elapsed = recent[-1] - recent[0]
    if elapsed <= 0:
        return None
    return (len(recent) - 1) / (elapsed / 60)


@app.post("/api/prod/pause")
def api_prod_pause():
    if PROD_JOB["state"] != "running":
        raise HTTPException(409, f"Job no esta corriendo (state={PROD_JOB['state']})")
    PROD_JOB["paused_event"].clear()
    PROD_JOB["state"] = "paused"
    return {"ok": True, "state": "paused"}


@app.post("/api/prod/resume")
def api_prod_resume():
    if PROD_JOB["state"] != "paused":
        raise HTTPException(409, f"Job no esta pausado (state={PROD_JOB['state']})")
    PROD_JOB["state"] = "running"
    PROD_JOB["paused_event"].set()
    return {"ok": True, "state": "running"}


@app.post("/api/prod/cancel")
def api_prod_cancel():
    if PROD_JOB["state"] not in ("running", "paused"):
        raise HTTPException(409, f"No hay job activo (state={PROD_JOB['state']})")
    PROD_JOB["cancelled"] = True
    # Si estaba pausado, desbloquearlo para que pueda terminar
    if PROD_JOB["paused_event"]:
        PROD_JOB["paused_event"].set()
    return {"ok": True, "state": "idle"}


@app.get("/api/prod/status")
def api_prod_status():
    elapsed = None
    if PROD_JOB["start_time"]:
        elapsed = round(time.time() - PROD_JOB["start_time"], 1)

    return {
        "state": PROD_JOB["state"],
        "job_id": PROD_JOB["job_id"],
        "model": PROD_JOB["model"],
        "input_file": PROD_JOB["input_file"],
        "output_file": PROD_JOB["output_file"],
        "processed": PROD_JOB["processed"],
        "total": PROD_JOB["total"],
        "elapsed": elapsed,
        "eta_seconds": round(_calc_eta(), 1) if _calc_eta() else None,
        "items_per_min": round(_calc_items_per_min(), 2) if _calc_items_per_min() else None,
        "distribution": PROD_JOB["distribution"],
        "errors": {k: v for k, v in PROD_JOB["errors"].items() if k != "details"},
    }


@app.get("/api/prod/events")
async def api_prod_events(request: Request):
    """SSE stream de eventos del job de produccion."""
    async def event_stream():
        last_idx = 0
        events_list = PROD_JOB.setdefault("_events", [])
        while True:
            if await request.is_disconnected():
                return

            # Enviar eventos nuevos
            while last_idx < len(events_list):
                evt = events_list[last_idx]
                yield f"event: {evt['type']}\ndata: {json.dumps(evt['data'])}\n\n"
                last_idx += 1

            if PROD_JOB["state"] in ("idle", "done", "error"):
                # Mandar los ultimos eventos pendientes y salir
                while last_idx < len(events_list):
                    evt = events_list[last_idx]
                    yield f"event: {evt['type']}\ndata: {json.dumps(evt['data'])}\n\n"
                    last_idx += 1
                return

            await asyncio.sleep(0.2)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/prod/feed")
def api_prod_feed():
    """Ultimos 50 items procesados (para carga inicial tras refresh)."""
    return {
        "items": PROD_JOB["results"],
        "processed": PROD_JOB["processed"],
        "total": PROD_JOB["total"],
        "state": PROD_JOB["state"],
    }


@app.get("/api/prod/history")
def api_prod_history():
    """Lista de runs de produccion anteriores."""
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    runs = []
    for p in sorted(HISTORY_DIR.glob("prod_*.json"), reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            runs.append(data)
        except Exception:
            continue
    return runs


# ----- Static files -----

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def root():
    return FileResponse(str(STATIC_DIR / "index.html"))


if __name__ == "__main__":
    import uvicorn

    print("\n" + "=" * 60)
    print("Antes de usar: abrir SSH tunnel en otra terminal:")
    print("  ssh -L 11434:localhost:11434 felipe@mini-fzamorano")
    print("=" * 60 + "\n")
    uvicorn.run(
        "scraper.prompt_lab.server:app",
        host="127.0.0.1",
        port=7860,
        reload=False,
        log_level="info",
    )
