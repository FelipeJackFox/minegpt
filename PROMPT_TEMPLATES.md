# MineGPT — Prompt Templates (Phase 4 Transform + Phase 5 Q&A)

> **Status (2026-05-02): TRANSFORM HALF DEPRECATED.**
> Transform sections (universal Transform header + per-bucket Transform prompts)
> are no longer used — Qwen body transformation abandoned 2026-04-27. Q&A halves
> remain valid; consolidated into `QA_GENERATION_PLAN.md`.
>
> Original purpose: fuente única de verdad para prompts de transformación y Q&A.
> Diseñado para qwen3:8b / qwen3:14b corriendo via Ollama en Mac Mini M2.
> Target: LLM custom de 125-200M params entrenado desde cero.
>
> Fecha: 2026-04-26 (banner 2026-05-02)

---

## Filosofía

### Estructura de 3 capas por prompt

```
[CAPA 1: HEADER UNIVERSAL]   ← idéntico para TODOS los transforms (o todos los Q&A)
  Reglas de formato, lenguaje, estructura.

[CAPA 2: BUCKET-SPECIFIC]    ← varía por familia (block/mob/item/plant/mechanic/command)
  Lista de campos ## Properties para esa familia.
  Foco específico cuando es lente also_in.

[CAPA 3: USER MESSAGE]       ← varía por artículo
  Texto pre-transform + cats originales.
```

### Por qué header universal compartido

1. **Consistencia**: 200+ buckets futuros usan las mismas reglas. Una regla en un solo lugar.
2. **Iteración barata**: bug detectado en bucket 87 → fix en header → todos los buckets futuros heredan.
3. **Prompt caching de Ollama**: header idéntico entre calls del mismo bucket → KV cache evita recomputarlo.
4. **Auditoría limpia**: una sola fuente de verdad para reglas globales.

### Reglas globales de formato (la "ley" del proyecto)

Estas reglas NO se violan nunca, las codifica el header universal:

- **Numéricos**: número puro, sin unidad pegada. `Hardness: 1.5`, no `Hardness: 1.5 hearts`.
- **Booleanos**: solo `Yes` o `No`. Nunca `True/False`, `yes/no`, `Y/N`.
- **Rangos**: con guión. `Damage: 1-3`, no `Damage: 1 to 3`.
- **Listas cortas**: separadas por coma. `Spawn: Plains, Forest, Taiga`.
- **Sin tablas markdown** (`|`, `---`).
- **Sin emojis o unicode** (♥, ★, ✓). Usar palabras.
- **Sin lenguaje promocional** ("iconic", "fascinating", "amazing", "must-have").
- **Sin meta-referencias** ("según el wiki", "as you may know").
- **Sin notas inline** ("Note:", "TIP:", "WARNING:").
- **Idioma**: inglés, presente, tono neutral, factual, enciclopédico.
- **Omitir si no aplica**: si un campo de Properties no aplica al artículo, NO emitirlo. No escribir `Damage: N/A`, `Damage: -`, etc.

---

## Header universal — Transform

Texto literal que va al modelo:

```text
You are an assistant that rewrites Minecraft Wiki articles (vanilla,
Java/Bedrock Edition) into a consistent structured format for training
a small language model.

# Output structure (strict)

# {Article name, exactly as given}
## Overview
## Properties
## Details
## Obtaining       (omit if not applicable)
## Trivia          (omit if no relevant lore exists)

# Formatting rules

## Properties section
- One key per line, format: `Key: value`
- Numeric values: bare numbers, no units. Write `Hardness: 1.5`, not
  `Hardness: 1.5 hearts` or `Hardness: 1.5 (one and a half)`.
- Boolean: only `Yes` or `No`. Never `True/False`, `yes/no`, `Y/N`.
- Range: hyphen-separated. `Damage: 1-3`, not `Damage: 1 to 3`.
- List values: comma-separated. `Spawn: Plains, Forest, Taiga`.
- If a field does not apply to this article, OMIT the line entirely.
  Do not write `Damage: N/A`, `Damage: -`, or `Damage: none`.

## Details section
- Dense factual prose, present tense.
- Explain mechanics, interactions, edge cases.
- No bullet points, no sub-headers.

## Overview section
- 1-2 sentences. State what the entity is and where/when it appears.
- No subjective adjectives ("iconic", "fascinating", "amazing").

# Forbidden

- Markdown tables (no `|`, no `---`).
- Emojis or unicode symbols (no ♥, ★, ✓). Use words.
- Promotional language ("fan-favorite", "must-have").
- Meta references ("according to the wiki", "as you may know").
- Inline notes ("Note:", "TIP:", "WARNING:").
- Repeating the prompt or adding "Here is the result:".

# Language

- English. Neutral, factual, encyclopedic tone.
- Present tense.
- Subject: the article name, or pronoun when clear.

Output ONLY the markdown. Nothing else.
```

