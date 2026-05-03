# MineGPT — Prompt Lab UI

> Reference for the Prompt Lab dev tool's current UI architecture.
> Replaces `../archive/PHASE4_UX_DESIGN.md` (which described the original 3-tab design before the merged tab + compare-mode redesign).
>
> Tool runs on Mac Mini at `http://mini-fzamorano:7860`. Code lives in `scraper/prompt_lab/`.
> See `reference_macmini_deployment.md` (memory) for deploy workflow.

## Tab structure

- **Prompt Lab** — Test prompts and run batch jobs (test_5/test_20/sample_50/full).
- **Articles** — Browse the wiki article corpus across pipeline versions.

## Articles tab (multi-version browser)

Pipeline versions shown as colored pills above each article body, ordered by phase:

| Pill | Phase | File | Color |
|---|---|---|---|
| raw | 1 | `articles.jsonl` | gray |
| filtered | 2 | `articles_filtered.jsonl` | blue |
| cleaned | 3 | `articles_cleaned.jsonl` | green light |
| removed | (audit) | `articles_removed.jsonl` | red |
| **hardened v2** | 4 | `articles_hardened.jsonl` | green saturated |
| **qa direct** | 4 | `articles_qa_direct.jsonl` | teal |
| transformed | 5 | (deprecated, no file) | purple |
| qa | 6 | (pending, no file) | amber |

Clicking a pill switches the active version. Pills disabled if the article is not in that file (each article exists in a different subset of versions depending on its routing).

External sources (Wikipedia bios, Word of Notch, YouTube transcripts) only have `cleaned` version available. Title prefixes: `[wp]`, `[notch]`, `[yt]`.

## Compare mode (key `c`) — redesigned 2026-05-02

Triggered by pressing `c` while in Articles tab. Toggles a side-by-side diff view.

**Mental model**: BASE → TARGET. The TARGET is the version pill currently active (what you're reading). The BASE is selected via dropdown — typically the previous pipeline phase. Diff direction matches `git diff base..head`:
- Red strikethrough on left = "in base, removed in target"
- Green highlight on right = "added in target, not in base"

**Layout**:

```
┌─ Compare bar ──────────────────────────────────────────────────┐
│ compare against [base ▾] →   target: hardened v2                │
│                                       ■ -345w   ■ +12w     [✕] │
└─────────────────────────────────────────────────────────────────┘
┌──── BASE ──────────────────┬──── TARGET (active) ──────────────┐
│ ┃ cleaned                  │ ┃ hardened v2                     │
│ ┃ For other uses, see      │ ┃ Rarity tier: Common             │
│ ┃ Diamond family.          │ ┃ Renewable: No (except via vault)│
│ ┃ Rarity tier: Common      │ ┃ Stackable: Yes (64)             │
│ ┃ ...                      │ ┃ ...                             │
└────────────────────────────┴───────────────────────────────────┘
```

**Visual cues**:
- 4px colored left border on each pane matching the version's pipeline color (persistent orientation as you scroll)
- Stats consolidated in compare bar (`-Nw  +Nw` instead of split per pane)
- Diff is always on (no toggle)
- Auto-picks sensible base if base equals target (prefers previous pipeline phase)

**Interactions**:
- `c` or `✕` button or `Esc` → exit compare
- `1-6` keys → switch active version (target). Compare auto-refreshes with new target.
- Click any pipeline pill above → also changes the target.

**Diff implementation** (`computeDiff` in index.html):
- Word-level LCS via dynamic programming (Uint16Array DP, ~30M cells max ≈ 5400×5400 tokens)
- Falls back to line-level LCS for huge articles (rare; only top-of-corpus version pages)
- Whitespace tokens excluded from word-count stats

## Prompt Lab tab (testing + batch runs)

3-column layout: prompt editor / article list / output panel.

- **Cmd+K** — bucket picker (tree-mode, super-cats expandable)
- **Phase toggle** — Transform / Q&A. Transform half is deprecated post-pivot but UI still supports it for legacy.
- **Mode radio** — test_5 / test_20 / sample_50 / full + checkbox `include also_in`
- **Single-test** "Test on this article" button → ~30-90s with qwen3:14b
- **Batch runs** via worker thread; queue strip persistent across tabs with current item, model, ETA, cancel button
- **Autosave** drafts every 2s to `prompts/drafts/{bucket}_{phase}_draft.txt`
- **Save as approved** → promotes draft to `prompts/{phase}/{family}.txt`
- **Status badges** in Articles sidebar (T ✓ / Q&A ✓ / pending) per bucket + super-cat aggregate counters
- **Run history** persisted per bucket + global; recovery on server restart

## Keyboard shortcuts

Articles tab:
- `c` toggle compare; `Esc` exit compare
- `f` flag misclassification (does NOT fire when Ctrl/Meta/Alt held — Ctrl+F passes through to browser find)
- `1-6` switch active version
- `v` / `V` cycle next/prev version
- `[` collapse sidebar
- `↑/↓` navigate articles in list
- `←/→` previous/next article
- `/` focus title filter
- `g` focus group filter
- `?` open help
- `p` toggle pin

Global:
- `Cmd+K` open palette (bucket picker)
- `Cmd+Enter` run prompt
- `Shift+Cmd+Enter` run as full

## Backend

`scraper/prompt_lab/server.py` — FastAPI on `0.0.0.0:7860`, ~1940 lines, 17+ endpoints.
Imports: `article_viewer`, `state_manager`, `batch_runner`, `output_normalizer`, `state`, `ollama_client`, `explore_subgroups` (transitively via article_viewer).

State files at `raw_data/_pipeline_state/`:
- `bucket_status.json` — per-bucket transform/qa status
- `article_exclusions.jsonl` — append-only event log
- `run_history.jsonl` — run audit log
- `run_queue.json` — current queue + active item

## Mac Mini-specific patches

The local `server.py` binds to `127.0.0.1`. After every tar deploy, sed-patch to `0.0.0.0`:

```bash
ssh felipe@mini-fzamorano "cd ~/minegpt && \
  sed -i.bak 's|host=\"127.0.0.1\"|host=\"0.0.0.0\"|' scraper/prompt_lab/server.py"
```

TODO long-term: env var `MINEGPT_BIND_HOST=0.0.0.0`.

## Open follow-ups

- `server.py:1466` — `skipped_lenses: TODO — Fase 4.1`. Returns empty list. Phase 4.1 is in limbo post-pivot; either implement or remove the dead code.
- The "transformed" pill is still in `ARTICLE_VERSIONS` but file doesn't exist (transform deprecated). Could remove from list, but harmless as-is (renders disabled).
- Compare mode could add a "show only changes" toggle (collapses unchanged paragraphs) for very long articles.
