# MineGPT — Phase 4.0 UX & Implementation Design

> Diseño consolidado del merged Prompt Lab + manual curation layer + status
> tracking, post-síntesis de los audits `/ui-ux-pro-max` y `/ux-designer`.
>
> Status: aprobado por Felipe 2026-04-26. Fuente única de verdad para la
> implementación de Fase 4.0.
>
> Fecha: 2026-04-26

---

## Decisiones cerradas (8 bloqueantes + 20 no-controvertidas)

### Bloqueantes (resueltas con Felipe)

| # | Decisión | Resolución |
|---|---|---|
| D1 | Modes UI | 2 ejes: segmented control de sample size (5/20/50/Full bucket) + checkbox `Include also_in` **default ON**. NO 5 opciones planas. |
| D2 | Sub-estados de bucket | Sí, granularidad fina. `transform_status: not_started \| drafting \| ready \| running \| completed \| skipped`. `qa_status: blocked \| not_started \| drafting \| ready \| running \| completed`. `last_touched_at` ISO. |
| D3 | Mark done | Separar `run_completed` (auto al terminar técnicamente) de `user_approved` (manual con atajo `M`). Badge `T ✓` solo si ambos. Estado intermedio `T ⚠` (run done, pending review). |
| D4 | Concurrencia | 1 run a la vez global + queue de máx 3. Banner visible con current + queued. Editor de prompt **per-bucket** para preparar drafts de buckets en queue mientras corre otro. |
| D5 | Output structure | 1 archivo por bucket+lens: `raw_data/transformed/{bucket_lens}.jsonl`. Resume cuenta líneas. Cada línea incluye `bucket_lens` explícito por audit. |
| D6 | Default scope exclusión | Solo current bucket-lens (1 click toggle). "Exclude from all lenses" detrás de modal estilo flag con campo razón obligatorio (reusa modal de Articles tab). |
| D7 | Layout merged Prompt Lab | 3 columnas: Prompt editor 35% / Article list 25% / Output+feed 40%. Mac Mini stats compactos en header global, siempre visibles. |
| D8 | Universal header | Read-only en UI, collapsible (default colapsado). Bucket-specific editable con autosave cada 2s a `prompts/drafts/{bucket}_{transform\|qa}_draft.txt`. Sobrevive cierre del UI. |

### No-controvertidas (aplico sin discusión)

1. Fix bug `x-text` con HTML entities (índex.html:606) — usar iconos UTF-8 directos.
2. Cache TTL 8s server-side del SSH a Mac Mini (de N×6/min a 6/min).
3. Persistir `RUNS` a disco (resume sobrevive reinicio del server).
4. Eliminar duplicado del Mac Mini stats bar (Production lo tiene además del header).
5. Button primitivo (sizes xs/sm/md, variants primary/secondary/tertiary/danger/success/warn, shape default/icon-only).
6. StatusBadge component (4 estados con icono+texto+color, WCAG AA verificado).
7. Tokens CSS (`--space-*`, `--border-subtle/default/strong`, `--surface-0..3`, `--text-muted/default/strong/emph`).
8. Replicar de Articles tab: Cmd+K palette, `?` cheat sheet, modal pattern, sidebar collapse, URL state, focus-visible ring.
9. Lock textarea durante run + indicador "prompt locked, edits apply to next run".
10. Confirm dialog para runs con ETA > 5 min.
11. Pre-run check de espacio en disco (warning si < 10% libre).
12. Snapshot de exclusiones al iniciar run + warning si cambian durante run.
13. Article expansion inline: max-height 40vh + sticky header + scroll interno.
14. Atajos: `Cmd+Enter`, `Shift+Cmd+Enter`, `Cmd+K`, `?`, `1/2/3/4`, `S`, `X`, `Cmd+Shift+N`, `↑↓`, `Space`, `Esc`, `M`, `Cmd+S`.
15. Bucket picker filtrado por default a buckets con `transform_status != skipped`. Toggle "Show all (1085)".
16. History timeline default filter = current bucket only. Toggle para all buckets.
17. Notificación overnight: Browser Notification API opt-in + persistent banner.
18. Lens-specific focus dinámico: prompt builder concatena solo la sección del lens activo.
19. Autosave del prompt en draft cada 2s a `prompts/drafts/{bucket}_{transform|qa}_draft.txt`.
20. URL state: `?bucket=X&mode=full&include_secondaries=true`.

