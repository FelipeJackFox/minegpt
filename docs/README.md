# MineGPT — Documentation Index

Project docs live here, organized by category. Code is in `../scraper/`,
data pipeline outputs are in `../raw_data/` (gitignored).

## Where to start

- **New session?** Start with [`handoffs/SESSION_HANDOFF_2026-05-02.md`](handoffs/SESSION_HANDOFF_2026-05-02.md).
- **Want the current pipeline state?** [`pipeline/HARDENING_V2_RESULTS.md`](pipeline/HARDENING_V2_RESULTS.md).
- **Working on the next phase (Q&A)?** [`pipeline/QA_GENERATION_PLAN.md`](pipeline/QA_GENERATION_PLAN.md).
- **Need the dev tool reference?** [`tools/PROMPT_LAB_UI.md`](tools/PROMPT_LAB_UI.md).

## Layout

```
docs/
├── README.md                          (this file)
├── LEGAL.md                           (license + attribution for all sources)
├── handoffs/                          (session handoffs — most recent at top)
│   └── SESSION_HANDOFF_2026-05-02.md
├── pipeline/                          (data cleaning, hardening, Q&A plans)
│   ├── WIKI_DATA_CLEANING.md          (Phase 1+2 plan; banner: post-hardening sections deprecated)
│   ├── HARDENING_V2_PLAN.md           (Phase D spec; status: implemented)
│   ├── HARDENING_V2_RESULTS.md        (final pipeline state + 9-iteration log)
│   └── QA_GENERATION_PLAN.md          (next phase: Q&A generation)
├── prompts/                           (prompt engineering reference)
│   ├── PROMPT_TEMPLATES.md            (Q&A prompts; transform half deprecated)
│   └── PHASE4_TRANSFORMATION_PLAN.md  (transform deprecated; Q&A halves still useful)
├── tools/                             (dev tooling docs)
│   └── PROMPT_LAB_UI.md               (current UI architecture, compare-mode redesign)
└── archive/                           (obsolete plans, kept for historical context)
    ├── CLASSIFIER_REDESIGN.md         (proposal; implemented in scraper/explore_subgroups.py)
    ├── EXPLORATION_REPORT.md          (Phase 0.5 baseline)
    ├── PHASE4_UX_DESIGN.md            (original 3-tab design; superseded by tools/PROMPT_LAB_UI.md)
    └── SESSION_HANDOFF_2026-04-27.md  (superseded by handoffs/SESSION_HANDOFF_2026-05-02.md)
```

## Status of each doc

### Current (active reference)

| Doc | Purpose |
|---|---|
| [`handoffs/SESSION_HANDOFF_2026-05-02.md`](handoffs/SESSION_HANDOFF_2026-05-02.md) | Most recent session handoff — read first |
| [`pipeline/HARDENING_V2_RESULTS.md`](pipeline/HARDENING_V2_RESULTS.md) | Final state of hardening v2 pipeline (7,135 main + 2,834 qa_direct + 174 dropped, 17.77% loss, idempotent) |
| [`pipeline/QA_GENERATION_PLAN.md`](pipeline/QA_GENERATION_PLAN.md) | Q&A pipeline plan (next phase) |
| [`tools/PROMPT_LAB_UI.md`](tools/PROMPT_LAB_UI.md) | Current dev-tool UI reference (compare-mode redesign, keyboard shortcuts) |
| [`LEGAL.md`](LEGAL.md) | License + source attribution (CC BY-SA, etc.) |

### Reference (some sections stale, but still useful)

| Doc | Status |
|---|---|
| [`pipeline/WIKI_DATA_CLEANING.md`](pipeline/WIKI_DATA_CLEANING.md) | Phase 1+2 sections accurate. Phase 4b-e (transformation) DEPRECATED. |
| [`pipeline/HARDENING_V2_PLAN.md`](pipeline/HARDENING_V2_PLAN.md) | Spec we worked from. Implementation diverged on ~5 points (see banner). |
| [`prompts/PROMPT_TEMPLATES.md`](prompts/PROMPT_TEMPLATES.md) | Transform sections DEPRECATED. Q&A sections still valid. |
| [`prompts/PHASE4_TRANSFORMATION_PLAN.md`](prompts/PHASE4_TRANSFORMATION_PLAN.md) | Transform half DEPRECATED. Q&A halves consolidated into pipeline/QA_GENERATION_PLAN.md. |

### Archive (obsolete; preserved for historical context)

See `archive/`. Don't update; reference for "what we used to think".

## Conventions

- **Cross-refs use relative paths.** Inside the same dir: bare filename (`HARDENING_V2_PLAN.md`). Across dirs: `../other-dir/FILE.md`.
- **Banners** at the top of partially-stale docs explain what's deprecated. Don't trust headers below the banner without reading it.
- **Memory files** (Claude session memories at `~/.claude/projects/D--Code-minegpt/memory/`) point to the relevant docs here. See `MEMORY.md` index there.
- **Snapshot dates** in handoff filenames (e.g. `SESSION_HANDOFF_2026-05-02.md`) — most recent is canonical, older ones go to `archive/`.

## How to navigate by question

| Question | Where |
|---|---|
| What's the current state of the data pipeline? | `pipeline/HARDENING_V2_RESULTS.md` |
| How do I run hardening v2 again? | `pipeline/HARDENING_V2_RESULTS.md` § Re-run command |
| What's next on the roadmap? | `handoffs/SESSION_HANDOFF_2026-05-02.md` § What's next |
| What's the Q&A plan? | `pipeline/QA_GENERATION_PLAN.md` |
| How does the Prompt Lab UI work? | `tools/PROMPT_LAB_UI.md` |
| How do I deploy to Mac Mini? | Memory file `reference_macmini_deployment.md` |
| What was Q&A prompt template structure? | `prompts/PROMPT_TEMPLATES.md` (Q&A sections only) |
| What's the project's category taxonomy? | Live code in `scraper/explore_subgroups.py`. Original proposal in `archive/CLASSIFIER_REDESIGN.md`. |
| What was the original wiki cleaning plan? | `pipeline/WIKI_DATA_CLEANING.md` (Phase 1+2 sections) |
| Why was Qwen body transformation abandoned? | Memory file `project_pipeline_decisions_2026-04-27.md` |
| What sources are scraped + their licenses? | `LEGAL.md` |
