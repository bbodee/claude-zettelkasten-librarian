"""
context.py — Assembles context packages for LLM injection.
Respects token budget and compresses intelligently.
"""

import os
import sys
from reader import VaultReader
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schema import Note, compress_note, lint_note, validate_frontmatter

# Approximate token budget for context injection
# 4 chars ≈ 1 token. Default budget: ~8000 tokens = ~32000 chars
DEFAULT_CHAR_BUDGET = 32000
NOTE_SEPARATOR = "\n" + "─" * 60 + "\n"


def _note_to_context(note: Note, compressed: bool = True) -> str:
    """Format a single note for context injection."""
    header = f"## [{note.note_type.upper()}] {note.title}"
    tags = f"tags: {', '.join(note.tags)}"
    if note.projects:
        tags += f" | projects: {', '.join(note.projects)}"

    if compressed:
        body = compress_note(note, mode="aggressive")
    else:
        body = note.body

    return f"{header}\n{tags}\n\n{body}"


def build_context(vault_path: str, project: str,
                  char_budget: int = DEFAULT_CHAR_BUDGET) -> str:
    """
    Build full context package for a project session.
    Order: MOC → recent logs → relevant permanent notes
    Truncates to char_budget.
    """
    reader = VaultReader(vault_path)
    sections = []
    chars_used = 0

    header = f"# Context: {project}\n"
    sections.append(header)
    chars_used += len(header)

    # 1. MOC
    moc = reader.load_moc(project)
    if moc:
        moc_text = f"\n## Project Map\n{moc.body[:2000]}"
        sections.append(moc_text)
        chars_used += len(moc_text)

    # 2. Recent logs
    logs = reader.recent_logs(project, n=3)
    if logs:
        log_header = "\n## Recent Sessions\n"
        sections.append(log_header)
        chars_used += len(log_header)
        for log in logs:
            if chars_used > char_budget * 0.4:
                break
            log_text = f"### {log.title}\n{log.body[:1500]}\n"
            sections.append(log_text)
            chars_used += len(log_text)

    # 3. Relevant permanent notes
    project_notes = reader.find_project_notes(project)
    if project_notes:
        notes_header = f"\n## Permanent Notes ({len(project_notes)} found)\n"
        sections.append(notes_header)
        chars_used += len(notes_header)

        for note in project_notes:
            if chars_used >= char_budget:
                sections.append(
                    f"\n... {len(project_notes)} notes total, "
                    f"truncated at budget. Use zk:cx to search more.\n"
                )
                break
            note_text = NOTE_SEPARATOR + _note_to_context(note) + "\n"
            sections.append(note_text)
            chars_used += len(note_text)

    # 4. Summary footer
    footer = (
        f"\n---\n"
        f"Context: {chars_used} chars | "
        f"Notes loaded: {len(project_notes)} | "
        f"Logs loaded: {len(logs)}\n"
    )
    sections.append(footer)

    return "".join(sections)


def cross_ref_context(vault_path: str, topic: str,
                      char_budget: int = 16000) -> str:
    """Build context for a cross-project topic search."""
    reader = VaultReader(vault_path)
    results = reader.cross_ref(topic)

    if not results:
        return f"No notes found for topic: '{topic}'"

    sections = [f"# Cross-Reference: {topic}\n"]
    sections.append(f"Found {len(results)} related notes:\n")
    chars_used = len(sections[0]) + len(sections[1])

    for note in results:
        if chars_used >= char_budget:
            sections.append(f"\n... truncated. {len(results)} total results.")
            break
        note_text = NOTE_SEPARATOR + _note_to_context(note) + "\n"
        sections.append(note_text)
        chars_used += len(note_text)

    return "".join(sections)


def audit_vault(vault_path: str) -> str:
    """
    Run full vault audit. Returns report of issues found.
    Checks: validation errors, prose patterns, note length, missing links.
    """
    reader = VaultReader(vault_path)
    notes = reader.all_permanent()

    report = [f"# Vault Audit — {len(notes)} permanent notes\n"]
    issues_found = 0

    for note in notes:
        note_issues = []

        # Validation
        val_errors = validate_frontmatter(note)
        if val_errors:
            note_issues.extend([f"  ✗ {e}" for e in val_errors])

        # Lint
        lint_issues = lint_note(note)
        if lint_issues:
            note_issues.extend([f"  ⚠ {i}" for i in lint_issues])

        if note_issues:
            issues_found += 1
            report.append(f"\n## {note.slug}\n")
            report.extend([f"{issue}\n" for issue in note_issues])

    if issues_found == 0:
        report.append("\n✓ No issues found. Vault is clean.\n")
    else:
        report.append(
            f"\n---\n{issues_found} notes with issues. "
            f"Run `zk:compress [slug]` to fix prose issues.\n"
        )

    return "".join(report)


def draft_session_log_context(vault_path: str, project: str) -> str:
    """
    Build context for drafting a session log.
    Returns recent state summary to help write the log.
    """
    reader = VaultReader(vault_path)
    logs = reader.recent_logs(project, n=1)
    inbox = reader.list_inbox()

    sections = [f"# Session Log Draft — {project}\n"]

    if logs:
        sections.append(f"## Last Session\n{logs[0].body[:1000]}\n")

    if inbox:
        sections.append(f"\n## Unprocessed Inbox ({len(inbox)} notes)\n")
        for note in inbox:
            sections.append(f"- {note.slug}: {note.title}\n")

    sections.append(
        "\n## Template\nFill in the session log template below:\n"
    )

    return "".join(sections)