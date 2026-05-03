"""
article_viewer.py — Indexador y serving de articulos para la UI Articles tab.

Carga los jsonl de raw_data/wiki/, computa primary_group, y expone funciones
de busqueda + lookup random-access via byte offsets.

Diseño:
- Indexing al startup (background): ~5s para 10K articulos.
- META[title] => {group, tier, word_count, categories, scraped_at, removal_reason?}
- BY_GROUP[group][tier] => sorted list of titles
- OFFSETS[version][title] => (byte_offset, length) para random read sin parsear todo
- DELTAS[title] => {raw, filtered, cleaned} word counts para sort by delta

Solo `articles_cleaned.jsonl` se parsea full a META al startup. Los demas
archivos se indexan solo por offset (rapido, ~1s cada uno).
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any

from scraper.explore_subgroups import primary_group, secondary_groups, tier_for, WORD_TIERS

ROOT = Path(__file__).resolve().parents[2]
WIKI_DIR = ROOT / "raw_data" / "wiki"
EXTERNAL_DIR = ROOT / "raw_data" / "external"

# External sources — non-wiki, single-version content (only "cleaned").
# Each entry is loaded into META as `[<prefix>] <orig_title>` to avoid title
# collisions with the wiki, and stored with source-specific bucket.
EXTERNAL_SOURCES = [
    {"group": "external_wikipedia",  "prefix": "wp",    "file": "wikipedia_bios_cleaned.jsonl",
     "label": "Wikipedia bios (CC BY-SA)"},
    {"group": "external_notch_blog", "prefix": "notch", "file": "word_of_notch_cleaned.jsonl",
     "label": "Word of Notch (Wayback Machine)"},
    {"group": "external_youtube",    "prefix": "yt",    "file": "youtube_transcripts_cleaned.jsonl",
     "label": "YouTube transcripts"},
]

# Pipeline order. Phase numbers for the UI stepper.
ARTICLE_VERSIONS = [
    {"name": "raw",         "phase": 1, "file": "articles.jsonl",            "label": "raw"},
    {"name": "filtered",    "phase": 2, "file": "articles_filtered.jsonl",   "label": "filtered"},
    {"name": "cleaned",     "phase": 3, "file": "articles_cleaned.jsonl",    "label": "cleaned"},
    {"name": "removed",     "phase": 0, "file": "articles_removed.jsonl",    "label": "removed"},
    {"name": "hardened",    "phase": 4, "file": "articles_hardened.jsonl",   "label": "hardened v2"},
    {"name": "qa_direct",   "phase": 4, "file": "articles_qa_direct.jsonl",  "label": "qa direct"},
    {"name": "transformed", "phase": 5, "file": "articles_transformed.jsonl","label": "transformed"},
    {"name": "qa",          "phase": 6, "file": "articles_qa.jsonl",         "label": "Q&A"},
]

# Super-categories to fight Hick's Law (24 buckets is too many at first sight).
# Ambientes (Layer A of the cat-driven classifier).
# Buckets within each ambiente are populated DYNAMICALLY from primary_group output —
# no hardcoded bucket lists, the wiki cats decide.
# Order here is display order in the viewer sidebar.
AMBIENTE_LABELS = [
    ("game_vanilla",      "Vanilla game"),
    ("tutorial",          "Tutorials (community guides)"),
    ("real_world",        "Real world (people, companies, events)"),
    ("media_franchise",   "Media franchise (movies, novels, comics)"),
    ("versions",          "Versions"),
    ("spinoff",           "Spin-off games (out of v1)"),
    ("april_fools",       "April Fools (out of v1)"),
    ("education_edition", "Education Edition (out of v1)"),
    ("wiki_meta",         "Wiki meta / discardable"),
]

# External sources (loaded separately from cleaned external jsonl files)
EXTERNAL_AMBIENTE_NAME = "external"
EXTERNAL_AMBIENTE_LABEL = "External sources"

# Buckets that should be visually flagged as "discardable / audit" inside their ambiente.
DISCARDABLE_BUCKETS = {
    "Other", "Wiki_meta_other", "Redstone_schemas",
    "Files", "Templates", "Help_pages", "Wiki_self_reference", "Redirects",
}

# State (filled by build_index)
INDEX_STATUS: dict[str, Any] = {
    "ready": False,
    "progress": 0.0,
    "stage": "not started",
    "error": None,
}

META: dict[str, dict] = {}                   # title -> meta
BY_GROUP: dict[str, dict[str, list[str]]] = {}              # group -> tier -> titles (primary only)
BY_GROUP_SECONDARY: dict[str, dict[str, list[str]]] = {}    # group -> tier -> titles (secondary only)
OFFSETS: dict[str, dict[str, tuple[int, int]]] = {}  # version -> title -> (offset, length)
WORD_COUNTS: dict[str, dict[str, int]] = {}  # version -> title -> word_count
REMOVAL_REASONS: dict[str, str] = {}         # title -> reason (from articles_removed.jsonl)
AVAILABLE_VERSIONS: list[str] = []           # versions whose file exists
# External (non-wiki) entries are stored separately for I/O — single source, single version.
# Mapping: title -> (file_path, byte_offset, byte_length)
EXTERNAL_OFFSETS: dict[str, tuple[str, int, int]] = {}


def _scan_offsets(path: Path) -> tuple[dict[str, tuple[int, int]], dict[str, int]]:
    """Scan a jsonl file once, return {title: (offset, length)} and {title: word_count}."""
    offsets: dict[str, tuple[int, int]] = {}
    wcs: dict[str, int] = {}
    with path.open("rb") as f:
        offset = 0
        for raw in f:
            length = len(raw)
            try:
                d = json.loads(raw)
                title = d.get("title")
                if title:
                    offsets[title] = (offset, length)
                    wcs[title] = d.get("word_count", 0)
            except Exception:
                pass
            offset += length
    return offsets, wcs


def _set_progress(stage: str, p: float) -> None:
    INDEX_STATUS["stage"] = stage
    INDEX_STATUS["progress"] = p


def build_index() -> None:
    """Build the in-memory index. Idempotent."""
    try:
        global AVAILABLE_VERSIONS
        AVAILABLE_VERSIONS = [
            v["name"] for v in ARTICLE_VERSIONS
            if (WIKI_DIR / v["file"]).exists()
        ]
        if "cleaned" not in AVAILABLE_VERSIONS:
            INDEX_STATUS["error"] = "articles_cleaned.jsonl not found"
            INDEX_STATUS["ready"] = True
            return

        n_versions = len(AVAILABLE_VERSIONS)
        step = 0
        total_steps = n_versions + 2  # +meta parse + grouping

        # 1. Offsets for every available version
        for v in ARTICLE_VERSIONS:
            if v["name"] not in AVAILABLE_VERSIONS:
                continue
            path = WIKI_DIR / v["file"]
            _set_progress(f"indexing {v['name']}", step / total_steps)
            offsets, wcs = _scan_offsets(path)
            OFFSETS[v["name"]] = offsets
            WORD_COUNTS[v["name"]] = wcs
            step += 1

        # 2. Parse cleaned full (we need group classification + categories)
        _set_progress("classifying articles", step / total_steps)
        cleaned_path = WIKI_DIR / "articles_cleaned.jsonl"
        with cleaned_path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                d = json.loads(line)
                title = d["title"]
                cats = d.get("categories") or []
                text = d.get("text", "")
                wc = d.get("word_count", 0)
                group = primary_group(title, cats, text)
                also = secondary_groups(title, cats, text, group)
                META[title] = {
                    "title": title,
                    "word_count": wc,
                    "tier": tier_for(wc),
                    "group": group,
                    "also_in": also,
                    "categories": cats,
                    "scraped_at": d.get("scraped_at"),
                }
        step += 1

        # 3. Removal reasons + virtual group entries for removed_in_phase1
        _set_progress("indexing removals", step / total_steps)
        removed_path = WIKI_DIR / "articles_removed.jsonl"
        if removed_path.exists():
            with removed_path.open("r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    title = d.get("title")
                    reason = d.get("removal_reason", "unknown")
                    if title:
                        REMOVAL_REASONS[title] = reason
                        # Virtual entry so removed articles appear in the listing
                        if title not in META:
                            wc = d.get("word_count", 0)
                            META[title] = {
                                "title": title,
                                "word_count": wc,
                                "tier": tier_for(wc),
                                "group": "removed_in_phase1",
                                "subgroup": reason,  # bucketed by reason
                                "categories": d.get("categories") or [],
                                "scraped_at": d.get("scraped_at"),
                                "removal_reason": reason,
                            }

        # 3.5 External sources (Wikipedia bios + Word of Notch + YouTube transcripts).
        # Loaded into META with title prefixed by source code to avoid wiki collisions.
        _set_progress("loading external sources", step / total_steps)
        for src in EXTERNAL_SOURCES:
            path = EXTERNAL_DIR / src["file"]
            if not path.exists():
                continue
            offset = 0
            with path.open("rb") as f:
                for raw in f:
                    length = len(raw)
                    try:
                        d = json.loads(raw)
                    except Exception:
                        offset += length
                        continue
                    orig_title = d.get("title") or d.get("our_title") or "untitled"
                    display_title = f"[{src['prefix']}] {orig_title}"
                    wc = d.get("word_count", 0)
                    # Pick best date: cleaner-extracted post_date > snapshot timestamp > scraped_at
                    snap_ts = d.get("snapshot_timestamp", "")
                    snap_date = f"{snap_ts[:4]}-{snap_ts[4:6]}-{snap_ts[6:8]}" if len(snap_ts) >= 8 else None
                    META[display_title] = {
                        "title": display_title,
                        "original_title": orig_title,
                        "word_count": wc,
                        "tier": tier_for(wc),
                        "group": src["group"],
                        "also_in": [],
                        "categories": d.get("categories") or [],
                        "scraped_at": d.get("scraped_at") or snap_date,
                        "post_date": d.get("post_date") or snap_date,
                        "source": d.get("source") or src["group"],
                        "license": d.get("license"),
                        "url": d.get("url") or d.get("url_original") or d.get("url_snapshot"),
                        "is_external": True,
                    }
                    EXTERNAL_OFFSETS[display_title] = (str(path), offset, length)
                    offset += length

        # 4. Build BY_GROUP (primary) and BY_GROUP_SECONDARY (also_in) — kept separate
        # so counts reflect primary-only but listings can combine both.
        for title, m in META.items():
            g = m["group"]
            t = m["tier"]
            BY_GROUP.setdefault(g, {}).setdefault(t, []).append(title)
            for sg in m.get("also_in") or []:
                BY_GROUP_SECONDARY.setdefault(sg, {}).setdefault(t, []).append(title)

        for g, tiers in BY_GROUP.items():
            for t in tiers:
                tiers[t].sort(key=str.lower)
        for g, tiers in BY_GROUP_SECONDARY.items():
            for t in tiers:
                tiers[t].sort(key=str.lower)

        INDEX_STATUS["ready"] = True
        INDEX_STATUS["progress"] = 1.0
        INDEX_STATUS["stage"] = "done"
    except Exception as e:
        INDEX_STATUS["error"] = str(e)
        INDEX_STATUS["ready"] = True


def start_indexing_async() -> None:
    """Kick off indexing in a background thread."""
    if INDEX_STATUS["ready"] or INDEX_STATUS["stage"] != "not started":
        return
    INDEX_STATUS["stage"] = "starting"
    t = threading.Thread(target=build_index, daemon=True)
    t.start()


# ============================================================
# Public API
# ============================================================

def get_status() -> dict:
    return dict(INDEX_STATUS)


def get_groups() -> list[dict]:
    """Return super-categories with sub-bucket stats."""
    if not INDEX_STATUS["ready"]:
        return []

    # Compute per-group stats — primary count + secondary count separately
    stats: dict[str, dict] = {}
    all_groups = set(BY_GROUP) | set(BY_GROUP_SECONDARY)
    for g in all_groups:
        tiers = BY_GROUP.get(g, {})
        sec_tiers = BY_GROUP_SECONDARY.get(g, {})
        total = 0
        sec_total = 0
        words = 0
        tier_counts: dict[str, int] = {}
        for tname, _, _ in WORD_TIERS:
            count = len(tiers.get(tname, []))
            tier_counts[tname] = count
            total += count
            sec_total += len(sec_tiers.get(tname, []))
        for titles in tiers.values():
            for title in titles:
                words += META[title]["word_count"]
        stats[g] = {
            "name": g,
            "count": total,
            "secondary_count": sec_total,
            "words": words,
            "tiers": tier_counts,
        }

    # Threshold: a bucket appears in sidebar only if it has primary>=1 OR secondary>=30.
    # This avoids cluttering with hundreds of secondary-only cats with low article counts.
    SECONDARY_ONLY_MIN = 30

    def _bucket_ambiente(g: str, st: dict) -> str:
        """Decide which ambiente a bucket belongs to."""
        if g.startswith("external_"):
            return EXTERNAL_AMBIENTE_NAME
        if "::" in g:
            return g.split("::", 1)[0]
        if g == "removed_in_phase1":
            return "removed_in_phase1"
        # Bucket has primary articles → use their META ambiente (consistent)
        if st["count"] > 0:
            primary_tiers = BY_GROUP.get(g, {})
            for titles in primary_tiers.values():
                if titles:
                    m = META.get(titles[0])
                    if m:
                        full_group = m["group"]
                        if "::" in full_group:
                            return full_group.split("::", 1)[0]
                        return "game_vanilla"
        # Secondary-only bucket → use first secondary article's ambiente
        sec_tiers = BY_GROUP_SECONDARY.get(g, {})
        for titles in sec_tiers.values():
            if titles:
                m = META.get(titles[0])
                if m:
                    full_group = m["group"]
                    if "::" in full_group:
                        return full_group.split("::", 1)[0]
                    return "game_vanilla"
        return "game_vanilla"

    by_ambiente: dict[str, list[dict]] = {}
    for g, st in stats.items():
        if st["count"] == 0 and st["secondary_count"] < SECONDARY_ONLY_MIN:
            continue

        ambiente = _bucket_ambiente(g, st)
        if g.startswith("external_"):
            bucket_label = g.replace("external_", "")
        elif "::" in g:
            bucket_label = g.split("::", 1)[1]
        else:
            bucket_label = g

        st_copy = dict(st)
        st_copy["display_name"] = bucket_label
        by_ambiente.setdefault(ambiente, []).append(st_copy)

    # Sort buckets within each ambiente by primary count desc, then alphabetical
    for amb in by_ambiente:
        by_ambiente[amb].sort(
            key=lambda s: (-s["count"], -s["secondary_count"], s["display_name"].lower())
        )

    # Build output in the order defined by AMBIENTE_LABELS, then external, then leftovers.
    out: list[dict] = []
    used_ambientes: set[str] = set()
    for amb_name, label in AMBIENTE_LABELS:
        if amb_name not in by_ambiente:
            continue
        sub = by_ambiente[amb_name]
        # Mark discardable buckets visually
        for st in sub:
            if st["display_name"] in DISCARDABLE_BUCKETS:
                st["discardable"] = True
        out.append({
            "name": amb_name,
            "label": label,
            "count": sum(s["count"] for s in sub),
            "secondary_count": sum(s["secondary_count"] for s in sub),
            "words": sum(s["words"] for s in sub),
            "subgroups": sub,
        })
        used_ambientes.add(amb_name)

    # External sources (Wikipedia/Notch/YouTube)
    if EXTERNAL_AMBIENTE_NAME in by_ambiente:
        sub = by_ambiente[EXTERNAL_AMBIENTE_NAME]
        out.append({
            "name": EXTERNAL_AMBIENTE_NAME,
            "label": EXTERNAL_AMBIENTE_LABEL,
            "count": sum(s["count"] for s in sub),
            "secondary_count": sum(s["secondary_count"] for s in sub),
            "words": sum(s["words"] for s in sub),
            "subgroups": sub,
        })
        used_ambientes.add(EXTERNAL_AMBIENTE_NAME)

    # Removed-in-phase1 (Phase 1 filter discards)
    if "removed_in_phase1" in by_ambiente:
        sub = by_ambiente["removed_in_phase1"]
        out.append({
            "name": "removed_in_phase1",
            "label": "Removed (Phase 1 filter)",
            "count": sum(s["count"] for s in sub),
            "secondary_count": sum(s["secondary_count"] for s in sub),
            "words": sum(s["words"] for s in sub),
            "subgroups": sub,
        })
        used_ambientes.add("removed_in_phase1")

    # Anything else (shouldn't happen with current ambientes, but defensive)
    leftovers = [s for amb, subs in by_ambiente.items() if amb not in used_ambientes for s in subs]
    if leftovers:
        out.append({
            "name": "leftovers",
            "label": "Other",
            "count": sum(s["count"] for s in leftovers),
            "secondary_count": sum(s["secondary_count"] for s in leftovers),
            "words": sum(s["words"] for s in leftovers),
            "subgroups": leftovers,
        })

    return out


def _word_delta(title: str) -> int:
    """Absolute delta cleaned vs raw, for sort. 0 if cleaned not available."""
    raw = WORD_COUNTS.get("raw", {}).get(title, 0)
    cleaned = WORD_COUNTS.get("cleaned", {}).get(title, 0)
    return abs(raw - cleaned)


def list_articles(
    group: str,
    tier: str | None = None,
    q: str | None = None,
    sort: str = "alpha",
    offset: int = 0,
    limit: int = 200,
) -> dict:
    """List articles in a group (optionally filtered by tier or title query)."""
    if not INDEX_STATUS["ready"]:
        return {"items": [], "total": 0, "ready": False}

    tiers = BY_GROUP.get(group, {})
    sec_tiers = BY_GROUP_SECONDARY.get(group, {})
    if tier and tier != "all":
        titles = list(tiers.get(tier, [])) + list(sec_tiers.get(tier, []))
    else:
        titles = []
        for tname, _, _ in WORD_TIERS:
            titles.extend(tiers.get(tname, []))
            titles.extend(sec_tiers.get(tname, []))
    # Dedupe (a title shouldn't normally be in both, but defensive)
    seen: set[str] = set()
    titles = [t for t in titles if not (t in seen or seen.add(t))]

    # Filter by query
    if q:
        ql = q.lower()
        titles = [t for t in titles if ql in t.lower()]

    # Sort
    if sort == "delta":
        titles.sort(key=lambda t: -_word_delta(t))
    elif sort == "wc":
        titles.sort(key=lambda t: -META[t]["word_count"])
    elif sort in ("date_asc", "date"):
        # Oldest first. Items without a date sink to the end.
        titles.sort(key=lambda t: (META[t].get("post_date") or "9999", t.lower()))
    elif sort == "date_desc":
        # Newest first.
        titles.sort(key=lambda t: ((META[t].get("post_date") or "0000"), t.lower()), reverse=True)
    else:
        titles.sort(key=str.lower)

    total = len(titles)
    page = titles[offset: offset + limit]

    items = []
    for t in page:
        m = META[t]
        # External entries only have "cleaned"; wiki entries query OFFSETS
        if m.get("is_external"):
            avail = ["cleaned"]
            wcs = {"cleaned": m["word_count"]}
            delta = None
        else:
            avail = [v for v in AVAILABLE_VERSIONS if t in OFFSETS.get(v, {})]
            wcs = {v: WORD_COUNTS.get(v, {}).get(t) for v in avail}
            delta = _word_delta(t) if "raw" in WORD_COUNTS and "cleaned" in WORD_COUNTS else None
        items.append({
            "title": t,
            "word_count": m["word_count"],
            "tier": m["tier"],
            "group": m["group"],
            "also_in": m.get("also_in") or [],
            "is_primary_here": m["group"] == group,
            "available_versions": avail,
            "version_word_counts": wcs,
            "removal_reason": m.get("removal_reason"),
            "delta": delta,
            "is_external": m.get("is_external", False),
            "post_date": m.get("post_date"),
        })

    return {"items": items, "total": total, "ready": True}


def _read_at(version: str, title: str) -> dict | None:
    """Random-access read of one article from a jsonl by precomputed offset."""
    off = OFFSETS.get(version, {}).get(title)
    if not off:
        return None
    file_name = next((v["file"] for v in ARTICLE_VERSIONS if v["name"] == version), None)
    if not file_name:
        return None
    path = WIKI_DIR / file_name
    offset, length = off
    with path.open("rb") as f:
        f.seek(offset)
        raw = f.read(length)
    try:
        return json.loads(raw)
    except Exception:
        return None


def _read_external_at(title: str) -> dict | None:
    """Random-access read of an external (non-wiki) entry."""
    info = EXTERNAL_OFFSETS.get(title)
    if not info:
        return None
    file_path, offset, length = info
    with open(file_path, "rb") as f:
        f.seek(offset)
        raw = f.read(length)
    try:
        return json.loads(raw)
    except Exception:
        return None


def get_article(title: str, version: str) -> dict | None:
    """Get one article in one version. Returns None if not present."""
    m = META.get(title) or {}

    # External entries: only "cleaned" version exists
    if m.get("is_external"):
        if version != "cleaned":
            return None
        data = _read_external_at(title)
        if not data:
            return None
        return {
            "title": title,
            "version": "cleaned",
            "text": data.get("text", ""),
            "word_count": data.get("word_count", 0),
            "categories": data.get("categories") or [],
            "scraped_at": m.get("scraped_at"),
            "removal_reason": None,
            "available_versions": ["cleaned"],
            "group": m.get("group"),
            "also_in": m.get("also_in") or [],
            "tier": m.get("tier"),
            "source": m.get("source"),
            "license": m.get("license"),
            "url": m.get("url"),
            "original_title": m.get("original_title"),
        }

    # Wiki entries: random access via OFFSETS
    data = _read_at(version, title)
    if not data:
        return None
    avail = [v for v in AVAILABLE_VERSIONS if title in OFFSETS.get(v, {})]
    return {
        "title": title,
        "version": version,
        "text": data.get("text", ""),
        "word_count": data.get("word_count", 0),
        "categories": data.get("categories") or [],
        "scraped_at": data.get("scraped_at"),
        "removal_reason": data.get("removal_reason") or m.get("removal_reason"),
        "available_versions": avail,
        "group": m.get("group"),
        "also_in": m.get("also_in") or [],
        "tier": m.get("tier"),
    }


def get_multi(title: str, versions: list[str]) -> dict:
    """Batch get one article across multiple versions (for prefetch)."""
    out: dict[str, dict | None] = {}
    for v in versions:
        out[v] = get_article(title, v)
    return out


def search_global(q: str, limit: int = 20) -> list[dict]:
    """Global title search across all groups (Cmd+K palette)."""
    if not q or not INDEX_STATUS["ready"]:
        return []
    ql = q.lower()
    matches = []
    for title, m in META.items():
        if ql in title.lower():
            matches.append({
                "title": title,
                "group": m["group"],
                "tier": m["tier"],
                "word_count": m["word_count"],
            })
            if len(matches) >= limit * 5:
                break
    # Prefer titles that start with the query
    matches.sort(key=lambda x: (
        not x["title"].lower().startswith(ql),
        x["title"].lower(),
    ))
    return matches[:limit]


def peek(title: str, max_chars: int = 240) -> str | None:
    """Return first N chars of cleaned text for hover preview."""
    if title not in OFFSETS.get("cleaned", {}):
        # Fallback to raw if cleaned absent
        for v in ("raw", "filtered"):
            if title in OFFSETS.get(v, {}):
                d = _read_at(v, title)
                if d:
                    return (d.get("text") or "")[:max_chars]
        return None
    d = _read_at("cleaned", title)
    if not d:
        return None
    return (d.get("text") or "")[:max_chars]


def get_versions_meta() -> list[dict]:
    """Return version definitions including which ones have files on disk."""
    out = []
    for v in ARTICLE_VERSIONS:
        out.append({
            **{k: v[k] for k in ("name", "phase", "label")},
            "available": v["name"] in AVAILABLE_VERSIONS,
        })
    return out


def get_meta_cat_regex() -> str:
    """Expose the META_CATEGORY_PATTERNS as a single regex string for the frontend
    to use when filtering wiki-maintenance cats out of the viewer's metadata strip."""
    from scraper.explore_subgroups import META_CATEGORY_PATTERNS
    return "|".join(META_CATEGORY_PATTERNS)


# ============================================================
# Misclassification log
# ============================================================

import time
from threading import Lock

FLAG_LOG_PATH = ROOT / "raw_data" / "_exploration" / "misclassifications.jsonl"
_flag_lock = Lock()


def log_flag(entry: dict) -> dict:
    """Append a misclassification flag to the log file. Returns the saved entry."""
    FLAG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    title = entry.get("title", "")
    m = META.get(title) or {}
    saved = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "title": title,
        "current_group": entry.get("current_group") or m.get("group"),
        "suggested_group": entry.get("suggested_group", "").strip() or None,
        "note": (entry.get("note") or "").strip() or None,
        "categories": m.get("categories", []),
        "word_count": m.get("word_count"),
        "tier": m.get("tier"),
        "removal_reason": m.get("removal_reason"),
    }
    with _flag_lock:
        with FLAG_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(saved, ensure_ascii=False) + "\n")
    return saved


def list_flags() -> list[dict]:
    if not FLAG_LOG_PATH.exists():
        return []
    out = []
    with FLAG_LOG_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out