---

## Header universal — Q&A

Texto literal que va al modelo:

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

---

## Mapping bucket → family

Este mapeo determina qué bucket-specific se concatena al header universal.

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
  Plants

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

FAMILY = "version":
  Bedrock_Edition_versions, Java_Edition_versions, Pocket_Edition_versions,
  Versions
  → Special handling: extract player-facing changelog only

FAMILY = "person":
  People, Companies, Events, History, Community_business
  → Solo regex clean, NO transform

FAMILY = "tutorial":
  Tutorials, Java_guides, Bedrock_guides, Redstone_tutorials
  → Solo regex clean, NO transform

FAMILY = "external":
  external_wikipedia, external_notch_blog, external_youtube
  → NO transform, ya están limpios
```

---

## Bucket-specific — Transform

### Family: `block`

```text
This article describes a Minecraft block. Apply the universal header
rules with these block-specific specifications.

# Properties fields (emit only those that apply)

Type: {Solid/Non-solid/Liquid/Falling/Block entity/Light source/Job block/...}
Hardness: {number}
Blast resistance: {number}
Tool: {axe/pickaxe/shovel/shears/hoe/any/none}
Mineable with: {wood/stone/iron/diamond/netherite/any}
Renewable: {Yes/No}
Stackable: {Yes (64) / Yes (16) / No}
Flammable: {Yes/No}
Light level: {0-15}
Light filter: {0-15, omit if 0 or not relevant}
Transparent: {Yes/No}

# Details section focus

Describe in prose:
- Mining mechanics, drop conditions (with/without Silk Touch, Fortune)
- Interactions with redstone, water, lava, gravity
- Special behaviors (e.g. crafting station GUI, sound when broken)
- Variants (planks types, color variants if relevant)

# Lens-specific focus (when this article is being transformed under a
secondary lens via also_in)

If lens is "Redstone": emphasize how redstone activates this block,
what the block does when powered, signal strength behavior.

If lens is "Block_entities": emphasize NBT data, GUI, saved state,
inventory if any.

If lens is "Hazardous_blocks": emphasize damage type, damage amount,
mob behavior near it.

If lens is "Light_sources": emphasize light level, range, what triggers
light emission.

If lens is "Mob_food": emphasize which mobs eat or breed with this item.

If lens is "Job_blocks": emphasize which villager profession claims it,
work patterns, particles when in use.

If lens is "Falling_blocks": emphasize fall damage, support requirements,
duplication mechanics if applicable.

If lens is "Mechanisms": emphasize activation conditions, output,
redstone integration.
```

### Family: `mob`

```text
This article describes a Minecraft mob (entity with AI). Apply the
universal header rules with these mob-specific specifications.

# Properties fields (emit only those that apply)

Type: {Passive/Hostile/Neutral/Boss/Tameable/Rideable/...}
Health: {number}
Damage: {number, omit if mob does not attack}
Walking speed: {decimal}
Swimming speed: {decimal, omit if not aquatic-capable}
Flying speed: {decimal, omit if not flying}
Spawn: {biomes, comma-separated}
Spawn light level: {0-15 / any}
XP drop: {number or range}
Tameable: {Yes/No}
Rideable: {Yes/No}
Breedable: {Yes/No}

