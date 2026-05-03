# MineGPT — Hardening v2 Results (final)

> Final state of the second-pass regex hardening pipeline.
> Pipeline source: `scraper/hardening_v2.py` (12 phases, idempotent).
> Spec we worked from: `../archive/HARDENING_V2_PLAN.md` (now archived).
> Implementation diverged on ~7 points, captured in "What was preserved" +
> "Iteration log" sections below.
>
> Last run: 2026-05-03 (v12). 12 iterations across two sessions on user feedback.

## Final stats

| | |
|---|---:|
| Input | `articles_cleaned.jsonl` — 10,143 entries, 9,267,355 words |
| Output: main_corpus | `articles_hardened.jsonl` — **6,715 entries** |
| Output: qa_direct | `articles_qa_direct.jsonl` — **2,932 entries** |
| Output: dropped (audit) | `articles_dropped.jsonl` — **496 entries** |
| Words after pipeline | **7,407,698** (~7.41M) |
| **Word loss** | **20.07%** |
| Idempotency check | ✓ OK on 20 random + 30 validation samples |

## Routing breakdown

| Decision | Reason | Count |
|---|---|---:|
| route_qa_direct | version_changelog_page (ambiente=versions) | 2,262 |
| route_qa_direct | disambig (Disambiguation_pages cat) | 557 |
| route_qa_direct | set_index (Set_index_pages cat — all routed) | 113 |
| drop | deprecated_content (banner match) | 405 |
| drop | unused_content (Unused_features/biomes cat) | 50 |
| drop | removed_format_nbt_only (Item/Block format/) | 24 |
| drop | wiki_meta + wiki_meta_prefix (license, templates, redirects) | 21 |
| drop | edu_discontinued + edu_stub | 21 |
| drop | list_pure_enumeration (long List of...) | 5 |
| drop | history_subpage_changelog_only | 5 |
| drop | removed_features_only (primary cat backstop) | 1 |

## Section drops (within kept articles)

Top sections dropped in main corpus (count of articles where dropped):

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

The original plan v2 dropped these as "template scaffolding". After review of
real output (Amethyst Shard, Diamond, etc.) they were revived as facts:

- `Renewable: Yes`, `Stackable: Yes (64)`, `Tool: Pickaxe`, `Hardness: 1.5`, `Rarity tier: Common`
- `Sounds` section (`Amethyst chimes, Friendly Mobs, When an amethyst shard duplicates an allay, ...`)
- `Data values / ID` section (`Name: ..., Identifier: amethyst_shard, Translation key: item.minecraft.amethyst_shard, Item tags: minecraft:trim_materials`)
- Loot tables (`Item: Amethyst Shard, Structure: Ancient City, Container: Chest, Quantity: 1-15, Chance: 23.7%`)
- `Advancements` section (modern fact rows like `Advancement: Diamonds!, In-game description: Acquire diamonds`)
- All `Crafting recipe` / `Smithing ingredient` / `Trading` rows

## What was added beyond the plan

Categorical filters not in the plan:

- **Set_index_pages → all qa_direct** (2026-05-03). Originally dropped if `prose_ratio < 0.4`. Revised: by design these are listing pages (`X may refer to: A, B, C`); all 113 go to qa_direct as Q&A source.
- **Version-family → qa_direct** (2026-04-27). Per-version pages (`Java Edition Classic 0.0.13a`, `Bedrock Edition 1.18.0.24`, `Bedrock Edition exclusive features`, etc., 2,066 articles) routed to qa_direct since snapshot codes (23w12a) don't help training but support "when was X added?" Q&A.
- **Removed_features as primary → drop** (2026-05-03). Classifier reordered to push `Removed_features` to lowest priority; if it's still the most specific cat (no Commands/Animal_mobs/etc. cat to override), the article is dropped (`removed_features_only`). 80 articles caught.
- **Deprecation banner filter** (2026-05-03). Articles whose body opens with a wiki deprecation banner are dropped. Six banner forms covered (audit-derived):
  - `This page describes content that has been removed (from the game|and was only present in earlier versions)`
  - `This article (is about|describes) the unused (mob|biome|feature|...)`
  - `This article documents a feature that has been officially scrapped`
  - `This page describes an edition of the game that has been officially discontinued`
  - `This feature is available only in MinecraftEdu, an edition of the game that has been officially discontinued`
  - `officially made unobtainable\.` with negative lookahead for ` in <Edition>` (only the GLOBAL form drops; edition-specific stays)
  Tutorials (`title.startswith("Tutorial:")`) are exempt — they reference removed bugs as historical context but the how-to is current.
- **Unused_features / Unused_biomes cat → drop** (2026-05-03). 50 articles. Audit confirmed cat-only filter is 54/54 safe (no false positives).

## Iteration log (12 runs across 2 sessions)

