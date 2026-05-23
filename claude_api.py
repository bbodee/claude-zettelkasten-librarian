"""
claude_api.py — Anthropic API integration for the librarian.

Handles:
- Note compression (semantic, not regex)
- Context synthesis (multiple notes → one summary)
- Project planning (vault context → project plan)

Safety:
- Checks llm_safe flag before sending any note
- Never sends notes with llm_safe: false
- Logs all API calls for transparency
"""

import os
import sys
from typing import Optional
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schema import Note

# ── API client setup ──────────────────────────────────────────────────────────

def get_api_key() -> Optional[str]:
    """Get API key from environment or cfg file."""
    # 1. Environment variable (takes priority)
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key

    # 2. librarian.cfg next to this script
    cfg = Path(__file__).parent / "librarian.cfg"
    if cfg.exists():
        for line in cfg.read_text().splitlines():
            line = line.strip()
            if line.startswith("api_key"):
                _, _, val = line.partition("=")
                val = val.strip()
                if val and not val.startswith("#"):
                    return val

    return None


def _call_api(prompt: str, max_tokens: int = 1000,
              model: str = "claude-haiku-4-5-20251001") -> Optional[str]:
    """
    Make a single API call. Returns text response or None on failure.
    Uses Haiku by default — cheap, fast, good enough for compression.
    """
    api_key = get_api_key()
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set in environment")
        return None

    try:
        import urllib.request
        import json

        payload = json.dumps({
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}]
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data["content"][0]["text"]

    except Exception as e:
        print(f"API error: {e}")
        return None


# ── Safety guard ──────────────────────────────────────────────────────────────

def _check_safe(note: Note) -> bool:
    """Check if note is safe to send to API."""
    if not note.llm_safe:
        print(f"  BLOCKED: {note.slug} has llm_safe: false — skipping")
        return False
    return True


# ── Compression ───────────────────────────────────────────────────────────────
COMPRESS_PROMPT = """Convert this knowledge base note to minimal LLM-directive format.

RULES:
- Keep ONLY: Pattern, Rules, Gotchas, Example sections
- DROP entirely: Context, Background, Problem, Related/Links sections
- Convert narrative prose to bullet points
- Compress section headers: "Solution / Pattern" → "## pattern", "Gotchas" → "## !"
- Strip wikilink brackets: [[note-name]] → note-name
- Strip bold/italic markdown: **text** → text
- Keep ALL technical facts, specific values, code examples
- Truncate code blocks longer than 8 lines with ...
- Deduplicate: if same fact appears in multiple sections, keep once
- Target length: 25-40% of original
- Output raw markdown only. No commentary, no explanation.

NOTE TO COMPRESS:
{body}"""


def compress_note_llm(note) -> Optional[str]:
    if not _check_safe(note):
        return None
    original_len = len(note.body)
    print(f"  Compressing {note.slug} ({original_len} chars)...")
    prompt = COMPRESS_PROMPT.format(body=note.body)
    result = _call_api(prompt, max_tokens=800)
    if result:
        new_len = len(result)
        savings = int((1 - new_len / max(original_len, 1)) * 100)
        print(f"  {original_len} → {new_len} chars ({savings}% saved)")
        return result + f"\n\n<!-- llm-compressed: {original_len}→{new_len}, {savings}% -->"
    return None

# ── Synthesis ─────────────────────────────────────────────────────────────────

SYNTHESIZE_PROMPT = """You are a technical context synthesizer.

Synthesize these knowledge base notes into a single dense context block
for a Claude Code session. The output will be injected at the start of
a coding session to give instant context.

RULES:
- Output a single cohesive block, not a list of summaries
- Lead with the most critical rules and gotchas
- Group related concepts together
- Use bullet points for rules, inline code for examples
- Maximum 400 words
- Directive language only: "Always X", "Never Y", "Use Z for W"
- No narrative, no explanation of what you're doing

PROJECT: {project}

NOTES:
{notes}"""


def synthesize_context(notes: list[Note], project: str) -> Optional[str]:
    """
    Synthesize multiple notes into a single context block.
    Filters out any notes with llm_safe: false.
    """
    safe_notes = [n for n in notes if _check_safe(n)]

    if not safe_notes:
        return None

    blocked = len(notes) - len(safe_notes)
    if blocked > 0:
        print(f"  Note: {blocked} note(s) blocked by llm_safe: false")

    notes_text = "\n\n---\n\n".join(
        f"# {n.title}\n{n.body}" for n in safe_notes
    )

    prompt = SYNTHESIZE_PROMPT.format(
        project=project,
        notes=notes_text
    )

    print(f"  Synthesizing {len(safe_notes)} notes for {project}...")
    return _call_api(prompt, max_tokens=600)


# ── Planning ──────────────────────────────────────────────────────────────────

PLAN_PROMPT = """You are a technical project planner with access to a knowledge base
of past project learnings.

Generate a concise project plan based on the description and past learnings below.

OUTPUT FORMAT (markdown):
## Tech Stack
- [recommended tools and why]

## Config Suite Structure
- [.claude/ folder structure]

## Known Gotchas (from vault)
- [specific issues to avoid based on past projects]

## Estimated Complexity
[Simple/Medium/Complex and why]

## First Steps
1. [ordered action items]

## Open Questions
- [things to decide before building]

Keep it concise — this will be posted to Claude for refinement.
Maximum 300 words.

PROJECT DESCRIPTION: {description}

RELEVANT VAULT CONTEXT:
{context}"""


def plan_project(description: str, vault_context: str) -> Optional[str]:
    """
    Generate a project plan informed by vault context.
    vault_context should already be filtered for llm_safe.
    """
    prompt = PLAN_PROMPT.format(
        description=description,
        context=vault_context
    )

    print(f"  Generating plan for: {description}")
    return _call_api(prompt, max_tokens=800)


# ── Batch operations ──────────────────────────────────────────────────────────

def compress_vault(notes: list[Note],
                   writer) -> dict[str, str]:
    """
    Batch compress all llm_safe notes in the vault.
    Returns dict of {slug: result_message}.
    """
    results = {}
    safe_notes = [n for n in notes if n.llm_safe and n.status != "deprecated"]

    print(f"\nBatch compressing {len(safe_notes)} notes "
          f"({len(notes) - len(safe_notes)} skipped)...\n")

    for i, note in enumerate(safe_notes, 1):
        print(f"[{i}/{len(safe_notes)}] {note.slug}")
        compressed = compress_note_llm(note)

        if compressed:
            ok, msg = writer.write_compressed(note.slug, compressed)
            results[note.slug] = f"{'✓' if ok else '✗'} {msg}"
        else:
            results[note.slug] = "✗ compression failed"

    return results