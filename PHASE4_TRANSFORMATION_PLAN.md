# MineGPT — Phase 4 (Transformation) + Phase 5 (Q&A) Plan

> **Status (2026-05-02): TRANSFORM HALF DEPRECATED.**
> Decision 2026-04-27: Qwen body transformation abandoned for v1. Wiki body
> goes directly into training corpus after `scraper/hardening_v2.py`. Qwen
> reserved for Q&A only.
>
> See `QA_GENERATION_PLAN.md` for the Q&A pipeline (this doc's Q&A halves
> consolidated there).
>
> Sections 1-3 ("Filosofía", "Cost estimate", "Tabla por bucket") describe the
> transform path that no longer exists. Q&A philosophy + per-bucket Q&A types
> remain valid as historical record.
>
> Plan operacional para transformar artículos del wiki + generar Q&A pairs,
> con la arquitectura cat-driven (CLASSIFIER_REDESIGN.md) ya aplicada.
>
> Status original: planeación → SUPERSEDED.
> Fecha: 2026-04-26

---

## Filosofía

1. **Q&A se genera del texto PRE-transformación** (post-regex, pre-Qwen). El Qwen transform comprime y pierde detalle granular. Q&A necesita detalle.
2. **No todo se transforma.** Buckets reciben tratamiento distinto según su naturaleza (ver tabla abajo).
3. **Multi-membership = multi-transform.** Cada artículo se transforma **N veces, una por cada bucket donde aparece** (primary + also_in). Cada transform tiene un prompt distinto enfocado en el lente del bucket. Resultado: el LLM ve cada artículo desde N ángulos en training. Lo mismo para Q&A: cada bucket genera Q&A pairs específicas a su lente.
4. **Forma ideal del texto** = prosa estructurada con headers consistentes + key:value properties + densidad alta (no boilerplate).

## Cost estimate (Mac Mini overnight)

Con multi-transform habilitado:
- ~5,000 artículo-bucket combinations (5 buckets avg per artículo, 1,000 articles vanilla)
- Transform ~88s cada uno (qwen3:8b, prompt 1K + output 1.5K tokens, ~17 tok/s)
- **~123 horas** total transform = ~5 días overnight

Q&A:
- ~50,000 Q&A pairs (10 avg per artículo-bucket)
- **~25-40 horas** total Q&A

**Total Mac Mini hours: ~150-160h = ~6-7 días** distribuidos entre overnight runs. Aceptable para v1.

Optimizaciones posibles:
- Skip lentes `also_in` que sean "padre" del primary (e.g. si primary es `Manufactured_blocks`, no transformar también como `Blocks`)
- Skip lentes con menos de N artículos en el bucket (no vale la pena prompt especializado)
- Batch Q&A en una sola call por artículo (genera 10 pairs en una llamada en vez de 10 llamadas)

---

## Tabla maestra: qué hacer con cada ambiente / bucket

### `game_vanilla`

| Bucket | Word tier | Qué hacer | Output |
|---|---|---|---|
| `Manufactured_blocks`, `Natural_blocks`, `Generated_structure_blocks` (290+187+19) | 500+w | **Transform full** | Block format estandarizado |
| `Manufactured_blocks` etc. | 100-499w | **Solo regex** + flag para Q&A | Texto limpio sin Qwen |
| `Manufactured_blocks` etc. | 10-99w | **Filter manual** (descartar stubs) | Subset que pase audit |
| `Items`, `Tools`, `Weapons`, `Armor`, `Food`, `Potions`, `Music_Discs` (480) | 500+w | **Transform full** | Item format |
| `Animal_mobs`, `Hostile_mobs`, `Monster_mobs`, `Passive_mobs`, etc. (~120) | todos | **Transform full** | Mob format con stats |
| `Plants` (98) | todos | **Transform full** (formato plant) | Plant format con growth/biome |
| `Ore` (26) | todos | **Transform full** | Ore format |
| `Redstone_mechanics` (5) + Redstone components dispersos | todos | **Transform full** | Redstone component format |
| `Game_mechanics`, `Effects`, `Status_effects`, `Enchantments` | todos | **Transform full** | Mechanic format |
| `Biomes`, `Overworld_biomes`, `Nether_biomes`, `End_biomes`, `Generated_structures`, `Generated_features`, `Environment` | todos | **Transform full** | World format |
| `Sounds`, `Music` | todos | **Skip** (solo metadata) | — |
| `Disambiguation_pages` (548) | todos | **NO transform → Q&A directo** | Q&A pairs |
| `Achievement_disambiguation_pages` (41), `Set_index_pages` (96), `Version_disambiguation_pages` (4) | todos | **Skip** o Q&A simple | — |
| `Removed_features` (290) | 500+w | **Transform** + flag historical | Historical feature format |
| `Commands` (103) | todos | **Transform (normalize)** | Command format con syntax |
| `Crafting_recipes` (16) virtual | — | **Extract as JSON structured** (RAG-ready) | JSON receta |
| `Structure_subpages` (33) | — | **Filter empty + transform contenido útil** | Texto + block layers description |
| `Lists` (11) | — | **NO transform → Q&A directo** | Q&A pairs |
| `Block_states_reference` (28), `Java_Edition_technical` (213) | — | **Skip** (out of v1) | — |
| `Game_modes` (7), `Menu_screens` (UI) | — | **Solo regex** | Texto limpio |
| `Cosmetic` (Skin_packs, Capes, Texture_packs) | — | **Skip** o **Solo regex** | — |
| `Other` (212), `Mechanic_history`, etc. | — | **Audit manual primero** | Decidir caso por caso |

