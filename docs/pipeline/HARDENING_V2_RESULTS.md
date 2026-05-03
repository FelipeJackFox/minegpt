# MineGPT — Hardening v2 Results (final)

> Final state of the second-pass regex hardening pipeline.
> Pipeline source: `scraper/hardening_v2.py` (12 phases, idempotent).
> Spec we worked from: `HARDENING_V2_PLAN.md` (with implementation deltas
> documented in its banner).
>
> Run completed: 2026-05-02 (after 9 iterations on user feedback).

## Final stats

| | |
|---|---:|
| Input | `articles_cleaned.jsonl` — 10,143 entries, 9,267,355 words |
| Output: main_corpus | `articles_hardened.jsonl` — **7,135 entries** |
| Output: qa_direct | `articles_qa_direct.jsonl` — **2,834 entries** |
| Output: dropped (audit) | `articles_dropped.jsonl` — **174 entries** |
| Words after pipeline | 7,624,042 (or ~7.62M) |
| **Word loss** | **17.77%** |
| Idempotency check | ✓ OK on 20 random + 30 validation samples |

## Routing breakdown

| Reason | Count | Action |
|---|---:|---|
| disambig (Disambiguation_pages cat) | 557 | route to qa_direct |
| version_changelog_page (ambiente=versions) | 2,066 | route to qa_direct |
| set_index_with_prose (set_index w/ prose ratio >0.4) | 15 | route to qa_direct |
| set_index_pure_list | 96 | drop |
| removed_format_nbt_only | 24 | drop |
| wiki_meta + wiki_meta_prefix | 21 | drop |
| edu_discontinued / edu_stub | 21 | drop |
| history_subpage_changelog_only | 5 | drop |
| list_pure_enumeration | 5 | drop |
| (no qa-route reason for the other ~196 dropped — version_stub etc.) | — | — |

## Section drops (within kept articles)

Top 10 sections dropped in main corpus (count of articles where dropped):

| Section | Articles |
|---|---:|
| Gallery | ~4,000 |
| History | ~4,000 |
| Issues (boilerplate-gated) | ~1,632 |
| Screenshots | ~1,400 |
| Achievements (non-achievement articles) | ~919 |
| Videos | ~917 |
| Data history | ~643 |
| In other media | ~589 |
| Renders | ~568 |
| Block states / Fluid states | ~391 |

## What was preserved (revised from plan)

The plan v2 dropped these as "template scaffolding". After Felipe reviewed real
output (Amethyst Shard, Diamond), they were revived as facts:

- `Renewable: Yes`, `Stackable: Yes (64)`, `Tool: Pickaxe`, `Hardness: 1.5`, `Rarity tier: Common`
- `Sounds` section (`Amethyst chimes, Friendly Mobs, When an amethyst shard duplicates an allay, ...`)
- `Data values / ID` section (`Name: ..., Identifier: amethyst_shard, Translation key: item.minecraft.amethyst_shard, Item tags: minecraft:trim_materials`)
- Loot tables (`Item: Amethyst Shard, Structure: Ancient City, Container: Chest, Quantity: 1-15, Chance: 23.7%`)
- `Advancements` section (modern fact rows like `Advancement: Diamonds!, In-game description: Acquire diamonds`)
- All `Crafting recipe` / `Smithing ingredient` / `Trading` rows

## Iteration log (9 runs, May 2)

| # | Change | Word loss |
|---|---|---:|
| v1 | Initial implementation following plan | 19.18% |
| v2 | Idempotency fixes (Layer A lookaheads, NBT strip moved to Phase 5, Phase 3 loop) | 19.07% |
| v3-v4 | Various edge cases (nbsp normalization, Editionand fix, Phase 8 patterns) | 19.07% |
| v5 | Removed universal INFOBOX_LABELS_RE; revived Sounds + Data values + ID; relaxed Phase 4 family-specific drops | 17.65% (less aggressive) |
| v6 | Added History/Data history to drop list | 19.18% |
| v7 | Routed version-family to qa_direct via primary_classify | 19.07% |
| v8 | Phase 5 ID-row protection (Identifier:/Translation key:/Item tags: masked before un-namespace); Advancements revived | 17.73% |
| v9 | `See also: X` cross-refs dropped | 17.77% (final) |

## Files

- Source: `scraper/hardening_v2.py` (1369 lines, 12 phases)
- Helpers:
  - `scraper/_token_freq_analysis.py` — generates Layer C glue from token frequencies
  - `scraper/_hardening_audit.py` — produces before/after sample markdown
- Generated dictionaries:
  - `scraper/_layer_c_glue.json` — 25 auto-split entries (loaded at runtime)
  - `scraper/_layer_c_candidates.json` — top 500 candidates for manual review
- Classifier dependency: `scraper/explore_subgroups.py` (cat-driven, used by Phase 0 + family detection)

## Re-run command

```bash
cd D:/Code/minegpt && python -m scraper.hardening_v2 --force
# ~6-10 min for full corpus
# Optional: --sample raw_data/_validate_samples/set_1.jsonl
```

After re-run, sync to Mac Mini per `reference_macmini_deployment.md`.

## Snapshot reproducibility

Input hash (sha256): `6306ce03e6245f5d...` (full hash in `hardening_report.json`).
Output hash (md5 of articles_hardened.jsonl): see latest run's md5sum.

## Known follow-ups

- Layer C glue has only 25 auto-split entries. Manual curation of 475 candidates pending (review `_layer_c_candidates.json`).
- 5,218 articles in family `none` (Manufactured_blocks / Natural_blocks) get only universal Phase 8 cleanup. May need a `block` family if Felipe sees residual noise in spot-checks.
- `Cause: ... Potency: ... Length: ...` rows currently kept verbatim (plan said "stitch into prose if Notes: present, else drop"). Stitching is a future enhancement.
- Mac Mini's `server.py` is sed-patched to bind `0.0.0.0`. Long-term: env var `MINEGPT_BIND_HOST`.
