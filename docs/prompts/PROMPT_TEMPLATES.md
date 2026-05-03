# MineGPT — Q&A Prompt Templates

Source of truth for the Q&A generation prompts run on Mac Mini against
qwen3:8b / qwen3:14b. Target output: ~50K-110K Q&A pairs over the hardened
corpus, used for training the v1 model (125-200M params).

> Last updated: 2026-05-03
> Replaces `../archive/PROMPT_TEMPLATES_v1_with_transform.md` — the v1 doc had
> both Transform and Q&A halves; transform was deprecated 2026-04-27. This is
> the Q&A-only successor.

## Strategy

Three-layer prompt construction, same pattern as the deprecated transform path:

1. **Universal Q&A header** (read-only, ~400 tokens) — output format, quantity rules, question/answer rules, forbidden patterns.
2. **Bucket-specific Q&A** (editable per family, ~50-200 tokens) — guides which question types are appropriate.
3. **User message** — article text + meta (title, primary bucket, current lens).

Files live in `scraper/prompt_lab/prompts/_headers/qa.txt` (universal) and
`scraper/prompt_lab/prompts/qa/<family>.txt` (per-bucket). Edited via the
Prompt Lab UI; full reference in `../tools/PROMPT_LAB_UI.md`.

## Universal Q&A header (literal text sent to model)

```text
You are an assistant that generates question-answer pairs from a
Minecraft Wiki article, for training a small language model on factual
recall.

# Output format (strict)

Q: {question}
A: {answer}

Q: {question}
A: {answer}

(Blank line between pairs. No numbering, no headers, no commentary.)

# Quantity (adaptive)

Decide the number of pairs based on article richness:
- Short stub (<200 words): 3-5 pairs.
- Medium (200-1000 words): 5-12 pairs.
- Long (1000+ words): 12-25 pairs.

Do NOT pad with trivial questions. If the article has limited content,
generate fewer pairs. Quality over quantity.

# Question rules

- One question per pair. No chained questions.
- Direct phrasing. No "could you tell me", "do you happen to know".
- Factual or mechanical (not opinion).
- Each question must be answerable from the article text alone.

# Answer rules

- Short and direct. No preambles ("Well,", "In Minecraft,",
  "According to the wiki,").
- 1-3 sentences for factual questions.
- Up to one short paragraph for mechanic questions.

# Question types (mix across the set)

- Factual: stats, properties, drops, materials.
- Mechanical: how something works, what activates it, what it does.
- Spatial: where it appears, which biome, which dimension.
- Comparative: difference between X and Y (only if article supports it).
- Procedural: how to obtain, how to craft, how to use.

# Forbidden

- Questions whose answer is not literally in the article (no
  hallucination).
- Redundant questions (same fact twice with rephrased question).
- Opinion questions ("Is Diamond Pickaxe the best?").
- Yes/No questions unless they have a clear factual answer.

Output ONLY the Q:/A: pairs. Nothing else.
```

## Mapping bucket → family

```
FAMILY = "block":
  Manufactured_blocks, Natural_blocks, Generated_structure_blocks,
  Technical_blocks, Utility_blocks, Non-solid_blocks, Liquids, Fluids,
  Ore, Light_sources, Storage, Hazardous_blocks, Falling_blocks,
  Job_blocks, Compacted_blocks, Blocks_with_GUI, Mechanisms,
  Flammable_blocks, Slabs, Stairs, Walls, Nether_blocks, End_blocks,
  Block_entities, Stationary_entities

FAMILY = "mob":
  Animal_mobs, Hostile_mobs, Passive_mobs, Monster_mobs, Aquatic_mobs,
  Tameable_mobs, Nether_mobs, Undead_mobs, Flying_mobs, Humanoid_mobs,
  Arthropod_mobs, Removed_mobs, Bosses, Mobs

FAMILY = "item":
  Tools, Weapons, Armor, Food, Brewing_ingredients, Raw_materials,
  Potions, Music_Discs, Mob_food, Items

FAMILY = "plant":
  Plants, Crops, Saplings, Flowers, Trees, Vegetation

FAMILY = "mechanic":
  Game_mechanics, Effects, Status_effects, Potion_effects, Enchantments,
  Game_terms, Element, Elements, Minigames, Achievements, Advancements

FAMILY = "world":
  Biomes, Overworld_biomes, Nether_biomes, End_biomes,
  Generated_structures, Generated_features, Dimensions, Environment,
  Settlements

FAMILY = "command":
  Commands

FAMILY = "crafting_recipe":
  Crafting_recipes (virtual bucket from `Crafting/...` titles)

FAMILY = "disambiguation":
  Disambiguation_pages (route_qa_direct after hardening v2)
  Set_index_pages (with prose; route_qa_direct)

FAMILY = "version":
  Bedrock_Edition_versions, Java_Edition_versions, Pocket_Edition_versions
  (route_qa_direct after hardening v2 — snapshot codes are too specific
  for direct training but useful for "when was X added?" Q&A)
```