### `tutorial`

| Bucket | Qué hacer | Output |
|---|---|---|
| `Tutorials` (419), `Java_Edition_guides`, `Bedrock_Edition_guides` | **Solo regex clean** | Mantener formato instructivo |
| `Redstone_tutorials` (11) | **Solo regex clean** | Conceptos generales redstone |
| `Software_tutorials` (30) | **Skip** o **Solo regex** | — |

### `versions`

| Bucket | Qué hacer | Output |
|---|---|---|
| `Bedrock_Edition_versions` (408), `Java_Edition_versions` (190), `Pocket_Edition_versions` etc. | **Transform extract player-facing** | Lista de cambios sin protocol |
| `Lost_versions` (293) | **Skip** | — |
| `Launcher_versions` (399) | **Skip** | — |
| `Versions` (180), `Versions_with_unofficial_names`, etc. | **Audit primero** | — |

### `real_world`

| Bucket | Qué hacer | Output |
|---|---|---|
| `People` (142) | **Solo regex clean** | Bio cortas tal cual |
| `Companies` (34), `Events` (44), `History` (55), `Community_business` (109) | **Solo regex clean** | — |

### `media_franchise`

| Bucket | Qué hacer | Output |
|---|---|---|
| `Books` (172), `Comics`, `Animated_shorts` (78), `Live_action`, `Maps`, `Trailers`, `Online_content`, `A_Minecraft_Movie` (87), `Mini_Series` | **Audit + decide v1 inclusion** | — |
| `Book_chapters` (124) | **Skip o include narrative samples** | — |

### Out-of-v1 ambientes (no transform)

- `spinoff`, `april_fools`, `education_edition`, `wiki_meta` — todos **skip** del training v1.

### `external_*`

- `external_wikipedia` (15 bios), `external_notch_blog` (294 posts), `external_youtube` (4 transcripts) — **NO transform**. Ya están en formato útil. Solo regex tumblr cleanup ya hecho. Pasar directos al training.

---

## Forma target del texto transformado (prompts por bucket)

### Bloques (`Manufactured_blocks`, `Natural_blocks`, etc.)

```markdown
# {Block name}

## Overview
{1-2 sentence description: what it is, where it appears.}

## Properties
Type: {block type}
Hardness: {value}
Blast resistance: {value}
Tool: {best tool, or "any" or "none"}
Mineable with: {required tier or "anything"}
Renewable: {Yes/No}
Stackable: {Yes (64) / No}
Flammable: {Yes/No}
Light level: {0-15}
Light filter: {value, if any}

## Details
{Mechanics, interactions, drops, special behaviors. Prose.}

## Obtaining
{How to obtain. Recipe if crafted, or biomes/structures if natural.}

## Trivia
{Optional, only if relevant lore/history.}
```

### Items (`Items`, `Tools`, `Weapons`, `Armor`, `Food`)

