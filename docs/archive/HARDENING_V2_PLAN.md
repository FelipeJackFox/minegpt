# MineGPT — Hardening v2 Plan (validated)

> **Status (2026-05-02): IMPLEMENTED. Pipeline shipped + ran 9 iterations on full corpus.**
> See `HARDENING_V2_RESULTS.md` for the actual final state (which differs from this
> plan in several places — see "Implementation deltas" below).
>
> This document is preserved as the spec-of-record we worked from.
>
> Final corpus: 9.27M → 7.62M words (17.77% loss), 7,135 main_corpus + 2,834 qa_direct + 174 dropped, idempotent.

## Implementation deltas vs this plan

The plan's Phase 2 dropped `Sounds`, `Data values`, `Block states`, `Block data`,
`Entity data` wholesale. After Felipe reviewed Amethyst Shard / Diamond outputs,
**Sounds, Data values, ID** were REVIVED (they're useful facts for training).
Block states / Fluid states / Block data / Entity data stay dropped (NBT scaffolding).

The plan's Phase 8 had a universal `INFOBOX_LABELS_RE` that dropped lines like
`Renewable: Yes`, `Stackable: Yes (64)`, `Hardness: 1.5`. These were REVIVED as
facts. Phase 8 now only drops genuinely corrupt scaffolding.

The plan kept version-family articles in main corpus. Implementation routes them
to `articles_qa_direct.jsonl` (snapshot codes confuse model). Phase 0 calls
`primary_classify` and routes ambiente=`versions` to qa_direct.

History / Data history sections are dropped wholesale (changelog by snapshot).
Plan didn't specify this; Felipe added the rule on 2026-05-02.

Phase 5 was extended to mask ID-row lines (Identifier:/Translation key:/Item tags:)
BEFORE un-namespacing, so `minecraft:trim_materials` etc. survive verbatim.

> Original plan info preserved below.
>
> Phase B + C output: consolidated, prioritized roadmap for second-pass regex
> hardening of `raw_data/wiki/articles_cleaned.jsonl`. Phase A audit covered
> 108+ articles across 10 families. Phase C validation tested the plan against
> 30 unseen articles via 3 independent agents.
>
> Phase A audit cleanliness: avg **3/10**.
> Phase C verdict: **GO with 12 caveats** (unanimous from 3 validators).
>
> Date: 2026-04-27

---

## Executive summary

The cleaner v1 stripped wiki markup but did NOT:
1. Insert spaces at template boundaries (creating 100% prevalent word-merge artifacts).
2. Drop entire low-signal sections (Sounds, Data values, Achievements, Issues, Gallery, History) that are template-driven and contribute zero prose.
3. Strip zero-width characters and editor maintenance markers.
4. Detect duplicated content (a single quote repeated 25 times in one article).

This plan defines **9 ordered passes** + **family-specific add-ons** + **category-based filters** to be implemented in `hardening_v2.py`.

**Phase C validation findings**: plan structurally sound. 12 issues identified, all addressable without re-architecture. Top concerns:
- **Pass 1 (word-boundary)** has too narrow DO_NOT_SPLIT list — must protect gamerule names, AI goal classes, translation keys, hex colors.
- **Pass 6 (namespaced ID strip)** deletes referents in real prose — must un-namespace instead of delete.
- **Lowercase-lowercase fusion** (e.g. `Notchshowed`, `acraftingrecipe`) is the #1 uncovered junk class — needs expanded CURATED_GLUE.
- **Infobox top-row stubs** (`Renewable:`, `Hardness:`, `Stackable:`, etc.) appear in every block/item/biome article and are not in plan v1.
- **Pipeline order** must change: section drops BEFORE word-boundary repair (not after).

---

## Pipeline execution order (REVISED v2)

```
Phase 0:  Category filter      → drop articles by (cat, word_count) rules
Phase 1:  Pre-clean (Pass 0)   → ZW chars, curly quotes, U+2044, multi-newlines
Phase 2:  Section drops         → Sounds, Data values, Block states, Issues, Gallery [MOVED EARLIER]
Phase 3:  Boilerplate strip    → "Issues relating to...", hatnotes, editor markers
Phase 4:  Family-specific drops → Climate/Colors block, Sulfur cube banner, etc. [MOVED EARLIER]
Phase 5:  Identifier protection → mask hex codes, identifiers, translation keys with placeholders
Phase 6:  Word-boundary repair  → CURATED_GLUE + camelCase split (now safe — drops happened first)
Phase 7:  Edition stutter       → collapse repeated edition prefixes in History
Phase 8:  Tabular row drops     → Block:, Mob:, Item:, Map color:, Category:, Data:, etc.
Phase 9:  Inline noise          → un-namespace minecraft:foo, anchor refs, NBT type tags
Phase 10: Identifier restore    → restore placeholders from Phase 5
Phase 11: Final cleanup         → multi-space, multi-newline, post-comma space, trim
Phase 12: Dedup repeated        → catch the Notch-quote bug (200+ char repeated paragraph)
```

**Key reordering vs v1**: section drops + family-specific drops now happen BEFORE word-boundary repair. This prevents Pass 6 (word-boundary) from damaging hex codes (`#6A7039`), identifiers (`RangedAttackGoal`), and other content slated for deletion anyway.

---

## Phase 0 — Category filter

Apply BEFORE any text cleanup — drop entire articles by category + word_count rules. Add 2 new rules from Phase C:

```python
def should_drop_article(art):
    cats = set(art.get("categories") or [])
    title = art.get("title", "")
    wc = art.get("word_count", 0)

    # Disambig pages: KEEP for Q&A direct (route to qa_direct, not main corpus)
    if "Disambiguation_pages" in cats:
        return ("route_qa_direct", "disambig")

    # Set_index_pages: route to qa_direct IF prose exists, else drop
    # (NEW v2: validation showed Game customization has real prose)
    if "Set_index_pages" in cats:
        text = art.get("text", "")
        lines = [l for l in text.split('\n') if l.strip()]
        prose_ratio = sum(1 for l in lines if len(l.split()) > 6) / max(len(lines), 1)
        if wc > 200 and prose_ratio > 0.4:
            return ("route_qa_direct", "set_index_with_prose")
        return ("drop", "set_index_pure_list")

    # Lists with majority short lines: DROP
    if title.startswith("List of ") and wc > 1000:
        text = art.get("text", "")
        lines = [l for l in text.split('\n') if l.strip()]
        if lines and sum(1 for l in lines if len(l.split()) <= 6) / len(lines) > 0.7:
            return ("drop", "list_pure_enumeration")

    # Version stubs
    if any(c in cats for c in ["Java_Edition_versions", "Bedrock_Edition_versions",
                                "Pocket_Edition_versions", "Lost_versions"]) and wc < 80:
        return ("drop", "version_stub")

    # NEW v2: Java Edition history of textures/* subpages — pure changelog, no prose
    if title.startswith("Java Edition history of ") and wc < 500:
        return ("drop", "history_subpage_changelog_only")

    # Removed format pages
    if "Removed_features" in cats and (title.startswith("Item format/") or title.startswith("Block format/")):
        return ("drop", "removed_format_nbt_only")

    # NEW v2: MinecraftEdu blocks (discontinued edition) — short ones add no value
    if "MinecraftEdu_blocks" in cats and wc < 400:
        return ("drop", "edu_discontinued_stub")

    # Education edition stubs
    if "Minecraft_Education" in cats and wc < 50:
        return ("drop", "edu_stub")

    # Wiki meta
    if any(c in cats for c in ["Files_with_a_license_template", "Mojang_images",
                                "Notice_templates", "Documentation_pages",
                                "Soft_redirects"]):
        return ("drop", "wiki_meta")
    if title.startswith(("File:", "Template:", "Help:", "Minecraft Wiki:")):
        return ("drop", "wiki_meta_prefix")

    return ("keep", None)
```

**Estimated drops**: ~1700-2000 articles (~17-20% of corpus). Disambig (548) + prose-bearing Set_index pages route to Q&A pipeline.

---

## Phase 1 — Pre-clean (free wins, do FIRST)

| # | Pattern | Action | Notes |
|---|---|---|---|
| 1.1 | Zero-width chars `[​‌‍﻿⁠]` (U+200B/200C/200D/2060/FEFF) | Strip globally | Pervasive in 100% articles |
| 1.2 | Curly quotes `“”„‟‘’` | Normalize to ASCII `"` and `'` | Mixed; bloats tokenizer |
| 1.3 | Fraction slash U+2044 | Replace with `/` | 97+ articles |
| 1.4 | 3+ consecutive newlines | Collapse to `\n\n` | Cosmetic |
| 1.5 | Trailing whitespace per line | Strip | Cosmetic |
| 1.6 | Em-dash/en-dash to hyphen in numeric ranges only (`\d–\d`, `\d—\d`) | Replace `–`/`—` with `-` | Keep them in prose |

---

## Phase 2 — Section-level wholesale drops [MOVED EARLIER in v2]

These sections are template-driven, ~99% noise. Drop the entire section from its `## Header` to next major section or EOF.

| Section name | Drop? | Notes |
|---|---|---|
| `Sounds` | DROP | `vte<word>sound type:` + IDs + ZW chars + numeric volume/pitch |
| `Data values` / `ID` | DROP | Translation keys, Numeric IDs, `Family: arthropodendermitelightweightmobmonster` glued |
| `Block states` / `Fluid states` | DROP | `Allowed values: 012345...15` collapsed digits |
| `Block data` / `Entity data` (NEW v2) | DROP | NBT scaffolding `[String]`, `[Int]`, `Template:Nbt inherit/...` |
| `Achievements` (sub-section) | CONDITIONAL DROP | Only drop if NOT primary topic. Plan-v2: `if "Achievement" not in title and "Achievement" not in primary_categories: drop` |
| `Advancements` (sub-section) | CONDITIONAL DROP | Same as Achievements |
| `Issues` (NEW v2: gate by content) | CONDITIONAL DROP | Drop only if section body contains the boilerplate `"are maintained on the bug tracker"`. Articles like Brick Pyramid have substantive `## Issues` text — keep those. |
| `Videos` | DROP | YouTube placeholders + boilerplate |
| `Gallery` / `Renders` / `Screenshots` / `Mojang screenshots` / `Mojang images` / `Concept artwork` / `Storyboards` / `Behind-the-scenes` / `Promotional images` / `Wallpapers` / `Posters` | DROP | Caption-only fragments |
| `In other media` | DROP | LEGO/merch references |
| `Trivia` | KEEP | Where lore lives. Highest-quality prose section. |
| `Overview` / lead | KEEP | Highest-value prose |
| `Behavior` / `Spawning` / `Drops` (when prose) | KEEP after table-strip | Useful after tabular junk removal |
| `Examples` (Commands/) | KEEP gold | Best training data in corpus (real `/give` invocations) |

**Implementation pattern**:
```python
DROP_SECTIONS_GLOBAL = ["Sounds", "Data values", "Block states", "Fluid states",
                        "Block data", "Entity data",  # NEW v2
                        "Videos", "Gallery", "Renders", "Screenshots",
                        "Mojang screenshots", "Mojang images", "Concept artwork",
                        "Storyboards", "Behind-the-scenes", "Promotional images",
                        "Wallpapers", "Posters", "In other media",
                        "Filmography", "Discography",  # NEW v2 (real_world)
                        "Credits"]  # NEW v2 (media)

DROP_SECTIONS_CONDITIONAL = {
    "Achievements": lambda art: not _is_achievement_article(art),
    "Advancements": lambda art: not _is_achievement_article(art),
    "Issues": lambda art, body: "are maintained on the bug tracker" in body,  # NEW v2
}

NEXT_SECTION_HINTS = ["Issues", "Trivia", "Gallery", "See also", "History",
                      "Data history", "Data values", "External links",
                      "References", "Notes"]
```

---

## Phase 3 — Line-level boilerplate

Universal duplicates and editor maintenance markers.

| Pattern | Action | Notes |
|---|---|---|
| `Issues relating to "X" are maintained on the bug tracker. Issues should be reported and viewed there.` | Strip the line+section | 1632 articles |
| `Issues relating to "X" are not maintained on the bug tracker because it is an April Fools' joke...Invalid"` (NEW v2) | Strip | Joke_features family |
| `An interactive widget is being loaded...` | Strip | 107 articles |
| `For other uses, see X.` | Strip | Pervasive |
| `For the X, see Y.` (NEW v2 — variant without "This article is about") | Strip | Multishot, Creaking |
| `For an overview of all X biomes, see Y.` (NEW v2) | Strip | World/Biomes |
| `Not to be confused with X.` | Strip | Pervasive |
| `This article is about X. For Y, see Z.` | Strip | Pervasive |
| `"X" redirects here. For Y, see Z.` | Strip | Pervasive |
| `Main article: X` (line) | Strip | Pervasive |
| `Main article: Movie:.../1CHP [edit]` (NEW v2) | Strip | Media chapter cross-refs |
| `See Tutorial:X` / `There is a related tutorial page` | Strip | Pervasive |
| `There is an associated technical blocks page for ...` | Strip | Pervasive |
| `This article documents an April Fools' Day joke.` | Keep as 1 sentence | Some |
| `This feature is exclusive to Java/Bedrock Edition.` | Keep as 1 sentence | Some |
| `This page describes content that has been removed...` | Keep as 1 sentence | Some |
| `This feature was exclusively part of a joke version...` (NEW v2) | Keep as 1 sentence | Joke_features |
| `Spoiler warning! This section contains detailed information about X...` | Strip | Media |
| `Editor's note: ...` | Strip | Media |
| `Tagged on: April 22, 2025.` | Strip | Wiki maintenance |
| `Reason: ...` (orphan) | Strip | Wiki maintenance |
| `It has been suggested that this section be split into its own page at X. [discuss]` (NEW v2) | Strip | Wiki maintenance |
| `If this split affects many pages, or may potentially be controversial, do not split until a consensus has been reached.` (NEW v2) | Strip | Wiki maintenance |
| `This section needs cleanup to comply with the style guide.` (NEW v2) | Strip | Wiki maintenance |
| `Please help improve this section.` (NEW v2) | Strip | Wiki maintenance |
| `An official name has not been given. Please update the name if confirmed by reliable sources.` (NEW v2) | Strip | Pages_with_unofficial_names |
| `This section uses a bug (MC-XXXXX) to make a contraption ...\nUse at your own risk.` | Strip | Tutorials |
| `This section describes content that is currently in development.` (NEW v2: PROMOTED to global) | Strip | Was Plants/Ore-only in v1 |
| `This content has appeared in development versions for X, but the full update adding it has not been released yet.` (NEW v2: PROMOTED to global) | Strip | Was Plants/Ore-only in v1 |
| `[verify]`, `[ verify ]`, `‌[verify]` | Strip with **collapse to space** (NEW v2) | 33+; was strip-to-empty in v1 |
| `[ more information needed ]`, `​[more information needed]` | Strip with collapse to space | 18+ |
| `[ citation needed ]` | Strip with collapse to space | Some |
| `[ check the code ]` (handle space variants) | Strip with collapse to space | Some |
| `[ is this the correct version? ]` | Strip with collapse to space | Some |
| `[ discuss ]`, `[ edit ]` | Strip with collapse to space | Many |
| `[sic]` | Strip with collapse to space | Few |
| `(MC-12345)`, `(MCPE-12345)` (with optional internal spaces) (NEW v2) | Strip parens | 232+; v1 missed `(\s*MCPE-X\s*)` |
| `‌ [ Java Edition only ]` and variants `[JE only]`, `[JEonly]`, `[BE only]`, `[BEonly]`, `[Bedrock and Pi editions only]`, `[edu only]`, `[upcoming]` (NEW v2: extended) | Strip | 704+ |
| `The specific instructions are: ...` | Strip | Wiki cleanup |
| `Please remove this notice once you have added a suitable ...` | Strip | Wiki cleanup |
| `This (page\|section\|article) (needs to be\|should be) rewritten\.` + body | Strip | Tutorials |
| `YouTube Video ( view on YouTube )` | Strip | Tutorials, 16+ per article |
| `<author> <title> ( view on YouTube )` (NEW v2) | Strip | Author-prefixed YouTube placeholders |
| `Vimeo Video ( view on Vimeo )` | Strip | Few |

**v2 critical fix**: `[verify]` and similar markers must collapse to a single space, not empty string. Otherwise `absent[verify]from` becomes `absentfrom`.

```python
re.sub(r'\s*‌?\[\s*(?:verify|more information needed|citation needed|check the code|is this the correct version\?|discuss|edit|sic)\s*\]\s*', ' ', text)
```

---

## Phase 4 — Family-specific drops [MOVED EARLIER in v2]

Apply only when article matches family. Run BEFORE word-boundary repair (Phase 6) so hex codes and identifiers are deleted before they get split.

### Mobs
- Strip "Achievements that apply to all mobs" stanza.
- Strip "41 monsters / 27 animals" CamelCase roster (after Pass 1 splits).
- Strip Iron Golem entity-interaction matrix.
- Strip mob-infobox stubs (`Mob type:`, `Hitbox size:`, `Speed:`, `Usable items:`, `Spawn:`) at top of article.

### Plants / Ore
- Strip long biome lists (>15 consecutive bare biome lines).
- Strip "Sulfur cube" boilerplate ← **PROMOTED TO GLOBAL in v2** (Phase 3).
- Strip Lava flow-arrangement orphan number rows (`8, 7, 6, 5, 4, 3, 2, 1`).

### Items
- Strip "Eat each of these 40 foods:" advancement (every Food article, identical).
- Strip Cake/Banner/Bed/Wool 16-color variants ID rows.
- Strip Bow/Trident damage matrix `Unenchanted: (no charge), 1HP, 0.1s, 2, ...`.
- **NEW v2**: Strip long `or`-chained smithing variant rows (`Name: Netherite Helmet or Netherite Chestplate or ... , Ingredients:...`).

### Mechanics / Effects / Enchantments
- **DEDUP catastrophic Notch quote**: any 200+ char string repeated >1× in same article → keep first only (Phase 12).
- Strip `Primary items` orphan line (regex_clean dropped value, kept label).
- Stitch `Cause: X, Potency: Y, Length: Z` rows into prose **IF Notes: present**, else drop. (NEW v2: was unconditional drop in v1)
- Strip "A Furious Cocktail / How Did We Get Here?" advancement-list CamelCase (Phase 6 should split).
- Strip enchantment infobox stub block (`Maximum level / Primary items / Enchantment weight / Identifier / Incompatible with`).

### World / Biomes
- Strip `Climate / Temperature: X / Downfall: X / Precipitation:` block.
- Strip `Colors / Grass color: #X / ...` block.  ← **CRITICAL: must run BEFORE Phase 6 to protect hex codes**
- Strip "Visit all of these 54 biomes:" full string.
- Strip "Hot Tourist Destinations" advancement.
- **NEW v2**: Strip `Features:` and `Blocks:` infobox rows (concatenated noun lists).

### Commands
- Strip `Result` and `Output` sections (corrupt comma-soup).
- KEEP `Examples` (gold).
- KEEP argument descriptions (prose).
- Fix `/tpnow → /tp now` slash-command-word fusion (Phase 6 covers).

### Versions
- Strip `Beta for: X.Y.Z` / `Build for: X.Y.Z` / `Preview for:` / `Snapshot for:` headers.
- Strip `(MCPE-XXXXX)` parens handled in Phase 3.

### Tutorials
- Strip `YouTube Video ( view on YouTube )` (Phase 3 covers).
- Strip schematic ASCII rows (`a: a, a: s, a: a` patterns).
- Strip mid-document rewrite banners.
- **NEW v2**: Strip `jsap-$` schematic placeholder tokens (`r'^[a-z]{2,5}-\$$'`).
- **NEW v2**: Strip `Category: X, Data: ...` analytical-table rows.

### Real-world
- Strip bio infoboxes (`Real name:`, `Twitter username:`, `Bluesky username:`, `Website:`, `Bandcamp:`, `YouTube:`, `Mojang username:`, `Minecraft name:`).
- Strip duplicate row stutter (handled by dedup Phase 12).
- Aggressive Gallery section drop (Phase 2).

### Media franchise
- Strip Awards section if it contains corrupt rows.
- Strip `Spoiler warning!` template (Phase 3).
- Strip Credits section (40+ role/name pairs).
- Strip `Ditto` lines in galleries.
- KEEP cast lists (Actor as Character).
- KEEP plot summaries.

### External

**Wikipedia bios**:
- Fix orphan `)` after `born X 1979)` (IPA-strip artifact).
- Strip trailing `///` artifacts.
- Drop terminal empty section headers.

**Notch blog**:
- Strip ` : The Word of Notch` from titles.
- Strip `Posted Month DD, YYYY.` prefix.
- Strip orphan `Tweet` lines.
- Strip duplicated title-as-first-body-line.
- Strip trailing `Comments` token.
- Replace bare URLs with `[link]`.

**YouTube transcripts**:
- **DROP all transcripts where `is_generated: true`**. Hallucinations.

---

## Phase 5 — Identifier protection (NEW v2)

Before Phase 6 runs word-boundary repair, mask content that should NOT be split. Restore in Phase 10.

```python
PROTECTION_RULES = [
    # Hex colors
    (re.compile(r'#[0-9A-Fa-f]{6,8}\b'), '__HEX_PROTECT__'),
    # Single-quoted identifiers (likely Minecraft class/translation key names)
    (re.compile(r"'[A-Za-z][A-Za-z0-9_.]+'"), '__QUOTED_PROTECT__'),
    # Tokens with namespace `:` or dotted identifier
    (re.compile(r'\bminecraft:[a-z_/]+\b'), '__NS_PROTECT__'),
    (re.compile(r'\b(?:block|item|entity|tile|effect|enchantment|potion|subtitles?)\.minecraft\.[a-z_.]+\b'), '__DOTTED_PROTECT__'),
    # Snapshot codes (extended pattern: 13w14a, 24w14potato)
    (re.compile(r'\b\d+w\d+[a-z]+\b'), '__SNAPSHOT_PROTECT__'),
    # Bug IDs
    (re.compile(r'\b(?:MC|MCPE|MCL|REALMS|EDU)-\d+\b'), '__BUGID_PROTECT__'),
    # Console version vectors
    (re.compile(r'\bTU\d+\b|\bCU\d+\b'), '__TUVER_PROTECT__'),
    # Known Minecraft identifier whitelist (extended in v2)
    (re.compile(r'\b(?:globalSoundEvents|randomTickSpeed|doDaylightCycle|keepInventory|doMobSpawning|mobGriefing|doFireTick|naturalRegeneration|doWeatherCycle|commandBlockOutput|sendCommandFeedback|RangedAttackGoal|MeleeAttackGoal|TemptGoal|FollowOwnerGoal|PanicGoal|SitGoal|FloatGoal|BeeEntityData|MushroomCow|craftingScreen|TransferCooldown|CustomName|DealtDamage|DuplicationCooldown|BatFlags|MinecraftEdu|JavaScript|PlayStation|TypeScript|MineCon|iPad|iPhone|PvP|PvE|MMORPG)\b'),
     '__WHITELIST_PROTECT__'),
]

def protect(text):
    placeholders = []
    for pattern, marker in PROTECTION_RULES:
        def replacer(m):
            placeholders.append(m.group(0))
            return f'{marker}{len(placeholders)-1}__'
        text = pattern.sub(replacer, text)
    return text, placeholders

def restore(text, placeholders):
    for i, original in enumerate(placeholders):
        # Find which marker matches
        for _, marker in PROTECTION_RULES:
            text = text.replace(f'{marker}{i}__', original)
    return text
```

---

## Phase 6 — Word-boundary repair (most critical, runs AFTER drops)

Three layers:

### Layer A: Programmatic regex (broad, conservative)

```python
text = re.sub(r'(\d)([A-Z])', r'\1 \2', text)           # "5HP" -> "5 HP"
text = re.sub(r'([a-z])([A-Z][a-z])', r'\1 \2', text)   # "biomesBadlands" -> "biomes Badlands"
text = re.sub(r'([.!?])([A-Z])', r'\1 \2', text)        # ".Notchbelieved" -> ". Notchbelieved"
text = re.sub(r'([a-z])(/[a-z])', r'\1 \2', text)       # "use/setblock" -> "use /setblock"
text = re.sub(r'([a-z])(@[aprs])', r'\1 \2', text)      # "use@a" -> "use @a"
text = re.sub(r'([a-z])(#[A-Za-z])', r'\1 \2', text)    # "see#Examples" -> "see #Examples"
# NEW v2: comma-followed-by-capital
text = re.sub(r',([A-Z])', r', \1', text)               # ",Weaving" -> ", Weaving"
# NEW v2: filename glue
text = re.sub(r'(\.(?:png|jar|ogg|json|txt|zip|lang))([a-zA-Z])', r'\1 \2', text)
# NEW v2: hex color rename (after Phase 5 protection, unprotected hexes)
text = re.sub(r'(from|to)(#[0-9A-Fa-f]{6,8})', r'\1 \2', text)
```

### Layer B: Curated glue dictionary (high-precision fixes)

```python
CURATED_GLUE = {
    # ──────── Proper-noun + verb fusions ────────
    r'\bNotchbelieved\b': 'Notch believed',
    r'\bNotchsaid\b': 'Notch said',
    r'\bNotchannounced\b': 'Notch announced',
    r'\bNotchteased\b': 'Notch teased',
    r'\bNotchshowed\b': 'Notch showed',
    r'\bNotchexpresses\b': 'Notch expresses',  # NEW v2
    r'\bJebexplained\b': 'Jeb explained',
    r'\bJebsaid\b': 'Jeb said',  # NEW v2
    r'\bDinnerbonesaid\b': 'Dinnerbone said',
    r'\bMojang Studiosconfirmed\b': 'Mojang Studios confirmed',
    r'\bWintersannounced\b': 'Winters announced',
    r'\bLydiaWinters\b': 'Lydia Winters',
    r'\bBergenstensays\b': 'Bergensten says',  # NEW v2
    r'\bKingbdogzstates\b': 'Kingbdogz states',  # NEW v2

    # ──────── Template list run-ons ────────
    r'\bVisitallof\b': 'Visit all of',
    r'\bEateachof\b': 'Eat each of',
    r'\bKilloneof\b': 'Kill one of',
    r'\bKilleachof\b': 'Kill each of',  # NEW v2
    r'\bHaveallof\b': 'Have all of',
    r'\bBreed a pair ofanyof\b': 'Breed a pair of any of',

    # ──────── Preposition + ProperNoun (extended in v2) ────────
    r'\bforJava Edition\b': 'for Java Edition',
    r'\bofJava Edition\b': 'of Java Edition',
    r'\binJava Edition\b': 'in Java Edition',
    r'\bbyJava Edition\b': 'by Java Edition',
    r'\btoJava Edition\b': 'to Java Edition',           # NEW v2
    r'\bfromJava Edition\b': 'from Java Edition',       # NEW v2
    r'\bonJava Edition\b': 'on Java Edition',           # NEW v2
    r'\bwithJava Edition\b': 'with Java Edition',       # NEW v2
    r'\bisJava Edition\b': 'is Java Edition',           # NEW v2
    r'\bforBedrock Edition\b': 'for Bedrock Edition',
    r'\bofBedrock Edition\b': 'of Bedrock Edition',
    r'\binBedrock Edition\b': 'in Bedrock Edition',
    r'\btoBedrock Edition\b': 'to Bedrock Edition',     # NEW v2
    r'\bfromBedrock Edition\b': 'from Bedrock Edition', # NEW v2
    r'\bonBedrock Edition\b': 'on Bedrock Edition',     # NEW v2
    r'\bwithBedrock Edition\b': 'with Bedrock Edition', # NEW v2
    r'\bofXbox 360 Edition\b': 'of Xbox 360 Edition',
    r'\b\.minecraftfolder\b': '.minecraft folder',

    # ──────── Data-cell label fusions ────────
    r'\bAvg\.per chest\b': 'Avg. per chest',
    r'\bcheststo search\b': 'chests to search',
    r'\bFilenamein Minecraft\b': 'Filename in Minecraft',
    r'\bAttenuationdistance\b': 'Attenuation distance',
    r'\bCraftingrecipe\b': 'Crafting recipe',
    r'\bSmeltingrecipe\b': 'Smelting recipe',
    r'\bAmbientsounds\b': 'Ambient sounds',
    r'\bUsableitems\b': 'Usable items',
    r'\bPricemultiplier\b': 'Price multiplier',
    r'\bVillagerexperience\b': 'Villager experience',
    r'\bTrades instock\b': 'Trades in stock',

    # ──────── Common verb fusions ────────
    r'\bbebred\b': 'be bred',
    r'\bbredusing\b': 'bred using',
    r'\bcraftedfrom\b': 'crafted from',
    r'\bnowuses\b': 'now uses',
    r'\bnowsell\b': 'now sell',
    r'\bnowdrop\b': 'now drop',
    r'\bnowspawn\b': 'now spawn',

    # ──────── Lowercase article+noun fusions (NEW v2 — universal pattern) ────────
    # Pattern: a/an/the + common Minecraft noun
    r'\babarrier\b': 'a barrier',
    r'\babeacon\b': 'a beacon',
    r'\bablock\b': 'a block',
    r'\babiomein\b': 'a biome in',
    r'\bachance\b': 'a chance',
    r'\bachest\b': 'a chest',
    r'\bafireball\b': 'a fireball',
    r'\baflower\b': 'a flower',
    r'\bahopper\b': 'a hopper',
    r'\bamob\b': 'a mob',
    r'\baplayer\b': 'a player',
    r'\bavillage\b': 'a village',
    r'\bavillager\b': 'a villager',
    r'\bawitch hut\b': 'a witch hut',
    r'\bazombie\b': 'a zombie',
    r'\baniron ingot\b': 'an iron ingot',
    r'\banillager\b': 'an illager',
    r'\bthebasalt\b': 'the basalt',
    r'\bthecrafting\b': 'the crafting',
    r'\bthechests\b': 'the chests',
    r'\btheinventory\b': 'the inventory',
    r'\btheblock\b': 'the block',
    r'\btheirpath\b': 'their path',
    r'\btheircreaking\b': 'their creaking',
    r'\btheterrain\b': 'the terrain',

    # ──────── Lowercase verb-after-subject (NEW v2) ────────
    r'\bWardensnow\b': 'Wardens now',
    r'\bWardensdrop\b': 'Wardens drop',
    r'\bGoatsnow\b': 'Goats now',
    r'\bPigsnowdrop\b': 'Pigs now drop',
    r'\bSheepnowdrop\b': 'Sheep now drop',
    r'\bEndermennow\b': 'Endermen now',
    r'\bEndermenare\b': 'Endermen are',
    r'\bMobscan\b': 'Mobs can',
    r'\bmobscan\b': 'mobs can',
    r'\bHostile mobscan\b': 'Hostile mobs can',
    r'\bspidersfollow\b': 'spiders follow',
    r'\bsomespiderson\b': 'some spiders on',
    r'\bcraftrabbit\b': 'craft rabbit',
    r'\bcraftfermented\b': 'craft fermented',
    r'\bcraftsuspicious\b': 'craft suspicious',
    r'\bcraftpurpur\b': 'craft purpur',
    r'\bcraftEnd\b': 'craft End',  # capital End, but caught by Layer A normally
    r'\bcraftcampfires\b': 'craft campfires',
    r'\bcrafttools\b': 'craft tools',
    r'\bSmeltcharred\b': 'Smelt charred',
    r'\bSmeltbaked\b': 'Smelt baked',
    r'\bbyshearing\b': 'by shearing',
    r'\bbridingmount\b': 'by riding mount',  # made up, illustrate pattern
    r'\bintrial\b': 'in trial',
    r'\binflower\b': 'in flower',
    r'\bpotsof\b': 'pots of',
    r'\bwithcows\b': 'with cows',
    r'\bwithwheat\b': 'with wheat',
    r'\bwithbuckets\b': 'with buckets',
    r'\bbestfoodin\b': 'best food in',
    r'\bviazombie\b': 'via zombie',
    r'\bacraftingrecipe\b': 'a crafting recipe',
    r'\bcraftablein\b': 'craftable in',
    r'\businggold\b': 'using gold',
    r'\bbecameobtainable\b': 'became obtainable',
    r'\bwhenlavaflows\b': 'when lava flows',
    r'\boversoul\b': 'over soul',
    r'\bsoilnext\b': 'soil next',
    r'\btoblue\b': 'to blue',
    r'\bitrenewable\b': 'it renewable',
    r'\bafteritem\b': 'after item',
    r'\bheartis\b': 'heart is',
    r'\bthroughcommands\b': 'through commands',
    r'\bsnowcapped\b': 'snow capped',  # context-dependent — review

    # ──────── Patch/feature template smoosh ────────
    r'(\d+\.\d+(?:\.\d+)?)Experiment([A-Z])': r'\1 (Experiment) \2',
    r'\bUpcomingBedrock Edition\b': 'Upcoming Bedrock Edition',
    r'\bUpcomingJava Edition\b': 'Upcoming Java Edition',

    # ──────── Conjunction fusions ────────
    r'(?<=[a-z]{3})and(?=[A-Z])': ' and ',         # "EditionandBedrock" -> "Edition and Bedrock"
    # REPLACED v2: was generic `(?<=[a-z])or([A-Z])`. Too risky (vendorMod, factorAdj).
    # Now: curated multi-noun-or chains.
    r'\bCoalorCharcoal\b': 'Coal or Charcoal',
    r'\bBone MealorLapis Lazuli\b': 'Bone Meal or Lapis Lazuli',
    r'\bBrown MushroomorRed Mushroom\b': 'Brown Mushroom or Red Mushroom',
    r'\bPlanksorMatchingPlanks\b': 'Planks or MatchingPlanks',
    r'\bHelmetorChestplate\b': 'Helmet or Chestplate',
    # ... (extended via corpus token-frequency analysis in Phase D)

    # ──────── Digit + lowercase noun fusions (NEW v2, scoped) ────────
    r'(\d+)(health|HP|points|seconds|minutes|hours|days|blocks|chunks|ticks|levels?|emeralds?|enchantments?)\b': r'\1 \2',

    # ──────── Filename glue (NEW v2) ────────
    r'\btheterrain\.png\b': 'the terrain.png',
    r'\binclient\.jar\b': 'in client.jar',
    r'\bgui/items\.pngwere\b': 'gui/items.png were',
    r'\bstitched_terrain\.pngand\b': 'stitched_terrain.png and',
}
```

### Layer C: Curated lowercase-glue dictionary (NEW v2 — corpus frequency analysis required)

Run a token-frequency analysis on `articles_cleaned.jsonl`: extract all `[a-z]{12,}` tokens with no spaces. Build a curated split-list from the top 200-500 most frequent. Examples already collected: `Pigsnowdrop0-2`, `usingflint`, `byshearing`, `intrial`, `withcows`, `acraftingrecipe`, etc.

This is the **highest-priority addition in v2**: without it, ~70% of lowercase fusion remains uncovered.

---

## Phase 7 — Edition stutter collapse

Same as v1, plus post-strip cleanup of orphan transition lines.

```python
def collapse_edition_stutter(text):
    EDITION_PREFIX = re.compile(
        r'^(Java Edition(?: Classic| Indev| Infdev| Alpha| Beta)?|'
        r'Pocket Edition(?: Alpha)?|'
        r'Bedrock Edition|'
        r'Legacy Console Edition|'
        r'New Nintendo 3DS Edition|'
        r'Minecraft Education|'
        r'PlayStation 4 Edition):\s+'
    )
    out, prev_prefix = [], None
    for line in text.split('\n'):
        m = EDITION_PREFIX.match(line)
        if m:
            current = m.group(1)
            body = line[m.end():]
            # NEW v2: detect phase-transition (prefix == body content)
            if body.startswith(('Java Edition', 'Pocket Edition', 'Bedrock Edition', 'Legacy Console Edition')):
                # update prev_prefix to the new phase
                prev_prefix = body.split(',')[0].strip() or current
                continue  # drop the transition line entirely (orphan)
            if current == prev_prefix:
                line = body  # drop redundant prefix
            else:
                prev_prefix = current
        else:
            prev_prefix = None
        out.append(line)
    return '\n'.join(out)
```

After Pass 7, also strip orphan platform vectors:

```python
re.sub(r'^Legacy Console Edition:\s+(?:Xbox 360|Xbox One|PS3|PS4|PS Vita|Wii U|Switch)(?:,\s*(?:Xbox 360|Xbox One|PS3|PS4|PS Vita|Wii U|Switch))+\s*$', '', text, flags=re.MULTILINE)
```

---

## Phase 8 — Tabular row drops

Lines that look like flattened table rows. Drop wholesale.

| Pattern | Notes |
|---|---|
| `^Block: <field>, .*$` (breaking-time) | "Block: Hardness, Hopper: 3" |
| `^Block: (Tool\|Options\|Breakingtime \(sec\)\|Efficiency\|Default\|Wooden)$` (NEW v2: orphan labels) | Without comma+value |
| `^Map color: \d+ [A-Z_ ]+$` (single color) | |
| `^Map color:(?:\s*\d+\s+COLOR\s+_[A-Z]+)+\s*$` (NEW v2: multi-color) | "Map color: 28 COLOR _RED 26 COLOR _BROWN" |
| `^Map color: JE: \d+ colors .*$` (NEW v2) | Coral-style multi-edition |
| `^Mob: .*Spawn weight:.*Group size:.*$` | |
| `^Mob: (Monster\|Creature\|Ambient\|...) category$` | |
| `^Item: .*Stack Size: .*Weight:.*Chance:.*$` | Loot tables (5-col) |
| `^Item: .*Quantity ?\/ ?Chance ?\/ ?Average:.*$` (NEW v2) | Mob drop tables (Mooshroom shape) |
| `^Quantity ?\/ ?Chance ?\/ ?Average:\s+[\w\s]+,\s+[\d–\.,%⁄\s]+$` (NEW v2) | |
| `^Item: \d+, Amount: [\d⁄\.\(\)%]+,.*$` (NEW v2) | |
| `^Item: (Java Edition\|Bedrock Edition\|Java Edition and Bedrock Edition).*$` | Loot pseudo-headers |
| `^Item: .*Structure:.*Container:.*Quantity:.*(?:Chance:.*)?$` (NEW v2: Chance now optional) | Generated loot rows |
| `^Mob: \d+, Amount:.*Probability:.*$` | Mob drop tables |
| `^\d+:\s+[A-Za-z][^,\n]*,\s*[\d.,]+(?:,\s*[\d.,]+){2,3}$` (NEW v2) | "1: Default, 50.00%, 0.50, 1, 100.00%, 1.00" |
| `^Cause: .*Potency:.*Length:.*Notes:.*$` (NEW v2: with Notes — STITCH instead of drop in family Phase 4) | Mechanics |
| `^Cause: .*Potency:.*Length:.*$` (without Notes — drop) | |
| `^Wandering Trader: \d+%, \d+%,.*$` | Trade tables |
| `^Villager: .*Probability:.*Villager wants:.*Player receives:.*Trades.*Pricemultiplier.*$` | |
| `^Award show: .*Date of ceremony:.*Category:.*Result:.*$` | Media |
| `^TU\d+(?:, CU\d+)?(?:, [\d.]+)+(?:, Patch \d+)?(?:, [\d.]+)?,\s*` (NEW v2: PREFIX strip only, keep tail) | Console version vector |
| `^\d+ (issues?\|bugs?) (fixed\|reported)\.?$` | Bug counter (versions) |
| `^(Beta\|Build\|Preview\|Snapshot\|Client version\|Server version)(?:\s+for)?:\s+\S.*$` | Version metadata |
| `^PS4, Other$` | Achievement column header |
| `^[A-Z][^\n,]+, [^\n]*?, \d+, (Bronze\|Silver\|Gold\|Platinum)\s*$` | Achievement reward tail |
| `^[?,\s]+,\s+Added .+$` | Lost-version unknown vectors |
| `^Identifier: [a-z_]+$` | NBT id (when in Properties block) |
| `^Numeric ID: -?\d+.*$` | NBT registry IDs |
| `^Translation key:\s*\S+$` | NBT translation keys |
| `^Name: .*Identifier:.*Translation key:.*$` | Per-variant ID rows |
| `^Allowed values:\s*[0-9]+\s*$` | Block-state digit blob |
| `^Metadata Bits:\s*(?:0x[0-9a-fA-F]\s*)+$` | Block-state metadata |
| `^Category:\s+[^,]+,\s+Data:\s+.*$` (NEW v2) | Tutorial analytical tables (Kelp farming) |
| `^Fish:.*?(?:Yes\|No)(?:\s*[‌]?\[[A-Za-z ]+only\])?.*$` (NEW v2) | Fish spawning matrix |
| `^[\w ]+ spawns in:\s+Category:.*$` (NEW v2) | Mob spawn intro |
| `^Category:\s+\w+:\s+[\w ]+,\s+Java Edition:\s+[\d⁄%]+,.*$` (NEW v2) | Mob spawn detail |
| `^Sources:\s*See\s*§\s*\w+\s*$` (NEW v2) | Effects |
| `^Heals: \d+\.?\d*\s*HP\s*×\s*\d+\.?\d*\s+Duration:.*$` (twice in row) | Cake-style dual-stat |
| **NEW v2: Universal infobox-row block** | "Renewable: Yes / Stackable: 64 / Tool: Pickaxe / Hardness: 1.5..." |

```python
INFOBOX_LABELS = (
    r'(?:Biomes|Blocks|Features|Structures|Mobs|'
    r'Generates in existing chunks|Consists of|'
    r'Rarity tier|Renewable|Stackable|Tool|Mineable with|'
    r'Blast resistance|Hardness|Luminous|Transparent|Waterloggable|'
    r'Flammable|Catches fire from lava|Map color|'
    r'Attack damage|Attack speed|Attack range|Hitbox margin|'
    r'Hitbox size|Speed|Walking speed|Swimming speed|Flying speed|'
    r'Durability|Enchantability|Mining efficiency|Mining level|'
    r'Climate|Temperature|Downfall|Precipitation|Snow accumulation|'
    r'Numeric ID|Health points|Health|Damage|XP drop|XP|'
    r'Spawn|Spawn light level|Mob type|Behavior|Type|'
    r'Tameable|Rideable|Breedable|'
    r'Usable items|Particle|Sources|Always consumable|'
    r'Hunger|Saturation|Saturation boost|Status effects|'
    r'Cause|Potency|Length|'
    r'Maximum level|Primary items|Secondary items|Enchantment weight|Incompatible with)'
)
re.sub(rf'^{INFOBOX_LABELS}(?:\s*\[[^\]]+\])?:\s.*$', '', text, flags=re.MULTILINE)
```

---

## Phase 9 — Inline noise (REVISED v2)

Critical change: **un-namespace, don't delete.**

```python
# OLD v1 (deletes referent):
# re.sub(r'\bminecraft:[a-z_/]+\b', '', text)

# NEW v2: un-namespace (preserve referent in prose)
def un_namespace(text):
    def repl(m):
        token = m.group(1)
        # snake_case to space-separated lowercase
        return token.replace('_', ' ').replace('/', ' ')
    text = re.sub(r'\bminecraft:([a-z_/]+)\b', repl, text)
    text = re.sub(r'\b(?:block|item|entity|tile|effect|enchantment|potion|subtitles?)\.minecraft\.([a-z_.]+)\b',
                  lambda m: m.group(1).replace('_', ' ').replace('.', ' '),
                  text)
    return text

# NBT type tags (drop)
text = re.sub(r'\[(NBT (?:Compound|List)(?:\s*/\s*JSON\s+(?:Object|Array))?|String|Int(?:eger)?|Long|Short|Byte|Float|Double|Boolean|Array|Int Array|Byte Array|Long Array|JSON Object|JSON Array)\]\s*', '', text)

# Anchor link refs (NEW v2: now handles § AND #)
text = re.sub(r'\(?\s*see\s*[#§]\s*[A-Z][\w ]+\s*\)?', '', text)
text = re.sub(r'\(?\s*see\s+(?:also[:,\s]+)?[A-Z][\w ]+\s*[#§]\s*[\w ]+\)?', '', text)

# Image asset paths
text = re.sub(r'#/media/File:[^\s]+', '', text)
text = re.sub(r'\bObjectSprite\s+[\w\-]+\.png:\s*Sprite image[^\n]+', '', text)

# Empty parens from icon-template strip (NEW v2)
text = re.sub(r'\(\s*\)', '', text)
text = re.sub(r'\(\s*×\s*\d+(?:\.\d+)?\s*\)', '', text)  # "( × 7)"
```

---

## Phase 10 — Identifier restore

Restore placeholders from Phase 5:

```python
text = restore(text, placeholders)
```

---

## Phase 11 — Final cleanup

```python
text = re.sub(r' {2,}', ' ', text)             # collapse multi-space
text = re.sub(r'\n{3,}', '\n\n', text)         # collapse multi-newline
text = '\n'.join(line.rstrip() for line in text.split('\n'))
# NEW v2: empty section headers
text = re.sub(r'^(#+\s+[^\n]+)\n+(?=^#+\s+)', '', text, flags=re.MULTILINE)
# NEW v2: bare-colon orphan lines (e.g. after ZW + [verify] strip)
text = re.sub(r'^\S+\s*:\s*$', '', text, flags=re.MULTILINE)
text = text.strip()
```

---

## Phase 12 — Dedup repeated content

```python
def dedup_repeated_blocks(text, min_chars=200):
    """Remove verbatim repetitions of any block >= min_chars within one article.
    Targets the Notch-quote-25-times catastrophic bug + similar."""
    seen_blocks = set()
    paragraphs = text.split('\n\n')
    out = []
    for p in paragraphs:
        normalized = ' '.join(p.split())
        if len(normalized) >= min_chars and normalized in seen_blocks:
            continue
        seen_blocks.add(normalized)
        out.append(p)
    return '\n\n'.join(out)
```

---

## Validation plan recap

Phase C ran 3 agents on 30 unseen articles. Verdict: **GO with caveats** unanimous.

12 caveats integrated into v2:
1. ✅ Reorder: section drops + family drops BEFORE word-boundary repair
2. ✅ Add identifier protection layer (Phase 5) for hex codes, gamerules, AI goals, translation keys
3. ✅ Pass 6 namespaced-id strip changed to **un-namespace** (preserve referents)
4. ✅ Replace generic `or` rule with curated chains
5. ✅ `[verify]` and similar strip now collapse to space, not empty
6. ✅ Loot table regex broadened to match `Quantity / Chance / Average` shape
7. ✅ Console version vector regex strips PREFIX only, keeps trailing prose
8. ✅ Universal infobox-row drop added to Phase 8
9. ✅ Phase-transition orphan strip after stutter collapse
10. ✅ Hex code protection via Phase 5 placeholder
11. ✅ Comma-followed-by-capital rule added to Phase 6
12. ✅ Sulfur cube boilerplate promoted from Plants/Ore to global

Plus Phase 0 refinements:
- Set_index_pages routes to qa_direct if word_count > 200 AND prose ratio > 0.4
- New drop rules: Java Edition history of textures/* (wc<500), MinecraftEdu_blocks (wc<400)

---

## Output schema

```jsonl
{
  "title": "...",
  "categories": [...],
  "version": "hardened_v2",
  "source_version": "cleaned",
  "text": "...",                          # the hardened text
  "word_count": N,
  "drop_reason": null,                    # or "version_stub", "set_index_pure_list", etc.
  "route": "main_corpus",                 # or "qa_direct"
  "hardening_meta": {
    "original_word_count": N,
    "passes_applied": ["pre_clean", "section_drops", ...],
    "transforms_count": N,
    "section_drops": ["Sounds", "Issues", "Gallery"],
    "warnings": ["dedup_removed_block_25_times", ...]
  }
}
```

Output paths:
- `raw_data/wiki/articles_hardened.jsonl` — main corpus, ready for training
- `raw_data/wiki/articles_qa_direct.jsonl` — disambig + prose-Set_index, routed to Q&A
- `raw_data/wiki/articles_dropped.jsonl` — audit trail of drops + reasons

---

## Effort estimate

| Phase | Effort |
|---|---|
| D — Implement `hardening_v2.py` (12 phases) | 8-10 hours |
| Token-freq analysis for Layer C glue dict | 1 hour |
| E — Apply to full corpus + verify on 20-article sample | 1-2 hours |
| **Total to hardened corpus** | **~10-13 hours** |

After this, Qwen is reserved for **Q&A multi-lente generation only** (Phase G).

---

## References

- Phase A audit reports (10 agents): consolidated.
- Phase C validation reports (3 agents): consolidated. **GO with caveats** unanimous.
- `../prompts/PHASE4_TRANSFORMATION_PLAN.md` — original plan (Qwen body transformation deprecated).
- `../prompts/PROMPT_TEMPLATES.md` — kept for Q&A phase only.
- `../archive/CLASSIFIER_REDESIGN.md` — taxonomy used for routing.
- `WIKI_DATA_CLEANING.md` — Phase 1+2 (already done; same directory).
