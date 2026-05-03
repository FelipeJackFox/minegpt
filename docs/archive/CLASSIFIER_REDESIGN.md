# MineGPT — Classifier Redesign Proposal

> Reemplazo del classifier actual (`scraper/explore_subgroups.py`) por un sistema cat-driven en 2 capas.
>
> Status: **propuesta para revisión** (Felipe + Claude). No implementado aún.
> Fecha: 2026-04-26

---

## Filosofía

**Las cats del wiki son la verdad.** Comunidad de años curándolas. Nosotros aportamos:

1. **Detección de ambiente** (capa A) — separar contextos para que no se mezclen (game vs tutorial vs movie vs personalidades)
2. **Jerarquía de prioridad** (capa B) — cuando un artículo tiene múltiples cats que compiten, cuál gana como primary

Lo que se va: nuestros buckets inventados (`block`, `mechanic`, `redstone`, `multi_concept`, `entity_other`, etc.), listas hardcoded de títulos (~50 entries), super-categorías arbitrarias.

Lo que se queda: multi-membership (primary + also_in), filter de meta cats, sistema de viewer, external sources, lecciones de auditoría (Bell→block, April Fools, Education detection, etc.).

---

## Capa A — Ambiente (1 de 7, en orden de prioridad)

Cada artículo cae en EXACTAMENTE un ambiente. Detección por reglas en este orden:

| Orden | Ambiente | Detección | ~Count | Razón |
|---|---|---|---|---|
| 1 | `wiki_meta` | Title prefix `File:`, `Template:`, `Help:`, `Minecraft Wiki:` o cats `Files_with_a_license_template`, `Mojang_images`, `Notice_templates`, `Documentation_pages`, `Soft_redirects` | ~30 | metadata pura del wiki, no es contenido |
| 2 | `spinoff` | Title prefix `Dungeons:`, `MCD:`, `Legends:`, `Earth:`, `Minecraft Earth:`, `Story Mode:` | ~1,720 | non-canonical (postponed v2) |
| 3 | `april_fools` | Cats `Joke_features`/`Joke_blocks`/`Joke_items`/`Joke_mobs`/`Joke_entities`/`Joke_biomes`/`Joke_effects`/`Joke_dimensions`/`Joke_block_renders` o title contiene `(April Fools' joke)` | ~260 | non-canonical |
| 4 | `education_edition` | Cats `Minecraft_Education`, `Minecraft_Education_specific_information`, `MinecraftEdu*`, `Education_Edition_*` (cuando aplica al CONTENIDO, no a versiones) | ~170 | non-canonical |
| 5 | `tutorial` | Title prefix `Tutorial:`, `Tutorials/` o cats `Tutorials`, `Java_Edition_guides`, `Bedrock_Edition_guides` o title exacto en `{Redstone circuits, Redstone components, Redstone mechanics, MCRedstoneSim schematics}` o title `Redstone circuits/X` (1-2 niveles) | ~560 | guías generadas por usuarios, NO mezclar con game |
| 6 | `media_franchise` | Cats `A_Minecraft_Movie*`, `Minecraft_Mini-Series*`, `Mob_Squad*`, `M.A.R.I.L.L.A.*`, `Comic_books`, `Live_action_content`, `Animated_content`, `Books`, `Fiction`, `Nick_Eliopulos_novels`, `Max_Brooks_novels`, `Meta_novels`, `Adventure_maps`, `Game_trailers`, `Editorials`, `Online_content`, `Minecraft:_Story_Mode`, `Maps`, `Science_fiction`, `Minecraft_(franchise)`, `Minecraft:_*_chapters` o title prefix `Movie:` | ~850 | meta-game content |
| 7 | `real_world` | Cats: personas (`Actors`, `YouTubers`, `Streamers`, `Hosts`, `Players`, `Students`, `Mobologists`), empresas (`Mojang_Studios`, `Microsoft`, `Companies`), eventos (`MINECON`, `Minecraft_Live`, `Events`, `Historical_events`, `Live_streams`, `Eerie_Mojang_Office_Party`), historia (`History`, `15th_Anniversary`, `10th_Anniversary`, `MCC_x_Minecraft_15th_Anniversary_Party`, `Birthday_skin_packs`), comunidad (`Community`, `Collaborations`, `Cross-franchise_promotions`, `Merchandise`, `Discontinued`, `Minecraft_Marketplace`, `Event_servers`) | ~600 | gente y empresas reales, eventos del mundo real |
| 8 | `game_vanilla` | DEFAULT (todo lo demás que tenga cats semánticas del juego) | ~6,800 | el juego canónico |