# Details section focus

Describe in prose:
- AI behavior (how it pursues, what scares it, breeding mechanics)
- Combat patterns (attack interval, projectiles, special abilities)
- Drops (regular drops, rare drops, Looting modifier effects, with prose
  describing drop conditions; the Properties section already lists XP)
- Variants (color, biome variants, baby form)
- Interactions with other mobs and players

# Lens-specific focus

If lens is "Tameable_mobs": emphasize taming mechanic, required item,
post-tame behavior, commands ("sit", "follow").

If lens is "Bosses": emphasize phases, summoning ritual, drops,
achievement unlocked, music change.

If lens is "Aquatic_mobs": emphasize water behavior, out-of-water
consequences, breeding underwater.

If lens is "Undead_mobs": emphasize Smite enchantment effect, healing
from harming potions, day/night burning.

If lens is "Nether_mobs": emphasize Nether-only spawn, lava immunity,
piglin/hoglin interactions.
```

### Family: `item`

```text
This article describes a Minecraft item (held in inventory). Apply
the universal header rules with these item-specific specifications.

# Properties fields (emit only those that apply)

Type: {Tool/Weapon/Armor/Food/Material/Fuel/Music disc/Map/Banner/...}
Stack: {1/16/64}
Renewable: {Yes/No}
Durability: {number, omit if not applicable}
Damage: {number, omit if not weapon/tool}
Mining speed: {number, omit if not tool}
Hunger restored: {number, omit if not food}
Saturation: {decimal, omit if not food}
Defense: {number, omit if not armor}
Toughness: {number, omit if not armor}
Knockback resistance: {decimal, omit if not armor}
Enchantability: {number, omit if not enchantable}
Burn time: {seconds, omit if not fuel}

# Details section focus

Describe in prose:
- Use cases (combat, crafting ingredient, ritual, decoration)
- Crafting outputs (what it makes when used)
- Special behaviors (eating effects, weapon mechanics, repair logic)
- Compatible enchantments, durability formulas

# Lens-specific focus

If lens is "Brewing_ingredients": emphasize potion recipes, base potion,
modifier role, redstone/glowstone interaction.

If lens is "Mob_food": emphasize which mobs eat it for healing, breeding,
or taming.

If lens is "Music_Discs": emphasize obtain method, play mechanism,
length, composer.

If lens is "Raw_materials": emphasize smelting recipe, yield, biomes/
structures where the source block is found.

If lens is "Food": emphasize hunger restored, saturation, eating speed,
side effects (regen, poison, etc.).

If lens is "Tools": emphasize tier, durability, mining speed by material,
attack damage as melee weapon.

If lens is "Armor": emphasize defense per slot, durability, special
effects (e.g. Turtle Shell water breathing).

If lens is "Weapons": emphasize damage, attack speed, knockback,
critical hit behavior.
```

### Family: `plant`

```text
This article describes a Minecraft plant (organic block or item that
grows or is grown). Apply the universal header rules with these
plant-specific specifications.

# Properties fields (emit only those that apply)

Type: {Crop/Tree/Bush/Flower/Aquatic plant/Fungus/Vine/Sapling/...}
Renewable: {Yes/No}
Growth stages: {number}
Light requirement: {0-15 minimum}
Soil: {Dirt/Farmland/Sand/Clay/Mud/Soul Sand/...}
Biomes: {comma-separated}
Bonemealable: {Yes/No}
Edible: {Yes/No}

# Details section focus

Describe in prose:
- Growth mechanics (speed, conditions, water proximity)
- Harvesting (drops with/without Fortune, breaking by hand vs tool)
- Generation in world (which structures, biome density)
- Cooking or processing if applicable
- Composter compatibility, bone meal interactions

# Lens-specific focus

If lens is "Mob_food": which animals eat or are bred by this plant.

If lens is "Brewing_ingredients": potion role.

If lens is "Items": stack size, where the item form is used.
```

### Family: `mechanic`

```text
This article describes a Minecraft game mechanic, status effect, or
enchantment (an abstract gameplay concept, not a physical entity).
Apply the universal header rules with these specifications.