```markdown
# {Item name}

## Overview
{Description.}

## Properties
Type: {Tool, Weapon, Armor, Food, Material, ...}
Stack: {1, 16, 64}
Renewable: {Yes/No}
{Tool-specific: Damage / Tier / Durability / Mining speed / Enchantability}
{Food-specific: Hunger restored / Saturation}
{Armor-specific: Defense / Toughness}

## Details
{Mechanics, uses, special interactions.}

## Obtaining
{Crafting recipe / drops / trades / chest loot.}
```

### Mobs (`Animal_mobs`, `Hostile_mobs`, etc.)

```markdown
# {Mob name}

## Overview
{Description.}

## Stats
Health: {value}
Damage: {value, attack pattern}
Speed: {Walking / Swimming / Flying speeds}
Spawn: {Biomes, structures, light conditions}
Behavior: {Passive / Hostile / Neutral / Boss}

## Drops
{What it drops. XP. Rare drops. With Looting modifier.}

## Behavior
{AI patterns, special abilities, interactions with other entities.}

## Trivia
{Optional.}
```

### Plants (`Plants`)

```markdown
# {Plant name}

## Overview
{Description.}

## Properties
Renewable: Yes
Growth stages: {N}
Light requirement: {min level}
Soil: {Dirt / Farmland / Sand / etc.}
Biomes: {where it generates}

## Mechanics
{Growth speed, water proximity, fertilizer, harvest.}

## Drops
{What it drops when broken. Bonemeal effect.}
```

### Mechanics (`Game_mechanics`, `Effects`, etc.)

```markdown
# {Mechanic name}

## Overview
{What it is.}

## How it works
{Explanation, in prose. Step by step if applicable.}

## Examples
{Practical examples.}

## Trivia
{Edge cases, history.}
```

### Commands (`Commands`)

```markdown
# Command: /{command}

## Syntax
/{command} {args}

## Edition support
Java Edition: Yes/No (since v...)
Bedrock Edition: Yes/No (since v...)

## Permission level
{0-4}

## Description
{What it does.}

## Arguments
{arg1}: {description, type}
{arg2}: {description, type}

## Examples
/example1
/example2
```

---

## Q&A generation: tipos de preguntas por bucket

### Vanilla blocks/items
- Factuales: "¿Cuánta dureza tiene Stone?"
- Mecánicas: "¿Qué herramienta minera Diamond Ore?"
- Ubicación: "¿Dónde aparece Ancient Debris?"
- Recipes: "¿Cómo se hace Iron Pickaxe?"
- Drops: "¿Qué dropea Wool al romperse sin shears?"
- Comparativas: "¿Diferencia entre Coal Ore y Deepslate Coal Ore?"

### Mobs
- Stats: "¿Cuánta vida tiene Creeper?"
- Damage: "¿Cuánto daño hace Skeleton con arrow?"
- Behavior: "¿Qué teme un Creeper?"
- Drops: "¿Qué dropea Spider al morir?"
- Spawn: "¿Dónde spawnea Enderman?"
- Mechanics: "¿Qué pasa si un Creeper es alcanzado por rayo?"

### Plants
- Growth: "¿En qué soil crece Wheat?"
- Drops: "¿Qué obtienes al romper Bamboo?"
- Mechanics: "¿Qué acelera el crecimiento de Sugar Cane?"

### Mechanics
- Conceptual: "¿Cómo funciona el sistema de hambre?"
- Procedural: "¿Cómo se aplica Bane of Arthropods?"

### Disambiguations (Q&A directo, sin transform)
- Listing: "¿Qué tipos de Sand existen?"
- Diferenciación: "¿Cuál es la diferencia entre Sand y Soul Sand?"

### Cross-bucket (multi-membership)
Para Bell (primary `Generated_structure_blocks`, also_in `[Redstone, Mechanisms, Block_entities, Utility_blocks]`):
- Como block: "¿Cuál es la dureza de Bell?"
- Como redstone: "¿Cómo se activa una Bell con redstone?"
- Como mechanism: "¿Qué efecto tiene una Bell en mobs cercanos?"
- Como block_entity: "¿Qué data NBT tiene Bell?"

Resultado: cada artículo genera **5-20 Q&A pairs** según riqueza, distribuidos entre tipos.

---

## Manual curation layer (added 2026-04-26 per Felipe's request)

Por más bueno que sea el classifier, dentro del contexto de un bucket el ojo humano detecta artículos que NO valen la pena transformar/Q&A. Necesitamos poder excluirlos manualmente, persistir la decisión, y visualizarla.

