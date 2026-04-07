"""Genera reporte exhaustivo de exploración del wiki scraping."""
from __future__ import annotations
import json, random, re, os
from collections import Counter

random.seed(42)
BASE = os.path.join(os.path.dirname(__file__), "..", "raw_data", "wiki")

arts = []
with open(os.path.join(BASE, "articles.jsonl"), encoding="utf-8") as f:
    for line in f:
        arts.append(json.loads(line))

cls = []
with open(os.path.join(BASE, "changelogs.jsonl"), encoding="utf-8") as f:
    for line in f:
        cls.append(json.loads(line))

out = open(os.path.join(BASE, "EXPLORATION_REPORT.md"), "w", encoding="utf-8")

def w(s=""):
    out.write(s + "\n")

def show_article(a, max_lines=12):
    w("#### %s (%d words)" % (a["title"], a["word_count"]))
    w("```")
    lines = a["text"].split("\n")
    for l in lines[:max_lines]:
        w(l[:140])
    if len(lines) > max_lines:
        w("... (%d lines total)" % len(lines))
    w("```")
    w()

# ===========================================
w("# MineGPT - Reporte de Exploracion del Wiki")
w()
total_w = sum(a["word_count"] for a in arts)
cl_w = sum(a["word_count"] for a in cls)
w("| Archivo | Registros | Palabras |")
w("|---------|-----------|----------|")
w("| articles.jsonl | %d | %s |" % (len(arts), "{:,}".format(total_w)))
w("| changelogs.jsonl | %d | %s |" % (len(cls), "{:,}".format(cl_w)))
w()

# ===========================================
w("---")
w("## 1. Distribucion de longitud")
w()
buckets = Counter()
for a in arts:
    wc = a["word_count"]
    if wc == 0: buckets["0 vacios"] += 1
    elif wc < 10: buckets["1-9"] += 1
    elif wc < 50: buckets["10-49"] += 1
    elif wc < 100: buckets["50-99"] += 1
    elif wc < 500: buckets["100-499"] += 1
    elif wc < 1000: buckets["500-999"] += 1
    elif wc < 5000: buckets["1000-4999"] += 1
    elif wc < 10000: buckets["5000-9999"] += 1
    else: buckets["10000+"] += 1

w("| Rango | Cantidad |")
w("|-------|----------|")
for b in ["0 vacios", "1-9", "10-49", "50-99", "100-499", "500-999", "1000-4999", "5000-9999", "10000+"]:
    w("| %s | %d |" % (b, buckets.get(b, 0)))
w()

# ===========================================
w("---")
w("## 2. DEBUG MODE (10 articles, 2.26M palabras) - Propuesta: GUARDAR APARTE")
w()
w("Son listas gigantes de block IDs. Ejemplo:")
w()
debug = [a for a in arts if a["title"].startswith("Debug mode")]
for a in debug[:2]:
    show_article(a, 15)

# ===========================================
w("---")
w("## 3. RENDER/TEXTURE HISTORY (2,711 articles) - Propuesta: ELIMINAR")
w()
w("Metadata de como se veia un bloque en cada version. Mayoria <50 palabras.")
w()
render = [a for a in arts if "block render history" in a["title"].lower() or "texture history" in a["title"].lower()]
for a in random.sample(render, min(6, len(render))):
    show_article(a, 8)

# ===========================================
w("---")
w("## 4. SPIN-OFFS - Propuesta: INCLUIR TODO")
w()
for label, prefix in [("Dungeons", "Dungeons:"), ("Legends", "Legends:"), ("Earth", "Earth:")]:
    matches = [a for a in arts if a["title"].startswith(prefix)]
    w("### %s (%d articles)" % (label, len(matches)))
    for a in random.sample(matches, min(2, len(matches))):
        show_article(a, 10)

story = [a for a in arts if "Story Mode" in a["title"]]
w("### Story Mode (%d articles)" % len(story))
for a in random.sample(story, min(2, len(story))):
    show_article(a, 10)

# ===========================================
w("---")
w("## 5. VACIOS Y <10 WORDS (106 articles) - Propuesta: ELIMINAR")
w()
tiny = [a for a in arts if a["word_count"] < 10]
for a in random.sample(tiny, min(10, len(tiny))):
    txt = a["text"][:100].replace("\n", " ").replace("`", "'")
    w("- **%s** (%d words): `%s`" % (a["title"], a["word_count"], txt))
w()

# ===========================================
w("---")
w("## 6. CATEGORY/USER PAGES (28 articles) - Propuesta: ELIMINAR")
w()
meta = [a for a in arts if a["title"].startswith("Category:") or a["title"].startswith("User:")]
for a in meta[:8]:
    txt = a["text"][:100].replace("\n", " ").replace("`", "'")
    w("- **%s** (%d words): `%s`" % (a["title"], a["word_count"], txt))
