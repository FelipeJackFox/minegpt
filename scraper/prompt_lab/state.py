"""
state.py — Pydantic models para Phase 4.0 persistence.

Modelos:
- BucketState           — estado por bucket en bucket_status.json
- ExclusionEntry        — evento append-only en article_exclusions.jsonl
- ExclusionState        — estado actual derivado (in-memory)
- RunHistoryEntry       — evento append-only en run_history.jsonl
- RunQueueItem          — item current/queued en run_queue.json
- RunQueueState         — contenido completo de run_queue.json

Schema de archivos en `raw_data/_pipeline_state/`. Ver PHASE4_UX_DESIGN.md.
"""

from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


# ============================================================
# Bucket state
# ============================================================

TransformStatus = Literal[
    "not_started", "drafting", "ready", "running", "completed", "skipped"
]

QaStatus = Literal[
    "not_started", "drafting", "ready", "running", "completed", "skipped"
]


class BucketState(BaseModel):
    """Estado de un bucket. Una entry por bucket en bucket_status.json."""

    ambiente: str
    family: str  # block | mob | item | plant | mechanic | world | command | crafting_recipe | version | person | tutorial | external | other
    primary_count: int = 0
    secondary_count: int = 0

    transform_status: TransformStatus = "not_started"
    transform_run_id: Optional[str] = None
    transform_run_completed: bool = False
    transform_user_approved: bool = False
    transform_last_run_at: Optional[str] = None
    transform_excluded_count: int = 0

    # Q&A is independent of transform: source is the pre-transform (regex-cleaned)
    # text, so Q&A can be drafted/run before, after, or without transform.
    qa_status: QaStatus = "not_started"
    qa_run_id: Optional[str] = None
    qa_run_completed: bool = False
    qa_user_approved: bool = False
    qa_last_run_at: Optional[str] = None
    qa_excluded_count: int = 0

    last_touched_at: Optional[str] = None
    skipped_reason: Optional[str] = None
    skipped_at: Optional[str] = None
    force_transform: bool = False


# ============================================================
# Exclusions (append-only audit log)
# ============================================================

ExclusionScope = Literal["this_lens", "all_lenses"]
ExclusionAction = Literal[
    "exclude_transform", "exclude_qa", "exclude_both",
    "include_transform", "include_qa", "include_both",
]


class ExclusionEntry(BaseModel):
    """Evento de exclusion/inclusion. Append-only en article_exclusions.jsonl."""

    ts: str  # ISO timestamp UTC
    title: str
    bucket_lens: str  # bucket name; "*" si scope=all_lenses
    scope: ExclusionScope
    action: ExclusionAction
    reason: Optional[str] = None  # obligatoria si scope=all_lenses
    actor: str = "felipe"


class ExclusionState(BaseModel):
    """Estado actual derivado para (title, bucket_lens). In-memory."""

    title: str
    bucket_lens: str
    transform_excluded: bool = False
    qa_excluded: bool = False
    transform_excluded_global: bool = False  # excluido via scope=all_lenses
    qa_excluded_global: bool = False
    last_change_ts: Optional[str] = None
    last_reason: Optional[str] = None


# ============================================================
# Run history (append-only)
# ============================================================

RunPhase = Literal["transform", "qa"]
RunMode = Literal["single", "test_5", "test_20", "sample_50", "full"]
RunStatus = Literal["running", "completed", "cancelled", "error", "interrupted"]


class RunHistoryEntry(BaseModel):
    """Run terminado o interrumpido. Append-only en run_history.jsonl."""

    run_id: str
    ts_start: str
    ts_end: Optional[str] = None
    bucket_lens: str
    phase: RunPhase
    mode: RunMode
    include_secondaries: bool = False
    prompt_hash: str  # sha256 del bucket-specific (sin universal header)
    universal_header_hash: str  # sha256 del header universal al momento del run
    model: str
    num_ctx: int
    temperature: float
    status: RunStatus
    item_count: int = 0
    success_count: int = 0
    error_count: int = 0
    output_path: Optional[str] = None


# ============================================================
# Run queue
# ============================================================


class RunQueueProgress(BaseModel):
    done: int = 0
    total: int = 0
    errors: int = 0
    # What the worker is doing RIGHT NOW (live tracking for the UI)
    current_title: Optional[str] = None
    current_item_started_at: Optional[str] = None  # ISO timestamp UTC
    last_item_duration: Optional[float] = None     # seconds, last completed item


class RunQueueItem(BaseModel):
    """Item en queue (current o queued)."""

    run_id: str
    bucket_lens: str
    phase: RunPhase
    mode: RunMode
    include_secondaries: bool = False
    enqueued_at: str
    started_at: Optional[str] = None
    progress: RunQueueProgress = Field(default_factory=RunQueueProgress)
    prompt_draft_path: Optional[str] = None  # snapshot del prompt al enqueue

    # Per-run model parameters (snapshot at enqueue time so the user can
    # change the dropdown without affecting in-flight runs).
    model: str = "qwen3:8b"
    num_ctx: int = 4096
    temperature: float = 0.0
    no_think: bool = True


class RunQueueState(BaseModel):
    """Contenido completo de run_queue.json."""

    current: Optional[RunQueueItem] = None
    queued: list[RunQueueItem] = Field(default_factory=list)
