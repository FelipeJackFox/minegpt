"""
state_manager.py — Persistencia de Phase 4.0.

Maneja:
- bucket_status.json     (state por bucket, atomic write)
- article_exclusions.jsonl (append-only event log)
- run_history.jsonl      (append-only event log)
- run_queue.json         (current + queued, atomic write)

Single-user, single-process. Usa threading.Lock para concurrencia in-process
y os.replace() para atomic write cross-platform (Windows + Unix).
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from scraper.prompt_lab.state import (
    BucketState,
    ExclusionAction,
    ExclusionEntry,
    ExclusionScope,
    ExclusionState,
    RunHistoryEntry,
    RunMode,
    RunPhase,
    RunQueueItem,
    RunQueueProgress,
    RunQueueState,
)

# ============================================================
# Paths
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = PROJECT_ROOT / "raw_data" / "_pipeline_state"

BUCKET_STATUS_PATH = STATE_DIR / "bucket_status.json"
EXCLUSIONS_PATH = STATE_DIR / "article_exclusions.jsonl"
RUN_HISTORY_PATH = STATE_DIR / "run_history.jsonl"
RUN_QUEUE_PATH = STATE_DIR / "run_queue.json"


# ============================================================
# Locks (in-process)
# ============================================================

_bucket_lock = threading.Lock()
_exclusions_lock = threading.Lock()
_history_lock = threading.Lock()
_queue_lock = threading.Lock()


# ============================================================
# Utils
# ============================================================


def now_iso() -> str:
    """ISO 8601 UTC with Z suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_run_id() -> str:
    return f"r_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"