**Notas:**
- Title prefix wins sobre cats (un artículo `Dungeons:Boss` con cat `Mobs` va a `spinoff`, no a `game_vanilla.Mobs`).
- April Fools y Education tienen prioridad alta para que NO se filtre como vanilla.
- `removed_feature` y `version` van dentro de `game_vanilla` (son contenido del juego, solo que histórico/no actual).

---

## Capa B — Buckets dentro de cada ambiente (cat-driven)

### `game_vanilla` — buckets = cats reales del wiki

Jerarquía de prioridad: si el artículo tiene varios cats matching, gana el primero en aparecer en la lista.

#### Tier 1: Identidad fuerte específica (más específica primero)

```
SPECIFIC_MOB_CATS:
  Animal_mobs (47)
  Hostile_mobs (43)
  Passive_mobs (40)
  Monster_mobs (55)
  Aquatic_mobs (16)
  Tameable_mobs (13)
  Nether_mobs (17)
  Undead_mobs (19)
  Flying_mobs (12)
  Humanoid_mobs (11)
  Removed_mobs (10)
  Arthropod_mobs (7)
  Bosses

SPECIFIC_BLOCK_CATS:
  Manufactured_blocks (370)
  Natural_blocks (187)
  Generated_structure_blocks (288)
  Technical_blocks
  Utility_blocks (131)
  Non-solid_blocks (122)
  Liquids
  Fluids

SPECIFIC_ITEM_CATS:
  Tools
  Weapons
  Armor
  Food (52)
  Brewing_ingredients
  Raw_materials
  Potions (16)
  Music_Discs
```

#### Tier 2: Identidad fuerte genérica (fallback si no Tier 1)

```
Mobs           → bucket `Mobs`
Blocks (727)   → bucket `Blocks`
Items (480)    → bucket `Items`
Plants (102)   → bucket `Plants`
Ore (34)       → bucket `Ore`
```

#### Tier 3: Tipos especiales

```
Versions / Removed:
  Removed_features (407)        → bucket `Removed_features`
  *_versions, *_betas, *_previews, *_snapshots → bucket `Versions`
  (sub-buckets por edition: Java_Edition_versions, Bedrock_Edition_versions, etc.)

Disambiguation:
  Disambiguation_pages (557)    → bucket `Disambiguation_pages`
  Set_index_pages (113)         → bucket `Set_index_pages`
  Achievement_disambiguation_pages → bucket `Achievement_disambiguation_pages`
  Version_disambiguation_pages  → bucket `Version_disambiguation_pages`

Commands:
  Commands (322) o title `Commands/`  → bucket `Commands`

Generated content / world:
  Biomes
  Overworld_biomes (57)
  Nether_biomes (5)
  End_biomes
  Generated_structures (34)
  Generated_features (84)
  Dimensions
  Environment (69)
  Settlements
  Structure_blueprints
  Village_blueprints
  Village_structure_subpages

Mechanics:
  Game_mechanics
  Effects (50)
  Status_effects
  Potion_effects
  Enchantments (46)
  Game_terms
  Element / Elements (11)
  Minigames (5)
  Server (5)

Sound:
  Sounds
  Music (160)

Achievements:
  Achievements
  Advancements

Cosmetic:
  Skin_packs (112)
  Capes (53)
  Texture_packs (13)
  Resource_packs (22)
  Mash-up_packs
  Character_Creator
  Add-ons
  Collaborative_skin_packs (51)

Entities (catch-all si no es mob ni block_entity):
  Entities (260)
  Block_entities (73)
  Stationary_entities
  Joke_entities (excluido — va a april_fools)
  Projectiles
  Vehicles
  Playable_entities

Title-based fallbacks (cats no aplicables):
  Title prefix `Crafting/`         → bucket `Crafting_recipes`
  Title prefix `List of `           → bucket `Lists`
  Title suffix `/Structure`         → bucket `Structure_subpages`
  Title suffix `/BS`                → bucket `Block_states_reference`
  Title in EDITION_OVERVIEW_TITLES  → bucket `Edition_overview`
  Cat `Game_modes`                  → bucket `Game_modes`
  Cat `Menu_screens` o `UI`         → bucket `UI_settings`
  Cat `Experimental` o `Java_experimental_*` o `Bedrock_experimental_*` → bucket `Experimental`
  Cat `Top-level_data_pages` o `Java_Edition_technical` o etc. → bucket `Technical_reference`
```

### `tutorial` — buckets = sub-tipos de tutoriales

