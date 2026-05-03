"""
batch_runner.py — Background worker que ejecuta batch runs encolados.

Modelo:
- Un solo worker thread global. Mac M2 no paraleliza inferencia → serial.
- Picks `current` from run_queue.json. Si no hay current pero hay queued,
  promueve el primero. Después ejecuta hasta terminar o ser cancelado.
- Output: 1 archivo por (bucket, lens, phase) en `raw_data/transformed/`
  (transform) o `raw_data/qa/` (qa). Append-only JSONL para resume.
- Update progress en run_queue.json cada item completado.
- Append run_history.jsonl al inicio + update al final.
- Recovery on startup: si run_queue.current existe pero el thread no está
  vivo, marcarlo como "interrupted" y limpiar.
"""

from __future__ import annotations

import json
import random
import re
import threading
import time
from pathlib import Path
from typing import Optional

from scraper.prompt_lab import state_manager
from scraper.prompt_lab.state import RunHistoryEntry, RunMode, RunPhase
from scraper.prompt_lab.ollama_client import generate
from scraper.prompt_lab import article_viewer
from scraper.prompt_lab.output_normalizer import normalize as normalize_output


# ============================================================
# Paths
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRANSFORM_OUT_DIR = PROJECT_ROOT / "raw_data" / "transformed"
QA_OUT_DIR = PROJECT_ROOT / "raw_data" / "qa"
HEADERS_DIR = Path(__file__).parent / "prompts" / "_headers"


def _output_path(bucket_lens: str, phase: str) -> Path:
    base = TRANSFORM_OUT_DIR if phase == "transform" else QA_OUT_DIR
    safe = re.sub(r"[^A-Za-z0-9_]", "_", bucket_lens)
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{safe}.jsonl"


# ============================================================
# Worker state (single thread, single-user)
# ============================================================

_worker_thread: Optional[threading.Thread] = None
_worker_lock = threading.Lock()
_signal = threading.Event()        # wake the worker when something is enqueued
_cancel_flag = threading.Event()   # current run should stop ASAP
_running = threading.Event()       # worker has work in flight


def signal() -> None:
    """Tell the worker to check the queue. No-op if already running."""
    _signal.set()


def cancel_current() -> None:
    """Request the running batch to stop after the current item."""
    _cancel_flag.set()


def is_running() -> bool:
    return _running.is_set()


# ============================================================
# Item selection
# ============================================================


def _select_items(
    bucket_lens: str,
    mode: RunMode,
    include_secondaries: bool,
) -> list[dict]:
    """
    Devuelve la lista de items (dicts con title/text/categories/etc) a procesar
    para el modo especificado. Aplica exclusiones del state.
    """
    raw = article_viewer.list_articles(
        bucket_lens, None, None, "alpha", 0, 100000
    )
    if not raw.get("ready"):
        return []
    items = raw.get("items", [])

    # Filter by primary/secondary scope
    if not include_secondaries:
        items = [it for it in items if it.get("is_primary_here", True)]

    # Apply exclusions (snapshot at start of run)
    titles = [it["title"] for it in items]
    excl_states = state_manager.derive_exclusions_for_bucket(bucket_lens, titles)

    def is_excluded(it: dict) -> bool:
        # phase-specific exclusion is checked at run-time below
        return False  # we filter per-phase later

    # We don't filter here yet — we need the phase. Caller does it.
    return items


def _filter_by_exclusions(
    items: list[dict],
    bucket_lens: str,
    phase: RunPhase,
) -> list[dict]:
    """Drop excluded items for the given phase."""
    titles = [it["title"] for it in items]
    excl_states = state_manager.derive_exclusions_for_bucket(bucket_lens, titles)
    out = []
    for it in items:
        s = excl_states.get(it["title"])
        if s is None:
            out.append(it)
            continue
        if phase == "transform" and s.transform_excluded:
            continue
        if phase == "qa" and s.qa_excluded:
            continue
        out.append(it)
    return out