def hash_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _atomic_write_json(path: Path, data: dict) -> None:
    """Atomic write: tempfile en mismo dir + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _append_jsonl(path: Path, obj: dict) -> None:
    """Append una linea JSON al archivo. Crea archivo si no existe."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(obj, ensure_ascii=False)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    """Lee JSONL skipping lineas malformadas (warning logged)."""
    if not path.exists():
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for i, raw in enumerate(f, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                out.append(json.loads(raw))
            except json.JSONDecodeError as e:
                # Skip + log; do not crash
                print(f"[state_manager] Skipping malformed line {i} in {path.name}: {e}")
    return out


# ============================================================
# Bucket status
# ============================================================


def load_bucket_status() -> dict[str, BucketState]:
    """Carga bucket_status.json. Devuelve dict de BucketState por bucket name."""
    if not BUCKET_STATUS_PATH.exists():
        return {}
    with open(BUCKET_STATUS_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    out = {}
    for name, state in raw.items():
        # Legacy migration: qa_status "blocked" -> "not_started" (Q&A is now
        # independent of transform; pre-transform text is the source).
        if state.get("qa_status") == "blocked":
            state["qa_status"] = "not_started"
        out[name] = BucketState(**state)
    return out


def save_bucket_status(states: dict[str, BucketState]) -> None:
    """Guarda atomic. Convierte BucketState a dict."""
    data = {name: s.model_dump() for name, s in states.items()}
    _atomic_write_json(BUCKET_STATUS_PATH, data)


def update_bucket_state(bucket: str, **fields) -> BucketState:
    """
    Update parcial del state de un bucket. Crea entry si no existe.

    Si el bucket no existe en el file, requiere `ambiente` y `family` en fields.
    Actualiza last_touched_at automaticamente.
    """
    with _bucket_lock:
        states = load_bucket_status()
        if bucket not in states:
            if "ambiente" not in fields or "family" not in fields:
                raise ValueError(
                    f"Bucket {bucket!r} not in state; need ambiente+family to create"
                )
            states[bucket] = BucketState(**fields)
        else:
            current = states[bucket].model_dump()
            current.update(fields)
            states[bucket] = BucketState(**current)

        states[bucket].last_touched_at = now_iso()
        save_bucket_status(states)
        return states[bucket]


def get_bucket_state(bucket: str) -> Optional[BucketState]:
    states = load_bucket_status()
    return states.get(bucket)


def approve_bucket_phase(bucket: str, phase: RunPhase) -> BucketState:
    """Marca user_approved=true. No cambia el status (se asume completed)."""
    field = f"{phase}_user_approved"
    return update_bucket_state(bucket, **{field: True})


def skip_bucket(bucket: str, reason: str) -> BucketState:
    return update_bucket_state(
        bucket,
        transform_status="skipped",
        skipped_reason=reason,
        skipped_at=now_iso(),
    )


def force_transform_bucket(bucket: str) -> BucketState:
    """Override skipped status para forzar transform."""
    state = get_bucket_state(bucket)
    if state and state.transform_status == "skipped":
        return update_bucket_state(
            bucket,
            transform_status="not_started",
            force_transform=True,
            skipped_reason=None,
            skipped_at=None,
        )
    return update_bucket_state(bucket, force_transform=True)


# ============================================================
# Exclusions (append-only event log + derived state)
# ============================================================


def append_exclusion(entry: ExclusionEntry) -> None:
    """Append entry al log. No deriva ni valida estado actual."""
    with _exclusions_lock:
        _append_jsonl(EXCLUSIONS_PATH, entry.model_dump())


def all_exclusion_events() -> list[ExclusionEntry]:
    """Lee todo el log. Skip lineas malformadas."""
    raw = _read_jsonl(EXCLUSIONS_PATH)
    out = []
    for r in raw:
        try:
            out.append(ExclusionEntry(**r))
        except Exception as e:
            print(f"[state_manager] Skipping invalid exclusion entry: {e}")
    return out


def _apply_action(state: ExclusionState, action: ExclusionAction, scope: ExclusionScope, ts: str, reason: Optional[str]) -> None:
    """Mutate state based on action+scope."""
    is_global = scope == "all_lenses"
    if action == "exclude_transform":
        state.transform_excluded = True
        if is_global:
            state.transform_excluded_global = True
    elif action == "exclude_qa":
        state.qa_excluded = True
        if is_global:
            state.qa_excluded_global = True
    elif action == "exclude_both":
        state.transform_excluded = True
        state.qa_excluded = True
        if is_global:
            state.transform_excluded_global = True
            state.qa_excluded_global = True
    elif action == "include_transform":
        state.transform_excluded = False
        state.transform_excluded_global = False
    elif action == "include_qa":
        state.qa_excluded = False
        state.qa_excluded_global = False
    elif action == "include_both":
        state.transform_excluded = False
        state.qa_excluded = False
        state.transform_excluded_global = False
        state.qa_excluded_global = False
    state.last_change_ts = ts
    state.last_reason = reason


def derive_exclusion_state(title: str, bucket_lens: str) -> ExclusionState:
    """
    Estado actual de (title, bucket_lens).

    Aplica eventos en orden cronologico. Eventos con scope=all_lenses afectan
    cualquier bucket. Eventos con scope=this_lens solo afectan el matching.
    """
    events = all_exclusion_events()
    state = ExclusionState(title=title, bucket_lens=bucket_lens)

    for e in events:
        if e.title != title:
            continue
        # all_lenses event with bucket_lens="*" applies to any bucket
        applies = (
            (e.scope == "all_lenses")
            or (e.scope == "this_lens" and e.bucket_lens == bucket_lens)
        )
        if not applies:
            continue
        _apply_action(state, e.action, e.scope, e.ts, e.reason)
    return state


def derive_exclusions_for_bucket(bucket_lens: str, titles: list[str]) -> dict[str, ExclusionState]:
    """
    Deriva estados de exclusion para una lista de titles dentro de un bucket.
    Una sola pasada por el archivo. O(events + titles).
    """
    events = all_exclusion_events()
    titles_set = set(titles)
    states = {t: ExclusionState(title=t, bucket_lens=bucket_lens) for t in titles}

    for e in events:
        if e.title not in titles_set:
            continue
        applies = (
            (e.scope == "all_lenses")
            or (e.scope == "this_lens" and e.bucket_lens == bucket_lens)
        )
        if not applies:
            continue
        _apply_action(states[e.title], e.action, e.scope, e.ts, e.reason)
    return states


def exclusion_history_for_title(title: str) -> list[ExclusionEntry]:
    """Audit log completo para un title (cualquier bucket)."""
    return [e for e in all_exclusion_events() if e.title == title]


# ============================================================
# Run history (append-only)
# ============================================================


def append_run_history(entry: RunHistoryEntry) -> None:
    with _history_lock:
        _append_jsonl(RUN_HISTORY_PATH, entry.model_dump())


def load_run_history(bucket: Optional[str] = None) -> list[RunHistoryEntry]:
    raw = _read_jsonl(RUN_HISTORY_PATH)
    out = []
    for r in raw:
        try:
            entry = RunHistoryEntry(**r)
        except Exception as e:
            print(f"[state_manager] Skipping invalid run history: {e}")
            continue
        if bucket and entry.bucket_lens != bucket:
            continue
        out.append(entry)
    return out


def find_run_history(run_id: str) -> Optional[RunHistoryEntry]:
    for entry in load_run_history():
        if entry.run_id == run_id:
            return entry
    return None


def update_run_history(run_id: str, **fields) -> None:
    """
    Update de un entry existente. Reescribe el archivo entero (run_history es
    append-only por convencion pero permitimos update para marcar status final).

    Para append-only puro, alternativa: append un nuevo entry con mismo run_id
    y al leer tomar el ultimo. Por ahora reescribimos para simplicidad.
    """
    with _history_lock:
        entries = load_run_history()
        found = False
        for i, e in enumerate(entries):
            if e.run_id == run_id:
                d = e.model_dump()
                d.update(fields)
                entries[i] = RunHistoryEntry(**d)
                found = True
                break
        if not found:
            return
        # Reescribir
        RUN_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            prefix=RUN_HISTORY_PATH.name + ".", suffix=".tmp",
            dir=str(RUN_HISTORY_PATH.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                for entry in entries:
                    f.write(json.dumps(entry.model_dump(), ensure_ascii=False) + "\n")
            os.replace(tmp, RUN_HISTORY_PATH)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


# ============================================================
# Run queue
# ============================================================


def load_run_queue() -> RunQueueState:
    if not RUN_QUEUE_PATH.exists():
        return RunQueueState()
    with open(RUN_QUEUE_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return RunQueueState(**raw)


def save_run_queue(state: RunQueueState) -> None:
    _atomic_write_json(RUN_QUEUE_PATH, state.model_dump())


def enqueue_run(
    bucket_lens: str,
    phase: RunPhase,
    mode: RunMode,
    include_secondaries: bool = False,
    prompt_draft_path: Optional[str] = None,
    max_queue: int = 3,
    model: str = "qwen3:8b",
    num_ctx: int = 4096,
    temperature: float = 0.0,
    no_think: bool = True,
) -> RunQueueItem:
    """
    Agrega un run al queue. Si no hay current, lo deja en queued (el caller
    decide cuando promoverlo a current via promote_next_to_current).

    Lanza ValueError si queue lleno.
    """
    with _queue_lock:
        state = load_run_queue()
        if len(state.queued) >= max_queue:
            raise ValueError(f"Queue is full (max {max_queue})")
        item = RunQueueItem(
            run_id=new_run_id(),
            bucket_lens=bucket_lens,
            phase=phase,
            mode=mode,
            include_secondaries=include_secondaries,
            enqueued_at=now_iso(),
            prompt_draft_path=prompt_draft_path,
            model=model,
            num_ctx=num_ctx,
            temperature=temperature,
            no_think=no_think,
        )
        state.queued.append(item)
        save_run_queue(state)
        return item


def promote_next_to_current() -> Optional[RunQueueItem]:
    """
    Si no hay current y hay queued, mueve el primero a current con started_at.
    Devuelve el item promovido, o None si nada que hacer.
    """
    with _queue_lock:
        state = load_run_queue()
        if state.current is not None:
            return None
        if not state.queued:
            return None
        item = state.queued.pop(0)
        item.started_at = now_iso()
        state.current = item
        save_run_queue(state)
        return item


def set_current_run(item: RunQueueItem) -> None:
    """Set current directamente (skipping queue)."""
    with _queue_lock:
        state = load_run_queue()
        state.current = item
        save_run_queue(state)


def update_current_progress(
    done: int,
    total: int,
    errors: int,
    current_title: Optional[str] = None,
    current_item_started_at: Optional[str] = None,
    last_item_duration: Optional[float] = None,
) -> None:
    """Update the live progress fields. Pass-through Nones leave the existing
    value unchanged (so the worker can update done/errors without clobbering
    current_title)."""
    with _queue_lock:
        state = load_run_queue()
        if state.current is None:
            return
        prev = state.current.progress
        state.current.progress = RunQueueProgress(
            done=done,
            total=total,
            errors=errors,
            current_title=current_title if current_title is not None else prev.current_title,
            current_item_started_at=(
                current_item_started_at
                if current_item_started_at is not None
                else prev.current_item_started_at
            ),
            last_item_duration=(
                last_item_duration
                if last_item_duration is not None
                else prev.last_item_duration
            ),
        )
        save_run_queue(state)


def update_current_item(title: Optional[str], started_at: Optional[str]) -> None:
    """Set just the 'currently processing' fields. Used at item start."""
    with _queue_lock:
        state = load_run_queue()
        if state.current is None:
            return
        state.current.progress.current_title = title
        state.current.progress.current_item_started_at = started_at
        save_run_queue(state)


def clear_current_run() -> Optional[RunQueueItem]:
    """Quita current. Devuelve el item que estaba ahi."""
    with _queue_lock:
        state = load_run_queue()
        prev = state.current
        state.current = None
        save_run_queue(state)
        return prev


def cancel_queued_run(run_id: str) -> bool:
    with _queue_lock:
        state = load_run_queue()
        before = len(state.queued)
        state.queued = [q for q in state.queued if q.run_id != run_id]
        if len(state.queued) < before:
            save_run_queue(state)
            return True
        return False


# ============================================================
# Init (run at startup)
# ============================================================


def ensure_state_files() -> None:
    """
    Crea archivos vacios si no existen. Idempotente.
    Llamar al startup del server.
    """
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if not BUCKET_STATUS_PATH.exists():
        _atomic_write_json(BUCKET_STATUS_PATH, {})
    if not RUN_QUEUE_PATH.exists():
        _atomic_write_json(RUN_QUEUE_PATH, RunQueueState().model_dump())
    EXCLUSIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    EXCLUSIONS_PATH.touch(exist_ok=True)
    RUN_HISTORY_PATH.touch(exist_ok=True)
