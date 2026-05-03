"""
hardening_v2.py - Phase D second-pass hardening per HARDENING_V2_PLAN.md (v2).
==============================================================================

12-phase pipeline:
  0  category_filter        -- drop / route_qa_direct / keep
  1  pre_clean              -- ZW chars, curly quotes, U+2044, multi-newlines
  2  section_drops          -- Sounds / Data values / Gallery / Issues(cond) / etc.
  3  boilerplate_strip      -- line-level templates + editor markers + [verify]->space
  4  family_specific        -- mob / world / mechanics / etc. (BEFORE word-boundary)
  5  protect_identifiers    -- mask hex / namespaced IDs / gamerules / whitelist
  6  word_boundary_repair   -- Layer A regex + Layer B CURATED_GLUE + Layer C corpus
  7  edition_stutter        -- collapse Java/Bedrock/Pocket prefix runs + orphans
  8  tabular_row_drops      -- flattened table rows + universal INFOBOX_LABELS
  9  inline_noise           -- un-namespace minecraft:foo, NBT tags, anchor refs
  10 restore_identifiers    -- undo Phase 5 placeholders
  11 final_cleanup          -- multi-space, multi-newline, empty headers, bare colons
  12 dedup_repeated         -- kill 200+ char paragraph repetitions (Notch bug)

Inputs:
  raw_data/wiki/articles_cleaned.jsonl

Outputs:
  raw_data/wiki/articles_hardened.jsonl    -- main corpus
  raw_data/wiki/articles_qa_direct.jsonl   -- disambig + Set_index w/ prose
  raw_data/wiki/articles_dropped.jsonl     -- audit trail
  raw_data/wiki/hardening_report.json      -- aggregate stats

Usage:
  python -m scraper.hardening_v2
  python -m scraper.hardening_v2 --force
  python -m scraper.hardening_v2 --sample raw_data/_validate_samples/set_1.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import random
import re
import sys
from pathlib import Path

from scraper.explore_subgroups import primary_classify

# ============================================================
# Paths + constants
# ============================================================

OUTPUT_DIR = Path(__file__).parent.parent / "raw_data" / "wiki"

ARTICLES_IN = OUTPUT_DIR / "articles_cleaned.jsonl"
ARTICLES_OUT = OUTPUT_DIR / "articles_hardened.jsonl"
QA_DIRECT_OUT = OUTPUT_DIR / "articles_qa_direct.jsonl"
DROPPED_OUT = OUTPUT_DIR / "articles_dropped.jsonl"
REPORT_OUT = OUTPUT_DIR / "hardening_report.json"

LAYER_C_PATH = Path(__file__).parent / "_layer_c_glue.json"

DEDUP_MIN_CHARS = 200
SOURCE_VERSION_DEFAULT = "cleaned"
HARDENED_VERSION = "hardened_v2"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ============================================================
# Compiled patterns / dictionaries
# ============================================================

# ---- Phase 1 ----
ZW_CHARS = re.compile(r"[​‌‍⁠﻿]")
CURLY_DOUBLE = re.compile(r"[“”„‟]")
CURLY_SINGLE = re.compile(r"[‘’]")
FRACTION_SLASH = re.compile(r"⁄")
NUMERIC_DASH = re.compile(r"(\d)[–—](\d)")
MULTI_NEWLINE_3PLUS = re.compile(r"\n{3,}")
# Unicode "other" spaces that the source treats as words separators but that
# regex `[ ]`/literal-space patterns won't match. Map them to ASCII space.
UNICODE_SPACES = re.compile(r"[  -   　]")

# ---- Phase 2 ----
# The cleaned text does NOT preserve Markdown header markers (`##`); section
# names appear as plain capitalized lines. Detection: a line whose stripped
# value matches an entry in SECTION_NAMES_ALL is a section header. The body
# of a section is everything until the next section header (or EOF).

SECTION_NAMES_DROP_GLOBAL: set[str] = {
    # Truly template-only (no fact density once cleaned).
    "Block states",
    "Fluid states",
    "Block data",
    "Entity data",
    # Per-version changelog (decision 2026-04-27): the model can't reason about
    # snapshot codes like 23w12a or version numbers like 1.20.3 and would
    # generate confused references. Drop wholesale.
    "History",
    "Data history",
    "Pre-release history",
    # Image / video sections (only captions, no prose).
    "Videos",
    "Gallery",
    "Renders",
    "Screenshots",
    "Mojang screenshots",
    "Mojang images",
    "Concept artwork",
    "Storyboards",
    "Behind-the-scenes",
    "Promotional images",
    "Wallpapers",
    "Posters",
    "In other media",
    "Filmography",
    "Discography",
    "Credits",
}

# Conditional drops: lambda(art, body_text, is_achievement_article) -> bool.
# Advancements: KEPT always (modern advancement rows have useful facts).
# Achievements: still conditional — in non-achievement articles the body is
# mostly LCE-only trophy rows that the model can't reason about.
DROP_SECTIONS_CONDITIONAL: dict = {
    "Issues": lambda art, body, is_ach: "are maintained on the bug tracker" in body,
    "Achievements": lambda art, body, is_ach: not is_ach,
}

# KEEP-side section names. Used ONLY as boundary hints so that a DROP section's
# scan stops at the right place (we don't actually do anything with these — they
# pass through unchanged).
SECTION_NAMES_KEEP: set[str] = {
    # Lead / general
    "Overview", "Description", "Appearance", "Lore",
    # Mob/Entity
    "Behavior", "Spawning", "Spawn", "Drops", "Combat", "Strategy",
    "Variants", "Taming", "Breeding", "Riding",
    # Block/Item
    "Properties", "Obtaining", "Usage", "Crafting", "Crafting ingredient",
    "Smelting", "Smelting ingredient", "Smelting fuel",
    "Trading", "Brewing", "Repairing", "Mining",
    # Sounds + Data values: kept for fact density (sound IDs imply
    # interactions, ID/translation key are reference data).
    "Sounds", "Data values", "ID", "Generated loot",
    # Worldgen
    "Generation", "Structures", "Biomes", "Mobs", "Blocks", "Climate", "Colors",
    "Features", "Vegetation",
    # Trivia / refs (NOTE: History / Data history dropped above)
    "Trivia", "See also", "References", "Notes",
    "External links",
    # Advancements: kept (modern fact rows). Achievements stays in conditional.
    "Advancements",
    # Commands
    "Examples", "Syntax", "Arguments", "Output", "Result", "Restrictions",
    "Permissions",
    # Media
    "Plot", "Cast", "Production", "Release", "Reception", "Awards",
    # Effects/Enchantments
    "Effect", "Effects", "Causes", "Levels",
    # Misc
    "Tools", "Recipes", "Furnace recipes", "Stonecutter recipes",
    "Smithing", "Stonecutting",
}

SECTION_NAMES_ALL: set[str] = (
    SECTION_NAMES_DROP_GLOBAL
    | set(DROP_SECTIONS_CONDITIONAL.keys())
    | SECTION_NAMES_KEEP
)

# ---- Phase 3 ----
# Full-line strips. Each pattern matches a complete line (with optional trailing newline).
LINE_STRIP_PATTERNS: list[re.Pattern] = [
    # "Issues relating to..." universal boilerplate (1632 articles)
    re.compile(r'^Issues relating to "[^"]+" are maintained on the bug tracker\..*\n?', re.MULTILINE),
    # April Fools variant
    re.compile(
        r'^Issues relating to "[^"]+" are not maintained on the bug tracker because it is an April Fools\' joke\..*?Invalid"\s*\n?',
        re.MULTILINE | re.DOTALL,
    ),
    # Interactive widget placeholder (107 articles)
    re.compile(r"^An interactive widget is being loaded\.{0,3}.*\n?", re.MULTILINE),
    # Hatnotes (universal)
    re.compile(r"^For other uses, see [^\n.]+\.\s*\n?", re.MULTILINE),
    re.compile(r"^For the [^,\n]+, see [^\n.]+\.\s*\n?", re.MULTILINE),
    re.compile(r"^For an overview of all [^,\n]+ biomes, see [^\n.]+\.\s*\n?", re.MULTILINE),
    re.compile(r"^Not to be confused with [^\n.]+\.\s*\n?", re.MULTILINE),
    re.compile(r"^This article is about [^\n.]+\. For [^,\n]+, see [^\n.]+\.\s*\n?", re.MULTILINE),
    re.compile(r'^"[^"]+" redirects here\. For [^,\n]+, see [^\n.]+\.\s*\n?', re.MULTILINE),
    re.compile(r"^Main article: .+\n?", re.MULTILINE),
    re.compile(r"^See Tutorial:.+\n?", re.MULTILINE),
    # Inline "See also: X" cross-refs (Tutorial:Foo, Article § Section, etc.).
    # The "See also" SECTION header (no colon) is handled by SECTION_NAMES_ALL.
    re.compile(r"^See also:\s+\S.*\n?", re.MULTILINE),
    re.compile(r"^There is a related tutorial page\b.*\n?", re.MULTILINE),
    re.compile(r"^There is an associated technical blocks page for .+\n?", re.MULTILINE),
    # Spoiler / editor's note
    re.compile(
        r"^Spoiler warning! This section contains detailed information about [^\n.]+\..*\n?",
        re.MULTILINE,
    ),
    re.compile(r"^Editor's note:.*\n?", re.MULTILINE),
    # Wiki maintenance
    re.compile(r"^Tagged on: \w+ \d+, \d{4}\.\s*\n?", re.MULTILINE),
    re.compile(
        r"^It has been suggested that this section be split into its own page at .+\[discuss\]\s*\n?",
        re.MULTILINE,
    ),
    re.compile(
        r"^If this split affects many pages, or may potentially be controversial, do not split until a consensus has been reached\.\s*\n?",
        re.MULTILINE,
    ),
    re.compile(r"^This section needs cleanup to comply with the style guide\..*\n?", re.MULTILINE),
    re.compile(r"^Please help improve this section\.\s*\n?", re.MULTILINE),
    re.compile(
        r"^An official name has not been given\. Please update the name if confirmed by reliable sources\.\s*\n?",
        re.MULTILINE,
    ),
    re.compile(
        r"^This section uses a bug \(MC-\d+\) to make a contraption.*?\nUse at your own risk\.\s*\n?",
        re.MULTILINE | re.DOTALL,
    ),
    # In-development banners (promoted to global in v2)
    re.compile(
        r"^This section describes content that is currently in development\.\s*\n?",
        re.MULTILINE,
    ),
    re.compile(
        r"^This content has appeared in development versions for [^,\n]+, but the full update adding it has not been released yet\.\s*\n?",
        re.MULTILINE,
    ),
    re.compile(r"^The specific instructions are:.+\n?", re.MULTILINE),
    re.compile(r"^Please remove this notice once you have added a suitable .+\n?", re.MULTILINE),
    re.compile(
        r"^This (?:page|section|article) (?:needs to be|should be) rewritten\..*\n?",
        re.MULTILINE,
    ),
    # YouTube/Vimeo placeholders
    re.compile(r"^YouTube Video \( view on YouTube \)\s*\n?", re.MULTILINE),
    re.compile(r"^.+ \( view on YouTube \)\s*\n?", re.MULTILINE),
    re.compile(r"^Vimeo Video \( view on Vimeo \)\s*\n?", re.MULTILINE),
    # Orphan "Reason: ..." standalone (not in a Cause/Potency table)
    re.compile(r"^Reason:\s+[^\n]+\n?", re.MULTILINE),
    # "Main article: Movie:.../1CHP [edit]" media chapter cross-refs
    re.compile(r"^Main article: Movie:[^\n]*\[edit\]\s*\n?", re.MULTILINE),
]

# Inline patterns that collapse to a SINGLE SPACE (avoid creating word-glue).
INLINE_TO_SPACE_PATTERNS: list[re.Pattern] = [
    # Editor markers (with optional ZW joiner / inner spaces)
    re.compile(
        r"‌?\[\s*(?:verify|more information needed|citation needed|"
        r"check the code|is this the correct version\?|discuss|edit|sic)\s*\]"
    ),
    # MC / MCPE / MCL / REALMS / EDU bug IDs in parens
    re.compile(r"\(\s*(?:MC|MCPE|MCL|REALMS|EDU)-\d+\s*\)"),
    # Edition exclusivity / status tags
    re.compile(
        r"‌?\[\s*(?:Java Edition only|JE only|JEonly|"
        r"Bedrock Edition only|BE only|BEonly|"
        r"Bedrock and Pi editions only|edu only|upcoming)\s*\]"
    ),
]

# ---- Phase 5 ----
# Un-namespacing (NOT protection) — runs first inside Phase 5 to convert
# `minecraft:foo_bar` to `foo bar` (preserve referent). Pulling this here
# (instead of Phase 9 as in the plan draft) means Phase 6's slash-command
# rule can't damage the path inside `minecraft:foo/bar`.
RE_UNNS_NAMESPACE = re.compile(r"\bminecraft:([a-z_/]+)(?=[^a-z_/]|$)")
RE_UNNS_DOTTED = re.compile(
    r"\b(?:block|item|entity|tile|effect|enchantment|potion|subtitles?)"
    r"\.minecraft\.([a-z_.]+)(?=[^a-z_.]|$)"
)
# ID-definition rows. These are reference data (used in commands / datapacks);
# the namespaced form is the value. Mask them before un-namespacing so the
# `minecraft:foo` and `item.minecraft.foo` inside survive verbatim.
RE_ID_ROW_LINE = re.compile(
    r"^(?:"
    r"Identifier:\s+\S.*"
    r"|Translation key:\s+\S.*"
    r"|Item tags:\s+\S.*"
    r"|Numeric ID:\s+\S.*"
    r"|Form:\s+\S.*"
    r"|Name:\s+[^\n]*Identifier:[^\n]*"
    r")$",
    re.MULTILINE,
)

# Token whitelist that must survive Phase 6 word-boundary repair verbatim
# (gamerule names, AI goal classes, NBT compound names, common identifiers).
PROTECTION_WHITELIST = (
    r"globalSoundEvents|randomTickSpeed|doDaylightCycle|keepInventory|"
    r"doMobSpawning|mobGriefing|doFireTick|naturalRegeneration|"
    r"doWeatherCycle|commandBlockOutput|sendCommandFeedback|"
    r"showDeathMessages|spectatorsGenerateChunks|disableElytraMovementCheck|"
    r"RangedAttackGoal|MeleeAttackGoal|TemptGoal|FollowOwnerGoal|PanicGoal|"
    r"SitGoal|FloatGoal|AvoidEntityGoal|"
    r"BeeEntityData|MushroomCow|craftingScreen|TransferCooldown|CustomName|"
    r"DealtDamage|DuplicationCooldown|BatFlags|"
    r"MinecraftEdu|JavaScript|TypeScript|PlayStation|MineCon|"
    r"iPad|iPhone|PvP|PvE|MMORPG|GitHub|YouTube|TikTok|"
    r"OpenGL|DirectX|FabricMC|NeoForge"
)

PROTECTION_RULES: list[tuple[re.Pattern, str]] = [
    # Hex colors (#RRGGBB or #RRGGBBAA), case-insensitive.
    (re.compile(r"#[0-9A-Fa-f]{6,8}\b"), "__HEX_PROTECT__"),
    # File paths with extension (gui/items.png, block/cobblestone.png).
    (
        re.compile(
            r"\b[a-z][a-z0-9_-]*/[a-z0-9_/-]+"
            r"\.(?:png|json|jar|ogg|txt|zip|lang|properties|nbt|mcfunction)\b"
        ),
        "__FILEPATH_PROTECT__",
    ),
    # Snapshot codes (13w14a, 24w14potato).
    (re.compile(r"\b\d+w\d+[a-z]+\b"), "__SNAPSHOT_PROTECT__"),
    # Bug IDs (standalone form; parenthesized form already stripped in Phase 3).
    (re.compile(r"\b(?:MC|MCPE|MCL|REALMS|EDU)-\d+\b"), "__BUGID_PROTECT__"),
    # Console version vectors.
    (re.compile(r"\bTU\d+\b|\bCU\d+\b"), "__TUVER_PROTECT__"),
    # Identifier whitelist.
    (re.compile(rf"\b(?:{PROTECTION_WHITELIST})\b"), "__WHITELIST_PROTECT__"),
]

# ---- Phase 6 ----
# Layer A: programmatic regex (broad, conservative). Phase 5 has already masked
# hex codes / file paths / namespaced IDs / whitelist tokens, so these rules
# can run without damaging identifiers.
LAYER_A_RULES: list[tuple[re.Pattern, str]] = [
    # Lookaheads where possible so consecutive boundaries (e.g. `eTo` next to
    # `oZo` in `IsImmuneToZombification`) don't consume each other's trailing
    # lowercase and miss the second match.
    # digit followed by Capital letter ("5HP" -> "5 HP")
    (re.compile(r"(\d)(?=[A-Z])"), r"\1 "),
    # lowercase followed by CamelCase boundary ("biomesBadlands" -> "biomes Badlands")
    (re.compile(r"([a-z])(?=[A-Z][a-z])"), r"\1 "),
    # sentence boundary (".Notchbelieved" -> ". Notchbelieved")
    (re.compile(r"([.!?])(?=[A-Z])"), r"\1 "),
    # slash command glue ("use/setblock" -> "use /setblock")
    (re.compile(r"([a-z])(?=/[a-z])"), r"\1 "),
    # @-selector glue ("use@a" -> "use @a")
    (re.compile(r"([a-z])(?=@[aprs])"), r"\1 "),
    # anchor link glue ("see#Examples" -> "see #Examples")
    (re.compile(r"([a-z])(?=#[A-Za-z])"), r"\1 "),
    # comma + Capital (",Weaving" -> ", Weaving")
    (re.compile(r",(?=[A-Z])"), r", "),
    # filename glue (".pngare" -> ".png are")
    (
        re.compile(
            r"(\.(?:png|jar|ogg|json|txt|zip|lang|nbt|mcfunction))(?=[a-zA-Z])"
        ),
        r"\1 ",
    ),
    # "from#hex" / "to#hex" glue (only fires on non-protected hex; protected
    # ones are already placeholders by Phase 5).
    (re.compile(r"(from|to)(?=#[0-9A-Fa-f]{6,8})"), r"\1 "),
]

# Layer B: curated high-precision split dictionary. Order matters where
# patterns could overlap; longer patterns first.
CURATED_GLUE: list[tuple[re.Pattern, str]] = [
    # ---- Proper-noun + verb ----
    (re.compile(r"\bNotchbelieved\b"), "Notch believed"),
    (re.compile(r"\bNotchsaid\b"), "Notch said"),
    (re.compile(r"\bNotchannounced\b"), "Notch announced"),
    (re.compile(r"\bNotchteased\b"), "Notch teased"),
    (re.compile(r"\bNotchshowed\b"), "Notch showed"),
    (re.compile(r"\bNotchexpresses\b"), "Notch expresses"),
    (re.compile(r"\bJebexplained\b"), "Jeb explained"),
    (re.compile(r"\bJebsaid\b"), "Jeb said"),
    (re.compile(r"\bDinnerbonesaid\b"), "Dinnerbone said"),
    (re.compile(r"\bMojang Studiosconfirmed\b"), "Mojang Studios confirmed"),
    (re.compile(r"\bWintersannounced\b"), "Winters announced"),
    (re.compile(r"\bLydiaWinters\b"), "Lydia Winters"),
    (re.compile(r"\bBergenstensays\b"), "Bergensten says"),
    (re.compile(r"\bKingbdogzstates\b"), "Kingbdogz states"),
    # ---- Template list run-ons ----
    (re.compile(r"\bVisitallof\b"), "Visit all of"),
    (re.compile(r"\bEateachof\b"), "Eat each of"),
    (re.compile(r"\bKilloneof\b"), "Kill one of"),
    (re.compile(r"\bKilleachof\b"), "Kill each of"),
    (re.compile(r"\bHaveallof\b"), "Have all of"),
    (re.compile(r"\bBreed a pair ofanyof\b"), "Breed a pair of any of"),
    # ---- Preposition + ProperNoun (Edition family) ----
    (re.compile(r"\bforJava Edition\b"), "for Java Edition"),
    (re.compile(r"\bofJava Edition\b"), "of Java Edition"),
    (re.compile(r"\binJava Edition\b"), "in Java Edition"),
    (re.compile(r"\bbyJava Edition\b"), "by Java Edition"),
    (re.compile(r"\btoJava Edition\b"), "to Java Edition"),
    (re.compile(r"\bfromJava Edition\b"), "from Java Edition"),
    (re.compile(r"\bonJava Edition\b"), "on Java Edition"),
    (re.compile(r"\bwithJava Edition\b"), "with Java Edition"),
    (re.compile(r"\bisJava Edition\b"), "is Java Edition"),
    (re.compile(r"\bforBedrock Edition\b"), "for Bedrock Edition"),
    (re.compile(r"\bofBedrock Edition\b"), "of Bedrock Edition"),
    (re.compile(r"\binBedrock Edition\b"), "in Bedrock Edition"),
    (re.compile(r"\btoBedrock Edition\b"), "to Bedrock Edition"),
    (re.compile(r"\bfromBedrock Edition\b"), "from Bedrock Edition"),
    (re.compile(r"\bonBedrock Edition\b"), "on Bedrock Edition"),
    (re.compile(r"\bwithBedrock Edition\b"), "with Bedrock Edition"),
    (re.compile(r"\bofXbox 360 Edition\b"), "of Xbox 360 Edition"),
    (re.compile(r"\b\.minecraftfolder\b"), ".minecraft folder"),
    # ---- Data-cell label fusions ----
    (re.compile(r"\bAvg\.per chest\b"), "Avg. per chest"),
    (re.compile(r"\bcheststo search\b"), "chests to search"),
    (re.compile(r"\bFilenamein Minecraft\b"), "Filename in Minecraft"),
    (re.compile(r"\bAttenuationdistance\b"), "Attenuation distance"),
    (re.compile(r"\bCraftingrecipe\b"), "Crafting recipe"),
    (re.compile(r"\bSmeltingrecipe\b"), "Smelting recipe"),
    (re.compile(r"\bAmbientsounds\b"), "Ambient sounds"),
    (re.compile(r"\bUsableitems\b"), "Usable items"),
    (re.compile(r"\bPricemultiplier\b"), "Price multiplier"),
    (re.compile(r"\bVillagerexperience\b"), "Villager experience"),
    (re.compile(r"\bTrades instock\b"), "Trades in stock"),
    # ---- Common verb fusions ----
    (re.compile(r"\bbebred\b"), "be bred"),
    (re.compile(r"\bbredusing\b"), "bred using"),
    (re.compile(r"\bcraftedfrom\b"), "crafted from"),
    (re.compile(r"\bnowuses\b"), "now uses"),
    (re.compile(r"\bnowsell\b"), "now sell"),
    (re.compile(r"\bnowdrop\b"), "now drop"),
    (re.compile(r"\bnowspawn\b"), "now spawn"),
    # ---- Article + noun fusions (lowercase) ----
    (re.compile(r"\babarrier\b"), "a barrier"),
    (re.compile(r"\babeacon\b"), "a beacon"),
    (re.compile(r"\bablock\b"), "a block"),
    (re.compile(r"\babiomein\b"), "a biome in"),
    (re.compile(r"\bachance\b"), "a chance"),
    (re.compile(r"\bachest\b"), "a chest"),
    (re.compile(r"\bafireball\b"), "a fireball"),
    (re.compile(r"\baflower\b"), "a flower"),
    (re.compile(r"\bahopper\b"), "a hopper"),
    (re.compile(r"\bamob\b"), "a mob"),
    (re.compile(r"\baplayer\b"), "a player"),
    (re.compile(r"\bavillage\b"), "a village"),
    (re.compile(r"\bavillager\b"), "a villager"),
    (re.compile(r"\bawitch hut\b"), "a witch hut"),
    (re.compile(r"\bazombie\b"), "a zombie"),
    (re.compile(r"\baniron ingot\b"), "an iron ingot"),
    (re.compile(r"\banillager\b"), "an illager"),
    (re.compile(r"\bthebasalt\b"), "the basalt"),
    (re.compile(r"\bthecrafting\b"), "the crafting"),
    (re.compile(r"\bthechests\b"), "the chests"),
    (re.compile(r"\btheinventory\b"), "the inventory"),
    (re.compile(r"\btheblock\b"), "the block"),
    (re.compile(r"\btheirpath\b"), "their path"),
    (re.compile(r"\btheircreaking\b"), "their creaking"),
    (re.compile(r"\btheterrain\b"), "the terrain"),
    # ---- Verb-after-subject ----
    (re.compile(r"\bWardensnow\b"), "Wardens now"),
    (re.compile(r"\bWardensdrop\b"), "Wardens drop"),
    (re.compile(r"\bGoatsnow\b"), "Goats now"),
    (re.compile(r"\bPigsnowdrop\b"), "Pigs now drop"),
    (re.compile(r"\bSheepnowdrop\b"), "Sheep now drop"),
    (re.compile(r"\bEndermennow\b"), "Endermen now"),
    (re.compile(r"\bEndermenare\b"), "Endermen are"),
    (re.compile(r"\bMobscan\b"), "Mobs can"),
    (re.compile(r"\bmobscan\b"), "mobs can"),
    (re.compile(r"\bHostile mobscan\b"), "Hostile mobs can"),
    (re.compile(r"\bspidersfollow\b"), "spiders follow"),
    (re.compile(r"\bsomespiderson\b"), "some spiders on"),
    (re.compile(r"\bcraftrabbit\b"), "craft rabbit"),
    (re.compile(r"\bcraftfermented\b"), "craft fermented"),
    (re.compile(r"\bcraftsuspicious\b"), "craft suspicious"),
    (re.compile(r"\bcraftpurpur\b"), "craft purpur"),
    (re.compile(r"\bcraftcampfires\b"), "craft campfires"),
    (re.compile(r"\bcrafttools\b"), "craft tools"),
    (re.compile(r"\bSmeltcharred\b"), "Smelt charred"),
    (re.compile(r"\bSmeltbaked\b"), "Smelt baked"),
    (re.compile(r"\bbyshearing\b"), "by shearing"),
    (re.compile(r"\bintrial\b"), "in trial"),
    (re.compile(r"\binflower\b"), "in flower"),
    (re.compile(r"\bpotsof\b"), "pots of"),
    (re.compile(r"\bwithcows\b"), "with cows"),
    (re.compile(r"\bwithwheat\b"), "with wheat"),
    (re.compile(r"\bwithbuckets\b"), "with buckets"),
    (re.compile(r"\bbestfoodin\b"), "best food in"),
    (re.compile(r"\bviazombie\b"), "via zombie"),
    (re.compile(r"\bacraftingrecipe\b"), "a crafting recipe"),
    (re.compile(r"\bcraftablein\b"), "craftable in"),
    (re.compile(r"\businggold\b"), "using gold"),
    (re.compile(r"\bbecameobtainable\b"), "became obtainable"),
    (re.compile(r"\bwhenlavaflows\b"), "when lava flows"),
    (re.compile(r"\boversoul\b"), "over soul"),
    (re.compile(r"\bsoilnext\b"), "soil next"),
    (re.compile(r"\btoblue\b"), "to blue"),
    (re.compile(r"\bitrenewable\b"), "it renewable"),
    (re.compile(r"\bafteritem\b"), "after item"),
    (re.compile(r"\bheartis\b"), "heart is"),
    (re.compile(r"\bthroughcommands\b"), "through commands"),
    # ---- Patch / template smoosh ----
    (
        re.compile(r"(\d+\.\d+(?:\.\d+)?)Experiment([A-Z])"),
        r"\1 (Experiment) \2",
    ),
    (re.compile(r"\bUpcomingBedrock Edition\b"), "Upcoming Bedrock Edition"),
    (re.compile(r"\bUpcomingJava Edition\b"), "Upcoming Java Edition"),
    # ---- Conjunction fusions (curated, NOT generic) ----
    (re.compile(r"(?<=[a-z]{3})and(?=\s*[A-Z])"), " and "),
    (re.compile(r"\bCoalorCharcoal\b"), "Coal or Charcoal"),
    (re.compile(r"\bBone MealorLapis Lazuli\b"), "Bone Meal or Lapis Lazuli"),
    (re.compile(r"\bBrown MushroomorRed Mushroom\b"), "Brown Mushroom or Red Mushroom"),
    (re.compile(r"\bHelmetorChestplate\b"), "Helmet or Chestplate"),
    # ---- Digit + lowercase noun ----
    (
        re.compile(
            r"(\d+)(health|HP|points|seconds|minutes|hours|days|"
            r"blocks|chunks|ticks|levels?|emeralds?|enchantments?)\b"
        ),
        r"\1 \2",
    ),
    # ---- Filename glue (specific) ----
    (re.compile(r"\btheterrain\.png\b"), "the terrain.png"),
    (re.compile(r"\binclient\.jar\b"), "in client.jar"),
    (re.compile(r"\bgui/items\.pngwere\b"), "gui/items.png were"),
    (re.compile(r"\bstitched_terrain\.pngand\b"), "stitched_terrain.png and"),
]

# Layer C: corpus token-frequency-derived split dictionary. Loaded at startup
# from scraper/_layer_c_glue.json (produced by _token_freq_analysis.py).
LAYER_C_GLUE: list[tuple[re.Pattern, str]] = []

# ---- Phase 7 ----
RE_EDITION_PREFIX = re.compile(
    r"^(Java Edition(?: Classic| Indev| Infdev| Alpha| Beta)?|"
    r"Pocket Edition(?: Alpha)?|"
    r"Bedrock Edition|"
    r"Legacy Console Edition|"
    r"New Nintendo 3DS Edition|"
    r"Minecraft Education|"
    r"PlayStation 4 Edition):\s+"
)
RE_LCE_PLATFORM_VECTOR = re.compile(
    r"^Legacy Console Edition:\s+"
    r"(?:Xbox 360|Xbox One|PS3|PS4|PS Vita|Wii U|Switch)"
    r"(?:,\s*(?:Xbox 360|Xbox One|PS3|PS4|PS Vita|Wii U|Switch))+\s*$",
    re.MULTILINE,
)

# ---- Phase 8 ----
# Only patterns that strip GENUINELY corrupt scaffolding (multi-cell tables
# without recoverable data, orphan labels, pseudo-headers). Loot tables,
# spawn data, trade tables, and effect rows are KEPT — they contain useful
# facts even when slightly malformed.
TABULAR_ROW_PATTERNS: list[re.Pattern] = [
    # "Block: Tool" / "Block: Options" / etc. — orphan labels with no value.
    re.compile(
        r"^Block: (?:Tool|Options|Breakingtime \(sec\)|Efficiency|"
        r"Default|Wooden)\s*$",
        re.MULTILINE,
    ),
    # "Block: Hardness, Hopper: 3" — breaking-time multi-cell scaffolding.
    re.compile(
        r"^Block: (?:Hardness|Wood|Stone|Iron|Diamond|Netherite|Hopper|"
        r"Dispenser|Sticky)[^\n]*$",
        re.MULTILINE,
    ),
    # Map color multi-cell scaffolding (no real data, just COLOR _RED / _BROWN).
    re.compile(
        r"^Map color:(?:\s*\d+\s+COLOR\s+_[A-Z]+)+\s*$", re.MULTILINE
    ),
    re.compile(r"^Map color: JE: \d+ colors? .*$", re.MULTILINE),
    re.compile(r"^Map color: \d+ [A-Z][A-Z_ ]+\s*$", re.MULTILINE),
    # Mob: (Monster|Creature|...) category orphan.
    re.compile(
        r"^Mob: (?:Monster|Creature|Ambient|Water Creature|Underground "
        r"Water Creature|Axolotl|Misc) category\s*$",
        re.MULTILINE,
    ),
    # Item: Java Edition / Bedrock Edition pseudo-header (delimiter, no data).
    re.compile(
        r"^Item:\s+(?:Java Edition|Bedrock Edition|"
        r"Java\s+Edition\s+and\s+Bedrock\s+Edition)\s*$",
        re.MULTILINE,
    ),
    # Bug counters: "12 issues fixed." — no info.
    re.compile(
        r"^\d+ (?:issues?|bugs?) (?:fixed|reported)\.?\s*$", re.MULTILINE
    ),
    # Achievement column header.
    re.compile(r"^PS4, Other\s*$", re.MULTILINE),
    # Achievement reward tail (LCE-only trophies).
    re.compile(
        r"^[A-Z][^\n,]+, [^\n]*?, \d+, "
        r"(?:Bronze|Silver|Gold|Platinum)\s*$",
        re.MULTILINE,
    ),
    # Lost-version "?,?,?, Added X".
    re.compile(r"^[?,\s]+,\s+Added .+$", re.MULTILINE),
    # Standalone Identifier orphan (when in Properties block, no context).
    re.compile(r"^Identifier:\s+[a-z_]+\s*$", re.MULTILINE),
    # Block-state digit blob and metadata.
    re.compile(r"^Allowed values:\s*[0-9]+\s*$", re.MULTILINE),
    re.compile(r"^Metadata Bits:\s*(?:0x[0-9a-fA-F]\s*)+$", re.MULTILINE),
    # Tutorial Category/Data analytical rows.
    re.compile(r"^Category:\s+[^,\n]+,\s+Data:\s+.*$", re.MULTILINE),
    # "Sources: See § Foo" cross-references.
    re.compile(r"^Sources:\s*See\s*§\s*\w+\s*$", re.MULTILINE),
]

# Console version vector PREFIX strip (keeps the trailing prose).
RE_CONSOLE_VERSION_PREFIX = re.compile(
    r"^(?:TU\d+(?:,\s*CU\d+)?(?:,\s*[\d.]+)+"
    r"(?:,\s*Patch \d+)?(?:,\s*[\d.]+)?,\s*)",
    re.MULTILINE,
)

# ---- Phase 11 ----
RE_MULTI_SPACE = re.compile(r" {2,}")
RE_EMPTY_HEADER = re.compile(r"^(#+\s+[^\n]+)\n+(?=#+\s+)", re.MULTILINE)
RE_BARE_COLON_LINE = re.compile(r"^\S+\s*:\s*$", re.MULTILINE)

# ---- Phase 4 family detection ----
BUCKET_TO_FAMILY: dict[str, str] = {
    # mob
    "Bosses": "mob",
    "Animal_mobs": "mob", "Hostile_mobs": "mob", "Monster_mobs": "mob",
    "Passive_mobs": "mob", "Aquatic_mobs": "mob", "Tameable_mobs": "mob",
    "Nether_mobs": "mob", "Undead_mobs": "mob", "Flying_mobs": "mob",
    "Humanoid_mobs": "mob", "Removed_mobs": "mob", "Arthropod_mobs": "mob",
    "Mobs": "mob",
    # plant_ore
    "Ore": "plant_ore",
    "Plants": "plant_ore", "Crops": "plant_ore", "Saplings": "plant_ore",
    "Flowers": "plant_ore", "Trees": "plant_ore", "Vegetation": "plant_ore",
    # item
    "Tools": "item", "Weapons": "item", "Armor": "item", "Food": "item",
    "Brewing_ingredients": "item", "Raw_materials": "item",
    "Potions": "item", "Music_Discs": "item", "Items": "item",
    # mechanic
    "Game_mechanics": "mechanic", "Status_effects": "mechanic",
    "Potion_effects": "mechanic", "Effects": "mechanic",
    "Enchantments": "mechanic", "Crafting": "mechanic",
    "Combat": "mechanic", "Gameplay": "mechanic",
    # world
    "Generated_structures": "world", "Structures": "world",
    "Biomes": "world", "Overworld_biomes": "world", "Nether_biomes": "world",
    "End_biomes": "world", "Dimensions": "world",
    "Environment": "world",
    # command
    "Commands": "command",
}

AMBIENTE_TO_FAMILY: dict[str, str] = {
    "versions": "version",
    "tutorial": "tutorial",
    "real_world": "real_world",
    "media_franchise": "media",
}

# ---- Phase 4 family-specific patterns ----
RE_F4_PLANT_LAVA_FLOW = re.compile(
    r"^\s*\d+(?:\s*,\s*\d+){5,}\s*$", re.MULTILINE
)
RE_F4_ITEM_EAT_FOODS = re.compile(
    r"^Eat each of these \d+ foods?:.*$", re.MULTILINE
)
RE_F4_ITEM_DAMAGE_MATRIX = re.compile(
    r"^Unenchanted:\s+\([^)]+\)(?:\s*,\s*[^,\n]+){5,}\s*$", re.MULTILINE
)
RE_F4_MECH_PRIMARY_ITEMS_ORPHAN = re.compile(
    r"^Primary items\s*$", re.MULTILINE
)
RE_F4_WORLD_VISIT_BIOMES = re.compile(
    r"^Visit all of these \d+ biomes?:.*$", re.MULTILINE
)
RE_F4_WORLD_HOT_TOURIST = re.compile(
    r"^Hot Tourist Destinations\s*$", re.MULTILINE
)
RE_F4_VERSION_HEADER = re.compile(
    r"^(?:Beta|Build|Preview|Snapshot|Client version|Server version)"
    r"(?:\s+for)?:\s+\S.*\n?",
    re.MULTILINE,
)
RE_F4_TUTORIAL_SCHEMATIC = re.compile(
    r"^[a-z]{2,5}-\$\s*$", re.MULTILINE
)
RE_F4_TUTORIAL_CATEGORY_DATA = re.compile(
    r"^Category:\s+[^,]+,\s+Data:\s+.*\n?", re.MULTILINE
)
RE_F4_MEDIA_DITTO = re.compile(r"^Ditto\s*$", re.MULTILINE)


# ============================================================
# Phase functions
# ============================================================

def phase_0_category_filter(art: dict) -> tuple[str, str | None]:
    """Decide keep / drop / route_qa_direct based on categories + word_count + title.
    Returns: ("keep", None) | ("drop", reason) | ("route_qa_direct", reason)."""
    cats = set(art.get("categories") or [])
    title = art.get("title", "")
    wc = art.get("word_count") or 0

    # Disambig pages: route to qa_direct (useful for Q&A pairs with Qwen).
    if "Disambiguation_pages" in cats:
        return ("route_qa_direct", "disambig")

    # Set_index pages: keep for qa_direct only if prose-bearing, else drop.
    if "Set_index_pages" in cats:
        text = art.get("text", "")
        lines = [ln for ln in text.split("\n") if ln.strip()]
        if lines:
            prose_ratio = sum(1 for ln in lines if len(ln.split()) > 6) / len(lines)
        else:
            prose_ratio = 0.0
        if wc > 200 and prose_ratio > 0.4:
            return ("route_qa_direct", "set_index_with_prose")
        return ("drop", "set_index_pure_list")

    # Title-prefixed wiki meta.
    if title.startswith(("File:", "Template:", "Help:", "Minecraft Wiki:")):
        return ("drop", "wiki_meta_prefix")

    # Wiki meta categories.
    if cats & {
        "Files_with_a_license_template",
        "Mojang_images",
        "Notice_templates",
        "Documentation_pages",
        "Soft_redirects",
    }:
        return ("drop", "wiki_meta")

    # Long "List of ..." pages dominated by short enumeration lines.
    if title.startswith("List of ") and wc > 1000:
        text = art.get("text", "")
        lines = [ln for ln in text.split("\n") if ln.strip()]
        if lines and sum(1 for ln in lines if len(ln.split()) <= 6) / len(lines) > 0.7:
            return ("drop", "list_pure_enumeration")

    # Route entire `version` family (per-version pages, version-history pages,
    # release timelines, "X removed/exclusive features") to qa_direct: pure
    # changelog content with snapshot codes / dates the model can't reason
    # about, but useful as Q&A source ("when was X added?").
    text_for_clf = art.get("text", "")
    try:
        ambiente, _ = primary_classify(title, list(cats), text_for_clf)
    except Exception:
        ambiente = None
    if ambiente == "versions":
        return ("route_qa_direct", "version_changelog_page")

    # Java Edition history-of-textures subpages — pure changelog.
    if title.startswith("Java Edition history of ") and wc < 500:
        return ("drop", "history_subpage_changelog_only")

    # Removed format pages (Item format / Block format / NBT-only).
    if "Removed_features" in cats and (
        title.startswith("Item format/") or title.startswith("Block format/")
    ):
        return ("drop", "removed_format_nbt_only")

    # MinecraftEdu blocks (discontinued edition).
    if "MinecraftEdu_blocks" in cats and wc < 400:
        return ("drop", "edu_discontinued_stub")

    # Generic Minecraft Education stubs.
    if "Minecraft_Education" in cats and wc < 50:
        return ("drop", "edu_stub")

    return ("keep", None)


def phase_1_pre_clean(text: str) -> str:
    """Free-win normalizations (idempotent)."""
    text = ZW_CHARS.sub("", text)
    text = UNICODE_SPACES.sub(" ", text)
    text = CURLY_DOUBLE.sub('"', text)
    text = CURLY_SINGLE.sub("'", text)
    text = FRACTION_SLASH.sub("/", text)
    text = NUMERIC_DASH.sub(r"\1-\2", text)
    text = MULTI_NEWLINE_3PLUS.sub("\n\n", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return text


def phase_2_section_drops(text: str, art: dict) -> tuple[str, list[str]]:
    """Drop entire sections detected as plain-text section headers (matches an
    entry in SECTION_NAMES_ALL exactly). Conditional drops for Issues (only if
    body contains the bug-tracker boilerplate) and Achievements / Advancements
    (only if NOT an achievement-topic article)."""
    lines = text.split("\n")

    headers: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        s = line.strip()
        if s in SECTION_NAMES_ALL:
            headers.append((i, s))

    if not headers:
        return (text, [])

    is_ach = _is_achievement_article(art)
    drop_ranges: list[tuple[int, int]] = []
    dropped_names: list[str] = []

    for idx, (line_idx, name) in enumerate(headers):
        end = headers[idx + 1][0] if idx + 1 < len(headers) else len(lines)
        body = "\n".join(lines[line_idx + 1:end])
        if name in SECTION_NAMES_DROP_GLOBAL:
            drop_ranges.append((line_idx, end))
            dropped_names.append(name)
        elif name in DROP_SECTIONS_CONDITIONAL:
            if DROP_SECTIONS_CONDITIONAL[name](art, body, is_ach):
                drop_ranges.append((line_idx, end))
                dropped_names.append(name)

    if not drop_ranges:
        return (text, [])

    drop_ranges.sort()
    merged: list[tuple[int, int]] = []
    for start, end in drop_ranges:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    new_lines = list(lines)
    for start, end in reversed(merged):
        del new_lines[start:end]

    return ("\n".join(new_lines), dropped_names)


def phase_3_boilerplate_strip(text: str) -> str:
    """Line-level templates / hatnotes / editor markers. `[verify]` and similar
    collapse to single SPACE (not empty) to avoid creating new word-glue.

    Loops until stable (max 5 iters) because some lines have multiple hatnotes
    joined and only one pattern matches per pass."""
    for _ in range(5):
        prev = text
        for pattern in LINE_STRIP_PATTERNS:
            text = pattern.sub("", text)
        for pattern in INLINE_TO_SPACE_PATTERNS:
            text = pattern.sub(" ", text)
        if text == prev:
            break
    return text


def _is_achievement_article(art: dict) -> bool:
    title = art.get("title", "")
    cats = set(art.get("categories") or [])
    if "Achievement" in title or "Advancement" in title:
        return True
    if "Achievements" in cats or "Advancements" in cats:
        return True
    return False


def phase_4_family_specific(text: str, art: dict, family: str) -> str:
    """Per-family drops applied BEFORE word-boundary repair. Only patterns
    that strip genuine noise (advancement copy, schematic placeholders,
    orphan labels) are kept. Infobox-stat rows (Mob type, Climate, Renewable,
    Maximum level, Real name, etc.) preserved as facts."""
    if family == "plant_ore":
        text = RE_F4_PLANT_LAVA_FLOW.sub("", text)
    elif family == "item":
        text = RE_F4_ITEM_EAT_FOODS.sub("", text)
        text = RE_F4_ITEM_DAMAGE_MATRIX.sub("", text)
    elif family == "mechanic":
        text = RE_F4_MECH_PRIMARY_ITEMS_ORPHAN.sub("", text)
    elif family == "world":
        text = RE_F4_WORLD_VISIT_BIOMES.sub("", text)
        text = RE_F4_WORLD_HOT_TOURIST.sub("", text)
    elif family == "version":
        text = RE_F4_VERSION_HEADER.sub("", text)
    elif family == "tutorial":
        text = RE_F4_TUTORIAL_SCHEMATIC.sub("", text)
        text = RE_F4_TUTORIAL_CATEGORY_DATA.sub("", text)
    elif family == "media":
        text = RE_F4_MEDIA_DITTO.sub("", text)
    return text


def phase_5_protect_identifiers(text: str) -> tuple[str, list[tuple[str, str]]]:
    """1. Strip inline artifacts (NBT type tags, image asset paths) that
       create CamelCase fusions when removed. Doing this BEFORE Phase 6
       ensures the fusion gets caught by word-boundary repair.
    2. Un-namespace `minecraft:foo_bar` -> `foo bar` (preserves referent).
    3. Mask hex codes / file paths / snapshot codes / bug IDs / console
       versions / whitelist tokens with placeholders so Phase 6 word-boundary
       repair can't damage them.
    Returns (masked_text, list_of_(marker, original))."""
    # 1. Pre-strip glue-creating artifacts.
    text = re.sub(
        r"\[(?:NBT (?:Compound|List)(?:\s*/\s*JSON\s+(?:Object|Array))?|"
        r"String|Int(?:eger)?|Long|Short|Byte|Float|Double|Boolean|"
        r"Array|Int Array|Byte Array|Long Array|JSON Object|JSON Array)\]",
        "",
        text,
    )
    text = re.sub(r"#/media/File:\S+", "", text)

    # 2. Mask ID-row lines (Identifier:/Translation key:/Item tags:/Numeric ID:/
    #    Form:/compound Name:..Identifier:..) so un-namespacing in step 3 does
    #    NOT alter the namespaced values they hold.
    id_rows: list[str] = []
    def _id_replacer(m):
        idx = len(id_rows)
        id_rows.append(m.group(0))
        return f"__IDROW_PROTECT__{idx}__"
    text = RE_ID_ROW_LINE.sub(_id_replacer, text)

    # 3. Un-namespace (operates only on prose now).
    text = RE_UNNS_NAMESPACE.sub(
        lambda m: m.group(1).replace("_", " ").replace("/", " "), text
    )
    text = RE_UNNS_DOTTED.sub(
        lambda m: m.group(1).replace("_", " ").replace(".", " "), text
    )

    # 4. Restore ID-rows verbatim BEFORE further protection.
    for i, original in enumerate(id_rows):
        text = text.replace(f"__IDROW_PROTECT__{i}__", original)

    # 5. Mask hex / file paths / snapshot codes / bug IDs / whitelist.
    placeholders: list[tuple[str, str]] = []
    for pattern, marker in PROTECTION_RULES:
        def replacer(m, marker=marker):
            idx = len(placeholders)
            placeholders.append((marker, m.group(0)))
            return f"{marker}{idx}__"
        text = pattern.sub(replacer, text)
    return (text, placeholders)


def phase_6_word_boundary_repair(text: str) -> str:
    """Three layers: A=programmatic regex, B=CURATED_GLUE, C=LAYER_C_GLUE.
    Assumes Phase 5 already masked content that must NOT be split."""
    for pattern, repl in LAYER_A_RULES:
        text = pattern.sub(repl, text)
    for pattern, repl in CURATED_GLUE:
        text = pattern.sub(repl, text)
    for pattern, repl in LAYER_C_GLUE:
        text = pattern.sub(repl, text)
    return text


def phase_7_edition_stutter(text: str) -> str:
    """Collapse repeated edition prefixes (e.g. `Java Edition: A / Java Edition:
    B / Java Edition: C` becomes `Java Edition: A / B / C`). Drop orphan
    platform vectors after collapse."""
    out: list[str] = []
    prev_prefix: str | None = None
    for line in text.split("\n"):
        m = RE_EDITION_PREFIX.match(line)
        if m:
            current = m.group(1)
            body = line[m.end():]
            if current == prev_prefix:
                line = body
            else:
                prev_prefix = current
        else:
            prev_prefix = None
        out.append(line)
    text = "\n".join(out)
    text = RE_LCE_PLATFORM_VECTOR.sub("", text)
    return text


def phase_8_tabular_row_drops(text: str) -> str:
    """Per-line drops of flattened table SCAFFOLDING rows (orphan labels,
    multi-cell color blobs, pseudo-headers, NBT digit blobs) + console version
    vector prefix strip. Loot/spawn/trade/effect tables KEPT for fact density."""
    for pattern in TABULAR_ROW_PATTERNS:
        text = pattern.sub("", text)
    text = RE_CONSOLE_VERSION_PREFIX.sub("", text)
    return text


def phase_9_inline_noise(text: str) -> str:
    """Anchor refs, ObjectSprite junk, empty parens. (NBT type tags and image
    asset paths were moved to Phase 5 because their removal creates CamelCase
    glue that Phase 6 needs to fix.)"""
    text = re.sub(r"\(?\s*see\s*[#§]\s*[A-Z][\w ]+\s*\)?", "", text)
    text = re.sub(
        r"\(?\s*see\s+(?:also[:,\s]+)?[A-Z][\w ]+\s*[#§]\s*[\w ]+\)?",
        "",
        text,
    )
    text = re.sub(
        r"\bObjectSprite\s+[\w-]+\.png:\s*Sprite image[^\n]+", "", text
    )
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"\(\s*×\s*\d+(?:\.\d+)?\s*\)", "", text)
    return text


def phase_10_restore_identifiers(
    text: str, placeholders: list[tuple[str, str]]
) -> str:
    """Reverse Phase 5: replace `__<MARKER>N__` tokens with the original.
    Iterate from highest index down so `__X__1__` doesn't shadow `__X__11__`."""
    for i in range(len(placeholders) - 1, -1, -1):
        marker, original = placeholders[i]
        text = text.replace(f"{marker}{i}__", original)
    return text


