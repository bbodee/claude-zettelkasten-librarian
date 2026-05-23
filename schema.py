"""
schema.py — Note templates, tag taxonomy, validation and linting rules.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional
import re

# ── Tag taxonomy ──────────────────────────────────────────────────────────────

TAG_TAXONOMY = {
    "tools": [
        "python", "renpy", "comfyui", "pygame", "streamlit", "pandas",
        "numpy", "sqlite", "swf", "noobai", "controlnet", "obsidian",
        "ck3", "eu5", "fm", "paradox",
    ],
    "concepts": [
        "pattern", "gotcha", "solution", "reference", "template",
        "state-management", "api-patterns", "file-io", "performance",
        "ui-patterns", "statistics", "probability", "save-parsing",
        "advisor", "game-loop", "screen-architecture", "sprite-pipeline",
        "data-structures", "oop", "domain-object", "config-suite",
        "context-injection", "atomic-note",
    ],
    "domains": [
        "game-dev", "management-sim", "visual-novel", "image-generation",
        "data-analysis", "workflow-automation", "modding", "overlay",
    ],
}

ALL_TAGS = set(
    tag for group in TAG_TAXONOMY.values() for tag in group
)

# ── Human prose detection ─────────────────────────────────────────────────────

PROSE_PATTERNS = [
    r"^The\s",
    r"^I\s",
    r"^We\s",
    r"^This\s(is|was|means|allows|ensures|provides|gives|note|approach)",
    r"^In\sorder\sto",
    r"^It\s(is|was|turns\sout|seems)",
    r"^Note\sthat",
    r"^Keep\sin\smind",
    r"^Remember\sthat",
    r"^Each\s\w+\s(is|was|represents|contains|has)",
    r"^One\s\w+\s(is|was|to)",
    r"^You\s(can|should|need|want|must)",
    r"^Here\s(is|are|we)",
    r"^When\s\w+\s(is|are|was|were|has|have)\s",
    r"^If\syou\s",
    r"^Because\s",
    r"^Since\s\w+\s(is|are|was)",
    r"^As\s(a\s|an\s|the\s)",
]

PROSE_REGEX = re.compile("|".join(PROSE_PATTERNS), re.IGNORECASE)


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class Note:
    slug: str
    path: str
    title: str = ""
    tags: list = field(default_factory=list)
    created: str = ""
    updated: str = ""
    status: str = "active"
    note_type: str = "permanent"
    projects: list = field(default_factory=list)
    body: str = ""
    llm_safe: bool = True  # False = never sent to API

    @property
    def frontmatter(self) -> dict:
        return {
            "title": self.title,
            "tags": self.tags,
            "created": self.created,
            "updated": self.updated,
            "status": self.status,
            "type": self.note_type,
            "projects": self.projects,
            "llm_safe": self.llm_safe,
        }


# ── Templates ─────────────────────────────────────────────────────────────────

def permanent_note_template(title: str, tags: list, projects: list,
                             content: str = "") -> str:
    today = date.today().isoformat()
    tag_str = ", ".join(tags)
    proj_str = ", ".join(projects)
    return f"""---
title: {title}
tags: [{tag_str}]
created: {today}
updated: {today}
status: active
type: permanent
projects: [{proj_str}]
---

# {title}

## Pattern
{content if content else "<!-- What is the reusable rule or pattern? -->"}

## Rules
- 

## Gotchas
- 

## Example
```
```

## Related
- 
"""


def session_log_template(project: str, description: str = "") -> str:
    today = date.today().isoformat()
    slug_date = today.replace("-", "")
    desc_slug = description.lower().replace(" ", "-") if description else "session"
    return f"""---
title: Session - {project} - {today}
tags: [{project}, session-log]
created: {today}
type: log
project: {project}
---

# Session: {project} — {today}

## What Was Accomplished
- 

## Decisions Made
- 

## Problems Encountered
- 

## Pending / Next Steps
- 