# Properties fields (emit only those that apply)

Type: {Game mechanic/Status effect/Enchantment/Game term}
Triggered by: {event or action that activates it}
Duration: {seconds or "infinite", omit if not time-bound}
Particle: {color or visual indicator, omit if not status effect}
Max level: {number, only enchantments}
Compatible with: {item types, only enchantments}
Treasure: {Yes/No, only enchantments}
Curse: {Yes/No, only enchantments}
Mutually exclusive with: {other effects/enchantments, comma-separated}

# Details section focus

Describe in prose:
- What it does mechanically (numerical effect on stats, gameplay change)
- How it interacts with other mechanics (stacking, cancellation)
- Edge cases (level 0, max level, removal with milk bucket)
- Practical examples

# Lens-specific focus

If lens is "Status_effects": emphasize particle color, sources of the
effect (potion, mob attack, beacon), removal methods, level scaling.

If lens is "Game_mechanics": emphasize formula, constants, edge cases,
version differences.

If lens is "Enchantments": emphasize compatible items, levels, treasure
status, curse status, conflicting enchantments.
```

### Family: `world`

```text
This article describes a Minecraft world feature (biome, structure,
generated feature, dimension). Apply the universal header rules with
these specifications.

# Properties fields (emit only those that apply)

Type: {Biome/Structure/Feature/Dimension}
Dimension: {Overworld/Nether/End}
Climate: {Temperate/Cold/Warm/Snowy/...}
Temperature: {decimal, only biomes}
Downfall: {Rain/Snow/None}
Generation: {Surface/Underground/Cave/Sky/...}
Mobs: {primary mobs spawning here, comma-separated}
Structures: {structures generating here, comma-separated, only biomes}

# Details section focus

Describe in prose:
- Visual appearance (terrain, foliage, sky color, fog)
- Block composition (top blocks, sub-surface, ores)
- Mob spawning (specific to this biome/structure)
- Loot (for structures: chest contents, rare items)
- Music or ambient sounds
- Generation logic (depth, frequency, world seed effects)

# Lens-specific focus

If lens is "Generated_structures": emphasize loot tables, mob spawners,
trap mechanics, finding strategy.

If lens is "Generated_features": emphasize generation conditions,
density, biome restrictions.
```

### Family: `command` (overrides universal structure)

```text
This article describes a Minecraft command. Use this STRUCTURE INSTEAD
of the universal Overview/Properties/Details structure. The universal
formatting rules (no emojis, no tables, no marketing language) still
apply.

# Output structure

# /{command name}

## Syntax
{full syntax with required arguments in <angle brackets> and optional
arguments in [square brackets], following Minecraft conventions}

## Edition support
Java Edition: {Yes/No, since version}
Bedrock Edition: {Yes/No, since version}

## Permission level
{0-4 for Java, equivalent for Bedrock}

## Description
{1-3 paragraphs explaining what the command does, side effects,
interactions with game state. Prose, no bullets.}

## Arguments
{argname}: {type, description, default value if any}
{argname}: {type, description, default value if any}

## Examples
/{example with explanation}
/{another example with explanation}

## Trivia
{optional, only if there is documented history or removed behavior}

# Notes

- Argument names use Minecraft conventions: <required> for mandatory,
  [optional] for optional.
- Examples must be runnable as-is (no placeholder text).
- Description: prose, no bullet points.
```

### Family: `crafting_recipe` (JSON output, not Qwen prose)

```text
This is a Minecraft crafting recipe. Output STRICTLY a JSON object,
no markdown, no prose, no explanation, no code fences.

# Output schema

{
  "result": "{item id, lowercase, snake_case, e.g. 'iron_pickaxe'}",
  "result_count": {integer},
  "shape": "{shaped|shapeless|smelting|blasting|smoking|campfire|stonecutting|smithing|brewing}",
  "pattern": ["{row 1}", "{row 2}", "{row 3}"],
  "key": {
    "{single character}": "{ingredient item id}"
  },
  "ingredients": ["{item ids}"],
  "experience": {decimal},
  "cooking_time": {integer ticks}
}