def _pick_subset(items: list[dict], mode: RunMode) -> list[dict]:
    if mode == "full":
        return items
    if mode == "test_5":
        return random.sample(items, min(5, len(items)))
    if mode == "test_20":
        return random.sample(items, min(20, len(items)))
    if mode == "sample_50":
        return items[:50]
    if mode == "single":
        return items[:1]
    return items


# ============================================================
# Resume support — count already-written titles in output JSONL
# ============================================================


def _already_processed(out_path: Path) -> set[str]:
    """Read output JSONL and return set of titles already written."""
    if not out_path.exists():
        return set()
    done = set()
    try:
        with open(out_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    t = obj.get("title")
                    if t:
                        done.add(t)
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return done


# ============================================================
# Prompt build
# ============================================================


def _read_universal_header(phase: str) -> str:
    p = HEADERS_DIR / f"{phase}.txt"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _read_bucket_specific(bucket_lens: str, phase: str) -> str:
    """
    Prefer the active draft for this bucket+phase (autosaved by the user).
    Fall back to family approved file if no draft. Family is heuristic from
    bucket_status.json (BucketState.family).
    """
    # 1. Draft for this specific bucket
    safe_bucket = re.sub(r"[^A-Za-z0-9_]", "_", bucket_lens)
    drafts_dir = Path(__file__).parent / "prompts" / "drafts"
    draft_p = drafts_dir / f"{safe_bucket}_{phase}_draft.txt"
    if draft_p.exists():
        text = draft_p.read_text(encoding="utf-8").strip()
        if text:
            return text
    # 2. Family approved
    state = state_manager.get_bucket_state(bucket_lens)
    if state and state.family:
        family_p = Path(__file__).parent / "prompts" / phase / f"{state.family}.txt"
        if family_p.exists():
            return family_p.read_text(encoding="utf-8").strip()
    return ""


def _build_prompt(
    bucket_lens: str,
    phase: str,
    title: str,
    text: str,
    cats: list[str],
    universal: str,
    bucket_specific: str,
) -> str:
    # Truncate article text to ~800 words to fit num_ctx with header
    words = text.split()
    if len(words) > 800:
        text = " ".join(words[:800]) + " [...]"
    return (
        f"{universal.strip()}\n\n"
        f"{bucket_specific.strip()}\n\n"
        f"# Article\n\n"
        f"Title: {title}\n"
        f"Wiki categories: {', '.join(cats) if cats else '(none)'}\n"
        f"Current lens: {bucket_lens}\n\n"
        f"---\n\n"
        f"{text}"
    )


# ============================================================
# Execute one batch run
# ============================================================


def _execute(item, *, fallback_model: str, fallback_num_ctx: int,
             fallback_temperature: float, fallback_no_think: bool) -> None:
    """
    Execute a queued run end-to-end.
    Per-run model params are read from the queue item (snapshot at enqueue
    time). Fallbacks are only used if the item lacks them (legacy queue
    items written before this field existed).
    """
    bucket_lens = item.bucket_lens
    phase = item.phase
    mode = item.mode
    include_sec = item.include_secondaries

    # Per-run params from the item (snapshotted at enqueue)
    model = getattr(item, "model", None) or fallback_model
    num_ctx = getattr(item, "num_ctx", None) or fallback_num_ctx
    temperature = getattr(item, "temperature", None)
    if temperature is None:
        temperature = fallback_temperature
    no_think = getattr(item, "no_think", fallback_no_think)

    # Resolve items
    items = _select_items(bucket_lens, mode, include_sec)
    items = _filter_by_exclusions(items, bucket_lens, phase)
    items = _pick_subset(items, mode)

    # Resume: skip already-processed titles for this bucket+phase
    out_path = _output_path(bucket_lens, phase)
    done_titles = _already_processed(out_path) if mode == "full" else set()
    items_to_run = [it for it in items if it["title"] not in done_titles]
    skipped = len(items) - len(items_to_run)
    total = len(items)

    # Universal header + bucket-specific (prefer draft)
    universal = _read_universal_header(phase)
    universal_hash = state_manager.hash_text(universal)
    bucket_specific = _read_bucket_specific(bucket_lens, phase)
    bucket_hash = state_manager.hash_text(bucket_specific)

    # Append run_history start
    run_id = item.run_id
    state_manager.append_run_history(RunHistoryEntry(
        run_id=run_id,
        ts_start=state_manager.now_iso(),
        bucket_lens=bucket_lens,
        phase=phase,
        mode=mode,
        include_secondaries=include_sec,
        prompt_hash=bucket_hash,
        universal_header_hash=universal_hash,
        model=model,
        num_ctx=num_ctx,
        temperature=temperature,
        status="running",
        item_count=total,
        output_path=str(out_path.relative_to(PROJECT_ROOT)),
    ))

    # Mark bucket as running (phase-specific)
    field = f"{phase}_status"
    try:
        state_manager.update_bucket_state(
            bucket_lens, **{field: "running", f"{phase}_run_id": run_id},
        )
    except ValueError:
        pass  # bucket not yet in state, will be created by frontend

    # Initial progress
    state_manager.update_current_progress(done=skipped, total=total, errors=0)

    success_count = 0
    error_count = 0
    final_status = "completed"

    try:
        for i, it in enumerate(items_to_run):
            if _cancel_flag.is_set():
                final_status = "cancelled"
                break

            title = it["title"]

            # Live tracking: announce we're starting this item
            state_manager.update_current_item(title, state_manager.now_iso())

            article = article_viewer.get_article(title, "cleaned")
            if article is None:
                error_count += 1
                _append_output(out_path, {
                    "title": title, "bucket_lens": bucket_lens, "phase": phase,
                    "mode": mode, "ts": state_manager.now_iso(),
                    "error": "article not found in cleaned version",
                    "raw_response": "", "duration": 0,
                })
                state_manager.update_current_progress(
                    done=skipped + i + 1, total=total, errors=error_count,
                    last_item_duration=0.0,
                )
                continue

            text = article.get("text", "")
            cats = article.get("categories", []) or []
            full_prompt = _build_prompt(
                bucket_lens, phase, title, text, cats, universal, bucket_specific
            )
            if no_think:
                full_prompt = "/no_think\n" + full_prompt

            t0 = time.time()
            try:
                result = generate(
                    full_prompt,
                    model=model,
                    num_ctx=num_ctx,
                    temperature=temperature,
                )
                raw = result.response
                duration = result.total_duration_s
                error = None
                success_count += 1
            except Exception as e:
                raw = ""
                duration = time.time() - t0
                error = str(e)
                error_count += 1

            # Normalize output to canonical format (only for transform; QA
            # has its own format with Q/A line prefixes, not the markdown
            # structure the normalizer targets)
            normalized = ""
            normalize_meta = None
            if phase == "transform" and raw:
                try:
                    norm_res = normalize_output(raw, expected_title=title)
                    normalized = norm_res.normalized
                    normalize_meta = {
                        "format_detected": norm_res.raw_format_detected,
                        "transforms_count": len(norm_res.transforms_applied),
                        "warnings": norm_res.warnings,
                    }
                except Exception as norm_err:
                    normalize_meta = {"error": str(norm_err)}

            _append_output(out_path, {
                "title": title,
                "bucket_lens": bucket_lens,
                "phase": phase,
                "mode": mode,
                "ts": state_manager.now_iso(),
                "error": error,
                "raw_response": raw,
                "normalized_response": normalized,
                "normalize_meta": normalize_meta,
                "duration": round(duration, 2),
                "input_chars": len(full_prompt),
            })
            # Live tracking: clear current_title; record last duration for ETA calc
            state_manager.update_current_progress(
                done=skipped + i + 1, total=total, errors=error_count,
                last_item_duration=round(duration, 2),
            )
            state_manager.update_current_item(None, None)

    finally:
        # Update run_history end
        state_manager.update_run_history(
            run_id,
            ts_end=state_manager.now_iso(),
            status=final_status,
            success_count=success_count + skipped,  # resumed items count as success
            error_count=error_count,
        )

        # Update bucket status. Rules:
        # - full + completed → mark phase status as 'completed'
        # - any test/sample/single + completed → back to 'drafting' (still iterating)
        # - cancelled or interrupted → back to 'drafting' (preserves resume target)
        # - error → back to 'drafting'
        try:
            updates = {
                f"{phase}_run_completed": (final_status == "completed" and mode == "full"),
                f"{phase}_last_run_at": state_manager.now_iso(),
                f"{phase}_run_id": None,  # clear active run id on terminal states
            }
            if final_status == "completed" and mode == "full":
                updates[field] = "completed"
            else:
                # All non-full terminations leave the bucket in 'drafting' so the
                # user keeps iterating. Manual approval (atajo M) is what flips
                # 'completed' to 'done' (user_approved=True).
                updates[field] = "drafting"
            state_manager.update_bucket_state(bucket_lens, **updates)
        except ValueError:
            pass

        # Clear current from queue
        state_manager.clear_current_run()
        _cancel_flag.clear()


def _append_output(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


# ============================================================
# Worker loop
# ============================================================


def _worker_loop(fallback_model: str, fallback_num_ctx: int,
                 fallback_temperature: float, fallback_no_think: bool) -> None:
    """Run continuously, picking from the queue when signaled. Per-run
    params come from the queue item; the fallbacks here are only used for
    legacy items that predate per-run params."""
    while True:
        _signal.wait()
        _signal.clear()
        # Drain the queue: pick next current, execute, repeat until empty
        while True:
            queue = state_manager.load_run_queue()
            if queue.current is None:
                # Try to promote next from queued
                if not queue.queued:
                    break
                item = state_manager.promote_next_to_current()
                if item is None:
                    break
            else:
                item = queue.current
            _running.set()
            try:
                _execute(
                    item,
                    fallback_model=fallback_model,
                    fallback_num_ctx=fallback_num_ctx,
                    fallback_temperature=fallback_temperature,
                    fallback_no_think=fallback_no_think,
                )
            except Exception as e:
                # Catastrophic failure: log + clear current to avoid stuck state
                print(f"[batch_runner] worker error on {item.run_id}: {e}")
                try:
                    state_manager.update_run_history(
                        item.run_id,
                        ts_end=state_manager.now_iso(),
                        status="error",
                    )
                except Exception:
                    pass
                state_manager.clear_current_run()
                _cancel_flag.clear()
            finally:
                _running.clear()


def start_worker(
    model: str = "qwen3:8b",
    num_ctx: int = 4096,
    temperature: float = 0.0,
    no_think: bool = True,
) -> None:
    """
    Start the worker thread (idempotent). Call once at server startup.
    The model/params here are FALLBACKS for legacy queue items that
    predate per-run params. Real runs read params from the queue item
    snapshot at enqueue time.
    """
    global _worker_thread
    with _worker_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            return
        _worker_thread = threading.Thread(
            target=_worker_loop,
            args=(model, num_ctx, temperature, no_think),
            name="batch_runner",
            daemon=True,
        )
        _worker_thread.start()


# ============================================================
# Recovery on startup
# ============================================================


def recover_interrupted() -> Optional[dict]:
    """
    Detect a `current` run left over from a previous server lifecycle and mark
    it as interrupted. Returns the orphaned run info if any, None otherwise.
    """
    queue = state_manager.load_run_queue()
    if queue.current is None:
        return None
    orphan = queue.current
    # Mark as interrupted in run_history (best-effort)
    try:
        state_manager.update_run_history(
            orphan.run_id,
            ts_end=state_manager.now_iso(),
            status="interrupted",
        )
    except Exception:
        pass
    # Also flip bucket status back to drafting so user can re-run
    try:
        bs = state_manager.get_bucket_state(orphan.bucket_lens)
        if bs is not None:
            field = f"{orphan.phase}_status"
            current = getattr(bs, field, None)
            if current == "running":
                state_manager.update_bucket_state(
                    orphan.bucket_lens, **{field: "drafting"},
                )
    except Exception:
        pass
    state_manager.clear_current_run()
    return {
        "run_id": orphan.run_id,
        "bucket_lens": orphan.bucket_lens,
        "phase": orphan.phase,
        "mode": orphan.mode,
        "progress": orphan.progress.model_dump() if orphan.progress else None,
    }