## Notes to Process
- 
"""


# ── Validation ────────────────────────────────────────────────────────────────

def validate_frontmatter(note: Note) -> list[str]:
    """Returns list of validation errors."""
    errors = []
    if not note.title:
        errors.append("Missing title")
    if not note.tags:
        errors.append("Missing tags")
    if not note.created:
        errors.append("Missing created date")
    if not note.projects and note.note_type == "permanent":
        errors.append("Permanent note missing projects field")
    unknown = [t for t in note.tags if t not in ALL_TAGS]
    if unknown:
        errors.append(f"Unknown tags (add to taxonomy): {unknown}")
    return errors


def lint_note(note: Note) -> list[str]:
    """Flags human-prose patterns that should be directives."""
    issues = []
    lines = note.body.split("\n")

    # Check note length
    if len(lines) > 60:
        issues.append(
            f"Note is {len(lines)} lines — consider splitting (target <60)"
        )

    # Check for prose sentences
    prose_lines = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped and not stripped.startswith(("#", "-", "`", "|", "!")):
            if PROSE_REGEX.match(stripped):
                prose_lines.append(f"  Line {i}: {stripped[:60]}...")
    if prose_lines:
        issues.append("Human prose detected (rewrite as directives):")
        issues.extend(prose_lines)

    # Check for wikilinks
    if "[[" not in note.body and note.note_type == "permanent":
        issues.append("No wikilinks found (minimum 2 required)")

    return issues


def compress_note(note: Note, mode: str = "standard") -> str:
    """
    Rewrites a note into LLM-optimized format.

    mode="standard"   — strips prose, keeps structure
    mode="aggressive" — full token optimization for injection
    """
    if mode == "aggressive":
        return _compress_aggressive(note)
    return _compress_standard(note.body)


def _compress_standard(body: str) -> str:
    """Strip human prose, keep structured content."""
    lines = body.split("\n")
    compressed = []
    in_code = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("```"):
            in_code = not in_code
            compressed.append(line)
            continue

        if in_code:
            compressed.append(line)
            continue

        # Keep headers
        if stripped.startswith("#"):
            compressed.append(line)
            continue

        # Keep bullets
        if stripped.startswith(("-", "*", "+")):
            compressed.append(line)
            continue

        # Keep tables
        if stripped.startswith("|"):
            compressed.append(line)
            continue

        # Keep wikilinks line
        if "[[" in stripped:
            # Strip brackets — Obsidian syntax, noise for LLM
            cleaned = re.sub(r"\[\[([^\]]+)\]\]", r"\1", stripped)
            compressed.append(cleaned)
            continue

        # Strip prose
        if PROSE_REGEX.match(stripped):
            continue

        # Keep short factual lines
        if stripped and len(stripped) < 100:
            compressed.append(line)

    # Remove consecutive blank lines
    result = []
    prev_blank = False
    for line in compressed:
        is_blank = not line.strip()
        if is_blank and prev_blank:
            continue
        result.append(line)
        prev_blank = is_blank

    return "\n".join(result)


# Sections to keep in aggressive mode (others dropped)
_KEEP_SECTIONS = {
    "pattern", "patterns",
    "rules", "rule",
    "gotchas", "gotcha",
    "example", "examples",
    "solution", "solutions",
    "structure", "format",
}

# Sections to drop entirely in aggressive mode
_DROP_SECTIONS = {
    "related", "links",
    "problem", "context", "problem / context",
    "background", "overview",
    "notes to process",
}

# Header aliases → compressed form
_HEADER_MAP = {
    "problem / context": "ctx",
    "problem": "ctx",
    "context": "ctx",
    "solution / pattern": "pattern",
    "solution": "pattern",
    "gotchas": "!",
    "example": "eg",
    "examples": "eg",
    "related": None,  # drop
    "links": None,    # drop
}


def _compress_aggressive(note: Note) -> str:
    """
    Full token optimization:
    - Compressed frontmatter (title + tags only)
    - Drop Related/Context/Background sections
    - Compress headers to short aliases
    - Strip wikilink brackets
    - Strip all prose
    - Deduplicate repeated facts
    - Truncate long code blocks to first 10 lines
    """
    lines = note.body.split("\n")
    result = []
    in_code = False
    code_lines = 0
    current_section_dropped = False
    seen_facts: set[str] = set()

    # Compressed header
    tags_str = " ".join(f"#{t}" for t in note.tags[:6])
    result.append(f"# {note.title}")
    result.append(tags_str)
    result.append("")

    for line in lines:
        stripped = line.strip()

        # Code block handling
        if stripped.startswith("```"):
            if not in_code:
                in_code = True
                code_lines = 0
                result.append(line)
            else:
                in_code = False
                result.append(line)
            continue

        if in_code:
            code_lines += 1
            if code_lines <= 10:
                result.append(line)
            elif code_lines == 11:
                result.append("  ...")
            continue

        # Section headers
        if stripped.startswith("#"):
            header_text = stripped.lstrip("#").strip().lower()
            alias = _HEADER_MAP.get(header_text)

            if alias is None and header_text in _DROP_SECTIONS:
                current_section_dropped = True
                continue

            current_section_dropped = False

            if alias:
                level = len(stripped) - len(stripped.lstrip("#"))
                result.append("#" * level + " " + alias)
            else:
                result.append(line)
            continue

        # Skip dropped sections
        if current_section_dropped:
            continue

        # Skip empty lines (consolidate later)
        if not stripped:
            if result and result[-1] != "":
                result.append("")
            continue

        # Strip wikilinks
        stripped = re.sub(r"\[\[([^\]]+)\]\]", r"\1", stripped)
        line = re.sub(r"\[\[([^\]]+)\]\]", r"\1", line)

        # Skip prose
        if PROSE_REGEX.match(stripped):
            continue

        # Deduplicate facts
        fact_key = re.sub(r"\s+", " ", stripped.lower())[:80]
        if fact_key in seen_facts:
            continue
        seen_facts.add(fact_key)

        # Keep tables
        if stripped.startswith("|"):
            result.append(line)
            continue

        # Keep bullets — strip markdown bold/italic noise
        if stripped.startswith(("-", "*", "+")):
            cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
            cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
            result.append(cleaned)
            continue

        # Keep short factual lines
        if len(stripped) < 120:
            result.append(stripped)

    # Clean up consecutive blanks
    final = []
    prev_blank = False
    for line in result:
        is_blank = not line.strip()
        if is_blank and prev_blank:
            continue
        final.append(line)
        prev_blank = is_blank

    compressed = "\n".join(final).strip()

    # Report savings
    original = len(note.body)
    new_size = len(compressed)
    savings = int((1 - new_size / max(original, 1)) * 100)

    return compressed + f"\n\n<!-- {original}→{new_size} chars, {savings}% saved -->"