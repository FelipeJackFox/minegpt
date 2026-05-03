"""
_token_freq_analysis.py - Produce candidate fusion tokens for Phase 6 Layer C.

Reads articles_hardened.jsonl (the output of hardening_v2 with Phase 6 still a
no-op). Extracts every lowercase token of length >= MIN_LEN with no internal
spaces. These are word-fusion candidates created by wiki-template stripping in
the prior cleaning pass.

Outputs:
  scraper/_layer_c_candidates.json   ordered (token, freq, auto_split) review list
  scraper/_layer_c_glue.json         auto-split dict {pattern: replacement}
                                     consumed by hardening_v2.phase_6_*

Run after hardening_v2 has executed (Phase 6 is the LAST phase to fill in).

Usage:
  python -m scraper._token_freq_analysis
  python -m scraper._token_freq_analysis --min-len 10 --top 800
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent.parent
HARDENED = ROOT / "raw_data" / "wiki" / "articles_hardened.jsonl"
CANDIDATES_OUT = Path(__file__).parent / "_layer_c_candidates.json"
GLUE_OUT = Path(__file__).parent / "_layer_c_glue.json"

# Word list for greedy longest-match split. Keep this small + curated. NEVER add
# fragment morphemes (`ing`, `ed`, `s`) — they create false splits.
WORDLIST: set[str] = {
    # Articles + prepositions + conjunctions
    "a", "an", "the", "of", "in", "on", "at", "to", "for", "from", "by",
    "with", "is", "are", "was", "were", "be", "been", "being", "and", "or",
    "but", "not", "as", "than", "then", "when", "where", "what", "which",
    "who", "via", "per", "into", "onto", "until", "while", "after", "before",
    "during", "such",
    # Common verbs (full forms, no morphemes)
    "do", "does", "did", "have", "has", "had", "will", "would", "can",
    "could", "may", "might", "must", "should", "go", "went", "gone",
    "make", "made", "take", "took", "give", "gave", "see", "saw", "seen",
    "say", "said", "says", "use", "used", "using", "show", "showed",
    "shown", "tell", "told", "spawn", "spawns", "spawned", "drop", "drops",
    "dropped", "kill", "killed", "kills", "find", "found", "place",
    "placed", "places", "open", "opens", "opened", "build", "built",
    "craft", "crafted", "crafting", "smelt", "smelting", "fight",
    "fights", "now", "follow", "follows", "ride", "rides", "rode",
    "shear", "shearing", "trade", "trades", "traded", "want", "wants",
    "need", "needs", "burn", "burns", "burned", "break", "breaks",
    "broke", "broken", "create", "creates", "created", "destroy",
    "destroys", "destroyed", "produce", "produces", "produced", "renew",
    "renewable", "stack", "stackable", "drop", "growable", "obtainable",
    "stop", "stops", "stopped", "start", "starts", "started", "added",
    "remove", "removed", "removes", "become", "becomes", "became",
    # Pronouns / determiners
    "it", "its", "his", "her", "their", "our", "your", "my", "you", "we",
    "they", "them", "him", "she", "he", "this", "that", "these", "those",
    "every", "each", "all", "any", "some", "no", "many", "few",
    # Adjectives / adverbs (selective — full English forms only)
    "first", "second", "third", "last", "new", "old", "small", "large",
    "big", "long", "short", "fast", "slow", "best", "good", "bad",
    "only", "also", "via",
    # Minecraft nouns (singular + plural where both occur)
    "block", "blocks", "item", "items", "mob", "mobs", "tool", "tools",
    "ore", "ores", "wood", "stone", "stones", "diamond", "diamonds",
    "iron", "gold", "coal", "redstone", "lapis", "emerald", "emeralds",
    "netherite", "village", "villager", "villagers",
    "zombie", "zombies", "creeper", "creepers", "spider", "spiders",
    "skeleton", "skeletons", "enderman", "endermen", "wolf", "wolves",
    "cat", "cats", "dog", "dogs", "cow", "cows", "pig", "pigs", "sheep",
    "chicken", "chickens", "horse", "horses", "donkey", "rabbit",
    "rabbits", "warden", "wardens", "goat", "goats", "axolotl", "axolotls",
    "world", "worlds", "biome", "biomes", "chunk", "chunks", "dimension",
    "dimensions", "overworld", "nether", "end",
    "portal", "portals", "fire", "lava", "water", "ice", "snow", "rain",
    "torch", "torches", "chest", "chests", "barrel", "barrels", "hopper",
    "hoppers", "furnace", "furnaces", "anvil", "anvils",
    "potion", "potions", "effect", "effects", "enchantment", "enchantments",
    "armor", "weapon", "weapons", "sword", "swords", "axe", "axes",
    "pickaxe", "pickaxes", "shovel", "shovels", "bow", "arrow", "arrows",
    "trident", "shield", "helmet", "chestplate", "leggings", "boots",
    "barrier", "beacon", "fireball", "flower", "flowers", "player",
    "players", "witch", "witches", "hut", "huts", "command", "commands",
    "version", "versions", "edition", "editions",
    "achievement", "advancement", "achievements", "advancements",
    "creature", "creatures", "hostile", "passive", "neutral", "boss",
    "bosses", "structure", "structures", "feature", "features", "vein",
    "veins", "tree", "trees", "leaf", "leaves", "sapling", "saplings",
    "crop", "crops", "wheat", "carrot", "potato", "beetroot", "cookie",
    "cake", "bread", "soup", "stew", "fish", "salmon", "cod", "pufferfish",
    "minecraft", "java", "bedrock", "education", "console",
    "screen", "menu", "inventory", "hotbar",
    "food", "trial", "spawn", "spawns", "particle", "particles", "light",
    "darkness", "soul", "soils", "soil", "next", "renewable", "stackable",
    "rabbit", "campfire", "campfires", "purpur", "fermented", "suspicious",
    "kelp", "rod", "rods", "trail", "ruins", "smithing", "template",
    "templates",
    # Tail extras commonly seen in fusions
    "pots", "buckets", "heart", "hearts", "amount", "level", "levels",
    "experience", "obtainable", "obtained", "obtaining", "added",
}


def greedy_split(token: str, max_words: int = 4) -> str | None:
    """Greedy longest-match split using WORDLIST. Returns the split string
    or None if the token can't be cleanly partitioned into 2..max_words
    known words."""
    pieces: list[str] = []
    i = 0
    n = len(token)
    while i < n:
        best = None
        for j in range(n, i, -1):
            if token[i:j] in WORDLIST:
                best = token[i:j]
                break
        if best is None:
            return None
        pieces.append(best)
        i += len(best)
        if len(pieces) > max_words:
            return None
    if len(pieces) < 2:
        return None
    return " ".join(pieces)


def analyze(min_len: int, top: int) -> None:
    if not HARDENED.exists():
        print(f"Error: {HARDENED} not found. Run hardening_v2 first.")
        return

    print(f"Reading {HARDENED}...")
    counter: Counter[str] = Counter()
    pattern = re.compile(rf"\b[a-z]{{{min_len},}}\b")

    n_articles = 0
    with open(HARDENED, encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            text = rec.get("text", "")
            for tok in pattern.findall(text):
                counter[tok] += 1
            n_articles += 1

    print(f"Articles: {n_articles:,}, unique long tokens: {len(counter):,}")

    top_candidates = counter.most_common(top)

    candidates: list[dict] = []
    auto_splits: dict[str, str] = {}
    for tok, freq in top_candidates:
        split = greedy_split(tok)
        candidates.append({"token": tok, "freq": freq, "auto_split": split})
        if split:
            auto_splits[rf"\b{tok}\b"] = split

    with open(CANDIDATES_OUT, "w", encoding="utf-8") as f:
        json.dump(candidates, f, indent=2, ensure_ascii=False)

    with open(GLUE_OUT, "w", encoding="utf-8") as f:
        json.dump(auto_splits, f, indent=2, ensure_ascii=False)

    print(f"Wrote {len(candidates)} candidates to {CANDIDATES_OUT.name}")
    print(f"Wrote {len(auto_splits)} auto-splits to {GLUE_OUT.name}")
    no_split = [c for c in candidates if c["auto_split"] is None]
    print(f"Tokens that did NOT auto-split: {len(no_split)}")
    print()
    print("Top 30 with auto-split:")
    shown = 0
    for c in candidates:
        if c["auto_split"] and shown < 30:
            print(f"  {c['freq']:>6}  {c['token']:>40}  ->  {c['auto_split']}")
            shown += 1
    print()
    print("Top 30 WITHOUT auto-split (need manual review):")
    for c in no_split[:30]:
        print(f"  {c['freq']:>6}  {c['token']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-len", type=int, default=12)
    parser.add_argument("--top", type=int, default=500)
    args = parser.parse_args()
    analyze(args.min_len, args.top)
