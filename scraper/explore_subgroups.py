"""
explore_subgroups.py — Cat-driven 2-layer classifier for Minecraft wiki articles.

LAYER A: Ambiente (1 of 7, mutually exclusive)
  wiki_meta, spinoff, april_fools, education_edition, tutorial,
  media_franchise, real_world, versions, game_vanilla (default)

LAYER B: Bucket within ambiente
  Bucket name = exact wiki category (Manufactured_blocks, Animal_mobs, Light_sources, ...)
  Title-based virtual buckets for cases without a useful cat
  (Crafting_recipes, Structure_subpages, Lists, Block_states_reference, Edition_overview)

LAYER C: Hierarchy
  When article matches multiple cats, PRIMARY_PRIORITY (ordered list) decides
  which is primary. The rest become also_in via secondary_groups().

OUTPUT: every semantic cat of the article ends up either as primary OR in also_in,
        so the article remains accessible from every relevant lens at Phase 4
        transformation/Q&A time.

Generates: raw_data/_exploration/subgroups_report.md
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "raw_data" / "wiki" / "articles_cleaned.jsonl"
OUTPUT = ROOT / "raw_data" / "_exploration" / "subgroups_report.md"


# ============================================================
# Meta cat filter (139 cats, ~17K mentions of wiki maintenance)
# ============================================================

META_CATEGORY_PATTERNS = [
    r"^Pages_with_",
    r"^Pages_using_",
    r"^Pages_needing_",
    r"^Pages_missing_",
    r"^Pages_",  # catch-all
    r"^Articles_to_be_",
    r"^Articles_with_empty_",
    r"^Articles_needing_",
    r"^Articles_missing_",
    r"^Articles_",  # catch-all
    r"^Minecraft_Work_in_progress",
    r"^Stubs$",
    r"^Minecraft_stubs$",
    r"_stubs$",
    r"^Verify$",
    r"^Verify_for_",
    r"^Verify_changelog_",
    r"^Verify_current_",
    r"^Check_version$",
    r"^Check_the_code$",
    r"^Testing_needed$",
    r"^Cleanup_with_a_reason$",
    r"^Cleanup_without_a_reason$",
    r"^Article_cleanup$",
    r"^Pending_",
    r"^Pending_split$",
    r"^Current_split$",
    r"^Missing_discussion_link",
    r"^Unknown_.*_version_history$",
    r"^Unknown_version_history$",
    r"^Information_needed$",
    r"^Citation_needed$",
    r"^Ajax_loaded_pages$",
    r"^Featured_articles$",
    r"^Needs_updating$",
    r"^CC_BY-SA_pages$",
    r"^Incomplete_lists$",
    r"^Asset_history_pages$",
    r"^Technical_block_history_sections$",
    r"^Blocks_without_map_color$",
    r"^Missing_blast_resistance$",
    r"^Missing_stackability$",
    r"^Resources_with_invalid_renewability$",
    r"^Createable_blocks$",
    r"^Readable_by_comparators$",
]
META_RE = re.compile("|".join(META_CATEGORY_PATTERNS))

# Edition tags are not "meta" but they're also not useful as bucket names.
# Filtered out of the cat→bucket priority list but kept visible in viewer.
EDITION_TAG_CATS = {
    "Bedrock_Edition", "Java_Edition", "Legacy_Console_Edition",
    "Bedrock_Edition_specific_information", "Java_Edition_specific_information",
    "Renewable_resources", "Stackable_resources",
    "Non-renewable_resources", "Non-stackable_resources",
}


# ============================================================
# Word count tiers
# ============================================================

WORD_TIERS = [
    ("10-49",     10,    50),
    ("50-99",     50,    100),
    ("100-499",   100,   500),
    ("500-999",   500,   1000),
    ("1000-4999", 1000,  5000),
    ("5000+",     5000,  10**9),
]


def tier_for(wc: int) -> str:
    for name, lo, hi in WORD_TIERS:
        if lo <= wc < hi:
            return name
    return "<10"


# ============================================================
# LAYER A: Ambiente detection
# ============================================================

# 1. wiki_meta — File:/Template: pages, etc.
WIKI_META_TITLE_PREFIXES = ("File:", "Template:", "Help:", "Minecraft Wiki:")
WIKI_META_CATS = {
    "Files_with_a_license_template", "Mojang_images", "Notice_templates",
    "Template_styles", "Documentation_pages", "Soft_redirects",
    "Version_banners", "Minecraft_Wiki",
}

# 2. spinoff
SPINOFF_TITLE_PREFIXES = (
    "Dungeons:", "MCD:", "Legends:", "Earth:",
    "Minecraft Earth:", "Story Mode:",
)

# 3. april_fools (joke content from April Fools' day releases)
APRIL_FOOLS_CATS = {
    "Joke_features", "Joke_blocks", "Joke_items", "Joke_mobs",
    "Joke_entities", "Joke_biomes", "Joke_effects", "Joke_dimensions",
    "Joke_block_renders", "April_Fools'", "April_Fools",
}
APRIL_FOOLS_TITLE_RE = re.compile(r"\(April Fools'? joke\)|\bApril Fools'?\b", re.IGNORECASE)

# 4. education_edition (non-canonical for vanilla v1)
EDUCATION_CATS = {
    "Minecraft_Education", "Minecraft_Education_specific_information",
    "MinecraftEdu", "MinecraftEdu_blocks", "MinecraftEdu_items",
    "MinecraftEdu_features", "Education_Edition_exclusive",
    "Education_Edition_features", "Minecraft_Education_features",
    "Chemistry_Resource_Pack",
}

# 5. tutorial (community-written guides, NOT official game content)
TUTORIAL_CATS = {"Tutorials", "Java_Edition_guides", "Bedrock_Edition_guides"}
TUTORIAL_TITLE_PREFIXES = ("Tutorial:", "Tutorials/")
# Redstone tutorial-style root pages (1-2 levels deep) — NOT actual redstone components
TUTORIAL_REDSTONE_TITLES = {
    "Redstone circuits", "Redstone components", "Redstone mechanics",
    "MCRedstoneSim schematics",
}

# 6. media_franchise
MEDIA_CATS = {
    "Minecraft_Mini-Series", "Mini-Series_episodes", "Minecraft_Mini-Series_characters",
    "Minecraft_Mini-Series_locations",
    "M.A.R.I.L.L.A._and_Narrator_series", "Mob_Squad", "Minecraft:_Mob_Squad_chapters",
    "A_Minecraft_Movie", "A_Minecraft_Movie_mobs", "A_Minecraft_Movie_characters",
    "A_Minecraft_Movie_locations", "A_Minecraft_Movie_objects",
    "Comic_books", "Live_action_content", "Animated_content",
    "Books", "Fiction", "Nick_Eliopulos_novels", "Max_Brooks_novels", "Meta_novels",
    "Adventure_maps", "Game_trailers", "Editorials",
    "Online_content", "Minecraft_(Dark_Horse_Comics)_series",
    "Minecraft:_Story_Mode", "Maps", "Science_fiction",
    "Minecraft_(franchise)",
}
MEDIA_CHAPTER_TOKEN = "_chapters"

# 7. real_world (people, companies, events, history)
# Strong real_world cats — claim ambient even if artículo tiene cats vanilla
REAL_WORLD_STRONG_CATS = {
    # People (real-life individuals)
    "Actors", "YouTubers", "Streamers", "Hosts",
    "Players", "Students", "Mobologists", "Musicians",
    # Companies (corporate entities)
    "Mojang_Studios", "Microsoft", "Companies",
    # Events
    "MINECON", "Minecraft_Live", "Events", "Historical_events",
    "Live_streams", "Eerie_Mojang_Office_Party",
    "A_Minecraft_Movie_Live_Event",
    # Community / business
    "Community", "Collaborations", "Cross-franchise_promotions",
    "Merchandise", "Discontinued",
    "Minecraft_Marketplace", "Event_servers",
    "Minecraft_Blast", "Minecraft_4k", "Mojam_games",
    "Minecraft_Earth", "Minecraft_Story_Mode", "Minecraft_Experience",
    "China_Edition",
}

# History / anniversary cats — DO NOT claim ambient if article has vanilla content cats
# (Cake has 10th_Anniversary but is primarily a block. The anniversary goes to also_in.)
HISTORY_CATS_SOFT = {
    "History",
    "15th_Anniversary", "10th_Anniversary",
    "MCC_x_Minecraft_15th_Anniversary_Party",
    "Birthday_skin_packs",
}

# Combined for legacy use (kept name for any external reference)
REAL_WORLD_CATS = REAL_WORLD_STRONG_CATS | HISTORY_CATS_SOFT

# Vanilla strong cats — if article has these AND a soft history cat,
# stays in game_vanilla (history goes to also_in).
VANILLA_STRONG_CATS = {
    "Blocks", "Manufactured_blocks", "Natural_blocks", "Generated_structure_blocks",
    "Utility_blocks", "Non-solid_blocks", "Technical_blocks",
    "Items", "Tools", "Weapons", "Armor", "Food",
    "Mobs", "Animal_mobs", "Hostile_mobs", "Monster_mobs",
    "Passive_mobs", "Aquatic_mobs", "Tameable_mobs", "Bosses",
    "Plants", "Crops", "Ore", "Entities", "Block_entities",
    "Game_mechanics", "Status_effects", "Potion_effects", "Effects",
    "Enchantments", "Generated_structures", "Biomes",
    "Sounds", "Music_Discs",
}

# Hardcoded company titles — disambiguate Mojang_Studios cat between
# "the company" article and "person who works for the company" articles.
COMPANY_TITLES_OVERRIDE = {
    "Mojang Studios", "Mojang", "Mojang AB", "Microsoft",
    "Sony", "Nintendo", "4J Studios", "Telltale Games",
}

# 8. versions (snapshots, betas, previews — non-content metadata pages)
VERSION_TOKEN_RE = re.compile(
    r".+_(versions|previews|betas|snapshots|development_versions?)$"
)
VERSION_CATS_EXTRA = {
    "Lost_versions", "Versions", "Versions_with_unofficial_names",
    "Release_timeline_subpages", "Development_version_lists",
    "Java_Edition_release_timeline", "Bedrock_Edition_release_timeline",
    "Minecraft_Education_release_timeline", "Named_updates",
}
VERSION_META_CATS_EXCLUDE = {
    "Unknown_Bedrock_version_history", "Unknown_Java_version_history",
    "Unknown_Console_version_history", "Unknown_Java_Indev_version_history",
    "Unknown_Java_Beta_version_history", "Unknown_Java_Classic_version_history",
    "Unknown_Java_Alpha_version_history", "Unknown_Pocket_Edition_version_history",
    "Unknown_MinecraftEdu_version_history", "Unknown_Education_Edition_version_history",
    "Unknown_version_history",
    "Check_version", "Check_the_code",
}


# ============================================================
# LAYER B: Bucket priority within game_vanilla
# ============================================================

# Title-based bucket overrides (FIRST priority within game_vanilla)
def _title_based_bucket(t: str, s: set[str]) -> str | None:
    if t.startswith("Crafting/"):
        return "Crafting_recipes"
    if t.startswith("Banner/") and ("crafting" in t.lower() or "pattern" in t.lower()):
        return "Crafting_recipes"
    if t.endswith("/Structure"):
        return "Structure_subpages"
    if t.endswith("/BS"):
        return "Block_states_reference"
    if t.startswith("List of "):
        return "Lists"
    if "/Before " in t:
        return "Mechanic_history"
    # Redstone real components: title "Redstone X" with cat Redstone (not Ore)
    if t.startswith("Redstone ") and "Redstone" in s and "Ore" not in s:
        return "Redstone_mechanics"
    # Edition overview pages
    if t in EDITION_OVERVIEW_TITLES:
        return "Edition_overview"
    return None

EDITION_OVERVIEW_TITLES = {
    "Bedrock Edition", "Java Edition", "Minecoin",
    "Pocket Edition", "Education Edition", "Minecraft Education",
    "Legacy Console Edition", "Xbox 360 Edition", "Xbox One Edition",
    "PlayStation 3 Edition", "PlayStation 4 Edition", "PlayStation Vita Edition",
    "Wii U Edition", "Nintendo Switch Edition", "New Nintendo 3DS Edition",
    "China Edition", "Apple TV Edition", "MinecraftEdu",
}

# Cat-driven priority — first cat in this list that matches becomes primary
# Order: most specific → less specific. Identity > aspect/use.
PRIMARY_PRIORITY_GAME_VANILLA = [
    # ----- Specific overrides -----
    "Ore",  # Ore wins over Blocks (Ancient Debris, Coal Ore)

    # ----- Mob sub-types (specific identity) -----
    "Bosses",
    "Animal_mobs", "Hostile_mobs", "Monster_mobs", "Passive_mobs",
    "Aquatic_mobs", "Tameable_mobs", "Nether_mobs", "Undead_mobs",
    "Flying_mobs", "Humanoid_mobs", "Removed_mobs", "Arthropod_mobs",

    # ----- Plants (over Blocks/Items) -----
    "Plants", "Crops", "Saplings", "Flowers", "Trees", "Vegetation",

    # ----- Block sub-types (specific identity) -----
    "Manufactured_blocks", "Natural_blocks", "Generated_structure_blocks",
    "Utility_blocks", "Non-solid_blocks", "Technical_blocks",
    "Liquids", "Fluids",

    # ----- Item sub-types -----
    "Tools", "Weapons", "Armor", "Food",
    "Brewing_ingredients", "Raw_materials", "Potions", "Music_Discs",

    # ----- Generic content fallbacks -----
    "Mobs",
    "Blocks", "Items",
    "Block_entities", "Stationary_entities", "Joke_entities", "Projectiles",
    "Vehicles", "Playable_entities",
    "Entities",  # most generic

    # ----- World / structures -----
    "Generated_structures", "Structures",
    "Generated_features",
    "Biomes", "Overworld_biomes", "Nether_biomes", "End_biomes",
    "Dimensions", "The_End", "The_Nether",
    "Environment", "Settlements",
    "Structure_blueprints", "Village_blueprints", "Village_structure_subpages",

    # ----- Mechanics / gameplay -----
    "Game_mechanics",
    "Status_effects", "Potion_effects", "Effects",
    "Enchantments",
    "Crafting", "Combat", "Gameplay",
    "Game_terms", "Game_modes",
    "Element", "Elements",
    "Minigames", "Server",
    "Mechanisms",
    "Redstone_mechanics", "Redstone_circuits",
    "Redstone",  # generic redstone (last resort for redstone)

    # ----- Removed / experimental (specific subtypes only here) -----
    # NOTE: `Removed_features` (catch-all) was moved to the END of this list
    # 2026-05-03 — it's too generic and was outranking Commands and other
    # specific buckets. Articles with both `Commands` and `Removed_features`
    # cats should land in Commands; articles with ONLY `Removed_features` as
    # their most-specific cat get dropped by Phase 0 of hardening_v2.
    "Removed_blocks", "Removed_items",
    "Experimental",

    # ----- Sound -----
    "Sounds", "Music",

    # ----- Achievements -----
    "Achievements", "Advancements",

    # ----- UI / menus -----
    "Menu_screens", "UI",
    "Game_modes",

    # ----- Cosmetic -----
    "Skin_packs", "Capes", "Texture_packs", "Resource_packs",
    "Mash-up_packs", "Character_Creator", "Add-ons",
    "Collaborative_skin_packs", "Collaborative_add-ons",
    "Collaborative_maps", "Collaboration_character_items",
    "DLC_promotions",

    # ----- Disambiguations -----
    "Achievement_disambiguation_pages",
    "Version_disambiguation_pages",
    "Disambiguation_pages",
    "Set_index_pages",

    # ----- Commands -----
    "Commands",

    # ----- Technical reference -----
    "Java_Edition_protocol", "Protocol_Details", "Java_Edition_technical",
    "Top-level_data_pages", "Data_packs", "Sound_data_pages",
    "Texture_atlases", "Textures",
    "Chunk_format", "Item_format",
    "Java_Edition_data_values", "Bedrock_Edition_level_format",
    "Custom_software", "Websites", "Calculators",
    "Interactive_tools_and_calculators",
    "Data_pages", "Fonts",
    "Minecraft_dynamic_lists",
    "Development",

    # ----- Modding -----
    "Mods", "Mod_loaders", "Mod_managers", "Game_customization",

    # ----- Catch-all "this thing was removed" (lowest priority) -----
    # Articles whose ONLY meaningful cat is `Removed_features` will land
    # here as primary, and Phase 0 of hardening_v2 drops them
    # (`removed_features_only`). Articles that ALSO have a more specific
    # cat (Commands, Manufactured_blocks, Animal_mobs, ...) win that
    # bucket as primary; Removed_features goes into also_in.
    "Removed_features",
]

# Title-based mechanic fallbacks (when no useful cat matches)
MECHANIC_TITLES = {
    "Block properties", "Block update", "Spawn limit", "Spawn event",
    "Hitbox", "Waxing", "Tick speed", "Piston/Technical components",
    "Block tick", "Random tick", "Game tick", "Cave",
    "Ore vein", "Hostility",
    "Villager professions", "Green particle", "File extensions",
    "Cooking", "Crafting", "Combat", "Smelting",
}
MECHANIC_TITLE_PREFIXES = ("Hitbox/",)

# UI settings titles that lack good cats
UI_SETTINGS_TITLES = {
    "Title Screen", "Menu screen", "Create New World", "Select World",
    "Graphics settings", "Controls", "World Options", "Tooltip/Colors",
    "Autosave", "Simulation distance", "Pause Menu", "Options",
    "Video Settings", "Audio Settings",
}

# Tech reference titles
TECH_TITLE_PREFIXES = (
    "Data component format/", "Data component predicate/",
    "Sounds.json/", "Bedrock Edition data values",
    "Java Edition data values", "Bedrock Edition protocol",
    "Java Edition protocol/", "Bedrock Edition level format/",
    "Java Edition level format/", "Block behaviour",
)


# ============================================================
# Parent map — when primary is X, drop these from also_in (they're parents)
# ============================================================

PARENT_MAP = {
    # Mobs hierarchy
    "Animal_mobs": {"Mobs", "Entities"},
    "Hostile_mobs": {"Mobs", "Entities"},
    "Monster_mobs": {"Mobs", "Entities"},
    "Passive_mobs": {"Mobs", "Entities"},
    "Aquatic_mobs": {"Mobs", "Entities"},
    "Tameable_mobs": {"Mobs", "Entities"},
    "Nether_mobs": {"Mobs", "Entities"},
    "Undead_mobs": {"Mobs", "Entities"},
    "Flying_mobs": {"Mobs", "Entities"},
    "Humanoid_mobs": {"Mobs", "Entities"},
    "Removed_mobs": {"Mobs", "Entities"},
    "Arthropod_mobs": {"Mobs", "Entities"},
    "Bosses": {"Mobs", "Entities", "Hostile_mobs"},
    "Mobs": {"Entities"},
    # Block sub-types → parent Blocks
    "Manufactured_blocks": {"Blocks"},
    "Natural_blocks": {"Blocks"},
    "Generated_structure_blocks": {"Blocks"},
    "Utility_blocks": {"Blocks"},
    "Non-solid_blocks": {"Blocks"},
    "Technical_blocks": {"Blocks"},
    "Liquids": {"Blocks"},
    "Fluids": {"Blocks"},
    # Item sub-types → parent Items
    "Tools": {"Items"},
    "Weapons": {"Items"},
    "Armor": {"Items"},
    "Food": {"Items"},
    "Brewing_ingredients": {"Items"},
    "Raw_materials": {"Items"},
    "Potions": {"Items"},
    "Music_Discs": {"Items"},
    # Ore implies block-of-something
    "Ore": {"Blocks", "Natural_blocks"},
    # Plants — Plants implies Blocks sometimes
    "Plants": set(),  # Plants stays standalone; Blocks/Items also_in is useful
    # Redstone hierarchy
    "Redstone_mechanics": {"Redstone"},
    "Redstone_circuits": {"Redstone"},
    # Disambiguation hierarchy
    "Achievement_disambiguation_pages": {"Disambiguation_pages", "Set_index_pages"},
    "Version_disambiguation_pages": {"Disambiguation_pages", "Set_index_pages"},
    "Set_index_pages": {"Disambiguation_pages"},
    # Effects hierarchy
    "Status_effects": {"Effects"},
    "Potion_effects": {"Effects"},
    # Generated_structure_blocks already child of Blocks
    "Generated_features": {"Generated_structures"},
    # Biome variants
    "Overworld_biomes": {"Biomes"},
    "Nether_biomes": {"Biomes"},
    "End_biomes": {"Biomes"},
}


# ============================================================
# LAYER A — determine ambiente
# ============================================================

def _determine_ambiente(title: str, cats: list[str], text: str) -> str:
    s = set(cats)
    t = title

    # spinoff has highest priority — title prefix is unambiguous
    if t.startswith(SPINOFF_TITLE_PREFIXES):
        return "spinoff"

    # april_fools second — must NOT pollute vanilla
    if (s & APRIL_FOOLS_CATS) or APRIL_FOOLS_TITLE_RE.search(t):
        return "april_fools"

    # education_edition third
    if s & EDUCATION_CATS:
        return "education_edition"

    # wiki_meta (File:/Template:/etc.)
    if t.startswith(WIKI_META_TITLE_PREFIXES) or (s & WIKI_META_CATS):
        return "wiki_meta"

    # tutorial — guides, NOT redstone components
    if t.startswith(TUTORIAL_TITLE_PREFIXES):
        return "tutorial"
    if s & TUTORIAL_CATS:
        return "tutorial"
    if t in TUTORIAL_REDSTONE_TITLES:
        return "tutorial"
    if t.startswith("Redstone circuits/") and t.count("/") == 1:
        return "tutorial"
    # Modding pages → tutorial (Mod, Mods/Forge)
    if s & {"Mods", "Mod_loaders", "Mod_managers", "Game_customization"}:
        # Only as tutorial if title is overview-style; otherwise stays vanilla.
        # Cat check above is sufficient — these pages are how-to.
        if t in {"Mod"} or t.startswith("Mods/"):
            return "tutorial"

    # versions ambiente (snapshots/betas/previews)
    real_version_cats = [c for c in cats if c not in VERSION_META_CATS_EXCLUDE]
    if any(VERSION_TOKEN_RE.search(c) for c in real_version_cats) or (s & VERSION_CATS_EXTRA):
        return "versions"

    # media_franchise (movies, novels, comics, mini-series)
    if t.startswith("Movie:") or (s & MEDIA_CATS):
        return "media_franchise"
    if any(c.endswith(MEDIA_CHAPTER_TOKEN) for c in cats):
        return "media_franchise"

    # real_world strong cats (people/companies/events/community) → ambient real_world
    if s & REAL_WORLD_STRONG_CATS:
        return "real_world"
    # History/anniversary cats: only ambient real_world if NO vanilla strong cat present
    if (s & HISTORY_CATS_SOFT) and not (s & VANILLA_STRONG_CATS):
        return "real_world"

    # Redstone schemas (3+ slash deep) → discardable, marked as wiki_meta-like
    if t.startswith("Redstone circuits/") and t.count("/") >= 2:
        return "wiki_meta"  # treated as discardable schema

    # default
    return "game_vanilla"


# ============================================================
# LAYER B — bucket within ambiente
# ============================================================

def _bucket_vanilla(t: str, cats: list[str], text: str) -> str:
    s = set(cats)

    # 1. Title-based virtual buckets (highest priority within vanilla)
    bucket = _title_based_bucket(t, s)
    if bucket:
        return bucket

    # 2. Tech reference titles
    if t.startswith(TECH_TITLE_PREFIXES):
        return "Java_Edition_technical"

    # 3. Disambiguation detection (cat or content)
    if "disambiguation page" in text[:300].lower():
        return "Disambiguation_pages"

    # 4. Cat-driven priority list — first match wins
    for cat in PRIMARY_PRIORITY_GAME_VANILLA:
        if cat in s:
            return cat

    # 5. Title-based mechanic fallbacks (no useful cats)
    if t in MECHANIC_TITLES or t.startswith(MECHANIC_TITLE_PREFIXES):
        return "Game_mechanics"

    # 6. UI settings fallback
    if t in UI_SETTINGS_TITLES or (s & {"Menu_screens", "UI"}):
        return "Menu_screens"

    # 7. Sound files
    if s & {"Sounds", "Music"}:
        return "Sounds"

    # 8. Last-resort: any cat that's not meta/edition becomes the bucket
    for c in cats:
        if not META_RE.search(c) and c not in EDITION_TAG_CATS:
            return c

    return "Other"


def _bucket_spinoff(t: str, cats: list[str], text: str) -> str:
    """Bucket = which spin-off game."""
    if t.startswith("Dungeons:") or t.startswith("MCD:"):
        return "Minecraft_Dungeons"
    if t.startswith("Legends:"):
        return "Minecraft_Legends"
    if t.startswith("Earth:") or t.startswith("Minecraft Earth:"):
        return "Minecraft_Earth"
    if t.startswith("Story Mode:"):
        return "Minecraft_Story_Mode"
    return "Spinoff_other"


def _bucket_april_fools(t: str, cats: list[str], text: str) -> str:
    s = set(cats)
    # Most specific Joke_* cat wins
    for cat in ["Joke_blocks", "Joke_items", "Joke_mobs", "Joke_entities",
                "Joke_biomes", "Joke_effects", "Joke_dimensions",
                "Joke_features", "April_Fools'", "April_Fools"]:
        if cat in s:
            return cat
    return "April_Fools_other"


def _bucket_education(t: str, cats: list[str], text: str) -> str:
    s = set(cats)
    if "MinecraftEdu_blocks" in s:
        return "MinecraftEdu_blocks"
    if "MinecraftEdu_items" in s:
        return "MinecraftEdu_items"
    if "Chemistry_Resource_Pack" in s:
        return "Chemistry"
    if s & {"MinecraftEdu", "MinecraftEdu_features"}:
        return "MinecraftEdu_features"
    return "Minecraft_Education_features"


def _bucket_tutorial(t: str, cats: list[str], text: str) -> str:
    s = set(cats)
    if "Java_Edition_guides" in s:
        return "Java_Edition_guides"
    if "Bedrock_Edition_guides" in s:
        return "Bedrock_Edition_guides"
    if t in TUTORIAL_REDSTONE_TITLES or t.startswith("Redstone circuits/"):
        return "Redstone_tutorials"
    if t.startswith("Tutorial:Programs"):
        return "Software_tutorials"
    return "Tutorials"


def _bucket_media_franchise(t: str, cats: list[str], text: str) -> str:
    s = set(cats)
    if t.startswith("Movie:") or any(c.startswith("A_Minecraft_Movie") for c in cats):
        return "A_Minecraft_Movie"
    if any(c.startswith("Minecraft_Mini-Series") for c in cats):
        return "Mini_Series"
    if "Minecraft_(Dark_Horse_Comics)_series" in s or "Comic_books" in s:
        return "Comics"
    if s & {"Books", "Fiction", "Nick_Eliopulos_novels", "Max_Brooks_novels", "Meta_novels", "Science_fiction"}:
        return "Books"
    if "Animated_content" in s:
        return "Animated_shorts"
    if "Live_action_content" in s:
        return "Live_action"
    if s & {"Adventure_maps", "Maps"}:
        return "Maps"
    if "Game_trailers" in s:
        return "Trailers"
    if any(c.endswith(MEDIA_CHAPTER_TOKEN) for c in cats):
        return "Book_chapters"
    if "Online_content" in s:
        return "Online_content"
    if "Editorials" in s:
        return "Editorials"
    if "Minecraft_(franchise)" in s:
        return "Franchise_meta"
    return "Media_other"


def _bucket_real_world(t: str, cats: list[str], text: str) -> str:
    s = set(cats)
    PEOPLE = {"Actors", "YouTubers", "Streamers", "Hosts", "Players",
              "Students", "Mobologists", "Musicians"}
    EVENTS = {"MINECON", "Minecraft_Live", "Events", "Historical_events",
              "Live_streams", "Eerie_Mojang_Office_Party",
              "A_Minecraft_Movie_Live_Event"}
    HISTORY = {"History", "15th_Anniversary", "10th_Anniversary",
               "MCC_x_Minecraft_15th_Anniversary_Party", "Birthday_skin_packs"}
    COMPANIES = {"Microsoft", "Companies"}
    COMMUNITY = {"Community", "Collaborations", "Cross-franchise_promotions",
                 "Merchandise", "Discontinued",
                 "Minecraft_Marketplace", "Event_servers",
                 "Minecraft_Blast", "Minecraft_4k", "Mojam_games",
                 "Minecraft_Earth", "Minecraft_Story_Mode", "Minecraft_Experience",
                 "China_Edition"}

    # Person check first — most specific
    if s & PEOPLE:
        return "People"

    # Mojang_Studios cat is ambiguous: company article vs employee.
    # Distinguished by hardcoded title: "Mojang Studios" → company, otherwise → person.
    if "Mojang_Studios" in s:
        if t in COMPANY_TITLES_OVERRIDE:
            return "Companies"
        return "People"  # employee or contributor

    if t in COMPANY_TITLES_OVERRIDE:
        return "Companies"
    if s & EVENTS:
        return "Events"
    if s & HISTORY:
        return "History"
    if s & COMPANIES:
        return "Companies"
    if s & COMMUNITY:
        return "Community_business"
    return "Real_world_other"


def _bucket_versions(t: str, cats: list[str], text: str) -> str:
    s = set(cats)
    # Bucket by edition
    for c in cats:
        if c.endswith("_versions") and c not in EDITION_TAG_CATS:
            # Java_Edition_versions, Bedrock_Edition_versions, Pocket_Edition_versions, etc.
            return c
    if "Lost_versions" in s:
        return "Lost_versions"
    return "Versions"


def _bucket_wiki_meta(t: str, cats: list[str], text: str) -> str:
    s = set(cats)
    if t.startswith("File:"):
        return "Files"
    if t.startswith("Template:"):
        return "Templates"
    if t.startswith("Help:"):
        return "Help_pages"
    if t.startswith("Minecraft Wiki:"):
        return "Wiki_self_reference"
    if "Soft_redirects" in s:
        return "Redirects"
    if t.startswith("Redstone circuits/") and t.count("/") >= 2:
        return "Redstone_schemas"
    return "Wiki_meta_other"


# ============================================================
# Public API
# ============================================================

def primary_group(title: str, cats: list[str], text: str) -> str:
    """Returns just the bucket name (for backwards compatibility with viewer).

    Bucket is prefixed with '<ambiente>::' if ambiente != game_vanilla so that
    the viewer can distinguish them. game_vanilla buckets keep their cat name
    untouched (they're the most common and the viewer treats them as default).
    """
    ambiente, bucket = primary_classify(title, cats, text)
    if ambiente == "game_vanilla":
        return bucket
    return f"{ambiente}::{bucket}"


def primary_classify(title: str, cats: list[str], text: str) -> tuple[str, str]:
    """Returns (ambiente, bucket) — the canonical 2-layer classification."""
    ambiente = _determine_ambiente(title, cats, text)
    if ambiente == "spinoff":
        bucket = _bucket_spinoff(title, cats, text)
    elif ambiente == "april_fools":
        bucket = _bucket_april_fools(title, cats, text)
    elif ambiente == "education_edition":
        bucket = _bucket_education(title, cats, text)
    elif ambiente == "tutorial":
        bucket = _bucket_tutorial(title, cats, text)
    elif ambiente == "media_franchise":
        bucket = _bucket_media_franchise(title, cats, text)
    elif ambiente == "real_world":
        bucket = _bucket_real_world(title, cats, text)
    elif ambiente == "versions":
        bucket = _bucket_versions(title, cats, text)
    elif ambiente == "wiki_meta":
        bucket = _bucket_wiki_meta(title, cats, text)
    else:  # game_vanilla
        bucket = _bucket_vanilla(title, cats, text)
    return ambiente, bucket


def secondary_groups(title: str, cats: list[str], text: str, primary: str) -> list[str]:
    """All semantic also_in cats for the article — every relevant lens.

    Includes all wiki cats EXCEPT:
      - Meta cats (Pages_*, Articles_*, Stubs, Verify, etc.)
      - Edition tag noise (Bedrock_Edition, Java_Edition, etc. — they're not buckets)
      - The primary bucket itself
      - Parents of the primary in PARENT_MAP (avoid redundancy)

    Title-based virtual lenses (Crafting_recipes, etc.) are NOT added as
    also_in unless the article matches them — those are primary-only.
    """
    # Strip ambiente prefix from primary if present
    primary_bucket = primary.split("::", 1)[-1] if "::" in primary else primary

    out: list[str] = []
    seen: set[str] = set()
    parents = PARENT_MAP.get(primary_bucket, set())

    for c in cats:
        if c == primary_bucket:
            continue
        if c in parents:
            continue
        if META_RE.search(c):
            continue
        if c in EDITION_TAG_CATS:
            continue
        if c in seen:
            continue
        seen.add(c)
        out.append(c)
    return out


# ============================================================
# Report generation
# ============================================================

def md_table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--samples", type=int, default=5)
    args = parser.parse_args()

    if OUTPUT.exists() and not args.force:
        raise SystemExit(f"{OUTPUT} ya existe. Usar --force para sobrescribir.")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    # Group by (ambiente, bucket)
    by_ambiente: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    total = 0
    total_words = 0

    for line in INPUT.open(encoding="utf-8"):
        d = json.loads(line)
        cats = d.get("categories") or []
        title = d.get("title", "")
        text = d.get("text", "")
        wc = d.get("word_count", 0)
        total += 1
        total_words += wc

        ambiente, bucket = primary_classify(title, cats, text)
        by_ambiente[ambiente][bucket].append({"title": title, "wc": wc, "cats": cats[:8]})

    lines: list[str] = []
    lines.append("# Sub-groups exploration report (cat-driven 2-layer)")
    lines.append("")
    lines.append(f"Articulos totales: **{total:,}**  ")
    lines.append(f"Palabras totales: **{total_words:,}**")
    lines.append("")

    # Tabla por ambiente
    lines.append("## 1. Distribucion por ambiente")
    lines.append("")
    rows = []
    for amb in sorted(by_ambiente, key=lambda a: -sum(len(v) for v in by_ambiente[a].values())):
        buckets = by_ambiente[amb]
        n = sum(len(v) for v in buckets.values())
        words = sum(it["wc"] for v in buckets.values() for it in v)
        rows.append([amb, f"{n:,}", f"{words:,}", str(len(buckets))])
    lines.append(md_table(["ambiente", "articulos", "palabras", "#buckets"], rows))
    lines.append("")

    # Tabla por (ambiente, bucket)
    lines.append("## 2. Distribucion por bucket")
    lines.append("")
    for amb in sorted(by_ambiente, key=lambda a: -sum(len(v) for v in by_ambiente[a].values())):
        buckets = by_ambiente[amb]
        amb_n = sum(len(v) for v in buckets.values())
        lines.append(f"### {amb} ({amb_n:,} articulos, {len(buckets)} buckets)")
        lines.append("")
        bucket_rows = []
        for b in sorted(buckets, key=lambda x: -len(buckets[x])):
            items = buckets[b]
            words = sum(i["wc"] for i in items)
            bucket_rows.append([b, f"{len(items):,}", f"{words:,}",
                                f"{words/max(len(items),1):.0f}"])
        lines.append(md_table(["bucket", "articulos", "palabras", "avg w/art"], bucket_rows))
        lines.append("")

    # Samples per (ambiente, bucket)
    lines.append(f"## 3. Samples por bucket (hasta {args.samples} titulos)")
    lines.append("")
    for amb in sorted(by_ambiente, key=lambda a: -sum(len(v) for v in by_ambiente[a].values())):
        buckets = by_ambiente[amb]
        lines.append(f"### {amb}")
        lines.append("")
        for b in sorted(buckets, key=lambda x: -len(buckets[x])):
            items = buckets[b]
            items.sort(key=lambda x: -x["wc"])
            picks = items[: args.samples]
            lines.append(f"**{b}** ({len(items):,} arts):")
            for p in picks:
                lines.append(f"- `{p['title']}` ({p['wc']}w) — cats: {', '.join(p['cats'][:5])}")
            lines.append("")

    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Reporte escrito: {OUTPUT}")
    print(f"Total: {total:,} articulos, {total_words:,} palabras")
    print(f"Ambientes: {sorted(by_ambiente, key=lambda a: -sum(len(v) for v in by_ambiente[a].values()))}")


if __name__ == "__main__":
    main()
