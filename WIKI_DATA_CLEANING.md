# MineGPT — Wiki Data Cleaning & Transformation Plan

> **Status (2026-05-02): heavily superseded by hardening v2.**
> Phases 1-2 (filter, regex_clean) sections below are still accurate.
> Phase 3 (spin-off classification) postponed for v2 (M4 hardware).
> Phases 4b-4e (Qwen body transformation) are **DEPRECATED** — wiki body
> goes directly into corpus after `scraper/hardening_v2.py`. Qwen reserved for Q&A.
> See `HARDENING_V2_RESULTS.md` for the actual current state, and
> `QA_GENERATION_PLAN.md` for the Q&A pipeline that replaces transformation.
>
> Final dataset: 7,135 main + 2,834 qa_direct + 174 dropped (~7.62M words),
> not the ~6-7.3M figure estimated in the original plan below.
>
> Última actualización: 2026-04-07 (banner agregado 2026-05-02)

---

## Progreso

### Fase 1: Filtro por reglas (sin LLM) — COMPLETADA 2026-04-23
- [x] Implementar `scraper/filter.py`
- [x] Ejecutar filtro sobre articles.jsonl y changelogs.jsonl
- [x] Verificar: 3,754 artículos removidos (esperado ~3,537, +217 adicionales de asset_history + template_page + meta_wiki_page agregados durante diseño)
- [x] Auditar `articles_removed.jsonl` — samplear 30 confirmó que son basura legítima

**Resultados fase 1:**
- Articles: 13,897 → 10,143 kept (27% removed, 2.68M palabras removidas)
- Changelogs: 1,271 → 1,270 kept (solo el de Lua error removido)
- Razones: render_history (1,755), texture_history (1,265), structure_blueprint (365), version_disambiguation (114), empty_or_tiny (106), asset_history (60), meta_wiki_page (34), template_page (24), category_page (11), debug_mode (10), user_page (7), structure_renders (3)

### Fase 2: Limpieza con regex — COMPLETADA 2026-04-23
- [x] Implementar `scraper/regex_clean.py` con 9 pasos de transformación en orden descubierto por los agentes
- [x] Ejecutar sobre articles_filtered.jsonl + changelogs_filtered.jsonl
- [x] Verificar: samplear 15 artículos flagged (top, mid, low loss ratio), todos legítimos
- [x] Verificar: cite artifacts como `ArmorItems[3]` protegidos con `(?<![A-Za-z0-9_\]])\[(\d+)\](?!\w)`
- [x] Idempotence check: correr clean_text sobre output no cambia nada (20 samples)

**Resultados fase 2:**
- Articles: 9.7M → 9.27M palabras (4.5% loss, dentro del rango esperado 2-8%)
- Changelogs: 2.19M → 2.04M palabras (6.84% loss)
- Flagged (>30% loss): 1,572 articles + 383 changelogs — todos son casos legítimos (changelogs cortos del launcher/Education, artículos que eran mayormente boilerplate)
- Empty after cleanup: 0

**Bugs detectados y corregidos durante implementación:**
1. Disambiguation markers: scraper usa "same **version number**" no solo "same **title**"
2. Idempotencia rota por orden de operaciones (`\n\n\n` residuales al aplicar rstrip después de colapsar newlines)
3. `Old file name` header strippeaba content tables en "Resource pack changes" pages → limite strip a primeras 30 líneas del changelog

**Outputs en `raw_data/wiki/`:**
- `articles_cleaned.jsonl` / `changelogs_cleaned.jsonl` — inputs para Qwen
- `articles_removed.jsonl` / `changelogs_removed.jsonl` — audit con `removal_reason`
- `clean_diffs.jsonl` — top 100 diffs por word-loss ratio
- `clean_flagged.jsonl` — >30% loss con text_before/after_head para review manual
- `filter_report.json` + `clean_report.json` — stats + SHA256 de inputs