Rules:
- "pattern" and "key" are used for shaped recipes only. Set to null
  otherwise.
- "ingredients" is used for shapeless recipes only. Set to null otherwise.
- "experience" and "cooking_time" only apply to smelting/blasting/smoking/
  campfire. Set to null for other recipe types.
- Use null for fields that don't apply. Do not omit them.

Output ONLY the JSON object. No markdown fences, no commentary.
```

### Family: `version` (player-facing changelog extraction)

```text
This article is a Minecraft version page (release notes, snapshot,
beta, or preview). Extract ONLY player-facing changes. Discard
protocol-level technical details, server admin commands not used by
typical players, and internal refactors.

# Output structure

# {Version name, exactly as given}

## Release date
{YYYY-MM-DD or "Unreleased" or "Unknown"}

## Type
{Release/Snapshot/Beta/Preview/Pre-release/Release candidate}

## Edition
{Java Edition/Bedrock Edition/Pocket Edition/Education Edition}

## Highlights
{2-5 bullet-style sentences as plain prose, separated by blank lines.
Each one names a major feature added or major change. NO bullets, NO
asterisks, just prose paragraphs.}

## Additions
{Each new block, item, mob, mechanic, biome, structure as a separate
prose paragraph. Group related items.}

## Changes
{Each behavior change to existing content as prose paragraphs.}

## Removals
{Each removed feature as prose, only if relevant to a player.}

# Forbidden

- Protocol version numbers, network changes, JSON schema updates.
- Internal refactors, code-level changes, performance optimizations
  unless user-visible.
- Bug fix lists for trivial issues.
```

### Other families: NO transform

- **`person`** (People, Companies, Events, History, Community_business): texto pre-transform ya está bien (regex limpio + bio del wiki). Pasa directo a training.
- **`tutorial`** (Tutorials, *_guides, Redstone_tutorials): formato instructivo del wiki ya es útil para training. Pasa directo.
- **`external`** (Wikipedia bios, Notch posts, YouTube transcripts): ya limpios. Pasa directo.

---

## Bucket-specific — Q&A

El header universal de Q&A ya cubre el formato. Por familia, agregamos guía sobre **tipos de pregunta apropiados**.

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

---

## Reglas de dedup por padres genéricos

### Por qué

Multi-transform aplica todos los lentes (primary + also_in) a cada artículo. Pero algunos lentes son **padres genéricos** de otros más específicos (`Blocks` es padre de `Manufactured_blocks`). Transformar un artículo dos veces con un padre y un hijo produce textos casi idénticos donde el padre es solo una versión más vaga del hijo. Esto es **redundancia tipo A** (paráfrasis pobre, no perspectiva nueva) y daña el training de modelos chicos al sobrepesar contenido duplicado.

### Lentes a skipear

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

### Hermanos específicos en la misma categoría

Cuando un artículo tiene múltiples cats específicas hermanas (e.g. `Animal_mobs` + `Passive_mobs` + `Tameable_mobs`), usar **solo el primary** (que ya es el más específico por la jerarquía del classifier). Los hermanos también se skipean.

### Lentes que SÍ se incluyen (perspectiva distinta real)

Cualquier cat funcional/temática que NO sea hermano ni padre:
- `Redstone`, `Mechanisms`, `Block_entities`, `Light_sources`
- `Hazardous_blocks`, `Falling_blocks`, `Job_blocks`, `Storage`
- `Compacted_blocks`, `Vehicles`, `Blocks_with_GUI`, `Flammable_blocks`
- `Mob_food`, `Slabs`, `Stairs`, `Walls`
- `10th_Anniversary`, `15th_Anniversary` (cosmetic-historical lenses)

### Persistencia y trazabilidad

Cada artículo en el output del classifier lleva campo:

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

UI muestra los `skipped_lenses` en:
- Vista detalle del artículo (Articles tab)
- Sidebar bucket counter ("47 articles → 38 transforms, 9 dedup'd as parent")
- Prompt Lab al elegir bucket ("Animal_mobs: 47 primary + 0 also_in [9 dedup'd]")

---

## Multi-membership: cómo se aplica el lente

Para cada artículo, el classifier produce N transformaciones (N = 1 primary + cantidad de also_in NO skipeados).

Cada transformación recibe:
- **CAPA 1**: header universal de transform (idéntico siempre).
- **CAPA 2**: bucket-specific de la familia del lente actual + sección "Lens-specific focus" si el lente es secundario.
- **CAPA 3**: texto pre-transform del artículo + cats originales + indicador del lente actual.

Ejemplo, Bell con primary `Generated_structure_blocks` y also_in `[Redstone, Mechanisms, Block_entities, Utility_blocks]`:

1. Transform 1 — lente `Generated_structure_blocks`: bucket-specific `block` + sin "Lens-specific focus" (es el primary). Output: formato block estándar enfocado en bell como bloque generado en estructuras.
2. Transform 2 — lente `Redstone`: bucket-specific `block` + sección "Lens-specific focus: Redstone". Output: enfoca en activación por señal redstone.
3. Transform 3 — lente `Mechanisms`: bucket-specific `block` + "Lens-specific focus: Mechanisms". Output: enfoca en activación y efecto mecánico.
4. Transform 4 — lente `Block_entities`: bucket-specific `block` + "Lens-specific focus: Block_entities". Output: NBT, data persistente.
5. Transform 5 — lente `Utility_blocks`: bucket-specific `block` + "Lens-specific focus: Utility_blocks". Output: uso utilitario en gameplay.

Lente `Blocks` (padre genérico) se skipea por dedup. 5 transformaciones totales en lugar de 6.

---

## Casos edge a manejar

### Artículo con stat ambiguo

Algunos stats varían por dificultad (Health del Zombie: 20 normal, 22 hard). Regla: **usar el valor de Normal difficulty como default** en `## Properties`. La variabilidad se menciona en `## Details` en prosa.