---

## Layout merged Prompt Lab tab

### Wireframe (1280px+)

```
┌────────────────── Header global (60px) ──────────────────────────┐
│ MineGPT  [Lab] [Articles]  conn ●  qwen3:14b ▾  ?               │
│ mini-fzamorano ● 8.1G/16G · CPU 78% · 52°C                       │
├──────────────── Task strip (96px) ───────────────────────────────┤
│ Bucket: [Animal_mobs ▾]  47 primary + 9 also_in                  │
│   T: drafting · Q&A: blocked · last touched 12 min ago           │
│ Sample: [● 5] [○ 20] [○ 50] [○ Full bucket]    ☑ Include also_in │
│ Phase: [● Transform] [○ Q&A]                            [▶ Run] │
├──── Prompt (35%) ──┬── Article list (25%) ──┬── Output (40%) ──┤
│ ▸ Universal header │ Sort: [A-Z ▾] Filter:  │ Live feed         │
│   (collapsed)      │ Show: [all ▾]          │ Progress 12/47    │
│ ─────────────      │                        │ ETA 18 min        │
│ Bucket-specific:   │ ▶ Cow         (3,776w) │ Errors: 0         │
│ [textarea          │     T ✓ Q&A ⏳         │                    │
│  autosave 2s]      │     also_in: 2         │ ─── Detail ───    │
│                    │ ▶ Pig         (1,200w) │ Last result:      │
│ Model params:      │     T ✓ Q&A ✓          │ Cow → output here │
│ num_ctx: 4096      │ ▶ Chicken     (800w)   │                    │
│ temp: 0.1          │     T ✗ "stub"         │ ─── History ───   │
│ no_think: ☑        │ ▼ Bell        (3,776w) │ - Animal_mobs     │
│                    │   primary: Generated_  │   full T ✓ 25min  │
│ [▶ Run test]       │     structure_blocks   │ - Animal_mobs     │
│ [▶ Run full]       │   also_in: Redstone,   │   test_20 90% acc │
│ Save: [as approved]│     Mechanisms, ...    │                    │
│                    │   ┌─ sticky header ──┐ │                    │
│                    │   │ Bell · 3,776w    │ │                    │
│                    │   │ [excl T] [excl Q]│ │                    │
│                    │   │ [⚐ flag exclude] │ │                    │
│                    │   ├──────────────────┤ │                    │
│                    │   │ scrollable body  │ │                    │
│                    │   │ ...max 40vh...   │ │                    │
│                    │   └──────────────────┘ │                    │
│                    │ ▶ ...                  │                    │
└────────────────────┴────────────────────────┴───────────────────┘
```

### Header global (compacto, 60px en 2 rows)

Row 1: app name · tabs · connection · model · cheat sheet
Row 2: mac mini stats (siempre visible)

### Task strip (96px en 3 rows)

Row 1: bucket selector + estado actual + last_touched_at
Row 2: sample size segmented + include_also_in checkbox
Row 3: phase toggle (Transform/Q&A) + Run button

### Main content flex (calc 100vh - header - task - feed-collapsed)

3 columnas con widths fijos:
- Prompt editor: 35% min 480px
- Article list: 25% min 320px
- Output panel: 40% min 480px

En 1920px+: prompt cap a 600px, el resto va a output.

### Live feed (colapsable, default 30vh, collapsed = 40px header only)

Cuando hay run activo: expanded por default.
Cuando no hay run: collapsed.

---

## Data model (persistencia)

### `raw_data/_pipeline_state/bucket_status.json`

```json
{
  "Animal_mobs": {
    "ambiente": "game_vanilla",
    "family": "mob",
    "primary_count": 47,
    "secondary_count": 9,

    "transform_status": "drafting",
    "transform_run_id": null,
    "transform_run_completed": false,
    "transform_user_approved": false,
    "transform_last_run_at": "2026-04-27T01:23:45Z",
    "transform_excluded_count": 2,

    "qa_status": "blocked",
    "qa_run_id": null,
    "qa_run_completed": false,
    "qa_user_approved": false,
    "qa_last_run_at": null,
    "qa_excluded_count": 0,

    "last_touched_at": "2026-04-27T02:15:00Z",
    "skipped_reason": null,
    "skipped_at": null,
    "force_transform": false
  }
}
```

### `raw_data/_pipeline_state/article_exclusions.jsonl` (append-only)