## Bucket-specific Q&A guidance

Each family-specific file appended to the universal header.

### Family: `block`

```text
Generate Q&A pairs for a Minecraft block article. Apply universal Q&A
header rules.

# Question types relevant to blocks (mix as appropriate)

- Hardness/blast resistance: "What is the hardness of {block}?"
- Tool requirement: "What tool is needed to mine {block}?"
- Tier requirement: "Can a stone pickaxe break {block}?"
- Drops: "What does {block} drop when broken?"
- Drops with Silk Touch: "What does {block} drop with Silk Touch?"
- Light: "What light level does {block} emit?"
- Spawn/generation: "Where does {block} naturally generate?"
- Crafting: "How is {block} crafted?"
- Interactions: "What happens when {block} is powered by redstone?"
- Comparisons (only if article supports): "What is the difference
  between {block} and {related_block}?"
```

### Family: `mob`

```text
Generate Q&A pairs for a Minecraft mob article. Apply universal Q&A
header rules.

# Question types relevant to mobs

- Health: "How much health does {mob} have?"
- Damage: "How much damage does {mob} deal?"
- Spawn: "Where does {mob} spawn?", "In which biomes does {mob} spawn?"
- Drops: "What does {mob} drop when killed?"
- Rare drops: "What is the rare drop of {mob}?"
- XP: "How much XP does {mob} drop?"
- Behavior: "Is {mob} hostile or passive?", "What scares {mob}?"
- Mechanics: "How does {mob} attack?", "What does {mob} eat?"
- Breeding: "How is {mob} bred?", "What does {mob} need to breed?"
- Taming (if applicable): "How is {mob} tamed?"
- Variants: "What variants of {mob} exist?"
- Special: "What happens when {mob} is struck by lightning?"
```

### Family: `item`

```text
Generate Q&A pairs for a Minecraft item article. Apply universal Q&A
header rules.

# Question types relevant to items

- Stack: "What is the stack size of {item}?"
- Durability: "How much durability does {item} have?"
- Damage (weapons): "How much damage does {item} deal?"
- Hunger (food): "How much hunger does {item} restore?"
- Defense (armor): "How much defense does {item} provide?"
- Crafting: "How is {item} crafted?"
- Obtaining: "How is {item} obtained?", "Where is {item} found?"
- Use: "What is {item} used for?"
- Enchantments: "What enchantments are compatible with {item}?"
- Side effects (food/potions): "What status effect does eating {item} cause?"
```

### Family: `plant`

```text
Question types: growth conditions, soil type, biome, drops, bonemealable,
bone meal effect, edible, cooking products, mob breeding/feeding role.
```

### Family: `mechanic`

```text
Question types: triggered by, duration, effect formula, level scaling,
removal method, conflicting effects, interaction with other mechanics,
practical use cases, edge cases.
```

### Family: `world`

```text
Question types: dimension, climate, mobs spawning, blocks present,
structures generating, music/ambient, loot (for structures), generation
conditions, comparisons with similar biomes.
```

### Family: `command`

```text
Question types: syntax, what it does, edition support, permission level,
specific arguments, examples, edge cases, version added.
```

### Family: `crafting_recipe` (Q&A on recipe data)

```text
This is a Minecraft crafting recipe. Generate factual Q&A pairs about
the recipe.

Question types: ingredients required, output, output count, shape
(shaped/shapeless), recipe type, smelting/cooking time, experience
gained.
```