### Fase 4a: Pruebas de prompts — COMPLETADA 2026-04-24 (spinoff classifier)
- [x] Construir Prompt Lab UI (FastAPI + HTML/Tailwind/Alpine.js) en `scraper/prompt_lab/`
- [x] Seleccionar 84 artículos representativos (50 originales + 15 edge cases + 19 unseen validation)
- [x] Iterar prompt de clasificación a través de 5+ iteraciones
- [x] Testear qwen3:8b (98.8% accuracy), qwen3:4b (descartado: timeouts), qwen3:14b (95.2%, mejor razonamiento)
- [x] Verificar M2 no paraleliza (Metal limitation, OLLAMA_NUM_PARALLEL no da speedup real)
- [x] Agregar Flash Attention (OLLAMA_FLASH_ATTENTION=1)
- [x] Cláusulas refinadas: "appearing ≠ relevant", "loot vs plot devices", "named character in flavor text trap"
- [ ] Prompt para changelogs — probar con 10 changelogs variados
- [ ] Prompt para commands — probar con 10 commands variados
- [ ] Prompt para clasificar shorts — probar con 10 shorts variados
- [ ] Prompt para transformar artículos core — probar con 10 artículos variados
- [ ] Prompt para generar Q&A

**Prompt Lab UI** (`scraper/prompt_lab/`):
- `server.py`: FastAPI backend con endpoints de test + producción (start/pause/resume/cancel/events/status/feed/history)
- `static/index.html`: UI con tabs Prompt Lab + Production dashboard (live feed, Mac Mini stats, ETA, distribution)
- `ollama_client.py`: wrapper Ollama con timeout 240s
- `testsets/spinoff_classifier.jsonl`: 84 items curados (41 KEEP / 43 DISCARD)
- Resume capability: si la corrida se interrumpe, continúa donde se quedó
- DISCARDs se guardan separado para audit en `spinoffs_classified_discarded.jsonl`
- Métricas persistidas cada 10 items en `history/prod_metrics_{job_id}.jsonl`

**Benchmarks realizados (Mac Mini M2 16GB):**
- qwen3:8b Q4_K_M: ~17 tok/s, ~27s/item, 98.8% accuracy en testset 84 items
- qwen3:14b Q4_K_M: ~10 tok/s, ~54s/item, 95.2% accuracy (mejor razonamiento pero más estricto)
- qwen3:4b Q4_K_M: ~30 tok/s pero timeouts y UNPARSEABLE en edge cases, descartado
- OLLAMA_NUM_PARALLEL: no da speedup real en producción (Metal es single-stream)
- OLLAMA_FLASH_ATTENTION=1: habilitado para mejora marginal

### Fase 3: Clasificación de spin-offs — POSPUESTA (decisión 2026-04-25)

**Decisión: posponer spin-offs para iteración v2 del LLM.**

Después de 2 días de iteración intensiva (5+ versiones de prompt, 3 modelos testeados, 2 corridas de producción completas, 4 audits con agentes), concluimos que incluir spin-offs en v1 del LLM no es viable:

1. **Problema de clasificación irresoluble con modelos locales:**
   - qwen3:14b (9.3GB): demasiado estricto, 94% accuracy. Descarta overviews de juego y narrativa con stats. Razón: ve stats → dice DISCARD, ignora contexto narrativo.
   - qwen3:8b (5.2GB): demasiado permisivo, 463/1723 KEEP (27%). Keepea enchantments específicos, mobs genéricos, versions. 
   - Ninguno logró el punto medio (~150-200 KEEPs, ~10%).
   - El prompt se refinó 5+ veces pero el trade-off strict/permissive es inherente al tamaño del modelo.

2. **Riesgo de confusión vanilla/spin-off:**
   - Un LLM de 125M params no tiene capacidad para distinguir "espada en Dungeons" de "espada en vanilla" si ambas están en el training data.
   - Incluso con clasificación perfecta, la transformación posterior sería otro proyecto entero.

3. **Costo de oportunidad:**
   - 2 días de iteración consumidos sin resultado productivo.
   - El dataset vanilla (9,267 artículos + 1,270 changelogs = ~11.3M palabras) es suficiente para v1.

