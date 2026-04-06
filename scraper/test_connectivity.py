"""
test_connectivity.py — Valida que las APIs de scraping responden
=================================================================

Ejecutar ANTES de lanzar scraping largo para evitar sorpresas.

Uso:
    python -m scraper.test_connectivity
"""

import requests
import json
import sys

WIKI_API = "https://minecraft.wiki/api.php"
ARCTIC_API = "https://arctic-shift.photon-reddit.com/api"
HEADERS = {"User-Agent": "MineGPT-Educational-Scraper/1.0 (connectivity test)"}


def test_wiki():
    print("Testing minecraft.wiki API...", end=" ")
    try:
        resp = requests.get(WIKI_API, params={
            "action": "query", "list": "allpages", "aplimit": "3", "format": "json"
        }, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        pages = data.get("query", {}).get("allpages", [])
        print(f"OK — {len(pages)} pages returned")
        for p in pages:
            print(f"  - {p['title']}")
        return True
    except Exception as e:
        print(f"FAILED — {e}")
        return False


def test_arctic_shift():
    print("Testing Arctic Shift API...", end=" ")
    try:
        resp = requests.get(f"{ARCTIC_API}/posts/search", params={
            "subreddit": "Minecraft", "limit": 3
        }, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        posts = data.get("data", [])
        print(f"OK — {len(posts)} posts returned")
        for p in posts[:3]:
            print(f"  - [{p.get('score', 0)} pts] {p.get('title', '?')[:60]}")
        return True
    except Exception as e:
        print(f"FAILED — {e}")
        return False


if __name__ == "__main__":
    print("=" * 50)
    print("MineGPT — Test de conectividad")
    print("=" * 50)

    wiki_ok = test_wiki()
    print()
    arctic_ok = test_arctic_shift()

    print("\n" + "=" * 50)
    if wiki_ok and arctic_ok:
        print("Todo OK — listo para scraping.")
    else:
        print("HAY PROBLEMAS — revisa la conexión antes de continuar.")
        sys.exit(1)