### Artículo con campo no documentado

Si el artículo no menciona un campo que normalmente aplicaría (e.g. mob sin Speed documentado), **omitir el campo**. NO inventar valores.

### Artículo con valor en rango muy variable

Para drops aleatorios: usar formato `1-3` o `0-2 with Looting III`. Para spawn light: `0-15` si no hay restricción. Para experiencia: `1-3` o el rango exacto del wiki.

### Artículo demasiado corto (stub <100 palabras)

Hay dos opciones decididas en el plan maestro:
- **Vanilla 10-99w**: filter manual, descartar la mayoría.
- **Vanilla 100-499w**: solo regex, no transform.
- Si llega a transform de todos modos, el modelo emite Overview corta + Properties incompletas + Details brief. No forzar contenido inventado.

### Artículo con referencias a versiones removidas

Mencionar la versión donde fue removido en `## Trivia` o `## Details` como prosa. NO inventar fechas. Si el wiki dice "removed in 1.13", emit literalmente "Removed in 1.13".

### Artículo bilingüe o con texto en otro idioma

Si el artículo pre-transform tiene fragmentos en otro idioma (ej: cita de Notch en sueco), **dejar la cita en idioma original entrecomillada** y traducir/explicar en prosa al lado.

---

## Estructura de archivos del prompt system

```
scraper/prompt_lab/prompts/
├── _headers/
│   ├── transform.txt         ← header universal Transform (~400 tokens)
│   └── qa.txt                ← header universal Q&A (~400 tokens)
├── transform/
│   ├── block.txt             ← bucket-specific por familia
│   ├── mob.txt
│   ├── item.txt
│   ├── plant.txt
│   ├── mechanic.txt
│   ├── world.txt
│   ├── command.txt
│   ├── crafting_recipe.txt
│   └── version.txt
└── qa/
    ├── block.txt
    ├── mob.txt
    ├── item.txt
    ├── plant.txt
    ├── mechanic.txt
    ├── world.txt
    ├── command.txt
    ├── crafting_recipe.txt
    └── disambiguation.txt
```

