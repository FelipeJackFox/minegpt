"""
output_normalizer.py — Normalize LLM transform outputs to canonical format.

The model emits inconsistent formats (bold-only, bullet+bold, hybrid, canonical).
This module deterministically converts ANY of those to a single canonical form:

    # {Article name}
    ## Overview
    {prose}
    ## Properties
    Key: value
    Key: value
    ## Details
    {prose}
    ## Obtaining (optional)
    {prose}
    ## Trivia (optional)
    {prose}

Principles:
1. Conservative: never invent or remove content (except explicit forbidden values).
2. Format-only: change wrappers (bold, bullets), not semantics.
3. Auditable: return list of transforms applied + warnings.
4. Idempotent: normalizing already-canonical text returns it unchanged.

Usage:
    from scraper.prompt_lab.output_normalizer import normalize
    result = normalize(raw_response, expected_title="Allay")
    result.normalized  # str — canonical text
    result.transforms_applied  # list[str] — audit log
    result.warnings  # list[str] — things that needed attention
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


CANONICAL_SECTIONS = ["Overview", "Properties", "Details", "Obtaining", "Trivia"]

# Sections the model invents that should fold into Details
NON_CANONICAL_SECTIONS = [
    "Spawning", "Spawn", "Behavior", "Behaviors", "Drops", "Breeding",
    "Variants", "Edition Differences", "Edition differences",
    "Mechanics", "Movement", "Combat", "Special Abilities", "Special abilities",
    "Interactions", "Persistence",
]

FORBIDDEN_PROPERTY_VALUES = {
    "n/a", "none", "not specified", "null", "-", "no", "false",
}

# Boolean fields where "No" means "omit the line entirely" per spec
OMIT_WHEN_NO = {"tameable", "rideable", "breedable", "damage"}


@dataclass
class NormalizationResult:
    normalized: str
    title: str
    sections: dict
    transforms_applied: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    raw_format_detected: str = "unknown"


# ============================================================
# Pass A — pre-processing
# ============================================================


def _strip_thinking(text: str) -> tuple[str, list[str]]:
    """Remove <think>...</think> blocks (qwen3 reasoning leak)."""
    transforms = []
    if "<think>" in text:
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        transforms.append("stripped_thinking_block")
    # Also strip common preambles
    for pre in [
        r"^\s*Here is the (output|result|markdown):\s*\n",
        r"^\s*Here'?s the (output|result|markdown):\s*\n",
        r"^\s*```markdown\s*\n",
        r"^\s*```\s*\n",
    ]:
        new = re.sub(pre, "", text, flags=re.IGNORECASE)
        if new != text:
            transforms.append(f"stripped_preamble: {pre[:30]}")
            text = new
    # Strip trailing code fence
    text = re.sub(r"\n```\s*$", "", text)
    return text.strip(), transforms


def _detect_format(text: str) -> str:
    """Heuristic: classify the raw format style."""
    has_h1 = bool(re.search(r"^#\s+\S", text, re.MULTILINE))
    has_h2 = bool(re.search(r"^##\s+\S", text, re.MULTILINE))
    has_bold_section = bool(re.search(r"^\*\*(Overview|Properties|Details|Obtaining|Trivia)\*\*", text, re.MULTILINE))
    has_bullet_bold = bool(re.search(r"^\s*[-*]\s+\*\*\w", text, re.MULTILINE))
    has_plain_kv = bool(re.search(r"^[A-Z][a-zA-Z ]+:\s+\S", text, re.MULTILINE))

    if has_h1 and has_h2 and has_plain_kv and not has_bullet_bold and not has_bold_section:
        return "canonical"
    if has_bold_section and not has_h2:
        return "bold_only"
    if has_h2 and has_bullet_bold:
        return "hybrid_bullet_bold"
    if has_bullet_bold:
        return "bullet_bold"
    return "mixed"


# ============================================================
# Pass B — title normalization
# ============================================================


def _normalize_title(text: str, expected: Optional[str]) -> tuple[str, str, list[str]]:
    """Ensure text starts with `# {Title}`. Return (text, title, transforms)."""
    transforms = []
    lines = text.split("\n")
    # Find first non-empty line
    first_idx = next((i for i, l in enumerate(lines) if l.strip()), 0)
    first = lines[first_idx].strip() if first_idx < len(lines) else ""

    title = expected or "Unknown"

    # Case 1: already `# Title`
    m = re.match(r"^#\s+(\S.*?)\s*$", first)
    if m:
        title = m.group(1).strip()
        return text, title, transforms

    # Case 2: `**Title**` — convert to `# Title`
    m = re.match(r"^\*\*([^*]+)\*\*\s*$", first)
    if m:
        candidate = m.group(1).strip()
        # Avoid section headers being misinterpreted as title
        if candidate not in CANONICAL_SECTIONS and candidate not in NON_CANONICAL_SECTIONS:
            title = candidate
            lines[first_idx] = f"# {title}"
            transforms.append(f"converted_bold_title_to_h1: {title}")
            return "\n".join(lines), title, transforms

    # Case 3: no title line — prepend
    transforms.append(f"prepended_missing_title: {title}")
    return f"# {title}\n\n" + text, title, transforms


# ============================================================
# Pass C — section headers
# ============================================================


def _normalize_section_headers(text: str) -> tuple[str, list[str]]:
    """Convert `**Section**` and `### Section` to `## Section` for canonical sections."""
    transforms = []

    # `**Overview**:?` (with optional colon and trailing whitespace) → `## Overview`
    for sec in CANONICAL_SECTIONS:
        pattern = re.compile(rf"^\s*\*\*{re.escape(sec)}\*\*\s*:?\s*$", re.MULTILINE)
        new = pattern.sub(f"## {sec}", text)
        if new != text:
            transforms.append(f"bold_to_h2: {sec}")
            text = new

    # `### Section` (only canonical) → `## Section`
    for sec in CANONICAL_SECTIONS:
        pattern = re.compile(rf"^###+\s+{re.escape(sec)}\s*$", re.MULTILINE)
        new = pattern.sub(f"## {sec}", text)
        if new != text:
            transforms.append(f"h3_to_h2: {sec}")
            text = new

    return text, transforms


def _flatten_non_canonical_sections(text: str) -> tuple[str, list[str]]:
    """
    Convert non-canonical section headers (Spawning, Behavior, Drops, etc.) to
    inline paragraph leads inside the prose. The content is preserved.

    `**Spawning**` → `\n\nSpawning. ` (paragraph break + lead-in)
    `## Drops` → `\n\nDrops. `
    `### Edition Differences` → `\n\nEdition differences. `
    """
    transforms = []
    for sec in NON_CANONICAL_SECTIONS:
        for pattern_str, name in [
            (rf"^\s*\*\*{re.escape(sec)}\*\*\s*:?\s*$", "bold"),
            (rf"^\s*##+\s+{re.escape(sec)}\s*$", "header"),
        ]:
            pattern = re.compile(pattern_str, re.MULTILINE)
            replacement = f"\n\n{sec}. "
            new = pattern.sub(replacement, text)
            if new != text:
                transforms.append(f"flattened_{name}_section: {sec}")
                text = new
    return text, transforms


# ============================================================
# Pass D — property lines
# ============================================================


def _normalize_property_lines(text: str) -> tuple[str, list[str]]:
    """Within ## Properties section, normalize each line to plain `Key: value`."""
    transforms = []

    # Find Properties section bounds
    m = re.search(r"^##\s+Properties\s*$(.*?)(?=^##\s+\w|\Z)", text, re.MULTILINE | re.DOTALL)
    if not m:
        return text, transforms

    props_block = m.group(1)
    new_lines = []
    for line in props_block.split("\n"):
        original = line
        line = line.strip()
        if not line:
            new_lines.append("")
            continue

        # Strip bullet prefix: `- **X**: Y` or `- X: Y`
        bullet_strip = re.match(r"^[-*]\s+(.+)$", line)
        if bullet_strip:
            line = bullet_strip.group(1)
            transforms.append("stripped_bullet")

        # Strip bold from field name: `**X**: Y` → `X: Y`
        bold_strip = re.match(r"^\*\*([^*:]+?)\*\*\s*:\s*(.*)$", line)
        if bold_strip:
            line = f"{bold_strip.group(1).strip()}: {bold_strip.group(2).strip()}"
            transforms.append("stripped_bold_field_name")

        # Strip parentheticals on Yes-only booleans: `Tameable: Yes (using lead)` → `Tameable: Yes`
        paren = re.match(r"^(Tameable|Rideable|Breedable):\s*Yes\b\s*\([^)]*\)\s*$", line, re.IGNORECASE)
        if paren:
            line = f"{paren.group(1)}: Yes"
            transforms.append("stripped_paren_on_boolean")

        # Strip units / multipliers from numeric fields. Capture the bare
        # number (or range), drop everything else trailing.
        # Examples handled:
        #   Health: 32 HP            → Health: 32
        #   Health: 32 HP × 16       → Health: 32
        #   Health Points: 32 HP × 16 → Health: 32
        #   Damage: 5 ♥              → Damage: 5
        #   XP drop: 1-3 experience  → XP drop: 1-3
        unit_match = re.match(
            r"^(Health Points|Health|Damage|XP drop|XP)\s*:\s*([0-9.]+(?:[-–][0-9.]+)?)\b[^\n]*$",
            line, re.IGNORECASE,
        )
        if unit_match:
            field_name = unit_match.group(1)
            value = unit_match.group(2)
            # Normalize "Health Points" → "Health"
            if field_name.lower() == "health points":
                field_name = "Health"
                transforms.append("renamed_health_points_to_health")
            new_line = f"{field_name}: {value}"
            if new_line != line:
                line = new_line
                transforms.append(f"stripped_units_from_{field_name.lower().replace(' ', '_')}")

        # Replace en-dash / em-dash with hyphen in numeric ranges
        if re.search(r"\d[–—]\d", line):
            line = re.sub(r"(\d)\s*[–—]\s*(\d)", r"\1-\2", line)
            transforms.append("normalized_dash_to_hyphen")

        # Decide if line should be omitted
        kv = re.match(r"^([A-Za-z ]+?)\s*:\s*(.+)$", line)
        if kv:
            field_name = kv.group(1).strip().lower()
            value = kv.group(2).strip().lower()

            # Omit forbidden values
            if value in FORBIDDEN_PROPERTY_VALUES:
                if field_name in OMIT_WHEN_NO and value in {"no", "none"}:
                    transforms.append(f"omitted_field_no_value: {field_name}")
                    continue
                if value in {"n/a", "not specified", "null", "-"}:
                    transforms.append(f"omitted_field_invalid_value: {field_name}")
                    continue

        new_lines.append(line)

    new_block = "\n".join(new_lines)
    new_text = text.replace(props_block, new_block, 1)
    return new_text, transforms