### Data model (nuevo)

**Estado por artículo** (persisted en `raw_data/_pipeline_state/article_exclusions.jsonl`, append-only):
```json
{
  "title": "Pig",
  "excluded_from_transform": false,
  "excluded_from_qa": false,
  "exclude_reason": null,
  "exclude_in_bucket": null,
  "exclude_timestamp": null
}
```

**Estado por bucket** (persisted en `raw_data/_pipeline_state/bucket_status.json`):
```json
{
  "Animal_mobs": {
    "transform_status": "completed",        // pending | running | completed | skipped
    "qa_status": "pending",
    "transform_run_id": "run_2026-04-27_abc",
    "qa_run_id": null,
    "transform_completed_at": "2026-04-27T03:15:22",
    "qa_completed_at": null,
    "transform_excluded_count": 2,
    "qa_excluded_count": 0
  }
}
```

### UI: mini-viewer integrado en Prompt Lab tab

Layout completo en una sola tab:

```
┌──────────────────────────────────────────────────────────┐
│ PROMPT LAB                                                │
├──────────────────────────────────────────────────────────┤
│ Bucket: [Animal_mobs ▾]  47 + 9 also_in                   │
│   Transform: ⏳ pending          [Mark done]              │
│   Q&A:       ⏳ pending          [Mark done]              │
│                                                           │
│ Mode: ⚫ Test 5  ⚪ Test 20  ⚪ Full (45 incl, 2 excl)    │
│ Prompt: [editor]                                          │
│ [▶ Run test]   [▶ Run full]                              │
├──────────────────────────────────────────────────────────┤
│ ARTICLE PREVIEW (scope: this bucket)                      │
│  Sort: [A-Z ▾]   Filter: [____]   Show: [all ▾]          │
│                                                           │
│  ▼ Cow (3,776w)              T ✓  Q&A ✓  [exclude...]    │
│    [text inline con scroll]                               │
│    [also_in: Passive_mobs]                                │
│                                                           │
│  ▶ Pig (1,200w)              T ✓  Q&A ✓                  │
│  ▶ Chicken (800w)            T ✗  Q&A ✓  ← excluded T    │
│      "short article, regex enough"                        │
│  ...                                                      │
├──────────────────────────────────────────────────────────┤
│ LIVE FEED / progress / errors                             │
└──────────────────────────────────────────────────────────┘
```

**Capabilities:**
- Click row → expandir text inline (no salir del tab)
- Per-artículo: exclude from transform / exclude from Q&A / exclude both / unexclude
- Filter dropdown: all / included / excluded from T / excluded from Q&A / primary only / with also_in
- Mode counts respetan exclusiones: "Full (45 included, 2 excluded)"
- Run respeta exclusiones automáticamente

### Articles tab updates (status badges)

Sidebar bucket rows muestran status:
```
▼ Animal_mobs        47   T ✓  Q&A ⏳
▼ Hostile_mobs       38   T ✓  Q&A ✓
▼ Manufactured_blocks 290 T ⏳ Q&A ⚪
▼ Plants             98   T ⚪ Q&A ⚪
```

Símbolos: `✓ done` `⏳ running` `⚪ pending` `✗ skipped`

Super-cats agregadas:
```
Vanilla game (12/142 buckets transformed, 8/142 Q&A done)
```

Lista col 2: artículos excluidos atenuados + tag "excluded from T" o "excluded from Q&A".

### Backend endpoints nuevos

```
POST /api/articles/exclude         — { title, from_transform, from_qa, reason }
POST /api/articles/include         — undo de exclude
GET  /api/articles/exclusions      — { bucket } → list
GET  /api/buckets/status           — todos los buckets con su status
POST /api/buckets/status           — actualizar (auto al terminar run)
GET  /api/buckets/<bucket>/articles — articles del bucket con included/excluded flags
```

### Effort estimado

- Data persistence layer (read/write JSONL/JSON): ~2h
- Backend endpoints (exclude/include/status): ~2h
- Prompt Lab merge + mini-viewer integrado: ~4-6h
- Articles tab status badges + sidebar updates: ~2h
- End-to-end testing: ~1-2h

**Total: ~12-15h** — setup correcto antes de cualquier transform real.

---