Construcción del prompt en código:

```python
def build_transform_prompt(article, lens: str) -> str:
    family = bucket_to_family(lens)
    is_secondary = (lens != article.primary_bucket)
    
    header = read_text("prompts/_headers/transform.txt")
    specific = read_text(f"prompts/transform/{family}.txt")
    
    user_msg = (
        f"# Article\n\n"
        f"Title: {article.title}\n"
        f"Wiki categories: {', '.join(article.cats)}\n"
        f"Current lens: {lens} ({'secondary' if is_secondary else 'primary'})\n\n"
        f"---\n\n"
        f"{article.text_pretransform}"
    )
    
    return f"{header}\n\n{specific}\n\n{user_msg}"
```

---

## Pendientes para validar con el tooling

Esta lista se valida en Fase 4.0 (al tener Prompt Lab funcionando) y en Fase 4.1 (pilot Animal_mobs):

1. **Validar que qwen3:8b respeta el header universal**: probar con 1 artículo Animal_mobs (Cow, ~3700 palabras). Verificar:
   - Estructura `# Name / ## Overview / ## Properties / ## Details / ## Obtaining / ## Trivia` exacta
   - Properties en formato `Key: value`, números puros, sin emojis
   - Sin tablas markdown
   - Sin lenguaje promocional
   - Idioma inglés, presente, factual

2. **Validar few-shot necesidad**: si el modelo respeta el header sin few-shot examples, no agregar. Si tiene problemas (ej: emite tablas), agregar 1 ejemplo few-shot al bucket-specific.

3. **Validar Q&A adaptive count**: probar con artículo corto (Stub, ~100 palabras), medio (~500), largo (Cow, 3700). El modelo debe generar 3-5, 8-10, 18-22 pairs respectivamente (con tolerancia).

4. **Validar lens-specific focus**: transformar Bell bajo lente `Redstone` vs `Block_entities`. Los outputs deben enfatizar aspectos distintos en `## Details`.

5. **Validar parsing**: el parser de output debe aceptar variaciones menores (espaciado, salto de línea extra) sin fallar.

6. **Validar JSON output de Crafting_recipes**: el modelo emite JSON parseable sin fences markdown.

7. **Iterar headers si es necesario**: si una regla universal se viola sistemáticamente, fortalecerla en el header (ej: agregar "DO NOT use unicode hearts ♥" si el modelo insiste).

---

## Decisiones tomadas durante diseño (resumen)

| Decisión | Resolución |
|---|---|
| Header universal compartido | Sí. 3 capas: header + bucket-specific + user message. |
| Formato stats | `clave: número_puro`, sin tablas, sin emojis, sin unidades pegadas. |
| Templates uniformes describibles | `# Name / ## Overview / ## Properties / ## Details / ## Obtaining / ## Trivia`. |
| Templates especiales | Commands (estructura propia), Crafting_recipes (JSON). |
| Multi-transform | Sí, una transformación por lente (primary + also_in). |
| Dedup de padres | Sí. `Blocks/Mobs/Items/Entities` skipean si hay específico. Hermanos mismos skipean también. |
| Q&A adaptive count | Sí. Modelo decide N según riqueza (3-5 / 5-12 / 12-25). 1 sola call por artículo. |
| Q&A pre-transform | Q&A se genera del texto post-regex pre-Qwen (más detalle). |
| Transform vs Q&A | Secuencial por bucket: primero transform, después Q&A. NO paralelo. |
| Lenguaje | Inglés. Presente. Tono neutral, factual, enciclopédico. |
| Few-shot examples | TBD. Probar sin first; agregar si es necesario. |

---

## Referencias

- `PHASE4_TRANSFORMATION_PLAN.md` — plan operacional completo
- `CLASSIFIER_REDESIGN.md` — taxonomía cat-driven
- `WIKI_DATA_CLEANING.md` — pipeline de Phases 1-3
- `raw_data/_exploration/misclassifications.jsonl` — auditoría de 130 flags