# ============================================================
# Pass E — body cleanup (Details / Obtaining / Trivia)
# ============================================================


def _cleanup_body_prose(text: str) -> tuple[str, list[str]]:
    """Strip inline bold + flatten bullets within prose sections (everything
    that is not Properties). Properties already cleaned in pass D."""
    transforms = []

    # Strip remaining inline `**X**` → `X` (in any section)
    new = re.sub(r"\*\*([^*\n]+?)\*\*", r"\1", text)
    if new != text:
        transforms.append("stripped_inline_bold_in_prose")
        text = new

    # Flatten bullets in Details / Obtaining / Trivia. Properties was already
    # processed line-by-line in pass D, so only touch sections AFTER
    # ## Properties.
    # Find ## Properties section end (start of next ## or EOF).
    props_match = re.search(r"^##\s+Properties\s*$", text, re.MULTILINE)
    body_start = 0
    if props_match:
        # Find the next ## after Properties
        next_h2 = re.search(r"^##\s+\w", text[props_match.end():], re.MULTILINE)
        if next_h2:
            body_start = props_match.end() + next_h2.start()

    if body_start > 0:
        head = text[:body_start]
        body = text[body_start:]
        # Convert bullet-prefixed lines to plain lines (just strip the bullet).
        # We don't try to merge them into a single sentence — leave them as
        # separate lines, which will read as short statements.
        new_body = re.sub(r"^\s*[-*]\s+", "", body, flags=re.MULTILINE)
        if new_body != body:
            transforms.append("flattened_bullets_in_body")
            body = new_body
        text = head + body

    return text, transforms