def phase_11_final_cleanup(text: str) -> str:
    """Whitespace + structural cleanup."""
    text = RE_MULTI_SPACE.sub(" ", text)
    text = MULTI_NEWLINE_3PLUS.sub("\n\n", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = RE_EMPTY_HEADER.sub("", text)
    text = RE_BARE_COLON_LINE.sub("", text)
    text = MULTI_NEWLINE_3PLUS.sub("\n\n", text)
    return text.strip()


def phase_12_dedup_repeated(text: str, min_chars: int = DEDUP_MIN_CHARS) -> tuple[str, int]:
    """Drop verbatim paragraph repetitions of length >= min_chars within ONE
    article. Whitespace-normalized comparison. Targets the catastrophic
    Notch-quote-25-times bug + similar."""
    paragraphs = text.split("\n\n")
    seen: set[str] = set()
    out: list[str] = []
    dedup_count = 0
    for p in paragraphs:
        normalized = " ".join(p.split())
        if len(normalized) >= min_chars and normalized in seen:
            dedup_count += 1
            continue
        if normalized:
            seen.add(normalized)
        out.append(p)
    return ("\n\n".join(out), dedup_count)


# ============================================================
# Family detection (Phase 4 dispatch)
# ============================================================

def detect_family(art: dict) -> str:
    """Map article -> family for Phase 4 dispatch via the cat-driven classifier.
    Ambiente takes precedence (versions / tutorial / real_world / media). Within
    game_vanilla, the bucket is mapped to a coarser family via BUCKET_TO_FAMILY.
    Returns 'none' if no rule matches."""
    title = art.get("title", "")
    cats = art.get("categories") or []
    text = art.get("text", "")
    try:
        ambiente, bucket = primary_classify(title, cats, text)
    except Exception:
        return "none"

    if ambiente in AMBIENTE_TO_FAMILY:
        return AMBIENTE_TO_FAMILY[ambiente]
    return BUCKET_TO_FAMILY.get(bucket, "none")


# ============================================================
# Orchestration
# ============================================================

def harden_article(art: dict) -> dict:
    """Run the 12-phase pipeline on one article. Always returns a record with
    `route` in {"main_corpus", "qa_direct", "dropped"} and the full schema."""
    title = art.get("title", "")
    categories = art.get("categories") or []
    sounds = art.get("sounds")
    scraped_at = art.get("scraped_at")
    source_version = art.get("version") or SOURCE_VERSION_DEFAULT
    original_text = art.get("text", "")
    original_wc = art.get("word_count") or _word_count(original_text)

    # Phase 0
    decision, reason = phase_0_category_filter(art)

    base_record = {
        "title": title,
        "categories": categories,
        "version": HARDENED_VERSION,
        "source_version": source_version,
    }
    if sounds is not None:
        base_record["sounds"] = sounds
    if scraped_at is not None:
        base_record["scraped_at"] = scraped_at

    if decision == "drop":
        return {
            **base_record,
            "text": "",
            "word_count": 0,
            "drop_reason": reason,
            "route": "dropped",
            "hardening_meta": {
                "original_word_count": original_wc,
                "passes_applied": ["category_filter"],
                "transforms_count": 0,
                "section_drops": [],
                "warnings": [],
                "family": None,
            },
        }

    # Phases 1-12 (run for both keep and route_qa_direct)
    family = detect_family(art)
    warnings: list[str] = []

    text = phase_1_pre_clean(original_text)
    text, dropped_sections = phase_2_section_drops(text, art)
    text = phase_3_boilerplate_strip(text)
    text = phase_4_family_specific(text, art, family)
    text, placeholders = phase_5_protect_identifiers(text)
    text = phase_6_word_boundary_repair(text)
    text = phase_7_edition_stutter(text)
    text = phase_8_tabular_row_drops(text)
    text = phase_9_inline_noise(text)
    text = phase_10_restore_identifiers(text, placeholders)
    text = phase_11_final_cleanup(text)
    text, dedup_count = phase_12_dedup_repeated(text)

    if dedup_count > 0:
        warnings.append(f"dedup_removed_{dedup_count}_blocks")

    new_wc = _word_count(text)
    route = "qa_direct" if decision == "route_qa_direct" else "main_corpus"

    return {
        **base_record,
        "text": text,
        "word_count": new_wc,
        "drop_reason": reason if decision == "route_qa_direct" else None,
        "route": route,
        "hardening_meta": {
            "original_word_count": original_wc,
            "passes_applied": [
                "pre_clean", "section_drops", "boilerplate_strip", "family_specific",
                "protect_identifiers", "word_boundary_repair", "edition_stutter",
                "tabular_row_drops", "inline_noise", "restore_identifiers",
                "final_cleanup", "dedup_repeated",
            ],
            "transforms_count": original_wc - new_wc,
            "section_drops": dropped_sections,
            "warnings": warnings,
            "family": family,
        },
    }


def process(input_path: Path) -> dict:
    """Iterate jsonl, harden each article, write outputs, return aggregate stats."""
    counts = {"main_corpus": 0, "qa_direct": 0, "dropped": 0}
    drop_reasons: dict[str, int] = {}
    qa_reasons: dict[str, int] = {}
    family_counts: dict[str, int] = {}
    section_drop_counts: dict[str, int] = {}
    warning_counts: dict[str, int] = {}

    total_in_words = 0
    total_out_words = 0
    processed = 0

    main_f = open(ARTICLES_OUT, "w", encoding="utf-8")
    qa_f = open(QA_DIRECT_OUT, "w", encoding="utf-8")
    drop_f = open(DROPPED_OUT, "w", encoding="utf-8")

    try:
        for art in _iter_jsonl(input_path):
            rec = harden_article(art)
            route = rec["route"]
            counts[route] += 1
            processed += 1

            meta = rec["hardening_meta"]
            total_in_words += meta["original_word_count"] or 0
            total_out_words += rec["word_count"] or 0
            family_counts[meta.get("family") or "none"] = (
                family_counts.get(meta.get("family") or "none", 0) + 1
            )
            for sec in meta.get("section_drops") or []:
                section_drop_counts[sec] = section_drop_counts.get(sec, 0) + 1
            for warn in meta.get("warnings") or []:
                warning_counts[warn] = warning_counts.get(warn, 0) + 1

            line = json.dumps(rec, ensure_ascii=False) + "\n"
            if route == "main_corpus":
                main_f.write(line)
            elif route == "qa_direct":
                qa_f.write(line)
                qa_reasons[rec["drop_reason"] or "unknown"] = (
                    qa_reasons.get(rec["drop_reason"] or "unknown", 0) + 1
                )
            else:
                drop_f.write(line)
                drop_reasons[rec["drop_reason"] or "unknown"] = (
                    drop_reasons.get(rec["drop_reason"] or "unknown", 0) + 1
                )
    finally:
        main_f.close()
        qa_f.close()
        drop_f.close()

    return {
        "processed": processed,
        "counts": counts,
        "drop_reasons": drop_reasons,
        "qa_route_reasons": qa_reasons,
        "family_counts": family_counts,
        "section_drop_counts": section_drop_counts,
        "warning_counts": warning_counts,
        "words_in": total_in_words,
        "words_out": total_out_words,
        "words_lost": total_in_words - total_out_words,
        "pct_loss": round(
            (total_in_words - total_out_words) / total_in_words * 100, 2
        ) if total_in_words else 0.0,
    }


def verify_idempotence(output_path: Path, sample_n: int = 20) -> bool:
    """Re-run harden_article on a sample of already-hardened records; assert
    no further change (one-pass convergence)."""
    if not output_path.exists():
        log.warning(f"Idempotence: {output_path} does not exist, skipping")
        return True

    random.seed(42)
    records = list(_iter_jsonl(output_path))
    if not records:
        log.info("Idempotence: no records to check")
        return True

    samples = random.sample(records, min(sample_n, len(records)))
    differences = 0
    for rec in samples:
        re_hardened = harden_article(rec)
        if re_hardened["text"] != rec["text"]:
            differences += 1

    if differences > 0:
        log.warning(
            f"Idempotence FAILED: {differences}/{len(samples)} records of {output_path.name} "
            f"changed on second pass"
        )
        return False
    log.info(f"Idempotence OK on {len(samples)} samples of {output_path.name}")
    return True


def run(force: bool = False, sample_path: Path | None = None) -> None:
    input_path = sample_path if sample_path else ARTICLES_IN

    if not input_path.exists():
        log.error(f"Input not found: {input_path}")
        sys.exit(1)

    outputs = [ARTICLES_OUT, QA_DIRECT_OUT, DROPPED_OUT, REPORT_OUT]
    existing = [p for p in outputs if p.exists()]
    if existing and not force:
        log.error(
            f"Outputs exist: {[p.name for p in existing]}. Use --force to overwrite."
        )
        sys.exit(1)

    # Layer C glue (optional). JSON is {regex_pattern: replacement_string}.
    if LAYER_C_PATH.exists():
        try:
            with open(LAYER_C_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f)
            for pattern, repl in raw.items():
                LAYER_C_GLUE.append((re.compile(pattern), repl))
            log.info(f"Loaded {len(LAYER_C_GLUE)} entries from {LAYER_C_PATH.name}")
        except Exception as e:
            log.warning(f"Failed to load Layer C glue ({e}); proceeding without")
    else:
        log.warning(
            f"Layer C glue not found at {LAYER_C_PATH}; "
            "Phase 6 Layer C will be empty. Run token-frequency analysis to populate."
        )

    log.info(f"Hashing input {input_path.name}...")
    input_hash = _sha256_file(input_path)
    log.info(f"  sha256: {input_hash[:16]}...")

    log.info(f"Processing {input_path}...")
    stats = process(input_path)

    log.info("Verifying idempotence on main corpus output...")
    idem = verify_idempotence(ARTICLES_OUT)

    report = {
        "input_path": str(input_path),
        "input_sha256": input_hash,
        "input_line_count": _line_count(input_path),
        "hardened_version": HARDENED_VERSION,
        "stats": stats,
        "idempotence_ok": idem,
        "layer_c_entries": len(LAYER_C_GLUE),
    }
    with open(REPORT_OUT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    log.info("=" * 60)
    log.info("HARDENING v2 COMPLETE")
    log.info(f"  processed:   {stats['processed']:>7,}")
    log.info(f"  main_corpus: {stats['counts']['main_corpus']:>7,}")
    log.info(f"  qa_direct:   {stats['counts']['qa_direct']:>7,}")
    log.info(f"  dropped:     {stats['counts']['dropped']:>7,}")
    log.info(f"  words_in:    {stats['words_in']:>10,}")
    log.info(f"  words_out:   {stats['words_out']:>10,} ({stats['pct_loss']}% loss)")
    log.info(f"  report:      {REPORT_OUT}")
    log.info("=" * 60)


# ============================================================
# Helpers
# ============================================================

def _iter_jsonl(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def _word_count(text: str) -> int:
    return len(text.split()) if text else 0


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _line_count(path: Path) -> int:
    with open(path, "r", encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Phase D - Hardening v2 of cleaned wiki articles."
    )
    parser.add_argument(
        "--force", action="store_true", help="Overwrite existing outputs."
    )
    parser.add_argument(
        "--sample",
        type=Path,
        default=None,
        help="Run on a smaller jsonl (e.g. raw_data/_validate_samples/set_1.jsonl).",
    )
    args = parser.parse_args()
    run(force=args.force, sample_path=args.sample)
