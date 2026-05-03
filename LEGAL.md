# MineGPT — Análisis Legal de Fuentes de Datos

Última actualización: 2026-04-26

Este documento analiza la legalidad de cada fuente de datos para entrenamiento de MineGPT.
El proyecto es **personal, educativo, sin fines comerciales**.

> **Nota (2026-04-26):** Reddit fue descartado del plan. Con 564 artículos en el bucket
> `tutorial` (instructivos del wiki) tenemos suficiente contenido conversacional/de
> instrucción sin necesidad de tocar fuentes con ToS hostiles. La sección de Reddit se
> conserva abajo como referencia histórica.

---

## Resumen rápido

| Fuente | Licencia | robots.txt | Viable? | Notas |
|--------|----------|------------|---------|-------|
| minecraft.wiki | CC BY-NC-SA 3.0 | **Bloquea bots de IA** | ⚠️ Zona gris | Licencia OK para no-comercial, pero tienen política anti-IA explícita |
| ~~Reddit r/Minecraft~~ | ~~ToS prohíben ML~~ | ~~N/A~~ | ❌ **Descartado** | Cubierto por el bucket `tutorial` del wiki (564 arts) |
| **Wikipedia EN** | **CC BY-SA 4.0** | — | ✅ **Libre** | Bios de Notch, Jeb, C418, Lena Raine, Julian Gough, Mojang Studios, etc. Atribución obligatoria. |
| **Word of Notch (vía Wayback Machine)** | Posts públicos del autor | — | ⚠️ Zona gris defensible | Blog de Notch (notch.tumblr.com) eliminado 2021-08-26. Snapshots en Internet Archive. Uso educativo no-comercial. |
| **YouTube captions oficiales** | Captions = metadata; copyright video del uploader | — | ⚠️ Zona gris defensible | Solo captions de uploads oficiales (2 Player Productions, Mojang). Para uso educativo no-comercial. |
| FTB Wiki | CC BY-NC-SA 3.0 | — | ⚠️ Similar a minecraft.wiki | |
| Minecraft Forums | Sin licencia abierta | — | ❌ No viable | Propiedad de Fandom, sin licencia para terceros |
| Wikibooks Minecraft | CC BY-SA 3.0 | — | ✅ Libre | Atribución requerida, uso comercial OK |
| Wikipedia (artículos MC) | CC BY-SA 4.0 | — | ✅ Libre | Atribución requerida |
| Wikidata | CC0 | — | ✅ Dominio público | Datos estructurados |
| WikiText-103 | CC BY-SA 3.0 | N/A | ✅ Libre | Dataset de HuggingFace |
| TinyStories | MIT | N/A | ✅ Libre | Dataset de HuggingFace |
| Alpaca | Apache 2.0 | N/A | ✅ Libre | Stanford, 52k instrucciones |
| HF: lparkourer10/minecraft-wiki | CC BY-NC-SA 3.0 heredada | N/A | ⚠️ | Ya scrapeado, pero hereda restricción NC |

---

## Detalle por fuente