w()

# ===========================================
w("---")
w("## 7. DISAMBIGUATION PAGES (558 articles) - Propuesta: MANTENER")
w()
w("Listan variantes de un mismo nombre.")
w()
disamb = [a for a in arts if "Disambiguation_pages" in " ".join(a.get("categories", []))]
for a in random.sample(disamb, min(5, len(disamb))):
    show_article(a, 10)

# ===========================================
w("---")
w("## 8. PROBLEMAS DE CALIDAD DEL TEXTO - Propuesta: FIX CON REGEX")
w()

w("### 8a. Espacios antes de puntuacion (65.8% de articulos)")
w()
w("Antes -> Despues:")
w("```")
w('"a player , hisses" -> "a player, hisses"')
w('"Mob Trophy . This" -> "Mob Trophy. This"')
w("```")
w()
w("Ejemplos reales:")
w()
count = 0
for a in arts:
    if count >= 4:
        break
    matches = re.findall(r".{15,25}\w+ [,\.].{15,25}", a["text"])
    if matches:
        w("**%s:**" % a["title"])
        w("```")
        for m in matches[:3]:
            w(m.replace("\n", " ")[:100])
        w("```")
        w()
        count += 1

w("### 8b. URLs residuales (182 articulos)")
w()
count = 0
for a in arts:
    if count >= 3:
        break
    urls = re.findall(r"https?://\S+", a["text"])
    if urls:
        w("**%s:**" % a["title"])
        for u in urls[:3]:
            w("- `%s`" % u[:120])
        w()
        count += 1

w("### 8c. Wiki markup residual (68 articulos)")
w()
count = 0
for a in arts:
    if count >= 3:
        break
    if "{{" in a["text"] or "[[" in a["text"]:
        markup = re.findall(r"(?:\{\{|\[\[).{0,80}", a["text"])
        if markup:
            w("**%s:**" % a["title"])
            for m in markup[:3]:
                w("- `%s`" % m[:100])
            w()
            count += 1

w("### 8d. Cite artifacts (58 articulos)")
w()
count = 0
for a in arts:
    if count >= 3:
        break
    cites = re.findall(r"\[\d+\]", a["text"])
    if cites:
        idx = a["text"].find(cites[0])
        ctx = a["text"][max(0,idx-30):idx+30].replace("\n", " ")
        w("- **%s:** `...%s...`" % (a["title"], ctx))
        count += 1
w()

# ===========================================
w("---")
w("## 9. GALERIA ('as it appears in...') - Propuesta: MANTENER")
w()
count = 0
for a in arts:
    if count >= 3:
        break
    glines = [l for l in a["text"].split("\n") if "as it appears in" in l.lower()]
    if glines:
        w("**%s:**" % a["title"])
        for l in glines[:3]:
            w("- `%s`" % l[:130])
        w()
        count += 1

# ===========================================
w("---")
w("## 10. CHANGELOGS - Propuesta: MANTENER TODOS")
w()
for a in random.sample(cls, min(3, len(cls))):
    secs = a.get("changelog_sections", {})
    pf = secs.get("player_facing", "")
    tech = secs.get("technical", "")
    w("### %s (%d words)" % (a["title"], a["word_count"]))
    w("Player-facing: %d words | Technical: %d words" % (len(pf.split()), len(tech.split())))
    w("```")
    for l in pf.split("\n")[:12]:
        w(l[:130])
    if len(pf.split("\n")) > 12:
        w("...")
    w("```")
    w()

# ===========================================
w("---")
w("## 11. CORE MINECRAFT - Ejemplos de articulos buenos")
w()
core = [a for a in arts if a["word_count"] > 500
        and not a["title"].startswith("Debug")
        and "render history" not in a["title"].lower()
        and "texture history" not in a["title"].lower()
        and not a["title"].startswith("Category:")
        and not a["title"].startswith("User:")]
for a in random.sample(core, min(5, len(core))):
    snd = len(a.get("sounds") or [])
    w("### %s (%d words, %d sounds)" % (a["title"], a["word_count"], snd))
    w("```")
    lines = a["text"].split("\n")
    for l in lines[:15]:
        w(l[:140])
    if len(lines) > 15:
        w("... (%d lines total)" % len(lines))
    w("```")
    w()

out.close()
size = os.path.getsize(os.path.join(BASE, "EXPLORATION_REPORT.md"))
print("Reporte generado: raw_data/wiki/EXPLORATION_REPORT.md")
print("Tamano: %.1f KB" % (size / 1024))