**Plan para v2 (Mac Mini M4 24GB, junio-julio 2026):**
- Modelo más grande (350-750M params) que maneje la distinción vanilla/spin-off
- Qwen más grande (30B+) para transformación con mejor calidad
- Dataset de spin-offs ya scrapeado y limpiado (fases 1+2) — listo para usar
- Archivo de referencia: `spinoffs_classified_8b_final.jsonl` (1,723 items, 463 KEEP / 1,260 DISCARD)

**Corridas de producción realizadas:**
- Run 1 (14b): 389/1723 items, 68 KEEP / 321 DISCARD. Audit encontró 14 overviews + 7 narrativos wrongly discarded, 7 skins wrongly kept.
- Run 2 (8b, prompt condensado): 1723/1723 completo. 463 KEEP / 1260 DISCARD. Audit encontró ~50+ false positives (enchantments, mobs genéricos, versions), 5 overviews + 3 narrativos aún wrongly discarded.

**Infraestructura construida (reutilizable para fases 4-5):**
- Prompt Lab UI con Production dashboard corre en Mac Mini via tmux
- SSH tunnel automático, resume capability, retry en connection errors
- Mac Mini stats monitoring (RAM, CPU, Swap, Thermal)
- DISCARDs se loggean separado para audit

- [ ] Prompt para changelogs — probar con 10 changelogs variados
- [ ] Prompt para commands — probar con 10 commands variados
- [ ] Prompt para clasificar shorts — probar con 10 shorts variados
- [ ] Prompt para transformar artículos core — probar con 10 artículos variados
- [ ] Prompt para generar Q&A
- [ ] Guardar todos los prompts finales en `scraper/prompts/`

### Fase 4b: Transformar changelogs (Qwen)
- [ ] Implementar `scraper/transform_changelogs.py` con resume
- [ ] Ejecutar en Mac Mini (~15-25h)
- [ ] Verificar: comparar 10 changelogs originales vs transformados side-by-side

### Fase 4c: Normalizar commands (Qwen)
- [ ] Implementar `scraper/transform_commands.py` con resume
- [ ] Ejecutar en Mac Mini (~2-3h)
- [ ] Verificar: samplear 10 commands normalizados

### Fase 4d: Clasificar artículos cortos (Qwen)
- [ ] Implementar `scraper/classify_shorts.py` con resume
- [ ] Ejecutar en Mac Mini (~7-10h)
- [ ] Verificar: auditar clasificaciones (~30 samples)

### Fase 4e: Transformar artículos core 500+w (Qwen)
- [ ] Implementar `scraper/transform_articles.py` con resume
- [ ] Ejecutar en Mac Mini (~79h / ~3.3 días)
- [ ] Verificar: comparar 20 artículos originales vs transformados
- [ ] Re-procesar artículos que fallaron

### Fase 5a: Q&A tier 1 — artículos 500+w
- [ ] Implementar `scraper/generate_qa.py` con resume
- [ ] Probar prompt de Q&A con 10 artículos variados
- [ ] Guardar prompt en `scraper/prompts/generate_qa.txt`
- [ ] Ejecutar en Mac Mini (~50-80h)
- [ ] Verificar: auditar 50 Q&A pairs por calidad y alucinaciones

### Fase 5b: Q&A tier 2 — artículos 100-499w
- [ ] Ejecutar con mismo script/prompt (~30-45h)
- [ ] Verificar: auditar 30 Q&A pairs

### Fase 5c: Q&A disambiguations
- [ ] Implementar `scraper/generate_qa_disambiguations.py`
- [ ] Probar prompt con 10 disambiguations variadas
- [ ] Ejecutar en Mac Mini (~10-15h)
- [ ] Verificar: auditar 20 Q&A pairs