Cada línea es un evento. Estado actual = última entry por (title, bucket_lens, scope).

```jsonl
{"ts":"2026-04-27T01:23:45Z","title":"Chicken","bucket_lens":"Animal_mobs","scope":"this_lens","action":"exclude_transform","reason":"stub article, regex enough","actor":"felipe"}
{"ts":"2026-04-27T01:25:10Z","title":"Bell","bucket_lens":"*","scope":"all_lenses","action":"exclude_transform","reason":"under review with classifier audit","actor":"felipe"}
{"ts":"2026-04-27T01:30:00Z","title":"Chicken","bucket_lens":"Animal_mobs","scope":"this_lens","action":"include_transform","reason":null,"actor":"felipe"}
```

Campos:
- `ts`: ISO timestamp UTC.
- `title`: artículo afectado.
- `bucket_lens`: bucket donde aplica. `*` si scope=all_lenses.
- `scope`: `this_lens` | `all_lenses`.
- `action`: `exclude_transform` | `exclude_qa` | `exclude_both` | `include_transform` | `include_qa` | `include_both`.
- `reason`: opcional para `this_lens` exclude/include. **Obligatorio** para `all_lenses`.
- `actor`: por ahora siempre "felipe", reservado para multi-user futuro.

Derivación del estado actual:

```python
def current_state(title, bucket_lens):
    # Last entry for this (title, bucket_lens) wins.
    # Then last entry for (title, "*") if no specific entry exists.
    ...
```

### `raw_data/_pipeline_state/run_history.jsonl` (append-only)

Persistencia de runs. Equivalente a `RUNS` en memoria pero a disco.

```jsonl
{"run_id":"r_2026-04-27_abc123","ts_start":"...","ts_end":"...","bucket_lens":"Animal_mobs","mode":"test_20","phase":"transform","prompt_hash":"sha256:...","model":"qwen3:14b","status":"completed","item_count":20,"success_count":18,"error_count":2,"output_path":"raw_data/transformed/Animal_mobs.jsonl"}
```

### `raw_data/_pipeline_state/run_queue.json` (in-flight + queued)

```json
{
  "current": {
    "run_id": "r_2026-04-27_xyz",
    "bucket_lens": "Animal_mobs",
    "phase": "transform",
    "mode": "full",
    "started_at": "...",
    "progress": {"done": 12, "total": 47, "errors": 0}
  },
  "queued": [
    {"run_id":"r_pending_1","bucket_lens":"Plants","phase":"transform","mode":"test_20","prompt_draft_path":"prompts/drafts/Plants_transform_draft.txt"}
  ]
}
```

### `scraper/prompt_lab/prompts/`

```
prompts/
├── _headers/
│   ├── transform.txt          (read-only en UI)
│   └── qa.txt
├── transform/
│   ├── block.txt              (approved bucket-specific por familia)
│   ├── mob.txt
│   ├── item.txt
│   ├── plant.txt
│   ├── mechanic.txt
│   ├── world.txt
│   ├── command.txt
│   ├── crafting_recipe.txt
│   └── version.txt
├── qa/
│   ├── block.txt
│   ├── mob.txt
│   ├── ... (idem)
└── drafts/
    ├── Animal_mobs_transform_draft.txt    (autosave por bucket)
    ├── Animal_mobs_qa_draft.txt
    └── ...
```

Lifecycle del draft:
- Cada keystroke → debounce 2s → POST `/api/prompts/draft/save` → escribe `prompts/drafts/{bucket}_{phase}_draft.txt`.
- Al cargar bucket en UI: `GET /api/prompts/draft?bucket=X&phase=transform` → si existe, carga draft. Si no, carga approved del archivo de la familia.
- Botón "Save as approved": copia draft al archivo approved (`prompts/transform/{family}.txt`) + actualiza `bucket_status[X].transform_status = "ready"`.
- Botón "Discard draft": borra draft, recarga approved.

---

## API endpoints (nuevos)

### Persistencia de bucket state

```
GET  /api/buckets/state                         → todo bucket_status.json
GET  /api/buckets/state/:bucket                 → estado de 1 bucket
POST /api/buckets/state/:bucket                 → update parcial (merge)
     body: {"transform_status":"running","transform_run_id":"r_..."}
POST /api/buckets/state/:bucket/approve         → user_approved=true para phase
     body: {"phase":"transform"}
POST /api/buckets/state/:bucket/skip            → mark skipped
     body: {"reason":"family is tutorial"}
POST /api/buckets/state/:bucket/force_transform → override skipped
```