### minecraft.wiki
- **Licencia**: CC BY-NC-SA 3.0 (Weird Gloop)
- **robots.txt**: Bloquea explícitamente todos los bots de IA conocidos (GPTBot, ClaudeBot, CCBot, etc.) Y los endpoints de API
- **Política de IA**: Tienen una [política explícita anti-IA generativa](https://minecraft.wiki/w/Minecraft_Wiki:Generative_AI_policy)
- **Análisis**: La licencia CC BY-NC-SA permite uso no-comercial con atribución. Sin embargo, el sitio ha señalado explícitamente que no quiere que se use para IA. Respetar robots.txt es la práctica ética estándar aunque no sea legalmente vinculante.
- **Alternativa**: Existe un dataset ya scrapeado en HuggingFace (lparkourer10/minecraft-wiki) que hereda la misma licencia CC BY-NC-SA.

### Wikipedia EN — agregado 2026-04-26
- **Licencia**: CC BY-SA 4.0 (libre, atribución requerida)
- **API**: `https://en.wikipedia.org/w/api.php` — endpoint público de extracts en plain text
- **Cobertura**: Markus Persson (Notch), Jens Bergensten (Jeb), Daniel Rosenfeld (C418), Lena Raine, Julian Gough (autor del End Poem), Mojang Studios, Microsoft, 2 Player Productions, Minecraft (game), Minecraft Live, Minecraft: Story Mode/Dungeons/Legends/Earth, Minecraft: The Story of Mojang, A Minecraft Movie. Total ~50K palabras.
- **Atribución**: cada entry guarda `url` con link al artículo original.
- **Script**: `scraper/wikipedia_bio_scraper.py`
- **Output**: `raw_data/external/wikipedia_bios.jsonl`

### Word of Notch (vía Wayback Machine) — agregado 2026-04-26
- **Origen**: Blog personal de Markus Persson en notch.tumblr.com, eliminado 2021-08-26.
- **Acceso**: Internet Archive Wayback Machine CDX API + snapshots públicos.
- **Status legal**: posts públicos del propio autor; uso educativo no-comercial; cada entry incluye `url_original` + `url_snapshot` para atribución.
- **Cobertura objetivo**: ~500 posts únicos en CDX. Por defecto se descargan los más antiguos (2009-2011) que cubren los inicios del desarrollo de Minecraft.
- **Script**: `scraper/wayback_blog_scraper.py`
- **Output**: `raw_data/external/word_of_notch.jsonl`
- **Limpieza pendiente**: Phase 2 regex_clean debe quitar template tumblr (Archive, Random Post, "powered by Tumblr", etc.) — viene como ruido del HTML.

### YouTube captions — agregado 2026-04-26
- **Status**: Script implementado pero lista de video IDs vacía por ahora. Los IDs deben agregarse manualmente desde YouTube (verificar canales oficiales: 2 Player Productions, Mojang/Minecraft, GDC).
- **Targets sugeridos**:
  - "Minecraft: The Story of Mojang" full doc en canal oficial 2 Player Productions (uploaded Nov 2013, free)
  - Notch GDC 2011 postmortem (canal GDC oficial)
  - Mojang official 10/15 anniversary retrospectives
- **Script**: `scraper/youtube_transcript_scraper.py`
- **Output**: `raw_data/external/youtube_transcripts.jsonl` (vacío hasta que se agreguen IDs)

### Reddit r/Minecraft — DESCARTADO 2026-04-26
- **Razón del descarte**: El audit del wiki dejó 564 artículos en bucket `tutorial`
  (Tutorials/, Java/Bedrock guides, redstone circuits root pages). Es suficiente para
  v1 sin necesidad de fuente conversacional adicional.
- **ToS**: Reddit prohíbe explícitamente usar datos para entrenar IA sin licencia comercial
- **Demandas activas**: Reddit demandó a Anthropic (junio 2025) y Perplexity AI (octubre 2024) por scraping
- **Dumps disponibles**: Arctic Shift y Academic Torrents tienen dumps históricos marcados "para uso científico y no comercial"
- **Decisión**: no se usará en v1. Si en v2 se quisiera contenido conversacional real,
  reevaluar.

### Datasets generales (WikiText-103, TinyStories, Alpaca)
- Todos tienen licencias permisivas (CC BY-SA, MIT, Apache 2.0)
- Disponibles en HuggingFace
- Sin restricciones para uso educativo

### Datasets de Minecraft en HuggingFace
Existen varios datasets ya curados:
- `lparkourer10/minecraft-wiki` — scrape completo del wiki
- `TopAI-1/Minecraft-WebText-2` — texto de mecánicas, bloques, entidades
- `amoghghadge/gemma-3-12b-mc-qa-dataset` — Q&A sintético
- `FalconNet/BlockData-minecraft-10k` — datos estructurados de bloques

---

## Decisión del proyecto

Para MineGPT, siendo un proyecto **personal y educativo**:

1. **Datasets generales**: ✅ Usar sin problema (WikiText-103, TinyStories, Alpaca)
2. **minecraft.wiki**: Evaluaremos usar el dataset de HuggingFace ya existente (evita scraping directo) o scrapear respetando rate limits. El uso es no-comercial y educativo.
3. ~~**Reddit**~~: ❌ **Descartado** (2026-04-26). El bucket `tutorial` del wiki (564 arts) cubre la necesidad de contenido conversacional/instructivo.
4. **Atribución**: Mantener atribución completa de todas las fuentes CC.
