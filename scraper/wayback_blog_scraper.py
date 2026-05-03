"""
wayback_blog_scraper.py — Word of Notch via Wayback Machine.

The Word of Notch fue el blog personal de Markus Persson (notch.tumblr.com),
borrado el 2021-08-26. Wayback Machine tiene snapshots arquivados.

Output: raw_data/external/word_of_notch.jsonl
Cada línea: {post_id, title, text, source: "word_of_notch_wayback",
             url_original, url_snapshot, snapshot_timestamp, word_count, scraped_at}

Uso:
    python -m scraper.wayback_blog_scraper                    # descarga 50 posts
    python -m scraper.wayback_blog_scraper --limit 200        # más posts
    python -m scraper.wayback_blog_scraper --since 2009 --until 2012   # filtra años
    python -m scraper.wayback_blog_scraper --force            # re-scrape
"""
from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "raw_data" / "external" / "word_of_notch.jsonl"

CDX_API = "http://web.archive.org/cdx/search/cdx"
WAYBACK = "https://web.archive.org/web"
USER_AGENT = "MineGPT-research/0.1 (educational, non-commercial; contact: github.com/FelipeJackFox/minegpt)"

# Match a tumblr post URL like /post/<id>/<slug>
POST_RE = re.compile(r"/post/(\d+)/([a-z0-9-]+)/?$")


def fetch_post_snapshots(since: int | None, until: int | None) -> list[dict]:
    """Get list of unique post URLs from Wayback CDX API."""
    params = {
        "url": "notch.tumblr.com/post/*",
        "output": "json",
        "fl": "timestamp,original,statuscode",
        "filter": "statuscode:200",
        "collapse": "urlkey",
    }
    headers = {"User-Agent": USER_AGENT}
    print("  Fetching CDX index... (this may take 30-60s)")
    r = requests.get(CDX_API, params=params, headers=headers, timeout=120)
    if r.status_code != 200:
        print(f"  CDX fetch failed: HTTP {r.status_code}")
        return []
    data = r.json()
    if len(data) <= 1:
        return []

    # Dedupe by post ID, keep earliest viable snapshot per post
    by_post: dict[str, dict] = {}
    for row in data[1:]:
        ts, url, _status = row
        m = POST_RE.search(url)
        if not m:
            continue
        post_id, slug = m.group(1), m.group(2)
        # Filter by year if requested
        year = int(ts[:4])
        if since and year < since:
            continue
        if until and year > until:
            continue
        # Skip /embed, /amp, ?route variants
        if "/embed" in url or "/amp" in url or "?route" in url:
            continue
        # Keep the earliest snapshot per post_id
        if post_id not in by_post or ts < by_post[post_id]["timestamp"]:
            by_post[post_id] = {
                "post_id": post_id,
                "slug": slug,
                "timestamp": ts,
                "original": url,
            }
    return sorted(by_post.values(), key=lambda x: x["timestamp"])


def parse_post_html(html: str) -> tuple[str, str]:
    """Extract (title, text) from a tumblr post HTML."""
    soup = BeautifulSoup(html, "html.parser")
    # Try og:title and og:description first
    title = ""
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()
    elif soup.title:
        title = soup.title.text.strip()

    # Body: try article/post content selectors
    candidates = [
        ("article",),
        ("div", {"class": "post-content"}),
        ("div", {"class": "post"}),
        ("div", {"class": "body"}),
        ("div", {"class": "entry-content"}),
        ("div", {"id": "content"}),
        ("main",),
    ]
    body_text = ""
    for spec in candidates:
        if len(spec) == 1:
            el = soup.find(spec[0])
        else:
            el = soup.find(spec[0], spec[1])
        if el:
            text = el.get_text("\n", strip=True)
            if len(text) > 80:
                body_text = text
                break

    if not body_text:
        # Fallback to og:description (just preview, but better than nothing)
        og_desc = soup.find("meta", property="og:description")
        if og_desc and og_desc.get("content"):
            body_text = og_desc["content"].strip()

    # Strip Wayback toolbar artifacts
    body_text = re.sub(r"Wayback Machine.*?https?://[^\s]*", "", body_text, flags=re.DOTALL)
    body_text = re.sub(r"WAYBACK MACHINE.*", "", body_text, flags=re.DOTALL)
    body_text = re.sub(r"\n{3,}", "\n\n", body_text)
    body_text = body_text.strip()

    return title, body_text


def fetch_post(snapshot: dict) -> dict | None:
    """Fetch + parse a single archived post."""
    ts = snapshot["timestamp"]
    orig = snapshot["original"]
    snap_url = f"{WAYBACK}/{ts}/{orig}"
    headers = {"User-Agent": USER_AGENT}
    try:
        r = requests.get(snap_url, headers=headers, timeout=30)
    except Exception as e:
        return None
    if r.status_code != 200:
        return None
    title, text = parse_post_html(r.text)
    if not text or len(text.split()) < 10:
        return None
    return {
        "post_id": snapshot["post_id"],
        "slug": snapshot["slug"],
        "title": title or snapshot["slug"].replace("-", " ").title(),
        "text": text,
        "categories": [],
        "source": "word_of_notch_wayback",
        "license": "public blog posts by Markus Persson; archived by Internet Archive; educational use",
        "url_original": orig,
        "url_snapshot": snap_url,
        "snapshot_timestamp": ts,
        "word_count": len(text.split()),
        "scraped_at": datetime.utcnow().isoformat(timespec="seconds"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50, help="Max posts to fetch")
    parser.add_argument("--since", type=int, default=None, help="Min year (inclusive)")
    parser.add_argument("--until", type=int, default=None, help="Max year (inclusive)")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--rate", type=float, default=2.0, help="Seconds between requests")
    args = parser.parse_args()

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    already: set[str] = set()
    if OUTPUT.exists() and not args.force:
        with OUTPUT.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        already.add(json.loads(line)["post_id"])
                    except Exception:
                        pass
    print(f"  Already saved: {len(already)} posts")

    snapshots = fetch_post_snapshots(args.since, args.until)
    print(f"  Found {len(snapshots)} unique posts in CDX index")

    todo = [s for s in snapshots if s["post_id"] not in already][: args.limit]
    print(f"  Will fetch {len(todo)} posts (limit={args.limit})")
    print()

    mode = "w" if args.force else "a"
    n_ok, n_miss = 0, 0
    with OUTPUT.open(mode, encoding="utf-8") as f:
        for i, snap in enumerate(todo, 1):
            print(f"  [{i}/{len(todo)}] {snap['post_id']} ({snap['timestamp'][:8]}) {snap['slug'][:50]}", end=" ")
            entry = fetch_post(snap)
            if not entry:
                print("MISSING")
                n_miss += 1
            else:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                f.flush()
                print(f"OK ({entry['word_count']:,}w)")
                n_ok += 1
            time.sleep(args.rate)

    print()
    print(f"Done. {n_ok} new, {n_miss} missing/failed.")
    print(f"Output: {OUTPUT}")


if __name__ == "__main__":
    main()