### Exclusiones

```
POST /api/articles/exclude
     body: {"title":"Chicken","bucket_lens":"Animal_mobs","scope":"this_lens",
            "action":"exclude_transform","reason":"stub"}
POST /api/articles/include
     body: {"title":"Chicken","bucket_lens":"Animal_mobs","scope":"this_lens",
            "action":"include_transform","reason":null}
GET  /api/articles/exclusions?bucket=Animal_mobs       → list current state
GET  /api/articles/exclusions/history?title=Chicken    → audit log
```

### Articles per bucket (con state)

```
GET /api/buckets/:bucket/articles
    response: [
      {"title":"Cow","word_count":3776,"primary":true,
       "also_in":["Passive_mobs","Tameable_mobs"],
       "skipped_lenses":[{"lens":"Mobs","reason":"parent_of_Animal_mobs"}],
       "transform_excluded":false,"qa_excluded":false,
       "last_transform_at":"...","last_qa_at":null}
    ]
```

### Drafts

```
GET  /api/prompts/draft?bucket=X&phase=transform   → text or null
POST /api/prompts/draft
     body: {"bucket":"X","phase":"transform","text":"..."}
POST /api/prompts/draft/promote                    → draft → approved
     body: {"bucket":"X","phase":"transform"}
DELETE /api/prompts/draft?bucket=X&phase=transform → discard
```

### Runs queue

```
GET  /api/runs/queue                                → current + queued
POST /api/runs/enqueue
     body: {"bucket_lens":"Plants","phase":"transform","mode":"test_20"}
DELETE /api/runs/queue/:run_id                      → cancel queued (no current)
POST /api/runs/cancel                               → cancel current
GET  /api/runs/history?bucket=X                     → run_history.jsonl filtrado
```

### Mac Mini stats (cached)

```
GET /api/mac/stats     (TTL server-side 8s, cliente puede llamar 10s)
```

---

## Componentes UI

### Button primitivo

```html
<button class="btn btn-primary btn-md">▶ Run test</button>
<button class="btn btn-danger btn-sm">Cancel</button>
<button class="btn btn-icon btn-md" aria-label="Pin"><svg .../></button>
```

CSS:

```css
.btn {
  display: inline-flex; align-items: center; gap: 6px;
  border-radius: 6px; transition: all 120ms ease;
  font-weight: 500;
}
.btn:focus-visible { outline: 2px solid var(--accent-fg); outline-offset: 2px; }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-xs { padding: 4px 8px;  font-size: 11px; }
.btn-sm { padding: 6px 12px; font-size: 12px; }
.btn-md { padding: 8px 16px; font-size: 14px; }

.btn-primary   { background: var(--accent-bg); color: var(--accent-fg); border: 1px solid var(--accent-bd); }
.btn-secondary { background: var(--surface-2); color: var(--text-default); border: 1px solid var(--border-default); }
.btn-tertiary  { background: transparent;     color: var(--text-muted);   border: 1px solid transparent; }
.btn-danger    { background: var(--error-bg); color: var(--error-fg);    border: 1px solid var(--error-bd); }
.btn-success   { background: var(--success-bg);color: var(--success-fg); border: 1px solid var(--success-bd); }
.btn-warn      { background: var(--warn-bg);  color: var(--warn-fg);     border: 1px solid var(--warn-bd); }
.btn-icon      { padding: 6px; aspect-ratio: 1; }
```

### StatusBadge (4 estados WCAG AA)

```html
<span class="status status-done">✓ T</span>
<span class="status status-running">◐ T</span>
<span class="status status-pending">○ T</span>
<span class="status status-skipped">⊘ T</span>
<span class="status status-warn">⚠ T</span>     <!-- run done, pending review -->
```

```css
.status {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 2px 8px; border-radius: 999px;
  font-size: 11px; font-weight: 500;
  border: 1px solid transparent;
}
.status-done    { background: rgba(52,211,153,0.15); color: #6ee7b7; border-color: rgba(52,211,153,0.30); }
.status-running { background: rgba(59,130,246,0.15); color: #93c5fd; border-color: rgba(59,130,246,0.30); animation: pulse 2s ease-in-out infinite; }
.status-pending { background: rgba(148,163,184,0.10); color: #cbd5e1; border-color: rgba(148,163,184,0.25); }
.status-skipped { background: rgba(148,163,184,0.08); color: #94a3b8; border-color: rgba(148,163,184,0.25); border-style: dashed; text-decoration: line-through; }
.status-warn    { background: rgba(245,158,11,0.15); color: #fbbf24; border-color: rgba(245,158,11,0.30); }

@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.6} }
```