### Post-pipeline
- [ ] Consolidar todo en dataset final
- [ ] Contar estadísticas finales (artículos, palabras, Q&A pairs)
- [ ] **Evaluar arquitectura del modelo**: con el dataset final definido, calcular tokens totales y decidir tamaño óptimo. Config actual (23M params, 6 layers, 512 dim) es demasiado pequeña. La Mac Mini M2 16GB aguanta hasta ~350M params para training. Recomendación tentativa: 125-200M params (12 layers, 768 dim, 3072 ff, 12 heads, 1024 ctx, 16K vocab). Ratio ideal: ~20 tokens/param (Chinchilla). Con ~170M tokens estimados → ~8.5M óptimo por Chinchilla, pero con curriculum learning + oversampling, 125M es stretch razonable. Documentar decisión en `utils/config.py`.
- [ ] Actualizar `data/mixer.py` con nuevos archivos
- [ ] Entrenar tokenizer con dataset limpio

---

## Estado del dataset crudo

| Archivo | Ubicación (Mac Mini) | Registros | Palabras |
|---------|----------------------|-----------|----------|
| articles.jsonl | `/Users/felipe/minegpt/raw_data/wiki/articles.jsonl` | 13,897 | 12,387,230 |
| changelogs.jsonl | `/Users/felipe/minegpt/raw_data/wiki/changelogs.jsonl` | 1,271 | 2,192,331 |

Cada registro es JSON con keys: `title`, `text`, `categories`, `sounds`, `word_count`, `scraped_at`.

### Distribución por categoría (datos reales contados 2026-04-07)

| Categoría | Artículos | Palabras | Acción |
|-----------|-----------|----------|--------|
| **Core Minecraft 500+w** | 3,779 | 7,849,464 | Transformar con Qwen |
| **Core Minecraft 100-499w** | 3,638 | 900,376 | Solo regex clean |
| **Core Minecraft 50-99w** | 861 | 64,782 | Clasificar con Qwen (keep/discard) |
| **Core Minecraft 10-49w** | 385 | 11,807 | Clasificar con Qwen (keep/discard) |
| **Disambiguations** | 1,603* | ~200K | Mantener (excluir version-only). Q&A-able. |
| **Spin-off: Dungeons** | 1,158 | 711,558 | Clasificar con Qwen (solo narrativa/lore) |
| **Spin-off: Legends** | 340 | 121,690 | Clasificar con Qwen (solo narrativa/lore) |
| **Spin-off: Earth** | 136 | 62,715 | Clasificar con Qwen (solo narrativa/lore) |
| **Spin-off: Story Mode** | 90 | 83,486 | Clasificar con Qwen (solo narrativa/lore) |
| **Movie** | 57 | 40,433 | Mantener todo |
| Render/Texture history | 3,025 | 202,693 | **ELIMINAR** |
| Debug mode | 10 | 2,257,965 | **ELIMINAR** |
| Empty/tiny (<10w) | 90 | 483 | **ELIMINAR** |
| Category/User pages | 27 | 6,806 | **ELIMINAR** |

*Las 1,603 disambiguations incluyen muchas no taggeadas en título — se detectan por contenido ("disambiguation page").

---

## Decisiones de diseño tomadas

### Por qué eliminar Debug Mode (2.26M palabras)
Son listas de 29,873 block states tipo "Block: Stone, ID: stone, State: -". Representan 18% de las palabras totales pero 0% de valor semántico. Un LM no aprende nada útil de esto y dominaría el training.

### Por qué NO saturar con items de spin-offs
El modelo target es pequeño. Si le metes 1,000 espadas de Dungeons + 5 de vanilla, va a contestar sobre espadas de Dungeons cuando le pregunten por espadas. Solución: de spin-offs solo mantener narrativa, historia, personajes y lore; descartar items, mobs, enchantments, weapons, armor específicos del spin-off.

### Por qué SÍ transformar artículos core 500+ con Qwen
Benchmark real: Wool (500w) → 74s sin thinking → output limpio y estructurado. Formato consistente (`# Nombre / ## Overview / ## Properties / ## Details`) ayuda al LM pequeño a aprender patrones vs 3,779 formatos wiki ligeramente distintos.