```
Tutorials (388)              → bucket `Tutorials` (default)
Java_Edition_guides (52)     → bucket `Java_guides`
Bedrock_Edition_guides (49)  → bucket `Bedrock_guides`

Title-based:
  Redstone circuits / Redstone components / Redstone mechanics → bucket `Redstone_tutorials`
  Tutorial:Programs and editors                                → bucket `Software_tutorials`
```

### `spinoff` — buckets por juego

```
Title prefix Dungeons:    → bucket `Dungeons`
  Sub-buckets por cat: Minecraft_Dungeons_items, Minecraft_Dungeons_entities, Minecraft_Dungeons_locations, Minecraft_Dungeons_enchantments, etc.
Title prefix Legends:     → bucket `Legends`
Title prefix Earth:       → bucket `Earth`
Title prefix Story Mode:  → bucket `Story_Mode`
```

### `april_fools` — buckets por tipo

```
Joke_features (254)   → bucket `Joke_features` (default)
Joke_blocks (95)      → bucket `Joke_blocks`
Joke_items (52)       → bucket `Joke_items`
Joke_mobs (30)        → bucket `Joke_mobs`
Joke_entities (18)    → bucket `Joke_entities`
Joke_biomes (10)      → bucket `Joke_biomes`
Joke_effects (7)      → bucket `Joke_effects`
Joke_dimensions (4)   → bucket `Joke_dimensions`
```

### `education_edition` — buckets por tipo

```
Minecraft_Education (149)            → bucket `Education_features`
MinecraftEdu_blocks (13)              → bucket `MinecraftEdu_blocks`
MinecraftEdu_items                    → bucket `MinecraftEdu_items`
Chemistry_Resource_Pack o cat sin     → bucket `Chemistry`
```

### `media_franchise` — buckets por medio

```
A_Minecraft_Movie* o title Movie:    → bucket `Movie`
Minecraft_Mini-Series*                → bucket `Mini_Series`
Books, Fiction, novels                → bucket `Books`
Comic_books                           → bucket `Comics`
Animated_content                      → bucket `Animated_shorts`
Live_action_content                   → bucket `Live_action`
Adventure_maps, Maps                  → bucket `Maps`
Game_trailers                         → bucket `Trailers`
Online_content, Editorials            → bucket `Online_content`
Minecraft:_*_chapters                 → bucket `Book_chapters`
```

### `real_world` — buckets por tipo

```
PERSONS_CATS (Actors, YouTubers, Streamers, Hosts, Players, Students):
                                      → bucket `People`
COMPANIES_CATS (Mojang_Studios, Microsoft, Companies):
                                      → bucket `Companies`
EVENTS_CATS (MINECON, Minecraft_Live, Events, Historical_events, Live_streams):
                                      → bucket `Events`
HISTORY_CATS (History, 10th/15th_Anniversary, MCC events):
                                      → bucket `History`
COMMUNITY_CATS (Community, Collaborations, Cross-franchise_promotions, Merchandise, Discontinued, Marketplace, Event_servers):
                                      → bucket `Community_business`
```

### `wiki_meta` — buckets internos

```
File: titles                          → bucket `Files`
Template: titles                      → bucket `Templates`
Help: titles                          → bucket `Help_pages`
Minecraft Wiki: titles                → bucket `Wiki_self_reference`
Soft_redirects                        → bucket `Redirects`
```

---

## Capa C — Reglas universales de jerarquía (when conflict)

Aplican DENTRO del ambiente cuando un artículo tiene múltiples cats que matchean buckets distintos:

1. **Cat más específica gana** sobre genérica:
   - `Animal_mobs` > `Mobs` > `Entities`
   - `Manufactured_blocks` > `Blocks`
   - `Joke_blocks` > `Blocks` (pero ya va a ambiente april_fools)

2. **Identidad fuerte antes que aspecto/mecánica**:
   - `Blocks` > `Combat` (Bed = block primary, mechanic es also_in)
   - `Items` > `Crafting`
   - `Plants` > `Items` (Beetroot Seeds = plant primary, item es also_in)

3. **Cat de origen antes que cat de uso**:
   - Bell tiene `Blocks` + `Redstone` → primary Block (porque es un bloque que tiene comportamiento redstone, no un componente redstone)
   - Redstone Dust tiene `Items` + `Redstone_mechanics` → primary `Redstone_mechanics` (es componente redstone que también es item)

4. **Multi-cat (Cake-style)**: `Blocks` + `Food` → primary `Blocks`, also_in `Food`

5. **Ore wins sobre Blocks**: artículo con cat `Ore` → bucket `Ore` (Ancient Debris, Coal Ore)

6. **`Removed_features`** + cat de tipo (Blocks/Items/Mobs/etc.) → primary cat de tipo, also_in `Removed_features`