### BucketPicker (Cmd+K palette adaptado)

- Reusa palette overlay de Articles tab.
- Search por name + family.
- Group by ambiente.
- Filter chips: Drafting / Ready / Running / Done / Pending.
- Each row: bucket name + family + counts (primary + also_in) + status badges.
- Default filter: ocultar `transform_status === "skipped"`. Toggle `Show all`.

### ModeRadio (segmented + checkbox)

```html
<div class="mode-radio">
  Sample:
  <button class="seg seg-active">5</button>
  <button class="seg">20</button>
  <button class="seg">50</button>
  <button class="seg">Full bucket: 47</button>
</div>
<label class="checkbox">
  <input type="checkbox" checked> Include also_in (+9)
</label>
```

`Include also_in` default checked. El conteo `+9` se actualiza dinámico al cambiar bucket.

### ArticleRow inline-expandable

Estados: collapsed (~48px) y expanded (~min(40vh, content)).

Collapsed:
```
[▶] Title (3,776w)            [T ✓] [Q&A ⏳]   [+2 also_in]   [⋯]
```

Expanded:
```
[▼] Title (3,776w)            [T ✓] [Q&A ⏳]   [+2 also_in]
┌─ sticky header ────────────────────────────────────────────┐
│ Bell · 3,776 words · primary: Generated_structure_blocks   │
│ also_in: Redstone, Mechanisms, Block_entities, Utility    │
│ skipped: Blocks (parent dedup)                             │
│ [exclude T] [exclude Q&A] [⚐ flag exclude all]            │
├────────────────────────────────────────────────────────────┤
│ scrollable body, max-height 40vh                           │
│ ...                                                         │
└────────────────────────────────────────────────────────────┘
```

`⚐ flag exclude all` abre modal con campo "razón" obligatorio.

### Live feed unificado

Una sola tabla con cols: `# | status | title | result_summary | duration | reason`. Click → expandir inline detalle (no nuevo tab). Lección de Articles tab.

---

## Atajos de teclado

| Tecla | Acción |
|---|---|
| `Cmd+Enter` | Run currently selected mode |
| `Shift+Cmd+Enter` | Run full bucket (con confirm si ETA > 5min) |
| `Cmd+S` | Save current draft as approved |
| `Cmd+K` | Bucket picker palette |
| `Cmd+/` | Focus article list filter |
| `Cmd+G` | Focus prompt editor |
| `Cmd+Shift+N` | Next bucket en orden de Fase 4.2 |
| `Cmd+Shift+P` | Previous bucket |
| `T` | Cycle focus: prompt → list → output |
| `?` | Cheat sheet modal |
| `Esc` | Cancel run / close modal / blur input |
| `↑ ↓` | Navigate article list (cuando focus en lista) |
| `Space` | Expand/collapse current article |
| `X` | Toggle exclude (current article, current lens, transform) |
| `Shift+X` | Open "exclude all lenses" modal con razón |
| `M` | Mark current bucket as user_approved (current phase) |
| `1` `2` `3` `4` | Sample size: 5 / 20 / 50 / Full |
| `S` | Toggle Include also_in |
| `H` | Toggle history panel |
| `U` | Toggle universal header expand/collapse |

Inputs/textareas: solo `Esc` y `Cmd+*` interceptan; `Tab` jamás se intercepta.

---

## Estados y transiciones

### Bucket lifecycle

```
not_started ─┬─→ drafting_transform ──┬─→ ready_transform ─┬─→ transform_running
             │                        │                    │
             └─→ skipped (auto)       │←──────loop─────────┘    │
                                      │                          │
                                      │                          ▼
                                      ↑                    transform_completed (run_completed=true)
                                      │                          │
                                      │                  M atajo │
                                      │                          ▼
                                      │                    transform_done (user_approved=true)
                                      │                          │
                                      │                          ▼
                                      │                    drafting_qa
                                      │                          │
                                      │←──────loop───────────────┘
                                      │                          ▼
                                      │                    ready_qa
                                      │                          │
                                      │                          ▼
                                      │                    qa_running
                                      │                          │
                                      │                          ▼
                                      │                    qa_completed
                                      │                          │
                                      │                  M atajo │
                                      │                          ▼
                                      │                    qa_done (bucket complete)
                                      │                          │
                                      └────── revisited ─────────┘
```