## Tooling redesign — merge Prompt Lab + Production

### Status actual

- **Prompt Lab tab**: testset chico (~84 items hardcoded), iteración de prompts
- **Production tab**: corrida full sobre dataset, controles separados
- **Articles tab**: viewer (lo nuevo)

Felipe quiere **unificar Prompt Lab + Production** en un solo tab:

### Diseño nuevo

```
┌─────────────────────────────────────────────────────────────┐
│ PROMPT LAB (unified)                                        │
├─────────────────────────────────────────────────────────────┤
│ ─────────────── TASK DEFINITION ────────────                 │
│ Bucket:  [Animal_mobs ▾]  47 primary + 9 also_in             │ ← search/picker dropdown
│ Mode:                                                        │
│   ⚪ Test — 5 random items     (validate prompt)            │
│   ⚪ Test — 20 random items    (broader validation)          │
│   ⚪ Sample — 50 first by sort                              │
│   ⚫ Full bucket — 47 items    (production run)             │
│   ⚪ Full + secondaries — 56 items (multi-membership)       │
│                                                              │
│ Prompt template: [editor 20 lines]                           │
│ Model: qwen3:14b ▾                                           │
│ Params: num_ctx=4096  temperature=0.1  no_think=on          │
│                                                              │
│ [▶ Run test]   [▶ Run full overnight]                       │
├─────────────────────────────────────────────────────────────┤
│ ─────────────── LIVE FEED ──────────────                     │
│ Progress: 12/47  ETA: 18 min                                 │
│ Errors: 0 timeouts, 0 unparseable                            │
│ Mac Mini stats: RAM 8.1G/16G, CPU 78%, thermal nominal       │
│                                                              │
│ [feed table or detail view, like current Production tab]     │
│                                                              │
│ [⏸ Pause] [▶ Resume] [■ Cancel]                             │
├─────────────────────────────────────────────────────────────┤
│ ─────────────── HISTORY ────────────                         │
│ - Animal_mobs (full, 47 items, 95% acc, 25min)  [load prompt]│
│ - Animal_mobs (test, 20 items, 90% acc, 10min)  [load prompt]│
│ - Hostile_mobs (full, 38 items, ...)            [load prompt]│
│ ...                                                          │
└─────────────────────────────────────────────────────────────┘
```

### Cambios técnicos

1. **Backend**: 
   - Reemplazar `TASK_CONFIG` hardcoded con dynamic bucket selection (vía `/api/articles/groups`)
   - Endpoint `/api/run` recibe `bucket` + `mode` (test_5, test_20, sample_50, full, full_secondaries)
   - Resume/checkpoint per bucket (no per-task)
   - History persiste por (bucket, mode, prompt_hash, timestamp)

2. **Frontend**:
   - Eliminar tabs separados Lab/Production
   - Combinar en uno solo "Prompt Lab"
   - Bucket picker (search + autocomplete)
   - Mode radio buttons
   - Test runs aparecen en mismo feed que production
   - History timeline unificado

3. **UX**:
   - Test run: 30 segundos a 5 min
   - Full run: 30 min a varias horas
   - Overnight runs: igual al full pero con notificación al terminar

---

## Implementation workflow (UX audits required)

Felipe explicitamente pidió replicar el pattern que funcionó con el viewer original:

### Antes de codear cualquier UI:

1. **Audit del estado actual** del Prompt Lab tab + Production tab + Articles tab usando:
   - Skill `/ui-ux-pro-max` — review de layout, density, design system consistency
   - Skill `/ux-designer` — review de mental model, error recovery, learnability vs efficiency
2. **Planeación detallada** del merge UI + mini-viewer + status badges, incorporando feedback de los audits
3. Documentar diseño final antes de codear

### Después de implementar:

4. **Audit final** con ambas skills sobre la UI implementada
5. Aplicar correcciones

### Por qué este flujo

Lo usamos para construir el Articles viewer y atrapó issues importantes (Tab key conflict, missing cheat sheet, no URL state, color-only pill states, responsive collapse, perf for long articles, etc.) ANTES de codear. Replicar para el merged Prompt Lab.

---

## Plan de implementación (próximo chat)

### Fase 4.0 — Tooling unificado + manual curation layer (~14-17h)