### Por qué SÍ generar Q&A de disambiguations
Ejemplo: la disambiguation de "Sand" lista Sand, Red Sand, Sandstone, Red Sandstone, Soul Sand, Suspicious Sand. Esto es perfectamente QA-able: "¿Qué tipos de arena hay en Minecraft?", "¿Cuál es la diferencia entre Sand y Soul Sand?". Son mapas de relaciones entre entidades.

### Q&A se genera del texto ORIGINAL (post-regex, pre-Qwen-transform)
Para artículos que se van a transformar con Qwen, el Q&A se genera del texto original limpiado con regex, no del transformado. Así el Q&A captura todo el detalle que puede perderse en la transformación.

---

## Infraestructura disponible

### Mac Mini M2 (mini-fzamorano / 100.84.151.4)
- **Chip**: Apple M2, 8 cores (4P + 4E)
- **RAM**: 16 GB unificada
- **Ollama**: `/usr/local/bin/ollama`
- **Modelo**: Qwen3:8b Q4_K_M (5.2GB)
- **Rendimiento**: ~17 tokens/sec, 1 instancia (no se pueden paralelizar — 2 instancias superan RAM disponible y causan swapping)
- **Concurrencia**: requests concurrentes se encolan, no hay ganancia real (probado: 3 concurrent = misma velocidad total que secuencial)
- **No-thinking vs thinking**: no-thinking es ~17% más rápido con calidad similar para estas tareas
- **Datos**: `/Users/felipe/minegpt/raw_data/wiki/`
- **Python**: 3.9 (necesita `from __future__ import annotations` para type hints modernos)
- **Acceso**: `ssh felipe@mini-fzamorano`

### Benchmark de referencia (2026-04-07)
| Tarea | Input | Tiempo | Output tokens |
|-------|-------|--------|---------------|
| Transformar artículo (Wool, ~500w) con thinking | 882 prompt tokens | 88.8s | 1,322 |
| Transformar artículo (Wool, ~500w) sin thinking | 886 prompt tokens | 74.1s | 1,166 |
| Clasificar artículo (corto) sin thinking | ~200 prompt tokens | ~20s | ~300 |

---

## Pipeline de ejecución

### FASE 1: Filtro por reglas (sin LLM) — `scraper/filter.py`
**Status**: [ ] Pendiente
**Tiempo estimado**: Minutos (script local)
**Input**: `articles.jsonl` (13,897)
**Output**: `articles_filtered.jsonl` (~10,360) + `articles_removed.jsonl` (~3,537 para auditoría)

Criterios de eliminación:
1. `title` contiene "render history" o "texture history" (case insensitive)
2. `title` empieza con "Debug mode"
3. `word_count < 10`
4. `title` empieza con "Category:" o "User:"
5. `title` contiene "/Structure/Blueprints/" o título termina en "/Renders"
6. Es disambiguation Y título es solo versión numérica (regex `^\d[\d.a-z]*$` — ej: "20100617", "0.30", "1.22")

### FASE 2: Limpieza con regex — `scraper/regex_clean.py`
**Status**: [ ] Pendiente
**Tiempo estimado**: Minutos (script local)
**Input**: `articles_filtered.jsonl` + `changelogs.jsonl`
**Output**: Mismos archivos con `text` limpio

Transformaciones regex (en orden):
1. **Espacios antes de puntuación**: `re.sub(r'\s+([.,;:!?])', r'\1', text)` — 65.8% de artículos afectados
2. **URLs residuales**: `re.sub(r'https?://\S+', '', text)` — 182 artículos
3. **Wiki markup roto**: `re.sub(r'\{\{[^}]*\}\}', '', text)` y `re.sub(r'\[\[(?:Special:)?[^\]]*\]\]', '', text)` — 68 artículos
4. **Cite artifacts**: `re.sub(r'\[(\d+)\]', '', text)` — 58 artículos (cuidado: no matchear cosas como `ArmorItems[3]` que son data paths válidos de Minecraft — usar lookahead/lookbehind)
5. **Navegación version**: strip líneas que contienen `◄` y `►`
6. **Boilerplate wiki**: strip frases conocidas:
   - "This article is a stub ."
   - "You can help by expanding it . The talk page may contain suggestions."
   - "This disambiguation page lists articles associated with the same title. If an internal link led you here, you may wish to change the link to point directly to the intended article."
   - "Instructions: Needs images and fill empty sections."
   - "This article is a work in progress."
   - "Please help expand and improve it."
   - "This article is a dynamic list ."
   - "Its subject matter requires frequent updates to remain current and complete..."