### Article exclusion lifecycle

```
included (default state)
   │
   │  X atajo / button click
   ▼
excluded_T (current lens only) ──── X again ──→ included
   │
   │  Shift+X / "flag exclude all"
   ▼
excluded_T_all_lenses (with reason) ──── include button ──→ included
```

Same for QA (`excluded_QA`, `excluded_QA_all_lenses`). Indep estado para T y QA.

---

## Edge cases (decisiones explícitas)

| # | Caso | Manejo |
|---|---|---|
| EC1 | Bucket con 1 artículo | `test_5/20/50` disabled con tooltip. Solo `Full bucket`. |
| EC2 | Bucket con 800 artículos | Article list virtualizada (lazy-render visible + body solo cuando expandido). |
| EC3 | Artículo en 5 buckets | Pills also_in clickables. Click → `Switch to bucket A? Unsaved changes lost.` confirm. |
| EC4 | Bucket skipped por family | `[Force transform anyway]` button con warning. Escribe `force_transform: true`. |
| EC5 | Edit prompt durante run | textarea read-only + indicador "edits apply to next run". |
| EC6 | Browser cierra durante overnight | Server continúa. Refresh detecta `transform_status: running` con `transform_run_id` activo. Reconecta SSE. |
| EC7 | Server reinicia durante run | `RUNS` persistido a disco (`run_history.jsonl` + `run_queue.json`). Resume desde último item escrito a output. |
| EC8 | Disk full overnight | Pre-run check, warning si <10% libre. Hard block si <2%. |
| EC9 | Mac Mini sleep / Wi-Fi drop | Reusa retry+tunnel logic existente. Timeout 30s, 3 retries. |
| EC10 | JSONL corrupto | Skip línea, log warning. Append-only protege parcialmente. |
| EC11 | Conflicto de exclusiones (re-include después) | Last entry wins. Audit log completo. Hover muestra "last changed N days ago". |
| EC12 | Bucket renamed por classifier rerun | Detect orphan keys en `bucket_status.json`. Banner: "Found N orphan bucket states. [Review]". |

---

## Plan de implementación (orden estricto)

### Fase 4.0.A — Backend persistence + endpoints (~3-4h)

1. **Crear** `raw_data/_pipeline_state/` (init vacío).
2. **Schema validation utils** (Pydantic models en `scraper/prompt_lab/state.py`):
   - `BucketState`, `ExclusionEntry`, `RunHistoryEntry`, `RunQueueState`.
3. **State manager module** (`scraper/prompt_lab/state_manager.py`):
   - `load_bucket_status() -> dict`
   - `update_bucket_status(bucket, **fields)` con write atomic
   - `current_exclusion_state(title, bucket_lens) -> ExclusionState` (deriva de JSONL)
   - `append_exclusion(entry)` con file lock
   - `current_run_queue() -> RunQueueState`
   - `enqueue_run(run)`, `dequeue_run(run_id)`
4. **Mac stats cache** en `server.py`: TTL 8s, single SSH source.
5. **Endpoints** (orden: state → exclusions → drafts → queue):
   - `/api/buckets/state*`
   - `/api/articles/exclude|include|exclusions*`
   - `/api/buckets/:bucket/articles`
   - `/api/prompts/draft*`
   - `/api/runs/queue|enqueue|cancel|history`
6. **Migration**: si no existen archivos de estado, crear vacíos al startup.
7. **Persistencia de RUNS in-memory a disco**: cada item completado escribe a `run_history.jsonl`. Server startup reconstruye `RUNS` desde disco.

### Fase 4.0.B — Frontend tokens + primitivos (~2h)

1. **CSS tokens** en `<style>` block: `--space-*`, `--surface-*`, `--text-*`, `--border-*`, `--accent/success/warn/error-bg/fg/bd`.
2. **Button primitivo** + refactor de los ~15 botones inline.
3. **StatusBadge component** (CSS classes + Alpine bindings).
4. **Fix bug `x-text` línea 606** (cambiar a UTF-8 directo o SVG).

### Fase 4.0.C — Merged Prompt Lab tab (~5-6h)

