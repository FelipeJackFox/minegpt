# MineGPT — Q&A Generation Plan

> Plan operacional para generar Q&A pairs sobre el corpus hardened.
> Reemplaza las secciones Q&A de `PROMPT_TEMPLATES.md` y `PHASE4_TRANSFORMATION_PLAN.md`
> (que también contenían la half de Transform, ya deprecada 2026-04-27).
>
> Status: planning. No ejecutado todavía.
> Fecha: 2026-05-02

---

## Por qué Q&A (y no transform)

Decisión 2026-04-27 (ver memoria `project_pipeline_decisions_2026-04-27.md`):

- Qwen body transformation abandonado. Wiki body va directo al training corpus después de `hardening_v2.py`.
- Qwen reservado para Q&A pairs. Output estructuralmente más simple (`Q: ... A: ...`), más fácil de validar, mejor para el modelo target (125-200M params).

## Inputs disponibles

Tres fuentes de Q&A:

1. **`articles_hardened.jsonl`** (7,135 artículos, 7.62M words)
   - Main training corpus
   - Genera Q&A multi-lente: 1 pass por bucket primario + opcional cada `also_in`
   - Estimación: 5-10 Q&A pairs por article × ~7K = 35K-70K pairs

2. **`articles_qa_direct.jsonl`** (2,834 artículos)
   - Disambig pages (557) + Set_index w/ prose (15) + version-family (2,066) + Achievement disambigs + meta-routed
   - **Tipos especiales** (cada uno requiere prompt distinto):
     - Disambig: "¿Cuáles tipos de X hay?", "¿Diferencia entre A y B?"
     - Set_index w/ prose: variantes / overview de un grupo
     - Version-family: "¿Cuándo se agregó X?", "¿Qué cambió en versión Y?"
   - Estimación: 5-15 Q&A por article × 2,834 = 15K-40K pairs

3. **`changelogs_cleaned.jsonl`** (1,270 entries, ~2M words)
   - **Inclusión TBD** — decisión pendiente de Felipe sobre si incorporar al training
   - Si se incluye: probable formato Q&A "¿Qué cambió en X?"

Total estimado: ~50K-110K Q&A pairs.

## Filosofía

1. **Q&A se genera del texto post-hardening**, NO del cleaned. El hardening preserva facts (Renewable, Stackable, Sounds IDs, Generated loot rows, Translation keys) — esos son exactamente los facts que el Q&A debe enseñar.
2. **Multi-membership = multi-Q&A**. Cada artículo se procesa N veces, una por bucket donde aparece (primary + also_in). Cada pass tiene un prompt enfocado al lente del bucket.
3. **Adaptive count**. No se fija N pairs — el modelo decide adaptivamente cuántos pairs por article según fact density. Articles cortos quizá 2-3, articles densos 10-20.
4. **Manual exclusion** vía Prompt Lab (ya implementada). Felipe puede excluir artículos del Q&A pipeline por bucket o globalmente con razón.

## Tipos de Q&A por bucket

(Detalles en `PROMPT_TEMPLATES.md` secciones 644-805 y `PHASE4_TRANSFORMATION_PLAN.md` 257-410. A consolidar acá cuando se itere sobre prompts en Prompt Lab.)

Resumen alto nivel por familia:

- **mob** — `¿Qué hace X cuando Y?`, `¿Qué dropea X?`, `¿Cómo se reproduce X?`
- **plant_ore** — `¿Cómo se obtiene X?`, `¿En qué bioma crece X?`, `¿Qué herramienta funciona mejor para minar X?`
- **item** — `¿Para qué sirve X?`, `¿Cómo se craftea X?`, `¿Stack de cuántos hace X?`
- **mechanic / effect / enchantment** — `¿Qué efecto tiene X?`, `¿Cómo se obtiene X?`, `¿Es compatible con Y?`
- **world / biome** — `¿Qué encuentras en bioma X?`, `¿Cómo se ve X?`, `¿Qué clima tiene X?`
- **command** — `¿Qué hace /X?`, `¿Cuál es la sintaxis de /X?`, `¿Qué argumentos toma /X?`
- **disambig** — `¿Cuáles tipos de X hay?`, `¿Cuál es la diferencia entre A y B?` (versions-family también)
- **real_world / media** — `¿Quién es X?`, `¿En qué año se hizo Y?`

## Tooling

Prompt Lab tab "Lab" (ver `PROMPT_LAB_UI.md`):
- Bucket picker (Cmd+K), prompt editor con header read-only + bucket-specific editable
- Modes: test_5 / test_20 / sample_50 / full
- Phase toggle: Q&A (transform half UI sigue presente pero deprecada)
- Output a `raw_data/qa_pairs/{bucket}_{lens}.jsonl`
- Manual exclusion per-article (Prompt Lab tracks state in `raw_data/_pipeline_state/`)

Modelo: qwen3:14b en Mac Mini (no-thinking, ~17 tokens/sec).

## Effort estimate

- Iteración de prompts por bucket: 30-60 min cada uno × 12-15 buckets = 6-15h human time
- Full Q&A run: ~50-100h Mac Mini wall-clock (5K articles × 1-3 lentes × 88s)
- Validación + manual exclusion: 5-10h human time
- Total: ~60-130h Mac Mini overnight + ~15-25h human time

## Status checklist

- [ ] Iterar prompt Q&A para bucket pilot (Animal_mobs sugerido por densidad de facts)
- [ ] Validar prompt en test_5 / test_20 hasta accuracy aceptable
- [ ] Repetir por bucket priority order: items → mobs → plants/ore → mechanics → world → command → disambig → versions
- [ ] Decidir inclusión de `changelogs_cleaned.jsonl`
- [ ] Decidir formato output canónico (`{"q": "...", "a": "...", "source_title": "...", "source_bucket": "..."}` propuesto)
- [ ] Run full Q&A en Mac Mini overnight
- [ ] Tokenizar + agregar a training dataset

## Referencias

- `project_hardening_v2.md` (memoria) — pipeline state actual
- `project_pipeline_decisions_2026-04-27.md` (memoria) — por qué Q&A reemplaza transform
- `PROMPT_TEMPLATES.md` — prompts originales (Q&A sections still valid)
- `PHASE4_TRANSFORMATION_PLAN.md` — Q&A sections still valid
- `PROMPT_LAB_UI.md` — UI tab actual