7. **Whitespace**: `re.sub(r'\n{3,}', '\n\n', text)` y `re.sub(r'  +', ' ', text)`, strip trailing whitespace

**Verificación post-fase-2**: samplear 20 artículos random, comparar antes/después, contar artículos y palabras totales.

### FASE 3: Clasificación de spin-offs (Qwen3:8b) — `scraper/classify_spinoffs.py`
**Status**: [ ] Pendiente
**Tiempo estimado**: ~10-15 horas en Mac Mini
**Input**: Artículos con prefijo `Dungeons:`, `MCD:`, `Legends:`, `Earth:`, `Story Mode:` (1,724 artículos)
**Output**: `spinoffs_keep.jsonl` + `spinoffs_discard.jsonl`

**Prompt de clasificación** (a refinar en fase de pruebas):
```
/no_think
You are classifying Minecraft spin-off wiki articles for an LLM training dataset.
We ONLY want to keep articles about: narrative, story, characters, lore, worldbuilding, game overview/concept.
We want to DISCARD articles about: specific items, weapons, armor, enchantments, individual mobs/enemies, version numbers, patches, crafting recipes, gameplay mechanics specific to the spin-off.

Article title: {title}
Article text (first 500 words): {text[:500]}

Classify as KEEP or DISCARD. Reply with only one word.
```

**Fase previa de pruebas**: Seleccionar ~20 artículos representativos:
- 5 de Story Mode (episodios, personajes, items)
- 8 de Dungeons (niveles, personajes como Arch-Illager, items como Gloopy Bow, enchantments)
- 5 de Legends (campaign, mobs, items)
- 2 de Earth (concepto, mobs)

Iterar prompt hasta que clasificación sea correcta en los 20. Guardar prompt final.

### FASE 4a: Pruebas de prompts para transformación
**Status**: [ ] Pendiente
**Tiempo estimado**: Manual, ~2-4 horas por tipo

Para cada tipo de transformación (4b, 4c, 4d, 4e), seleccionar ~10 artículos y probar prompts. Documentar:
- Prompt usado
- Input de ejemplo
- Output obtenido
- Problemas encontrados
- Prompt final validado

Guardar prompts en `scraper/prompts/` como archivos .txt.

### FASE 4b: Transformar changelogs (Qwen3:8b) — `scraper/transform_changelogs.py`
**Status**: [ ] Pendiente
**Tiempo estimado**: ~15-25 horas en Mac Mini
**Input**: `changelogs.jsonl` (1,271 artículos, 2.19M palabras)
**Output**: `changelogs_clean.jsonl` (~600K-800K palabras)

Lo que Qwen extrae:
- Nombre de versión, fecha de release, edición (Java/Bedrock/Pocket)
- Lista limpia de cambios player-facing (Additions, Changes, Fixes)

Lo que se descarta:
- Protocol version, data version, resource pack format, minimum Java version
- Links de descarga (Client .json, Server, Obfuscation maps)
- Líneas de navegación (◄ ► ya strippeadas por regex, pero Qwen limpia el resto)
- Development versions listings
- Cache ID, compilation date, version codes

### FASE 4c: Normalizar commands (Qwen3:8b) — `scraper/transform_commands.py`
**Status**: [ ] Pendiente
**Tiempo estimado**: ~2-3 horas en Mac Mini
**Input**: Artículos `Commands/*` con 100-499w (209 artículos)
**Output**: Mismos artículos con formato normalizado

Formato target:
```
Command: /gamemode
Edition: Java Edition, Bedrock Edition
Permission level: 2
Syntax: /gamemode <mode> [target]
Description: Changes the game mode of a player.
```