### Family: `disambiguation`

```text
This article is a disambiguation page (lists multiple things sharing a
name). Generate listing and differentiation questions.

Question types:
- "What types of {topic} exist in Minecraft?"
- "What is the difference between {A} and {B}?"
- Listing-style answers are acceptable here (rare exception to the
  "1-3 sentences" rule).
```

### Family: `version` (qa_direct route)

```text
This article describes a specific Minecraft version (release / snapshot /
beta). Generate Q&A pairs about what was added or changed.

Question types:
- "When was {feature} added?"
- "What was added in {version}?"
- "What changed in {version}?"
- "Which edition first received {feature}?"

Do NOT generate questions about specific snapshot codes (e.g. "23w12a")
unless the article frames them as user-facing version markers.
```

## Multi-membership: how the lens is applied

Each article generates N Q&A passes (N = 1 primary + count of also_in lenses
not skipped by dedup rules below).

Each pass receives:
- **Layer 1**: universal Q&A header (always identical)
- **Layer 2**: bucket-specific Q&A guidance for the lens's family + a "Lens-specific focus" hint when the lens is secondary
- **Layer 3**: article text (post-hardening, from `articles_hardened.jsonl`) + meta (title, primary, current lens)

Example, Bell with primary `Generated_structure_blocks` and also_in
`[Redstone, Mechanisms, Block_entities, Utility_blocks]`:

1. Pass 1 — primary `Generated_structure_blocks`: family `block` Q&A. Generates structure-spawn questions.
2. Pass 2 — secondary `Redstone`: family `block` Q&A + lens focus "Redstone activation". Generates redstone-interaction Q&A.
3. Pass 3 — secondary `Mechanisms`: family `block` Q&A + lens focus "Mechanics". Generates Q&A on the bell's mechanical behavior.
4. Pass 4 — secondary `Block_entities`: family `block` Q&A + lens focus "Block entity / NBT". Generates persistent-data Q&A.
5. Pass 5 — secondary `Utility_blocks`: family `block` Q&A + lens focus "Utility usage in gameplay".

Lens `Blocks` (parent) is **skipped by dedup** (see below). 5 passes total.

## Dedup rules for parent lenses

### Why

Multi-lens applies all of (primary + also_in). Some lenses are **generic
parents** of more specific buckets (`Blocks` is parent of `Manufactured_blocks`).
Q&A for an article under a parent lens produces near-duplicate pairs vs the
specific lens — wastes corpus space and overweights the article in training.

### Parent-buckets to skip

```python
PARENT_BUCKETS = {
    "Blocks": [
        "Manufactured_blocks", "Natural_blocks",
        "Generated_structure_blocks", "Utility_blocks",
        "Non-solid_blocks", "Technical_blocks",
        "Liquids", "Fluids", "Nether_blocks", "End_blocks",
    ],
    "Mobs": [
        "Animal_mobs", "Hostile_mobs", "Passive_mobs",
        "Monster_mobs", "Aquatic_mobs", "Tameable_mobs",
        "Nether_mobs", "Undead_mobs", "Flying_mobs",
        "Humanoid_mobs", "Arthropod_mobs", "Removed_mobs",
        "Bosses",
    ],
    "Items": [
        "Tools", "Weapons", "Armor", "Food",
        "Brewing_ingredients", "Raw_materials", "Potions",
        "Music_Discs",
    ],
    "Entities": [
        "Block_entities", "Stationary_entities", "Projectiles",
        "Vehicles", "Playable_entities",
        # plus any *_mobs from PARENT_BUCKETS["Mobs"]
    ],
}

# Rule: if article has primary OR any also_in in a child list,
# skip the parent lens.
```

### Sibling specifics

When an article has multiple specific sibling cats (e.g. `Animal_mobs` +
`Passive_mobs` + `Tameable_mobs`), use **only the primary** (already the most
specific by classifier hierarchy). Sibling cats are also skipped.

### Lenses that DO add a new perspective

