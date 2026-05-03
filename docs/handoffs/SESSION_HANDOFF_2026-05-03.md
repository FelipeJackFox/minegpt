# Session Handoff — 2026-05-03

> Reading order for next-Claude:
> 1. This file
> 2. `../pipeline/PIPELINE_OVERVIEW.md` (6-phase status)
> 3. `../pipeline/HARDENING_V2_RESULTS.md` (final pipeline state, v12)
> 4. `../pipeline/QA_GENERATION_PLAN.md` (next phase)
> 5. `C:/Users/luis/.claude/projects/D--Code-minegpt/memory/MEMORY.md` (memory index)
>
> Replaces `../archive/SESSION_HANDOFF_2026-05-02.md`.

---

## TL;DR — current state

1. **Hardening v2 final at v12** (2026-05-03). 6,715 main_corpus + 2,932 qa_direct + 496 dropped. 9.27M → 7.41M words (20.07% loss). Idempotent. Source: `scraper/hardening_v2.py`.

2. **3 new filter rules added today** (deprecation cleanup pass):
   - `Removed_features` reordered in classifier + Phase 0 drop rule (80 articles dropped, others enter via Commands/etc.)
   - `Set_index_pages` → ALL qa_direct (113 articles, drop prose-ratio gate)
   - **Deprecation banner filter** — 6 banner regex patterns + `Unused_features`/`Unused_biomes` cat drops + Tutorial exemption (455 articles dropped)

3. **All work pushed to GitHub.** 4 commits today.

4. **Mac Mini synced** (code + data). Server up at `http://mini-fzamorano:7860`.

5. **Next phase: Q&A generation.** See `../pipeline/QA_GENERATION_PLAN.md`.

## What changed in this session (2026-05-03)

### Code

- **`scraper/explore_subgroups.py`** — moved `Removed_features` from "Removed/experimental" priority group to the END of `PRIMARY_PRIORITY_GAME_VANILLA`. `Removed_features` was outranking specific buckets (Commands, etc.). Articles like `Commands/locatebiome` now correctly classify as primary=Commands; `Removed_features` lives in `also_in`.

- **`scraper/hardening_v2.py`** — Phase 0 routing additions:
  - `Set_index_pages` cat → route_qa_direct (no prose-ratio gate; 113 articles).
  - `primary_bucket == "Removed_features"` → drop with reason `removed_features_only` (80 articles).
  - Cat-based drop: `Unused_features` or `Unused_biomes` in cats → drop with reason `unused_content` (50 articles).
  - Banner-based drop: compiled `DEPRECATION_BANNER_RE` matches on first ~1500 chars of cleaned text → drop with reason `deprecated_content` (405 articles). 6 patterns covered (audit-derived):
    - `This page describes content that has been removed (from the game|and was only present in earlier versions)`
    - `This article (is about|describes) the unused (mob|biome|feature|...)`
    - `This article documents a feature that has been officially scrapped`
    - `This page describes an edition of the game that has been officially discontinued`
    - `This feature is available only in MinecraftEdu, an edition of the game that has been officially discontinued`
    - `officially made unobtainable\.` with negative lookahead for ` in <Edition>` (only the GLOBAL form drops; edition-specific stays)
  - Tutorial preservation: `title.startswith("Tutorial:")` skips both the cat check and the banner check (Tutorial:Zero-ticking etc. reference removed bugs as historical context but the how-to is current).

### Audits performed (4 parallel agents)

To inform the deprecation filter design, ran 4 deep audits:

- **Agent A** (Removed_features): sampled 30 articles across primary buckets. Confirmed banner-based detection covers ~90% of cases. Found Tutorial: edge case.
- **Agent B** (Unobtainable, all 45): confirmed GLOBAL vs EDITION-qualifier hypothesis. Period-vs-space lookahead is the decisive token.
- **Agent C** (Unused_features + Unused_biomes, 54): cat-only filter is 54/54 safe.
- **Agent D** (false-negative scan): found ~140-160 deprecation articles outside the 4 cats — caught by `officially scrapped`, `officially discontinued`, MinecraftEdu banners.

### Docs

- `docs/pipeline/HARDENING_V2_RESULTS.md` — updated with v10/v11/v12 iterations, new routing breakdown, drop reasons, audit-verified spot-checks.
- `docs/pipeline/PIPELINE_OVERVIEW.md` — updated dataset numbers (6,715 / 2,932 / 496) and decisions log.
- `docs/handoffs/SESSION_HANDOFF_2026-05-02.md` → archived; this file replaces it.

### Memory updates

- `project_minegpt.md`: updated corpus counts.
- `project_hardening_v2.md`: updated stats + iteration list.

### Commits (today)

```
4fdf14d  Drop articles whose primary bucket is Removed_features
8f81fd7  Route all Set_index_pages to qa_direct (drop prose-ratio gate)
18098a5  Phase 0: drop articles fully describing deprecated/removed/unused content
[next]   Update docs with v12 final state
```

## What's next (priority order)