### FASE 4d: Clasificar artículos cortos (Qwen3:8b) — `scraper/classify_shorts.py`
**Status**: [ ] Pendiente
**Tiempo estimado**: ~7-10 horas en Mac Mini
**Input**: Artículos core 10-99w post-filtro (~1,246 artículos)
**Output**: keep/discard classification

### FASE 4e: Transformar artículos core 500+w (Qwen3:8b) — `scraper/transform_articles.py`
**Status**: [ ] Pendiente
**Tiempo estimado**: ~79 horas (~3.3 días 24/7) en Mac Mini
**Input**: Artículos core con word_count >= 500 (3,779 artículos, ~7.85M palabras)
**Output**: `articles_transformed.jsonl`

**Prompt** (a refinar en fase de pruebas):
```
/no_think
Reformat this Minecraft Wiki article into a clean, structured format for LLM training.
Keep ALL factual information. Do not add information not in the original.
Use this format:

# [Item/Mob/Block Name]
## Overview
[1-2 sentence summary of what this is]
## Properties
[Key stats as clean key: value pairs, one per line]
## Details
[Main content as clean prose, organized by topic]
## Trivia
[If trivia section exists in original]

Article title: {title}
Article:
{text}
```

**Notas importantes**:
- Usar no-thinking (`/no_think`) — 17% más rápido, calidad similar
- Truncar input a ~4000 tokens (~3000 words) para artículos muy largos — context limit de Qwen es 40960 pero más contexto = más lento
- Para artículos >3000 words, considerar procesar en chunks o solo enviar los primeros 3000 words
- Implementar resume capability (guardar progreso cada N artículos)
- Log errores y artículos que fallen para re-procesamiento

### FASE 5: Generación de Q&A
**Status**: [ ] Pendiente

#### 5a. Q&A de artículos core 500+w — `scraper/generate_qa.py`
**Tiempo estimado**: ~50-80 horas en Mac Mini
**Input**: Artículos ORIGINALES post-regex-clean (no los transformados por Qwen)
**Output**: `qa_tier1.jsonl`
**Cantidad estimada**: ~40K-70K Q&A pairs (5-20 por artículo según densidad)

Tipos de preguntas a generar:
- **Factuales**: "¿Cuánta vida tiene un Creeper?" → "20 HP"
- **Descriptivas**: "¿Qué es un Creeper?" → "Un mob hostil que..."
- **Relaciones**: "¿De qué tiene miedo el Creeper?" → "De los gatos y ocelotes"
- **Mecánicas**: "¿Qué pasa cuando un rayo cae cerca de un Creeper?" → "Se convierte en charged creeper"
- **Drops/obtención**: "¿Qué dropea un Creeper al morir?" → "0-2 gunpowder"

#### 5b. Q&A de artículos medium 100-499w — `scraper/generate_qa.py`
**Tiempo estimado**: ~30-45 horas en Mac Mini
**Input**: Artículos core 100-499w post-regex-clean (~3,161)
**Output**: `qa_tier2.jsonl`
**Cantidad estimada**: ~10K-15K Q&A pairs (3-5 por artículo)

#### 5c. Q&A de disambiguations — `scraper/generate_qa_disambiguations.py`
**Tiempo estimado**: ~10-15 horas en Mac Mini
**Input**: Disambiguation pages (~1,400 útiles post-filtro versiones)
**Output**: `qa_disambiguations.jsonl`
**Cantidad estimada**: ~4K-7K Q&A pairs (2-5 por disambiguation)

Ejemplo de Sand disambiguation → Q&A:
- "¿Qué tipos de arena existen en Minecraft?" → "Sand, Red Sand, Soul Sand, y Suspicious Sand"
- "¿Dónde se encuentra Suspicious Sand?" → "En desert wells y desert pyramids"
- "¿Qué relación hay entre Sand y Sandstone?" → "Sandstone se forma debajo de Sand y en estructuras del desierto"

#### Q&A total estimado: ~54K-92K pairs

---

## Orden de ejecución recomendado