| # | Date | Change | main_corpus | Word loss |
|---|---|---|---:|---:|
| v1 | 2026-04-27 | Initial implementation following plan | — | 19.18% |
| v2 | 2026-04-27 | Idempotency fixes (Layer A lookaheads, NBT strip moved to Phase 5, Phase 3 loop) | — | 19.07% |
| v3-v4 | 2026-04-27 | Various edge cases (nbsp normalization, `Editionand` fix, Phase 8 patterns) | — | 19.07% |
| v5 | 2026-04-27 | Removed universal `INFOBOX_LABELS_RE`; revived Sounds + Data values + ID; relaxed Phase 4 family-specific drops | — | 17.65% |
| v6 | 2026-04-27 | Added History/Data history to drop list | — | 19.18% |
| v7 | 2026-04-27 | Routed version-family to qa_direct via primary_classify | 7,135 | 19.07% |
| v8 | 2026-04-27 | Phase 5 ID-row protection (`Identifier:`/`Translation key:`/`Item tags:` masked before un-namespace); Advancements revived | 7,135 | 17.73% |
| v9 | 2026-04-27 | `See also: X` cross-refs dropped | 7,135 | 17.77% |
| v10 | 2026-05-03 | Classifier: `Removed_features` → end of priority list. New Phase 0 rule: drop if primary == `Removed_features`. | 7,055 | 18.35% |
| v11 | 2026-05-03 | Set_index_pages: drop prose-ratio gate; route ALL to qa_direct | 7,055 | 18.18% |
| v12 | 2026-05-03 | Deprecation filter: 6-pattern banner regex + `Unused_features`/`Unused_biomes` cat drops + Tutorial: exemption. 4 parallel deep audits informed pattern selection. | **6,715** | **20.07%** |

## Files

- Source: `scraper/hardening_v2.py` (~1400 lines, 12 phases)
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
# ~7-9 min for full corpus
# Optional: --sample raw_data/_validate_samples/set_1.jsonl  (10 articles, fast)
```

After re-run, sync to Mac Mini per memory `reference_macmini_deployment.md`.

## Snapshot reproducibility

- Input hash (sha256): `6306ce03e6245f5d...` (full hash in `hardening_report.json`)
- Articles processed: 10,143
- v12 outputs: `articles_hardened.jsonl` 6,715 / `articles_qa_direct.jsonl` 2,932 / `articles_dropped.jsonl` 496

Idempotence is part of the contract: `harden_article(harden_article(art)) == harden_article(art)`. The pipeline aborts with a warning if the check fails on the 20-sample run-time test.

## Spot-check (audit verified)

| Article | Verdict | Pass? |
|---|---|---|
| Reserved6 (former Bedrock technical block) | drop (banner: GLOBAL_UNOBT) | ✓ |
| Giant (unused mob, JE+LCE) | drop (cat: Unused_features) | ✓ |
| Nether Reactor Core (Pocket Edition removed) | drop (banner: GLOBAL_UNOBT) | ✓ |
| Petrified Oak Slab | drop (cat: Unused_features; borderline accepted) | ✓ |
| Bad Luck (unused effect) | drop (cat: Unused_features) | ✓ |
| Tutorial:Zero-ticking (uses removed bug as how-to) | keep (Tutorial: exempt) | ✓ |
| Tutorial:Mapping | keep | ✓ |
| Tutorial:Command stats | keep | ✓ |
| A Familiar Room (music — current in JE) | keep (EDITION_UNOBT) | ✓ |
| Java Edition Classic 0.0.13a | qa_direct (ambiente=versions) | ✓ |
| Commands/locatebiome (removed command) | drop (banner: removed) | ✓ |
| Diamond | keep (full corpus, infobox + sounds + IDs preserved) | ✓ |
| Amethyst Shard | keep (full corpus, generated loot preserved) | ✓ |

## Known follow-ups

- Layer C glue has only 25 auto-split entries. Manual curation of 475 candidates pending (`scraper/_layer_c_candidates.json`).
- ~5,200 articles in family `none` (Manufactured_blocks / Natural_blocks) get only universal Phase 8 cleanup. May need a dedicated `block` family if residual noise spotted.
- `Cause: ... Potency: ... Length: ...` rows currently kept verbatim (plan said "stitch into prose if Notes: present, else drop"). Stitching is a future enhancement.
- Mac Mini's `server.py` is sed-patched after every deploy to bind `0.0.0.0`. Long-term: env var `MINEGPT_BIND_HOST`.
- April Fools content (~253 articles, e.g. `Trophy (April Fools' joke)`, `2.0`) currently still in main corpus. Audit suggested separate handling — TBD.
- Consider adding `Lost_versions` (295) and `Discontinued` (40) cats to the drop filter — currently most are caught by version routing, but a few may slip through.