Any functional/thematic cat that's not parent or sibling:
- `Redstone`, `Mechanisms`, `Block_entities`, `Light_sources`
- `Hazardous_blocks`, `Falling_blocks`, `Job_blocks`, `Storage`
- `Compacted_blocks`, `Vehicles`, `Blocks_with_GUI`, `Flammable_blocks`
- `Mob_food`, `Slabs`, `Stairs`, `Walls`
- `10th_Anniversary`, `15th_Anniversary` (cosmetic-historical lenses)

### Persistence

Each article's classifier output records which lenses were skipped:

```json
{
  "title": "Bell",
  "primary": "Generated_structure_blocks",
  "also_in": ["Redstone", "Mechanisms", "Block_entities", "Utility_blocks"],
  "skipped_lenses": [
    {"lens": "Blocks", "reason": "parent_of_Generated_structure_blocks"}
  ]
}
```

UI shows skipped lenses in:
- Article detail view (Articles tab)
- Sidebar bucket counter ("47 articles → 38 Q&A passes, 9 dedup'd as parent")
- Prompt Lab when picking a bucket

## Edge cases

### Article with ambiguous stat

Some stats vary by difficulty (Zombie health: 20 normal, 22 hard). Rule:
**use the Normal-difficulty value as default**. The Q&A may include one pair
about the variability.

### Article with undocumented field

If the article doesn't mention a normally-applicable field (e.g. mob without
documented Speed), **generate Q&A only for documented facts**. Don't fabricate
values.

### Article with very variable value

For random drops: use formats like `1-3` or `0-2 with Looting III`. For ranges,
match the wiki's exact phrasing.

### Article too short (stub <100 words)

Vanilla 10-99w articles are typically filtered out before hardening (Phase 0
in `hardening_v2.py`). If a stub somehow reaches Q&A, the model should generate
3-5 pairs only, no padding.

### Article with removed-version references

If the article mentions "removed in 1.13", emit literal Q&A like
"In what version was {feature} removed?" → "1.13". Don't extrapolate.

### Article with bilingual / quote in another language

If the pre-Q&A text contains a quote in another language (e.g. Notch in Swedish),
keep the quote in the original language with quotation marks; the Q&A answer
can quote it directly.

## File structure on Mac Mini

```
scraper/prompt_lab/prompts/
├── _headers/
│   └── qa.txt                  ← universal Q&A header (~400 tokens)
└── qa/
    ├── block.txt
    ├── mob.txt
    ├── item.txt
    ├── plant.txt
    ├── mechanic.txt
    ├── world.txt
    ├── command.txt
    ├── crafting_recipe.txt
    ├── disambiguation.txt
    └── version.txt
```

(The deprecated transform/ subdir was removed; see archive.)

Construction in code:

```python
def build_qa_prompt(article, lens: str) -> str:
    family = bucket_to_family(lens)
    is_secondary = (lens != article.primary_bucket)

    header = read_text("prompts/_headers/qa.txt")
    specific = read_text(f"prompts/qa/{family}.txt")

    user_msg = (
        f"# Article\n\n"
        f"Title: {article.title}\n"
        f"Wiki categories: {', '.join(article.cats)}\n"
        f"Current lens: {lens} ({'secondary' if is_secondary else 'primary'})\n\n"
        f"---\n\n"
        f"{article.text_hardened}"
    )

    return f"{header}\n\n{specific}\n\n{user_msg}"
```

## Pending validation (Phase G — see QA_GENERATION_PLAN.md)

1. Iterate qa/<family>.txt prompts in Prompt Lab on pilot bucket (Animal_mobs suggested).
2. Validate adaptive count: stub (3-5), medium (5-12), long (12-25) with tolerance.
3. Validate lens-specific focus produces meaningfully different Q&A for primary vs secondary lenses.
4. Validate parser tolerates minor whitespace variations.
5. Define output schema: `{"q": "...", "a": "...", "source_title": "...", "source_bucket": "...", "lens": "..."}` proposed.

## References

- `../pipeline/QA_GENERATION_PLAN.md` — strategic plan for Phase G
- `../pipeline/PIPELINE_OVERVIEW.md` — full pipeline state
- `../tools/PROMPT_LAB_UI.md` — dev tool UI reference
- `../archive/PROMPT_TEMPLATES_v1_with_transform.md` — original doc with transform halves (now deprecated)
