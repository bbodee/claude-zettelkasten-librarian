"""
reader.py — Reads vault, searches notes, loads context.
"""

import os
import sys
import re
from pathlib import Path
from typing import Optional

# Ensure schema is importable from same directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schema import Note

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


# ── Frontmatter parsing ───────────────────────────────────────────────────────

def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from note content. Returns (meta, body)."""
    if not content.startswith("---"):
        return {}, content

    end = content.find("---", 3)
    if end == -1:
        return {}, content

    fm_str = content[3:end].strip()
    body = content[end + 3:].strip()

    if YAML_AVAILABLE:
        try:
            meta = yaml.safe_load(fm_str) or {}
        except Exception:
            meta = {}
    else:
        # Minimal fallback parser
        meta = {}
        for line in fm_str.split("\n"):
            if ":" in line:
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip()

    return meta, body


def load_note_from_path(path: Path) -> Note:
    """Load a Note object from a file path."""
    content = path.read_text(encoding="utf-8", errors="replace")
    meta, body = parse_frontmatter(content)

    slug = path.stem
    return Note(
        slug=slug,
        path=str(path),
        title=meta.get("title", slug),
        tags=meta.get("tags", []),
        created=str(meta.get("created", "")),
        updated=str(meta.get("updated", "")),
        status=meta.get("status", "active"),
        note_type=meta.get("type", "permanent"),
        projects=meta.get("projects", []),
        body=body,
        llm_safe=meta.get("llm_safe", True),
    )


# ── Vault reader ──────────────────────────────────────────────────────────────

class VaultReader:
    def __init__(self, vault_path: str):
        self.vault = Path(vault_path)
        self.permanent = self.vault / "permanent"
        self.logs = self.vault / "logs"
        self.mocs = self.vault / "mocs"
        self.inbox = self.vault / "inbox"

    def _load_dir(self, directory: Path) -> list[Note]:
        """Load all .md files from a directory recursively."""
        if not directory.exists():
            return []
        notes = []
        for path in sorted(directory.rglob("*.md")):
            try:
                notes.append(load_note_from_path(path))
            except Exception as e:
                print(f"  Warning: could not load {path.name}: {e}")
        return notes

    def search_permanent(self, tags: list[str]) -> list[Note]:
        """Find permanent notes matching ANY of the given tags."""
        notes = self._load_dir(self.permanent)
        tags_lower = [t.lower() for t in tags]
        return [
            n for n in notes
            if n.status != "deprecated"
            and any(t.lower() in tags_lower for t in n.tags)
        ]

    def search_permanent_all(self, tags: list[str]) -> list[Note]:
        """Find permanent notes matching ALL of the given tags."""
        notes = self._load_dir(self.permanent)
        tags_lower = set(t.lower() for t in tags)
        return [
            n for n in notes
            if n.status != "deprecated"
            and tags_lower.issubset(set(t.lower() for t in n.tags))
        ]

    def load_note(self, slug: str) -> Optional[Note]:
        """Load a specific note by slug."""
        path = self.permanent / f"{slug}.md"
        if path.exists():
            return load_note_from_path(path)
        # Search recursively
        matches = list(self.permanent.rglob(f"{slug}.md"))
        if matches:
            return load_note_from_path(matches[0])
        return None

    def recent_logs(self, project: str, n: int = 3) -> list[Note]:
        """Load the N most recent session logs for a project."""
        project_log_dir = self.logs / project
        if not project_log_dir.exists():
            # Try fuzzy match
            for d in self.logs.iterdir():
                if d.is_dir() and project.lower() in d.name.lower():
                    project_log_dir = d
                    break
            else:
                return []

        logs = []
        for path in sorted(project_log_dir.glob("*.md"), reverse=True)[:n]:
            logs.append(load_note_from_path(path))
        return logs

    def load_moc(self, project: str) -> Optional[Note]:
        """Load the MOC for a project."""
        # Exact match first
        path = self.mocs / f"{project}.md"
        if path.exists():
            return load_note_from_path(path)
        # Fuzzy match
        for path in self.mocs.glob("*.md"):
            if project.lower() in path.stem.lower():
                return load_note_from_path(path)
        return None

    def list_inbox(self) -> list[Note]:
        """List all notes in inbox."""
        return self._load_dir(self.inbox)

    def all_permanent(self) -> list[Note]:
        """Load all permanent notes."""
        return self._load_dir(self.permanent)

    def cross_ref(self, topic: str) -> list[Note]:
        """
        Find notes related to a topic across all projects.
        Searches title, tags, and body.
        """
        topic_lower = topic.lower()
        results = []

        for note in self.all_permanent():
            score = 0
            if topic_lower in note.title.lower():
                score += 3
            if any(topic_lower in t.lower() for t in note.tags):
                score += 2
            if topic_lower in note.body.lower():
                score += 1
            if score > 0:
                results.append((score, note))

        # Also search logs
        for note in self._load_dir(self.logs):
            if topic_lower in note.body.lower():
                results.append((1, note))

        results.sort(key=lambda x: x[0], reverse=True)
        return [note for _, note in results]

    def find_project_notes(self, project: str) -> list[Note]:
        """Find all permanent notes tagged with or belonging to a project."""
        all_notes = self.all_permanent()
        project_lower = project.lower()
        return [
            n for n in all_notes
            if project_lower in [p.lower() for p in n.projects]
            or project_lower in [t.lower() for t in n.tags]
        ]