```
Semana 1:
  [1] Implementar y correr Fase 1 (filtro) + Fase 2 (regex)     — horas
  [2] Fase 4a: pruebas de prompts (manual, iterativo)            — 1-2 días
  [3] Lanzar Fase 3: clasificación spin-offs en Mac Mini         — ~10-15h background

Semana 2:
  [4] Revisar resultados de Fase 3, ajustar si necesario
  [5] Lanzar Fases 4b+4c+4d secuencialmente en Mac Mini          — ~24-38h background
  [6] Revisar resultados, re-procesar errores

Semana 2-3:
  [7] Lanzar Fase 4e: transformar artículos core 500+w            — ~79h background (~3.3 días)

Semana 3-4:
  [8] Lanzar Fase 5a: Q&A tier 1                                  — ~50-80h background
  [9] Lanzar Fase 5b: Q&A tier 2                                  — ~30-45h background
  [10] Lanzar Fase 5c: Q&A disambiguations                        — ~10-15h background

Total Qwen: ~203-272 horas (~8.5-11.3 días 24/7 en Mac Mini)
```

---

## Archivos del proyecto relevantes

| Archivo | Descripción |
|---------|-------------|
| `scraper/wiki_scraper.py` | Scraper original (referencia de cómo se obtuvieron los datos) |
| `scraper/clean.py` | Dedup existente con MinHash/LSH |
| `raw_data/wiki/articles.jsonl` | Dataset fuente (Mac Mini) |
| `raw_data/wiki/changelogs.jsonl` | Changelogs fuente (Mac Mini) |
| `utils/config.py` | Config central (vocab_size=8000, 6 layers, 512 dim, 512 ctx) |
| `data/mixer.py` | Mezclador de datasets para training (70/20/10 split) |
| `EXPLORATION_REPORT.md` | Reporte de exploración del dataset crudo |
| `LEGAL.md` | Análisis legal de fuentes |

## Scripts a crear

| Script | Fase | Dónde corre |
|--------|------|-------------|
| `scraper/filter.py` | 1 | Local (Windows/cualquier) |
| `scraper/regex_clean.py` | 2 | Local (Windows/cualquier) |
| `scraper/prompts/*.txt` | 4a | Referencia |
| `scraper/classify_spinoffs.py` | 3 | Mac Mini |
| `scraper/transform_changelogs.py` | 4b | Mac Mini |
| `scraper/transform_commands.py` | 4c | Mac Mini |
| `scraper/classify_shorts.py` | 4d | Mac Mini |
| `scraper/transform_articles.py` | 4e | Mac Mini |
| `scraper/generate_qa.py` | 5a,5b | Mac Mini |
| `scraper/generate_qa_disambiguations.py` | 5c | Mac Mini |

Todos los scripts que corren en Mac Mini deben:
- Usar `from __future__ import annotations` (Python 3.9)
- Tener resume capability (guardar progreso)
- Loggear errores para re-procesamiento
- Llamar a Ollama via `http://localhost:11434/api/generate`
- Usar `"options": {"num_ctx": 8192}` (o menos para tareas simples)

---

## Dataset final estimado

| Componente | Artículos | Palabras estimadas |
|------------|-----------|-------------------|
| Core 500+w transformados | ~3,779 | ~4-5M |
| Core 100-499w (regex clean) | ~3,638 | ~900K |
| Core shorts que pasaron filtro | ~600-800 | ~40K |
| Spin-offs narrativos | ~200-400 | ~150-300K |
| Movie | 57 | ~40K |
| Disambiguations (útiles) | ~1,400 | ~180K |
| Changelogs limpios | ~1,271 | ~600-800K |
| Commands normalizados | ~209 | ~50K |
| **Subtotal artículos** | **~11,154-11,554** | **~6-7.3M** |
| Q&A pairs | ~54K-92K | ~2-4M |
| **TOTAL DATASET** | | **~8-11.3M palabras** |

vs original: 14.6M palabras (12.4M articles + 2.2M changelogs) con 2.26M de debug mode basura.