def _wrap_orphan_content_in_details(text: str) -> tuple[str, list[str]]:
    """If there is content AFTER ## Properties that is not under any ## section
    header, wrap it in ## Details. This handles outputs where the model never
    emitted '## Details' (jumped straight to non-canonical sections that we
    flattened to inline paragraphs)."""
    transforms = []

    props_match = re.search(r"^##\s+Properties\s*$", text, re.MULTILINE)
    if not props_match:
        return text, transforms

    after_props_start = props_match.end()
    after_props = text[after_props_start:]

    # If ## Details already exists somewhere after Properties, nothing to do.
    if re.search(r"^##\s+Details\s*$", after_props, re.MULTILINE):
        return text, transforms

    # Find the end of the Properties block (first blank line followed by
    # non-Key:value content, or first paragraph that's not a property line).
    lines = after_props.split("\n")
    # Properties lines are `Key: value`; track until we hit a blank-then-prose pattern.
    prop_end_line = 0
    in_props = True
    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue
        # Property lines: `Word: ...` (1-3 capitalized words, then colon)
        if in_props and re.match(r"^[A-Z][A-Za-z ]{0,30}:\s+\S", s):
            prop_end_line = i + 1
            continue
        # Hit non-property prose — properties section ends here
        in_props = False
        break

    if prop_end_line == 0 or prop_end_line >= len(lines):
        # No prose content after properties — nothing to wrap
        return text, transforms

    # Check whether there is real content after the property block
    remaining = "\n".join(lines[prop_end_line:]).strip()
    if not remaining:
        return text, transforms

    # If a ## Obtaining or ## Trivia exists in remaining, only wrap content
    # before that header.
    next_section_match = re.search(r"^##\s+(Obtaining|Trivia)\s*$", remaining, re.MULTILINE)
    if next_section_match:
        details_content = remaining[:next_section_match.start()].strip()
        rest = remaining[next_section_match.start():]
    else:
        details_content = remaining
        rest = ""

    if not details_content:
        return text, transforms

    # Reassemble: keep everything up to + including the property lines,
    # insert "## Details", then the wrapped content, then the rest.
    head = text[:after_props_start] + "\n" + "\n".join(lines[:prop_end_line]).rstrip()
    new_text = (
        head + "\n\n## Details\n" + details_content
        + (("\n\n" + rest) if rest else "")
    )
    transforms.append("wrapped_orphan_content_in_details")
    return new_text, transforms