1. **Eliminar tab Production**, mover sus features útiles al merged.
2. **Header global compacto**: tabs + connection + model + cheat sheet ? + mac stats row.
3. **Task strip** con bucket selector + status badges + sample radio + include_secondaries + phase toggle + Run button.
4. **3-column main**:
   - Col 1: prompt editor (universal collapsible header + bucket-specific textarea + params + run buttons + save approved button)
   - Col 2: article list (sort + filter + show + virtualized scroll + ArticleRow expandable)
   - Col 3: output panel (live feed + detail + history)
5. **Autosave** del bucket-specific cada 2s a draft.
6. **Confirmation modals**: full run con ETA > 5min, exclude all_lenses, switch bucket con unsaved.
7. **Atajos de teclado** (lista completa).
8. **URL state** (bucket, phase, sample size, include_also_in).
9. **Cheat sheet modal** (`?`).
10. **Browser notification** opt-in al primer run > 30 min + persistent banner post-run.

### Fase 4.0.D — Articles tab status badges (~2h)

1. **Sidebar**: cada bucket muestra `T ✓ Q&A ⏳` con StatusBadge component.
2. **Super-cats**: counter agregado `(12/142 buckets transformed, 8/142 Q&A done)`.
3. **Article list col 2**: excluded articles atenuados (opacity 0.6 + dashed border-left + tag).
4. **Article detail**: muestra `skipped_lenses` con razón.

### Fase 4.0.E — Resume + history unificado (~2h)

1. **Reconexión SSE** al detectar `transform_status: running` post-refresh.
2. **History timeline** en col 3 del Prompt Lab. Default filter: current bucket. Toggle all.
3. **Click en history entry**: load that prompt version into editor (con confirm si hay draft con cambios).
4. **Banner "next bucket"** post-completion: bucket sugerido del orden de Fase 4.2.

### Fase 4.0.F — Post-implementation audits (~1-2h)

1. Re-run skill `/ui-ux-pro-max` sobre el merged tab.
2. Re-run skill `/ux-designer` sobre el flujo end-to-end.
3. Aplicar correcciones (focus-visible, contrast, keyboard interception).

### Fase 4.0.G — Smoke test pilot (~30min)

1. Bucket: `Animal_mobs`.
2. Iterar prompt transform `mob` family con test_5.
3. Validar autosave de draft (cerrar tab, abrir, verificar texto).
4. Validar exclusión (excluir 1 artículo, verificar JSONL, re-include).
5. Validar enqueue (correr test_20 mientras ya hay un run).
6. Validar status badges en Articles tab.
7. Validar `M` atajo para user_approved.
8. Validar `Cmd+Shift+N` next bucket.

**Total estimado: ~16-19h** (sin contar fixes de los audits post).

---

## Token budget (referencia para Phase 4.1+)

```
num_ctx: 4096
universal_header_transform: ~400 tokens
bucket_specific (with lens-specific filtered): ~400 tokens
user_message (article truncated to 800 words): ~1100 tokens
─────────────────────────────────────
Total prompt: ~1900 tokens
Output budget: 4096 - 1900 = ~2200 tokens (suficiente para articles formato ## structure)
```

Si un artículo necesita más, ajustar `prepare_input(text, max_words=N)` per-bucket.

---

## Archivos creados/modificados (índice)

### Nuevos archivos

```
raw_data/_pipeline_state/
  bucket_status.json
  article_exclusions.jsonl
  run_history.jsonl
  run_queue.json

scraper/prompt_lab/
  state.py                         (Pydantic models)
  state_manager.py                 (load/save/derive logic)
  prompts/
    drafts/                        (autosave directory)
    _headers/transform.txt
    _headers/qa.txt
    transform/{family}.txt × 9
    qa/{family}.txt × 9
```

### Modificados

```
scraper/prompt_lab/
  server.py                        (new endpoints, cache, persistence)
  static/index.html                (rediseño merged tab + tokens + primitivos)
```

---

## Referencias

- `PHASE4_TRANSFORMATION_PLAN.md` — plan operacional completo
- `PROMPT_TEMPLATES.md` — headers + bucket-specific + dedup rules
- `CLASSIFIER_REDESIGN.md` — taxonomía cat-driven (impl actual)
- `WIKI_DATA_CLEANING.md` — pipeline Phases 1-3
- Audits internos (no archivados): `/ui-ux-pro-max` + `/ux-designer` 2026-04-26