7. **Multi-membership universal**: TODOS los aspectos secundarios entran como `also_in`. Ej: Cake → primary `Blocks`, also_in `[Items, Food, Manufactured_blocks, 10th_Anniversary]` (la fecha de aniversario aparece como also_in pero el artículo NO va a ambiente real_world).

---

## Sub-bucketing (jerárquico)

Para que el viewer no muestre 100 buckets sueltos, agrupar visualmente en super-cats por ambiente. Ejemplo en `game_vanilla`:

```
Mobs
  ├ Animal_mobs (47)
  ├ Hostile_mobs (43)
  ├ Passive_mobs (40)
  └ ... (todos los *_mobs específicos)
Blocks
  ├ Manufactured_blocks (370)
  ├ Natural_blocks (187)
  ├ Generated_structure_blocks (288)
  ├ Utility_blocks (131)
  └ Non-solid_blocks (122)
Items
  ├ Food (52)
  ├ Tools (41)
  ├ Weapons
  ├ Armor (34)
  └ Brewing_ingredients
Plants (102)
Ore (34)
Mechanics
  ├ Game_mechanics
  ├ Enchantments (46)
  ├ Effects (50)
  └ Status_effects
World
  ├ Biomes
  ├ Generated_structures
  ├ Generated_features (84)
  └ Environment (69)
Sound
  ├ Sounds
  └ Music (160)
...
```

El sidebar del viewer respeta esta jerarquía (super-cat colapsable → buckets dentro).

---

## Decisiones específicas (lecciones de auditoría a preservar)

| Caso | Decisión |
|---|---|
| Bell, Door, Lectern, Honey Block, Hopper, Piston, Observer | primary `Manufactured_blocks` (no `Redstone`); also_in incluye `Redstone` |
| Redstone Dust, Redstone Repeater, Redstone Lamp, Redstone Torch | primary `Redstone_mechanics` o el equivalente más específico; con title `Redstone X` también funciona |
| Cake | primary `Manufactured_blocks`; also_in `[Items, Food, 10th_Anniversary]` |
| Wheat, Carrot, Beetroot Seeds | primary `Plants`; also_in `[Items, Mob_food]` |
| Anvil | primary `Manufactured_blocks`; also_in `[Block_entities, Falling_blocks, Hazardous_blocks, Blocks_with_GUI]` |
| Ancient Debris | primary `Ore`; also_in `[Natural_blocks, Nether_blocks]` |
| 2×2 grid, Anvil mechanics, Cooking, Hitbox | primary `Game_mechanics` (gracias a fallback Gameplay/Combat/Crafting cats sin cats vanilla específicas) |
| Mod, Mods/Forge | primary `Tutorials` (ambiente `tutorial`) |
| Vu Bui, Emma Myers, GoodTimesWithScar, Agnes Larsson | primary `People` (ambiente `real_world`) |

---

## Cosas que se eliminan / consolidan

### Buckets inventados que desaparecen
- `block` (renombrado a `Blocks` o sub-buckets)
- `mechanic` (renombrado a `Game_mechanics`)
- `redstone` (renombrado a `Redstone_mechanics` o sub-buckets de redstone)
- `multi_concept` (ya muerto)
- `entity_other` (renombrado a `Entities` o `Block_entities`)
- `world_gen` (split en `Biomes`, `Generated_structures`, `Generated_features`)
- `cosmetic_event_tied` / `cosmetic_generic` (consolidado en `Capes`, `Skin_packs`, `Collaborations`, etc.)
- `mob` (renombrado a `Mobs` o sub-buckets)
- `plant` (renombrado a `Plants`)
- `ore` (renombrado a `Ore`)
- `crafting_recipe` (renombrado a `Crafting_recipes`)
- `structure_subpage` (renombrado a `Structure_subpages`)
- `list_reference` (renombrado a `Lists`)
- `game_mode` (renombrado a `Game_modes`)
- `personalities` (renombrado a `People`)
- `experiment` (renombrado a `Experimental`)
- `redstone_schema` (mantenido — es discardable, no cat real)
- `disambiguation_meta` (consolidado en `Achievement_disambiguation_pages` + `Version_disambiguation_pages`)

