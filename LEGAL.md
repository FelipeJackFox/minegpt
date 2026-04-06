# MineGPT — Análisis Legal de Fuentes de Datos

Última actualización: 2026-04-06

Este documento analiza la legalidad de cada fuente de datos para entrenamiento de MineGPT.
El proyecto es **personal, educativo, sin fines comerciales**.

---

## Resumen rápido

| Fuente | Licencia | robots.txt | Viable? | Notas |
|--------|----------|------------|---------|-------|
| minecraft.wiki | CC BY-NC-SA 3.0 | **Bloquea bots de IA** | ⚠️ Zona gris | Licencia OK para no-comercial, pero tienen política anti-IA explícita |
| Reddit r/Minecraft | ToS prohíben ML | N/A | ⚠️ Zona gris | Dumps históricos en Arctic Shift/Academic Torrents disponibles |
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

### Reddit r/Minecraft
- **ToS**: Reddit prohíbe explícitamente usar datos para entrenar IA sin licencia comercial
- **Demandas activas**: Reddit demandó a Anthropic (junio 2025) y Perplexity AI (octubre 2024) por scraping
- **Dumps disponibles**: Arctic Shift y Academic Torrents tienen dumps históricos marcados "para uso científico y no comercial"
- **Riesgo práctico**: Para un proyecto individual educativo, el riesgo de demanda es mínimo, pero el riesgo legal teórico existe

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
3. **Reddit**: Evaluaremos usar dumps de Arctic Shift si decidimos incluir datos conversacionales.
4. **Atribución**: Mantener atribución completa de todas las fuentes CC.