# ============================================================
# Pass F — final cleanup
# ============================================================


def _final_cleanup(text: str) -> tuple[str, list[str]]:
    """Collapse whitespace, fix trailing artifacts."""
    transforms = []

    # Collapse 3+ blank lines to exactly 2
    new = re.sub(r"\n{3,}", "\n\n", text)
    if new != text:
        transforms.append("collapsed_blank_lines")
        text = new

    # Strip trailing whitespace per line
    new = "\n".join(line.rstrip() for line in text.split("\n"))
    text = new

    return text.strip(), transforms


# ============================================================
# Section parser
# ============================================================


def _parse_sections(text: str) -> dict:
    """Extract content of each ## section into a dict."""
    sections = {}
    # Match h2 headers and capture content until next h2 or end
    matches = list(re.finditer(r"^##\s+(\w[\w ]*?)\s*$", text, re.MULTILINE))
    for i, m in enumerate(matches):
        name = m.group(1).strip().lower()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[name] = text[start:end].strip()
    return sections


# ============================================================
# Main entry point
# ============================================================


def normalize(raw: str, expected_title: Optional[str] = None) -> NormalizationResult:
    """
    Normalize a raw LLM transform output to canonical format.

    Args:
      raw: the model's raw response.
      expected_title: the article title from the input (used as fallback if
                      the model didn't emit a `# Name` line).

    Returns:
      NormalizationResult with .normalized text + audit trail.
    """
    if not raw or not raw.strip():
        return NormalizationResult(
            normalized="",
            title=expected_title or "",
            sections={},
            warnings=["empty input"],
        )

    transforms_all = []
    warnings = []

    # Detect format before mutation (for telemetry)
    raw_format = _detect_format(raw)

    # Pass A
    text, t = _strip_thinking(raw)
    transforms_all.extend(t)

    # Pass B — title
    text, title, t = _normalize_title(text, expected_title)
    transforms_all.extend(t)

    # Pass C — sections
    text, t = _normalize_section_headers(text)
    transforms_all.extend(t)
    text, t = _flatten_non_canonical_sections(text)
    transforms_all.extend(t)

    # Pass D — properties
    text, t = _normalize_property_lines(text)
    transforms_all.extend(t)

    # Pass D2 — wrap orphan post-Properties content in ## Details if missing
    text, t = _wrap_orphan_content_in_details(text)
    transforms_all.extend(t)

    # Pass E — body cleanup (bullets in prose, inline bold)
    text, t = _cleanup_body_prose(text)
    transforms_all.extend(t)

    # Pass F — final
    text, t = _final_cleanup(text)
    transforms_all.extend(t)

    # Parse for downstream consumers
    sections = _parse_sections(text)

    # Warnings
    if "overview" not in sections:
        warnings.append("missing canonical section: ## Overview")
    if "properties" not in sections:
        warnings.append("missing canonical section: ## Properties")
    if "details" not in sections:
        warnings.append("missing canonical section: ## Details")
    remaining_bullets = len(re.findall(r"^\s*[-*]\s+", text, re.MULTILINE))
    if remaining_bullets > 0:
        warnings.append(f"{remaining_bullets} bullet lines remain in prose (review)")

    return NormalizationResult(
        normalized=text,
        title=title,
        sections=sections,
        transforms_applied=transforms_all,
        warnings=warnings,
        raw_format_detected=raw_format,
    )