### Lenses inventadas que se vuelven cats:
- `light_source` → cat `Light_sources`
- `storage` → cat `Storage`
- `hazardous_block` → cat `Hazardous_blocks`
- `falling_block` → cat `Falling_blocks`
- `job_block` → cat `Job_blocks`
- `compacted_block` → cat `Compacted_blocks`
- `vehicle` → cat `Vehicles`
- `functional_block` → cat `Blocks_with_GUI`
- `mechanism` → cat `Mechanisms`
- `flammable_block` → cat `Flammable_blocks`
- `mob_food` → cat `Mob_food`
- `nether` → cat `Nether_blocks` + `Nether_mobs` + `The_Nether`
- `end` → cat `End_blocks` + `The_End`
- `overworld` → cat `Overworld_biomes`
- `slab` → cat `Slabs`
- `stair` → cat `Stairs`
- `wall` → cat `Walls`
- `block_natural` → cat `Natural_blocks`
- `block_crafted` → cat `Manufactured_blocks`
- `block_generated` → cat `Generated_structure_blocks`

**Resultado:** los nombres de buckets/lenses son IDÉNTICOS a los cats wiki. El LLM, cuando reciba prompts, ve nombres que reconoce.

---

## Lo que se mantiene tal cual

- Multi-membership architecture (primary + also_in)
- Filter de meta cats (139 cats hidden)
- External sources buckets (Wikipedia / Notch / YouTube)
- Toggle "+ meta cats" en viewer
- Sistema de flags + log de misclassifications
- Sub-types de Block como secondary lenses adicionales
- Date sort en posts de Notch
- Pre-fetch, keyboard nav, palette Cmd+K, etc.

---

## Plan de migración

### Paso 1: Preparación
- [ ] Felipe revisa este doc, marca dudas/cambios
- [ ] Diseñar tabla CSV: `cat_name, ambiente, bucket_primary, priority_tier`
- [ ] Validar que cubre todos los flags previos (130 hasta ahora)

### Paso 2: Implementación core
- [ ] Reescribir `scraper/explore_subgroups.py` con nueva arquitectura
- [ ] `primary_group(title, cats, text)` retorna `(ambiente, bucket)` en lugar de solo bucket
- [ ] `secondary_groups(...)` se simplifica — todos los cats semánticos no-primary van a also_in

### Paso 3: Viewer update
- [ ] `article_viewer.py` SUPER_CATEGORIES → mapeo nuevo: super-cat = ambiente, sub-buckets = cats
- [ ] Frontend respeta nueva jerarquía
- [ ] Verificar contra los 130 flags

### Paso 4: Auditoría
- [ ] Re-run + contrast con flags previos
- [ ] Felipe valida en viewer que no se perdió funcionalidad
- [ ] Documentar nuevos casos edge si emergen

### Paso 5: Cleanup
- [ ] Borrar código muerto (MECHANIC_TITLES, hardcoded lists que ya no aplican)
- [ ] Simplificar imports/tests

---

## Ventajas concretas

1. **Código ~70% más chico**: ~150 líneas de classifier en vez de ~500
2. **Sin hardcoded lists** salvo casos donde NO existe cat (spinoff prefix, /Structure suffix, etc.)
3. **Buckets que el LLM entiende**: en Fase 4 transformación, `"Manufactured_blocks"` es un dominio reconocible. `"block"` no significa nada particular para Qwen.
4. **Tutoriales NO contaminan game**: están en otro ambiente, no se mezclan
5. **Mantenible**: agregar bucket = agregar cat al mapeo. Hoy es escribir nueva regla en classifier.
6. **Coherente con dominio**: la wiki Minecraft es la verdad

## Riesgos

1. **Cats no son perfectas**: algunos artículos están mal cateados en wiki. Mitigación: el viewer ya tiene flag system para corregir.
2. **Más buckets visibles** (50+ vs 25 actuales): mitigación: jerarquía colapsable + filtro de search.
3. **Migración takes time**: ~4-5h código + revisión.

## Decisiones tomadas

- `Removed_features` → dentro de `game_vanilla` (contenido del juego, histórico)
- `Versions` → ambiente propio `versions` (diferente naturaleza)
- `technical_reference` → bucket dentro de `game_vanilla`, default discardable
- `cosmetic_*` → en `game_vanilla` por default; las event-tied (MINECON capes, Anniversary) tienen also_in `History`

## Diferido a Fase 2 (NO en este refactor)

**Thematic lenses NUESTROS** (lush_caves, deep_dark, dripstone_caves, mangrove_swamp, etc.) — Felipe pidió posponerlo:
- "Los biomas que mencioné son solo algunos de muchos"
- "Necesitamos fuente real de todos los biomas (no de la memoria de Claude)"
- "Necesitamos manera sistemática de detectar qué artículos pertenecen a qué bioma"

**Plan futuro:** scrape lista canónica de biomas desde minecraft.wiki → mapeo automático artículo→bioma. Fuera de scope de este refactor.
