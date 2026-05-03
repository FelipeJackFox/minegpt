# MineGPT — Data Pipeline Overview

Current state of the data pipeline. Lightweight reference; canonical details
in the per-phase docs linked below.

> Last updated: 2026-05-03
> Replaces `WIKI_DATA_CLEANING.md` (now archived as `../archive/WIKI_DATA_CLEANING_v1.md`).

## Pipeline phases

| # | Phase | Script | Status | Output | Words |
|---|---|---|---|---|---:|
| 1 | Filter (rule-based) | `scraper/filter.py` | ✅ done 2026-04-23 | `articles_filtered.jsonl` (10,143) | — |
| 2 | Regex clean | `scraper/regex_clean.py` | ✅ done 2026-04-23 | `articles_cleaned.jsonl` (10,143) | 9.27M |
| 3 | Cat-driven classifier | `scraper/explore_subgroups.py` | ✅ done 2026-04-26 | `META[]` in-memory (9 ambientes × 142 buckets) | — |
| 4 | Hardening v2 (12-phase regex) | `scraper/hardening_v2.py` | ✅ done 2026-05-02 | `articles_hardened.jsonl` (7,135) + `articles_qa_direct.jsonl` (2,834) + `articles_dropped.jsonl` (174) | 7.62M |
| 5 | Q&A generation (Qwen) | `scraper/prompt_lab/...` (TODO) | ⏳ planned | `qa_pairs/*.jsonl` (target ~50K-110K pairs) | — |
| 6 | Tokenize + train | `tokenizer/`, `model/` | ⏳ planned | trained model weights | — |

**Spin-off classification** (originally Phase 3) is **postponed for v2**, blocking on
Mac Mini M4 24GB hardware (June-July 2026). Current data archived at
`raw_data/_archive/spinoffs_v1/`.

## Inputs / Outputs (per phase)

### Phase 1 — Filter

`scraper/filter.py` removes articles that match rule-based junk patterns:

- title contains "render history" / "texture history" (case insensitive)
- title starts with "Debug mode"
- `word_count < 10`
- title starts with `Category:` / `User:`
- title contains `/Structure/Blueprints/` or ends in `/Renders`
- disambiguation pages whose title is just a version number (`^\d[\d.a-z]*$`)

**Audit**: 30-article random sample of `articles_removed.jsonl` confirmed all
drops are legitimate junk.

### Phase 2 — Regex clean

`scraper/regex_clean.py` runs ordered passes:

1. wiki links `[[x]]` and `[[x|y]]` → preserve display text
2. wiki templates `{{...}}` → strip
3. URLs → strip
4. cite artifacts `[N]` (protected against NBT paths like `ArmorItems[3]`)
5. nav lines (containing `◄` or `►`) → strip
6. boilerplate (`This article is a stub.`, etc.) → strip
7. final whitespace cleanup

**Audit**: `clean_diffs.jsonl` (top 100 by word-loss ratio) and `clean_flagged.jsonl`
(>30% loss) reviewed.

### Phase 3 — Cat-driven classifier

`scraper/explore_subgroups.py`. 9 ambientes (Layer A): `game_vanilla`, `tutorial`,
`real_world`, `media_franchise`, `versions`, `spinoff`, `april_fools`,
`education_edition`, `wiki_meta`. 142 vanilla buckets (Layer B = exact wiki cat
name). Multi-membership: each article has 1 primary + N also_in.

Used by Phase 4 (Phase 0 routing) and the Prompt Lab UI (article browsing).

### Phase 4 — Hardening v2

12-phase regex hardening. See `HARDENING_V2_RESULTS.md` for the full state +
9-iteration log. Key facts:

- Routes ~2,066 version-family articles to qa_direct (snapshot codes confuse model)
- Drops `History` / `Data history` sections wholesale
- Preserves `Renewable: Yes`, `Stackable: Yes (64)`, sound IDs, loot tables, ID rows as facts
- Idempotent (verified on 50 samples)

Re-run: `python -m scraper.hardening_v2 --force` (~6-10 min).

### Phase 5 — Q&A generation (next)

Plan: `QA_GENERATION_PLAN.md`. Prompt templates: `../prompts/PROMPT_TEMPLATES.md`.

Inputs:
- `articles_hardened.jsonl` (7,135) → main Q&A source, multi-lente per bucket
- `articles_qa_direct.jsonl` (2,834) → disambig + version-family + set_index w/ prose
- `changelogs_cleaned.jsonl` (1,270) — inclusion TBD

Target: ~50K-110K Q&A pairs. Tooling: Prompt Lab on Mac Mini.

### Phase 6 — Tokenize + train (later)

Stack: MLX, sentencepiece. Target model: 125-200M params on M2; up to 750M on M4.

## Dataset (current real numbers)

| Source | Entries | Words | Status |
|---|---:|---:|---|
| Wiki main (hardened) | 7,135 | 7.62M | ready for tokenize |
| Wiki Q&A-direct (hardened) | 2,834 | (subset of 7.62M) | ready for Q&A pipeline |
| Wiki dropped (audit) | 174 | (negligible) | not used |
| Changelogs (cleaned) | 1,270 | 2.04M | inclusion TBD |
| External: Wikipedia bios | 17 | ~50K | ready (cleaned) |
| External: Word of Notch posts | 294 | ~25K | ready (cleaned) |
| External: YouTube transcripts | 4 | ~5K | ready (cleaned) |

## Decisions log (context for next sessions)

- **Reddit dropped 2026-04-26.** ToS friction + redundant with wiki tutorials.
- **Spin-off classification postponed for v2** (Mac Mini M4, June-July 2026).
- **Qwen body transformation abandoned 2026-04-27.** Wiki body goes directly to corpus after hardening. Qwen reserved for Q&A.
- **Version-family articles routed to qa_direct** (snapshot codes are noise for training).
- **History / Data history sections dropped wholesale** (changelog by snapshot).
- **Infobox stats / Sounds / Data values KEPT as facts** (revived from plan v2).

For detailed reasoning see memory `project_pipeline_decisions_2026-04-27.md`.

## Infrastructure

### Mac Mini M2 (mini-fzamorano / Tailscale 100.103.89.96)

- Apple M2, 8 cores (4P + 4E), 16 GB RAM
- Ollama at `localhost:11434` (LaunchDaemon, auto-boot)
- Models available: `qwen3:8b`, `qwen3:14b`, `qwen3:4b`
- Throughput: ~17 tokens/sec (single instance; can't parallelize on M2 Metal)
- Python 3.9 (uses `from __future__ import annotations`)
- Project at `/Users/felipe/minegpt/`
- Prompt Lab tmux session `promptlab` on port 7860 (binds 0.0.0.0)

Deployment workflow: see memory `reference_macmini_deployment.md`.

### Hardware roadmap

- Mac Mini M4 24GB arrives June-July 2026
- Enables: larger model (350-750M), larger Qwen (30B+), spin-off inclusion in v2

## References

- `HARDENING_V2_RESULTS.md` — final state of Phase 4
- `QA_GENERATION_PLAN.md` — strategic plan for Phase 5
- `../prompts/PROMPT_TEMPLATES.md` — Q&A prompt templates
- `../tools/PROMPT_LAB_UI.md` — dev tool for Q&A iteration
- `../archive/WIKI_DATA_CLEANING_v1.md` — original detailed pipeline plan (historical)
- `../archive/HARDENING_V2_PLAN.md` — original hardening spec (implementation diverged)
- `../LEGAL.md` — license and source attribution
