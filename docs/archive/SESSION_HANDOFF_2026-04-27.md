# Session Handoff — 2026-04-27

> Comprehensive log of decisions, work done, and pending state across this
> 12+ hour session. Read this BEFORE doing anything in the next session.
>
> Author: Claude Opus 4.7
> User: Felipe Pacheco (FelipeJackFox)
> Project: MineGPT — custom 125-200M LLM trained on Minecraft Wiki

---

## TL;DR — strategic state

1. **Major pivot decided**: abandon Qwen-based transformation of wiki article bodies. Reason: LLM is inherently inconsistent, hallucinates, and 3 hours of prompt iteration produced 0-2/5 success rate. Wiki text is well-written; transforming it loses information.

2. **New strategy**:
   - **Wiki body**: hardened (regex-cleaned v2) directly into training corpus.
   - **Qwen role**: ONLY Q&A pair generation (structurally simpler output, more reliable).
   - **Q&A scale**: multi-lente per article (primary + also_in lenses, ~225K Q&A pairs total).

3. **Current state**:
   - Phase 4.0 tooling FULLY BUILT (Prompt Lab merged tab, batch worker, drafts, exclusions, status tracking, queue, single-test, atajos, URL state). Functional, server runnable.
   - Phase B+C done: `HARDENING_V2_PLAN.md` v2 published, validated by 3 independent agents on 30 unseen articles. Verdict: **GO with caveats** (all 12 caveats integrated into v2).
   - Phase D NOT YET IMPLEMENTED: `hardening_v2.py` is the next step.

4. **What to do next session**: implement `hardening_v2.py` per `HARDENING_V2_PLAN.md`, then apply to corpus, then pivot Prompt Lab UI to Q&A focus, then Q&A generation at scale.

---

## Reading order for next session

**Critical** (read these in order):
1. `HARDENING_V2_PLAN.md` — the operational spec for Phase D. 12-phase pipeline, complete regex specs, family-specific add-ons.
2. This file (`SESSION_HANDOFF_2026-04-27.md`) — context of what got done and why.
3. `C:/Users/luis/.claude/projects/D--Code-minegpt/memory/MEMORY.md` and the linked memories.

**Reference** (if needed):
4. `PHASE4_TRANSFORMATION_PLAN.md` — original plan, partially deprecated (Qwen transform removed from scope; Q&A part still applies).
5. `PROMPT_TEMPLATES.md` — Q&A prompt templates (still valid for Phase G).
6. `PHASE4_UX_DESIGN.md` — UX design of merged Prompt Lab tab (already implemented).
7. `CLASSIFIER_REDESIGN.md` — classifier taxonomy (already implemented, used for routing).
8. `WIKI_DATA_CLEANING.md` — Phase 1+2 plan (already done, documented).

---

## Decisions made this session (chronological)