1. **Q&A prompt iteration** in Prompt Lab. Pilot bucket suggestion: `Animal_mobs` (47 articles, dense facts). See `../pipeline/QA_GENERATION_PLAN.md` § Status checklist + `../prompts/PROMPT_TEMPLATES.md`.
2. **Decide on `Lost_versions` (295) and `Discontinued` (40) cats** — currently most caught by version routing but a few may slip through the deprecation filter. Quick audit + decision.
3. **April Fools content (~253 articles)** still in main corpus (e.g., `Trophy (April Fools' joke)`, `2.0`). Audit suggested separate handling. TBD: keep, drop, or route to a `april_fools_corpus` for an opt-in fine-tune later.
4. **Decide `changelogs_cleaned.jsonl` (1,270 entries, 2.04M words)** inclusion in training. Currently outside the main corpus pipeline.
5. **Run full Q&A pipeline** on Mac Mini once prompts are validated. ETA ~50-100h Mac Mini wall clock.
6. **Tokenize + train v1 model**. Decide model architecture (125-200M target).

## Things to NOT do

- Do NOT propose Qwen body transformation. It's abandoned.
- Do NOT invoke spin-off classification. Postponed for v2 (M4 hardware, June-July 2026). Data archived at `raw_data/_archive/spinoffs_v1/`.
- Do NOT push --force to main without explicit confirmation.
- Do NOT delete files / databases / commit destructively without confirming.
- Do NOT commit changes without Felipe explicitly asking.

## Quick verification on next session start

```bash
# 1. Check git is clean and on main
cd D:/Code/minegpt && git status && git log --oneline -8

# 2. Required pipeline files exist with current sizes
ls -la raw_data/wiki/articles_hardened.jsonl raw_data/wiki/articles_qa_direct.jsonl raw_data/wiki/articles_dropped.jsonl

# 3. Mac Mini server is up
curl -sf http://mini-fzamorano:7860/api/articles/groups > /dev/null && echo "Mac Mini OK"

# 4. Hardening is reproducible (optional)
python -m scraper.hardening_v2 --sample raw_data/_validate_samples/set_1.jsonl --force
```

If Mac Mini is down: see memory `reference_macmini_deployment.md` for tmux restart command.

## Open TODOs in code

- `scraper/prompt_lab/server.py:1466` — `skipped_lenses: TODO — Fase 4.1`. Returns empty list. Either implement or remove.
- Mac Mini `server.py` is sed-patched after every deploy to bind `0.0.0.0`. Long-term: env var `MINEGPT_BIND_HOST`.
- Layer C glue dictionary (`scraper/_layer_c_glue.json`) has only 25 auto-split entries. ~475 manual-curation candidates pending in `_layer_c_candidates.json`.
- `Cause: ... Potency: ... Length: ...` rows currently kept verbatim — plan said "stitch into prose if Notes: present, else drop". Stitching is a future enhancement.

## Spot-check (audit verified, run on Mac Mini API)

| Article | Verdict | Where |
|---|---|---|
| Diamond | keep | main_corpus (1,279w hardened) |
| Amethyst Shard | keep | main_corpus (381w hardened) |
| Cow, Warden, Allay | keep | main_corpus |
| Reserved6 (former Bedrock technical block) | drop | dropped (deprecated_content) |
| Giant (unused mob, JE+LCE) | drop | dropped (unused_content) |
| Nether Reactor Core (Pocket Edition removed) | drop | dropped (deprecated_content) |
| Tutorial:Zero-ticking | keep | main_corpus (Tutorial: exempt) |
| A Familiar Room (music — current in JE) | keep | main_corpus (EDITION_UNOBT, kept) |
| Java Edition Classic 0.0.13a | qa_direct | qa_direct (version_changelog_page) |
| Function (disambiguation) | qa_direct | qa_direct (disambig) |
| Commands/locatebiome (removed command) | drop | dropped (deprecated_content) |
| Java Edition Alpha server (set_index) | qa_direct | qa_direct (set_index) |

## Lessons from this session

- **Banner-based filtering is more precise than cat-based** for deprecation. Cats are noisy (Tutorial:* with `Removed_features`); banners are explicit ("This article describes the unused mob"). Use banners as primary, cats as secondary.
- **The `period vs " in"` token in unobtainable banner** is a brittle but reliable signal: GLOBAL has `unobtainable.`, EDITION has `unobtainable in <X> Edition.`. Lookahead-based regex captures the difference cleanly.
- **Always run a "false-negative scan"** when designing a categorical filter — Agent D found ~140-160 deprecation articles that the 4 cats alone would have missed.
- **Tutorial preservation is a real edge case** worth special handling. Without it, `Tutorial:Zero-ticking` (a how-to using a removed bug as a redstone trick) gets wrongly dropped.

## Stack reminder

Python 3.9 on Mac Mini (uses `from __future__ import annotations`).
Local Windows: Python 3.12+.
MLX (Apple Silicon training), sentencepiece, FastAPI + Alpine.js + Tailwind CDN.
GitHub: `https://github.com/FelipeJackFox/minegpt` (public).