**A. Pre-implementation audit + planning (~1-2h)**
- Audit del estado actual con `/ui-ux-pro-max` skill
- Audit con `/ux-designer` skill
- Sintetizar feedback en design final
- Documentar antes de codear

**B. Implementation (~12-14h)**
1. **Data model + storage** (~2h):
   - `raw_data/_pipeline_state/article_exclusions.jsonl` (append-only)
   - `raw_data/_pipeline_state/bucket_status.json`
2. **Backend endpoints** (~2h):
   - exclude/include articles
   - bucket status read/update
3. **Prompt Lab merge + mini-viewer** (~5h):
   - Bucket picker dinámico
   - Mode radio (test_5 / test_20 / sample / full / full_secondaries)
   - Article list inline con expand/exclude
   - Show filter dropdown
4. **Articles tab status badges** (~2h):
   - T ✓ / Q&A ✓ por bucket
   - Super-cat aggregated counts
   - Excluded articles atenuados en lista
5. **Resume + history unificado** (~1-2h)

**C. Post-implementation audit + fixes (~1-2h)**
- Audit final con `/ui-ux-pro-max` skill
- Audit final con `/ux-designer` skill
- Aplicar correcciones
- Verificar accessibility, keyboard nav, contrast

**D. End-to-end test** con bucket pilot (~30min)

### Fase 4.1 — Validar tooling con bucket chico (30 min)
- Bucket pilot: **Crafting_recipes** (16 arts, formato regular, fácil de validar)
- O alternativa: **Animal_mobs** (47 arts, vanilla core, más representativo)
- Iterar prompt con test_5, después test_20, después full
- Validar pipeline completo

### Fase 4.2 — Transform por bucket (orden recomendado)
**Orden por riesgo creciente:**
1. **Crafting_recipes** (16) — extract structured JSON, no Qwen prose
2. **Commands** (103) — normalize format (1-2h Mac Mini)
3. **Animal_mobs** (47), **Hostile_mobs** (38) — vanilla mob core (~3h cada uno)
4. **Plants** (98) — vanilla plant core
5. **Ore** (26) — chico pero importante
6. **Manufactured_blocks** (290) — el grande, ~3 días overnight
7. **Items, Tools, Weapons, Armor, Food** — items vanilla
8. **Game_mechanics, Effects, Enchantments** — mechanics
9. **Generated_structures, Biomes, Environment** — world
10. **Versions** (extract player-facing) — opcional v1
11. **Removed_features** (290) — histórico

### Fase 5 — Q&A generation (de pre-transformación)
Mismo tooling, prompt de Q&A en lugar de transform. Por bucket:
1. **Disambiguations** (548) — Q&A directo, no requiere transform
2. **Vanilla 500+w** — Q&A de pre-transform después de validar transform
3. **Vanilla 100-499w** — Q&A más simple

---

## Decisiones a confirmar antes de empezar

1. ¿Empezamos con Crafting_recipes (16) o Animal_mobs (47) como pilot? Mi voto: **Animal_mobs** (más representativo del flujo target).
2. ¿Q&A en paralelo a transformación o secuencial? Mi voto: **paralelo** (cada bucket transformado dispara su Q&A run del original).
3. ¿`also_in` se transforma también? Mi voto: **No en v1**. Cada artículo se transforma una vez con prompt de su bucket primary. Los `also_in` solo informan al prompt del primary que el artículo "también es X". Q&A SÍ se beneficia de also_in para variar tipos de pregunta.
4. ¿Mantener buckets `Other` (212), `Mechanic_history`, `Lego` (3), etc.? Mi voto: **audit primero, decidir después.**

---

## Lo que esto significa para el chat actual

Tenemos suficiente contexto guardado entre:
- `CLASSIFIER_REDESIGN.md` (taxonomía cat-driven)
- `WIKI_DATA_CLEANING.md` (plan original Phase 1+2 hecho, Phase 3 spinoffs pospuesto)
- Este doc (Phase 4 + 5 + tooling redesign)
- Memoria del proyecto (`project_minegpt.md`, `project_classifier_notes.md`, `reference_external_sources.md`, `feedback_specialize_subgroups.md`)
- Auditoría de 130 flags en `misclassifications.jsonl`

**Próximo chat empieza con:** "Implementemos el tooling unificado y arrancamos con bucket pilot {Animal_mobs/Crafting_recipes}." Yo voy a leer estos docs para retomar contexto.
