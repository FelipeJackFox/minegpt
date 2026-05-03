# MineGPT — Documentation Index

Project docs live here, organized by category. Code is in `../scraper/`,
data pipeline outputs are in `../raw_data/` (gitignored).

## Where to start

- **New session?** Start with [`handoffs/SESSION_HANDOFF_2026-05-03.md`](handoffs/SESSION_HANDOFF_2026-05-03.md).
- **Want pipeline state at a glance?** [`pipeline/PIPELINE_OVERVIEW.md`](pipeline/PIPELINE_OVERVIEW.md).
- **Want the hardening pipeline final state?** [`pipeline/HARDENING_V2_RESULTS.md`](pipeline/HARDENING_V2_RESULTS.md).
- **Working on the next phase (Q&A)?** [`pipeline/QA_GENERATION_PLAN.md`](pipeline/QA_GENERATION_PLAN.md) + [`prompts/PROMPT_TEMPLATES.md`](prompts/PROMPT_TEMPLATES.md).
- **Need the dev tool reference?** [`tools/PROMPT_LAB_UI.md`](tools/PROMPT_LAB_UI.md).

## Layout

```
docs/
├── README.md                          (this file)
├── LEGAL.md                           (license + attribution)
├── handoffs/
│   └── SESSION_HANDOFF_2026-05-02.md  (most recent session handoff)
├── pipeline/                          (data pipeline)
│   ├── PIPELINE_OVERVIEW.md           (slim status of all 6 phases)
│   ├── HARDENING_V2_RESULTS.md        (Phase 4 final state + 9-iteration log)
│   └── QA_GENERATION_PLAN.md          (Phase 5 plan: Q&A generation)
├── prompts/                           (prompt engineering)
│   └── PROMPT_TEMPLATES.md            (Q&A prompt templates per family)
├── tools/                             (dev tooling)
│   └── PROMPT_LAB_UI.md               (current UI architecture)
└── archive/                           (deprecated; historical context only)
    ├── CLASSIFIER_REDESIGN.md
    ├── EXPLORATION_REPORT.md
    ├── HARDENING_V2_PLAN.md
    ├── PHASE4_TRANSFORMATION_PLAN.md
    ├── PHASE4_UX_DESIGN.md
    ├── PROMPT_TEMPLATES_v1_with_transform.md
    ├── SESSION_HANDOFF_2026-04-27.md
    └── WIKI_DATA_CLEANING_v1.md
```

## Status of each doc

### Current (active reference; trustworthy as-of 2026-05-03)

| Doc | Purpose |
|---|---|
| [`handoffs/SESSION_HANDOFF_2026-05-03.md`](handoffs/SESSION_HANDOFF_2026-05-03.md) | Most recent session handoff — read first |
| [`pipeline/PIPELINE_OVERVIEW.md`](pipeline/PIPELINE_OVERVIEW.md) | All 6 pipeline phases, status, dataset counts, decisions log |
| [`pipeline/HARDENING_V2_RESULTS.md`](pipeline/HARDENING_V2_RESULTS.md) | Phase 4 final state (6,715 main + 2,932 qa_direct + 496 dropped, 20.07% loss, idempotent) |
| [`pipeline/QA_GENERATION_PLAN.md`](pipeline/QA_GENERATION_PLAN.md) | Phase 5 plan (Q&A generation) |
| [`prompts/PROMPT_TEMPLATES.md`](prompts/PROMPT_TEMPLATES.md) | Q&A prompt templates (universal header + per-family) |
| [`tools/PROMPT_LAB_UI.md`](tools/PROMPT_LAB_UI.md) | Dev-tool UI (compare-mode, shortcuts, deploy hooks) |
| [`LEGAL.md`](LEGAL.md) | License + source attribution (CC BY-SA, etc.) |

### Archive (obsolete; preserved for historical context)

| Doc | Why archived |
|---|---|
| `archive/HARDENING_V2_PLAN.md` | Original spec; implementation diverged on ~5 points. `pipeline/HARDENING_V2_RESULTS.md` is canonical. |
| `archive/PHASE4_TRANSFORMATION_PLAN.md` | Qwen body transformation abandoned 2026-04-27. Q&A halves consolidated into `pipeline/QA_GENERATION_PLAN.md` + `prompts/PROMPT_TEMPLATES.md`. |
| `archive/PROMPT_TEMPLATES_v1_with_transform.md` | v1 doc with both Transform + Q&A. Transform deprecated; Q&A extracted to current `prompts/PROMPT_TEMPLATES.md`. |
| `archive/WIKI_DATA_CLEANING_v1.md` | Original detailed pipeline plan from 2026-04-07. Replaced by slim `pipeline/PIPELINE_OVERVIEW.md`. |
| `archive/CLASSIFIER_REDESIGN.md` | Proposal that's now implemented (`scraper/explore_subgroups.py` is source of truth). |
| `archive/PHASE4_UX_DESIGN.md` | Original 3-tab Prompt Lab design, superseded by `tools/PROMPT_LAB_UI.md`. |
| `archive/EXPLORATION_REPORT.md` | Phase 0.5 baseline audit; frozen historical record. |
| `archive/SESSION_HANDOFF_2026-04-27.md` | Superseded by `handoffs/SESSION_HANDOFF_2026-05-03.md`. |

Don't update archive docs. They're snapshots of "what we used to think".

## Conventions

- **Cross-refs use relative paths.** Same dir: bare filename. Across dirs: `../other-dir/FILE.md`.
- **No deprecation banners** in active docs anymore. If a doc is deprecated, it's in `archive/`. If a doc is current, its content is current.
- **Memory files** (Claude session memories at `~/.claude/projects/D--Code-minegpt/memory/`) point to docs here. See `MEMORY.md` index there.
- **Snapshot dates** in handoff filenames (e.g. `SESSION_HANDOFF_2026-05-02.md`) — most recent is canonical, older ones go to `archive/`.

## Navigate by question

| Question | Where |
|---|---|
| What's the current state of the data pipeline? | `pipeline/PIPELINE_OVERVIEW.md` |
| What did hardening v2 do? | `pipeline/HARDENING_V2_RESULTS.md` |
| How do I re-run hardening? | `pipeline/HARDENING_V2_RESULTS.md` § Re-run command |
| What's next? | `handoffs/SESSION_HANDOFF_2026-05-03.md` § What's next |
| What's the Q&A pipeline strategy? | `pipeline/QA_GENERATION_PLAN.md` |
| What are the Q&A prompts? | `prompts/PROMPT_TEMPLATES.md` |
| How does the Prompt Lab UI work? | `tools/PROMPT_LAB_UI.md` |
| How do I deploy to Mac Mini? | Memory file `reference_macmini_deployment.md` |
| What's the project's category taxonomy? | Live code in `scraper/explore_subgroups.py` (proposal at `archive/CLASSIFIER_REDESIGN.md`). |
| Why was Qwen body transformation abandoned? | Memory file `project_pipeline_decisions_2026-04-27.md` |
| What sources are scraped + their licenses? | `LEGAL.md` |
| What was the original wiki cleaning plan? | `archive/WIKI_DATA_CLEANING_v1.md` (kept for context only) |