### Stage 1: Confirmation of plan from previous session
- Pilot bucket: **Animal_mobs** (47 articles, vanilla core). Confirmed.
- Transform vs Q&A: **sequential per bucket** (transform first, Q&A second). Both phases get their own prompt iteration cycle.
- Multi-transform: **YES, all also_in lenses**. NO skip parents in v2 (Felipe's decision: information density worth the redundancy).
- Q&A: 1 call per article, model decides count adaptively (not fixed N). Avoid truncation risk on important articles.
- Audit of `Other`/`Mechanic_history` buckets: deferred to after pilot.

### Stage 2: PROMPT_TEMPLATES.md created
3-layer prompt architecture documented:
- **Layer 1**: universal header (read-only, ~400 tokens). One per phase (transform, qa).
- **Layer 2**: bucket-specific (editable, ~150-300 tokens). One per family (block, mob, item, plant, mechanic, world, command, crafting_recipe).
- **Layer 3**: user message (article text + meta).

Universal headers:
- `# Context — MineGPT classification system` block added (explains lenses).
- Strict formatting rules: `Key: value` plain, no bold, no bullets, no tables, omit-if-not-applicable, no emojis/unicode hearts.
- Output structure: `# Name / ## Overview / ## Properties / ## Details / ## Obtaining / ## Trivia`.
- Anti-hallucination rules: source-of-truth = article text only.

### Stage 3: UX audit + design (Phase 4.0)
- 2 background agents: `/ui-ux-pro-max` + `/ux-designer` audited the existing 3-tab Prompt Lab.
- Synthesis: `PHASE4_UX_DESIGN.md` published.
- 8 UX decisions confirmed by Felipe:
  1. Modes: 2 axes (sample size 5/20/50/full + checkbox `include also_in` default ON). NOT 5 plain options.
  2. Sub-states: `not_started → drafting → ready → running → completed | skipped` (instead of just `pending → running → completed`).
  3. Auto-mark `run_completed` (auto) vs `user_approved` (manual via `M` shortcut).
  4. Concurrency: 1 run at a time + queue max 3, prompts editable per bucket while in queue.
  5. Output structure: 1 file per bucket+lens (not single big file).
  6. Default exclude scope: per-bucket-lens. "Exclude all lenses" requires reason via flag modal.
  7. Layout: 3-col inline (35% prompt / 25% list / 40% output).
  8. Universal header: read-only collapsible in UI, editable only at file level.

### Stage 4: Phase 4.0 tooling implementation (FULLY BUILT)

**Backend** (`scraper/prompt_lab/`):
- `state.py` — Pydantic models (BucketState, ExclusionEntry, RunHistoryEntry, RunQueueState).
- `state_manager.py` — atomic write, threading locks, append-only JSONL for events, derive-state helpers.
- `batch_runner.py` — background worker thread, queue execution, output JSONL per bucket+lens, recovery on startup, cancel flag, current-item tracking with `last_item_duration` for ETA.
- `output_normalizer.py` — written then ARCHIVED (transform deprecated; not used in current pipeline).
- `server.py` — added 17+ new endpoints, Mac stats cache TTL 8s, integrated state manager + batch runner.

**Frontend** (`static/index.html`):
- Merged Prompt Lab + Production tabs into one. Old Production tab removed.
- 3-column layout: prompt editor / article list / output panel.
- Header redesign: tabs reduced (Prompt Lab + Articles), Mac Mini stats persistent across tabs.
- Bucket picker tree-mode (Cmd+K palette) showing super-cats expandible like Articles sidebar.
- Article detail enriched: wiki_categories + primary_bucket + also_in (clickable pills).
- Status badges in Articles tab sidebar (T/Q&A per bucket + supercat counters).
- StatusBadge component with 4 states (done/running/pending/skipped) + pulse animation.
- Button primitive (xs/sm/md sizes, primary/secondary/danger/success/warn variants).
- Tokens CSS: `--space-*`, `--surface-*`, `--text-*`, `--accent-bg/fg/bd`, etc.
- Autosave drafts cada 2s a `prompts/drafts/{bucket}_{phase}_draft.txt`.
- Single-test "Test on this article" button → `/api/runs/single` → result inline.
- Persistent queue strip at bottom of viewport (visible on Articles tab too).
- Detailed run progress: model, current item, time per item, ETA, errors.
- Keyboard shortcuts: Cmd+K, Cmd+Enter, Shift+Cmd+Enter, ?, 1/2/3/4, S, P, T, X, M, etc.
- URL state: `?view=lab&bucket=X&phase=transform&mode=full&also_in=1`.
- Toggle normalized/raw output view (when normalizer was active).
- Cheat sheet `?` modal extended with Lab shortcuts.
- Fix bug: `x-text` with HTML entities (line 606 was rendering `&#9654;` literal).

**Critical bug fix discovered mid-session**:
- `RunQueueItem` did NOT carry `model`/`num_ctx`/`temperature`/`no_think`. Frontend sent these in single-run only. Batch runs ALWAYS used `qwen3:8b` regardless of dropdown selection.
- Fixed: added params to `RunQueueItem`, `EnqueueBody`, propagated through `_execute()`.
- Implication: ALL test_5/test_20/full runs Felipe did before this fix were qwen3:8b, not qwen3:14b. The "qwen3:14b iteration" he thought he was doing was actually qwen3:8b.

### Stage 5: Iterating on transform (failed approach)
- Felipe ran multiple test_5 batches on Animal_mobs.
- Iteration sequence: simple prompt → anti-hallucination rules → Section assignment → Strict field emission rules → Pure prose (cleaning bullets/bold from prompt itself).
- Pattern: model output formatting was inconsistent. 5 mobs would yield 3 distinct format patterns (canonical / hybrid / bold-only).
- Felipe's observation: "Es muy caro para el tokenizador y muy difícil de aprender" → asked if we should embrace the model's natural format.
- Verification: cleaned source has 0 bold/bullets — the inconsistency was generated by the model from its training, not the source.
- Felipe's final decision (key pivot): **abandon Qwen transformation entirely**. Use cleaned wiki text directly with hardening v2 regex. Reserve Qwen for Q&A only.

### Stage 6: Multi-agent audit (Phase A)
- 10 agents launched in parallel, each auditing one family (mobs, manufactured_blocks, natural_blocks, items, mechanics, world, commands, versions, non_vanilla, external).
- Constraint discovered: agents can't run Bash/curl in their sandbox; must Read filesystem directly.
- 8/10 succeeded (used Read directly on `articles_cleaned.jsonl`); 2 gave up asking for Bash.
- Phase A.5: relaunched 2 agents with pre-extracted samples in `raw_data/_audit_samples/{family}.jsonl`. Both succeeded.
- Total: 108+ articles audited. Cleanliness average: 3/10. Massive residual junk in cleaned text.

### Stage 7: Synthesis (Phase B)
- `HARDENING_V2_PLAN.md` v1 written.
- 11 ordered passes, family-specific add-ons, category-based filters.
- Estimated: ~17-20% of corpus drops at Phase 0 (~1700-2000 articles), ~30-50% bytes reduction in remaining articles.
- Disambig pages NOT dropped — routed to `qa_direct` for Q&A pipeline.
- Achievement/Advancement sub-sections in OTHER articles dropped, but PRIMARY achievement articles kept.

### Stage 8: Validation (Phase C)
- 30 unseen articles (3 sets of 10) validated by 3 independent agents.
- Verdict: **GO with caveats** (unanimous from 3 agents).
- 12+ caveats identified, all addressable without re-architecture.
- Critical fixes:
  - **Pass 6 (namespaced ID strip)**: was deleting subjects of sentences (`minecraft:weeping_vines and minecraft:weeping_vines_plant have been added to the #minecraft:mineable/axe block tag` → `and have been added to the # block tag`). FIX: un-namespace, don't delete.
  - **Pipeline order**: word-boundary repair (Pass 6) was BEFORE section drops, damaging hex codes (`#6A7039` → `# 6 A7039`) and identifiers slated for deletion. FIX: section drops + family drops BEFORE word-boundary.
  - **Pass 1 DO_NOT_SPLIT too narrow**: missed gamerule names (`globalSoundEvents`), AI goal classes (`RangedAttackGoal`), translation keys (`craftingScreen`). FIX: Phase 5 protection layer with placeholders.
  - **Lowercase-lowercase fusion** (e.g. `Notchshowed`, `acraftingrecipe`, `withcows`): #1 uncovered junk class. FIX: expand `CURATED_GLUE` from ~40 to ~100 entries + Layer C corpus token-frequency analysis.
  - **Universal infobox-row stubs** (`Renewable: Yes / Stackable: 64 / Tool: Pickaxe / ...`): in every block/item/biome article, plan v1 missed. FIX: universal `INFOBOX_LABELS` regex in Phase 8.
  - **`## Issues` blanket drop too aggressive**: Brick Pyramid has substantive prose in its Issues section. FIX: conditional drop only if section body contains "are maintained on the bug tracker".
  - **`[verify]` strip caused word-glue** (`absent[verify]from` → `absentfrom`). FIX: collapse to space.

### Stage 9: Plan v2 published
- `HARDENING_V2_PLAN.md` updated to v2 with all 12 caveats integrated.
- 12 phases (was 11), Phase 5 added (identifier protection placeholders).
- Pipeline reordered.
- Pass 6 rewritten (un-namespace).
- ~30 new pattern entries added across all phases.

---

## Files created/modified this session

### Documents (read these next session)
- `HARDENING_V2_PLAN.md` (created, v2 final) — **PRIMARY SPEC for Phase D**.
- `SESSION_HANDOFF_2026-04-27.md` (this file) — context.
- `PROMPT_TEMPLATES.md` (created, valid for Q&A phase).
- `PHASE4_UX_DESIGN.md` (created, work already done).

### Code (DO NOT need to modify in next session — backend is functional)
- `scraper/prompt_lab/state.py` (created)
- `scraper/prompt_lab/state_manager.py` (created)
- `scraper/prompt_lab/batch_runner.py` (created)
- `scraper/prompt_lab/output_normalizer.py` (created, ARCHIVED — transform deprecated)
- `scraper/prompt_lab/server.py` (extensively modified — 17+ new endpoints)
- `scraper/prompt_lab/static/index.html` (extensively modified — merged tab built)
- `scraper/prompt_lab/static/_legacy_index_pre_merge.html` (backup before merge)
- `scraper/prompt_lab/prompts/_headers/transform.txt` (created, valid)
- `scraper/prompt_lab/prompts/_headers/qa.txt` (created, valid)
- `scraper/prompt_lab/prompts/drafts/` (autosave directory)
- `scraper/prompt_lab/ollama_client.py` (modified: timeout 240→900s, default temp 0.0)

### Data
- `raw_data/_audit_samples/` (Phase A.5 sample files for gap-fill agents)
- `raw_data/_validate_samples/` (Phase C 30-article sample, 3 sets)
- `raw_data/_pipeline_state/bucket_status.json` (state file)
- `raw_data/_pipeline_state/article_exclusions.jsonl` (event log)
- `raw_data/_pipeline_state/run_history.jsonl` (run audit log)
- `raw_data/_pipeline_state/run_queue.json` (queue state)
- `raw_data/transformed/` (output dir for batch runs — currently EMPTY after final cleanup)

### Sample audit data preserved (useful for Phase D + E validation)
```
raw_data/_audit_samples/
  manufactured_blocks.jsonl  (12 articles, ~170KB)
  mechanics.jsonl            (12 articles, ~200KB)
raw_data/_validate_samples/
  set_1.jsonl                (10 unseen articles, ~78KB)
  set_2.jsonl                (10 unseen articles, ~99KB)
  set_3.jsonl                (10 unseen articles, ~89KB)
```

---

## State of the Prompt Lab tooling

The tooling at `http://127.0.0.1:7860` is functional. Server can be started with:
```bash
python -m scraper.prompt_lab.server
```

Features that work today:
- Cmd+K bucket picker (tree-mode, super-cats expandable, search-fuzzy when query present).
- Bucket selection → loads state, articles, draft, status badges.
- Phase toggle Transform/Q&A (independent, no blocking).
- Sample mode radio (5/20/50/Full) + include also_in checkbox.
- Prompt editor with universal header collapsible (read-only) + bucket-specific (editable).
- Autosave draft every 2s.
- "Save as approved" → promotes draft to `prompts/{phase}/{family}.txt`.
- Article list with filter, sort, show=all|excluded_t|excluded_qa|primary|also_in.
- Article expand inline → shows full text + cats wiki + primary bucket + also_in pills.
- Exclude per-article (transform/qa independent toggles).
- "Flag exclude all lenses" → modal with reason field (mandatory).
- Status badges in Articles tab sidebar + super-cat counters.
- Single-test "Test on this article" → ~30-90s with qwen3:14b (or selected model).
- Batch runs (test_5/test_20/sample_50/full) execute correctly via worker thread.
- Queue strip persistent across tabs with current item, model, ETA, cancel button.
- Mac Mini stats persistent in header (RAM, thermal, CPU, online/cached state).
- Run history per bucket + global.
- Resume on refresh, recovery on server restart.
- Atajos: Cmd+K, Cmd+Enter, Shift+Cmd+Enter, ?, 1/2/3/4, S, P, T, X, M, ↑↓, Esc.
- URL state: `?view=lab&bucket=X&phase=transform&mode=full&also_in=1`.

Features pending pivot for Q&A focus (Phase F):
- Rename "Transform" phase label to be Q&A-friendly when transform deprecated.
- Add "Hardening Preview" tab to inspect before/after of `hardening_v2.py` output.
- Possibly: add multi-lente Q&A iteration UI (current Q&A flow assumes single-lens).

---

## What is NOT done (the operational backlog)

### Phase D — Implement hardening_v2.py (NEXT, ~8-10h)
Spec: `HARDENING_V2_PLAN.md` v2.
12-phase pipeline:
- Phase 0: category filter (drop or route_qa_direct)
- Phase 1: pre-clean (ZW chars, curly quotes, U+2044, multi-newlines)
- Phase 2: section drops (Sounds, Data values, Block states, Block data, Entity data, Issues conditional, Videos, Gallery, etc.)
- Phase 3: line-level boilerplate (1632× "Issues relating to...", 107× "An interactive widget...", hatnotes, editor markers, `[verify]` collapse to space)
- Phase 4: family-specific drops (mob spawn tables, world climate/colors block, mechanics enchantment infobox)
- Phase 5: identifier protection (placeholder substitution for hex codes, gamerules, AI goals, translation keys)
- Phase 6: word-boundary repair (Layer A regex + Layer B CURATED_GLUE ~100 entries + Layer C corpus-frequency-derived dictionary)
- Phase 7: edition stutter collapse + phase-transition orphans
- Phase 8: tabular row drops (~30 patterns)
- Phase 9: inline noise (un-namespace `minecraft:foo` to `foo`, anchor refs, NBT tags, empty parens)
- Phase 10: identifier restore (un-mask placeholders)
- Phase 11: final cleanup (multi-space, multi-newline, post-comma space, empty headers)
- Phase 12: dedup repeated 200+ char blocks (the Notch quote bug)

### Phase E — Apply hardening to full corpus (~1-2h)
- Run `hardening_v2.py` on `raw_data/wiki/articles_cleaned.jsonl` (10143 articles).
- Output:
  - `raw_data/wiki/articles_hardened.jsonl` — main corpus for training.
  - `raw_data/wiki/articles_qa_direct.jsonl` — disambig + Set_index pages with prose.
  - `raw_data/wiki/articles_dropped.jsonl` — audit log of drops.
- Validate via 1 agent comparing before/after on 20 articles.

### Phase F — Pivot Prompt Lab UI (~2-3h)
- Hide/disable Transform UI (it's deprecated).
- Add "Hardening Preview" tab where Felipe can compare before/after for any article (uses `articles_hardened.jsonl`).
- Refactor Q&A pipeline to support multi-lente per article.

### Phase G — Q&A multi-lente at scale (~50-100h Mac Mini wall clock)
- Iterate Q&A prompts per family.
- Generate 3-25 Q&A pairs per article × 5000 articles × 1-3 lenses average = ~50-225K Q&A pairs.

### Other deferred items (do not block Phase D)
- Spin-off classification (Phase 3 of original WIKI_DATA_CLEANING.md plan) — postponed to v2 of MineGPT, when Mac Mini M4 24GB arrives (June-July 2026).
- Q&A direct generation for disambig pages (separate path).

---

## Quick verification on next session start

Run these to confirm state:

```bash
# 1. Server can start
python -m scraper.prompt_lab.server
# (Ctrl+C after seeing "Pipeline state files ready" + "Batch run worker started")

# 2. Required files exist
ls -la HARDENING_V2_PLAN.md PROMPT_TEMPLATES.md PHASE4_UX_DESIGN.md
ls scraper/prompt_lab/state.py scraper/prompt_lab/state_manager.py scraper/prompt_lab/batch_runner.py
ls -la raw_data/wiki/articles_cleaned.jsonl

# 3. Pipeline state is clean (or contains last session's setup)
cat raw_data/_pipeline_state/bucket_status.json
cat raw_data/_pipeline_state/run_queue.json

# 4. Sample data preserved for Phase D validation
ls raw_data/_audit_samples/ raw_data/_validate_samples/

# 5. The article corpus (read-only input for Phase D)
wc -l raw_data/wiki/articles_cleaned.jsonl   # Should be 10143
```

If all pass: read `HARDENING_V2_PLAN.md` start to finish, then start Phase D implementation.

---

## Lessons from this session (don't repeat)

1. **Don't fight LLM inconsistency with more rules**. After 3 hours iterating prompts trying to get qwen3:14b to produce consistent format, the answer was to stop trying. Felipe was right.

2. **Don't use agents for tasks requiring HTTP unless you confirm Bash works in sandbox**. 2 of 10 agents in Phase A failed because they couldn't curl. Pre-extract samples to filesystem files before launching agents.

3. **Don't trust dropdown values match what's actually being sent**. The qwen3:14b dropdown bug went undetected for hours. Always verify the per-run snapshot in run_history.jsonl matches what was selected.

4. **Always confirm decisions in writing, not in flight**. The original handoff that started this session had hallucinated user votes that the user never gave. Reconfirm always.

5. **Sub-section drops are higher ROI than line-level regex**. Dropping `## Sounds`, `## Data values`, `## Issues`, `## Gallery` wholesale recovers 40-60% of every article's bytes. Trying to clean them line-by-line is fighting losing battles.

6. **Validation is non-negotiable**. The 12 caveats found in Phase C would have caused real damage (corrupted training data) if implemented as v1. The 2-hour validation cost was worth it.

7. **Lowercase-lowercase fusion is the dominant junk class** (the `[a-z][A-Z][a-z]` regex misses ~70% of real fusions). Without a corpus-frequency-derived curated dictionary (Phase 6 Layer C), the hardening will plateau at ~6/10 cleanliness instead of ~8/10.

---

## Remember for next-Claude

- User is Felipe Pacheco Zamorano (FelipeJackFox on GitHub), data science student at ITESM Querétaro.
- Speaks Spanish-Mexico, prefers tú (not vos), avoid argentinismos / españolismos peninsulares.
- No emojis unless asked.
- Concise, no preambles, no end-of-response summaries.
- Don't push --force without confirmation.
- Don't delete files without confirming.
- The server runs at `http://127.0.0.1:7860`.
- The Mac Mini M2 (`mini-fzamorano`) hosts Ollama with qwen3:8b and qwen3:14b.
- `D:/Code/minegpt` is the repo root. CLAUDE.md exists.
- Memory persists at `C:/Users/luis/.claude/projects/D--Code-minegpt/memory/`.
