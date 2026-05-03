# Session Handoff — 2026-05-02

> Reading order for next-Claude:
> 1. This file
> 2. `HARDENING_V2_RESULTS.md` (final pipeline state)
> 3. `QA_GENERATION_PLAN.md` (next phase)
> 4. `C:/Users/luis/.claude/projects/D--Code-minegpt/memory/MEMORY.md` (memory index)
>
> Replaces `docs/archive/SESSION_HANDOFF_2026-04-27.md`.

---

## TL;DR — current state

1. **Hardening v2 pipeline is DONE and applied.** Corpus split into 7,135 main + 2,834 qa_direct + 174 dropped. 9.27M → 7.62M words (17.77% loss). Idempotent. Source: `scraper/hardening_v2.py`. Final state in `HARDENING_V2_RESULTS.md`.

2. **Major decision: Qwen body transformation ABANDONED.** Wiki body goes directly into the training corpus after hardening. Qwen reserved for Q&A. See memory `project_pipeline_decisions_2026-04-27.md`.

3. **Repo state cleaned 2026-05-02.** All recent work was uncommitted; this session staged + committed via 5 logical commits and pushed to GitHub. `.gitignore` updated, `.tmp_audit/` archived to `raw_data/_archive/`, legacy files deleted.

4. **Prompt Lab UI redesigned** (Articles tab compare mode). Single base selector, target = active version, colored side borders, stats in single bar. Deployed to Mac Mini.

5. **Next phase: Q&A generation.** See `QA_GENERATION_PLAN.md`.

## What changed in this session (2026-05-02)

### Cleanup
- Archived 4 obsolete root docs (SESSION_HANDOFF_2026-04-27, PHASE4_UX_DESIGN, CLASSIFIER_REDESIGN, EXPLORATION_REPORT) to `docs/archive/`
- Added banners to 4 partially-stale docs (HARDENING_V2_PLAN, WIKI_DATA_CLEANING, PHASE4_TRANSFORMATION_PLAN, PROMPT_TEMPLATES) explaining what's deprecated
- Deleted 2 legacy code files: `scraper/explore_subgroups_legacy.py`, `scraper/prompt_lab/static/_legacy_index_pre_merge.html`
- Archived 4 raw_data subtrees to `raw_data/_archive/`: spinoffs_v1, phase1_2_audit, exploration, hardening_iterations_2026-04-27 (.tmp_audit moved here)
- Recovered ~99 MB of disk space (deleted byte-identical snapshot, deprecated changelogs_filtered, deprecated transformed/Animal_mobs)
- Updated `.gitignore`: removed duplicate `raw_data/`, added `.tmp_audit/`, organized comments

### Memory updates
- Deleted: `reference_phase4_plan.md`, `reference_wiki_cleaning.md` (both fully stale)
- Rewrote: `project_minegpt.md`, `project_classifier_notes.md`, `reference_prompt_lab.md`
- Created: `project_hardening_v2.md`, `project_pipeline_decisions_2026-04-27.md`, `reference_macmini_deployment.md`
- Updated `MEMORY.md` index

### New docs
- `HARDENING_V2_RESULTS.md` — final state of hardening pipeline + iteration log
- `QA_GENERATION_PLAN.md` — consolidated Q&A plan replacing transformation
- `PROMPT_LAB_UI.md` — current UI architecture, replaces archived PHASE4_UX_DESIGN
- `SESSION_HANDOFF_2026-05-02.md` (this file)

### Git
- 5 logical commits made (see `git log` for messages). Pushed to `origin/main`.

## What's next (priority order)

1. **Iterate Q&A prompts** in Prompt Lab. Pilot bucket suggestion: `Animal_mobs` (47 articles, dense facts, validates flow). See `QA_GENERATION_PLAN.md` "Status checklist".
2. **Decide inclusion of `changelogs_cleaned.jsonl`** in training. ~2M words separate corpus. Currently NOT in main pipeline.
3. **Decide cosmetic_generic exclusion** (per memory `project_classifier_notes.md`).
4. **Run full Q&A pipeline** on Mac Mini once prompts are validated. ETA ~50-100h wall clock.
5. **Tokenize + train v1 model**. Decide model architecture (125-200M target). See `WIKI_DATA_CLEANING.md` post-pipeline section (still valid for that part).

## Things to NOT do

- Do NOT propose Qwen body transformation. It's abandoned.
- Do NOT invoke spin-off classification. Postponed for v2 (M4 hardware, June-July 2026). Data archived at `raw_data/_archive/spinoffs_v1/`.
- Do NOT push --force to main without explicit confirmation.
- Do NOT delete files / databases / commit destructively without confirming.
- Do NOT commit changes without Felipe explicitly asking.

## Quick verification on next session start

```bash
# 1. Check git is clean and on main
cd D:/Code/minegpt && git status && git log --oneline -5

# 2. Required pipeline files exist
ls raw_data/wiki/articles_hardened.jsonl raw_data/wiki/articles_qa_direct.jsonl raw_data/wiki/articles_dropped.jsonl

# 3. Mac Mini server is up
curl -sf http://mini-fzamorano:7860/api/articles/groups > /dev/null && echo "Mac Mini OK"

# 4. Hardening is reproducible (optional sanity test)
python -m scraper.hardening_v2 --sample raw_data/_validate_samples/set_1.jsonl --force
```

If Mac Mini server is down: see `reference_macmini_deployment.md` for tmux restart command.

## Open TODOs in code

- `scraper/prompt_lab/server.py:1466` — `skipped_lenses: TODO — Fase 4.1`. Returns empty list. Either implement or remove the dead code path.
- Mac Mini `server.py` is sed-patched after every deploy to bind `0.0.0.0`. Long-term: env var `MINEGPT_BIND_HOST`.
- Layer C glue dictionary (`scraper/_layer_c_glue.json`) has only 25 auto-split entries. ~475 manual-curation candidates pending in `_layer_c_candidates.json`.

## Lessons from past sessions

- **Don't fight LLM inconsistency with more rules.** 3+ hours iterating prompts on Animal_mobs convinced us that Qwen body transformation can't be made reliable. The fix was to stop trying.
- **Sub-section drops are higher ROI than line-level regex.** Dropping `## Sounds`, `## Data values` etc. wholesale would have been cleaner — but for FACTS in those sections, we revived them.
- **Validation is non-negotiable.** Phase C's 12 caveats would have caused real damage if implemented as v1 plan. The 2-hour validation cost was worth it.
- **Lowercase-lowercase fusion is the dominant junk class** in word-boundary repair. Layer A regex catches ~30%; Layer B/C dictionary handles the rest.
- **Idempotence isn't free.** Took 2 iterations to land (Layer A lookaheads, NBT-strip-before-Phase-6, Phase 3 loop until stable). Test it explicitly on each new pattern.

## Stack reminder

Python 3.9 on Mac Mini (uses `from __future__ import annotations`).
Local Windows can use Python 3.12+ for development.
MLX (Apple Silicon training), sentencepiece, FastAPI + Alpine.js + Tailwind CDN (no build step).
GitHub: `https://github.com/FelipeJackFox/minegpt` (public).
