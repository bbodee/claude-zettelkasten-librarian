"""
writer.py — Creates notes, updates frontmatter, writes session logs.
"""

import os
import sys
import re
from pathlib import Path
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schema import Note, permanent_note_template, session_log_template

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


class VaultWriter:
    def __init__(self, vault_path: str):
        self.vault = Path(vault_path)
        self.permanent = self.vault / "permanent"
        self.logs = self.vault / "logs"
        self.inbox = self.vault / "inbox"

    def _ensure_dir(self, path: Path):
        path.mkdir(parents=True, exist_ok=True)

    def _slug(self, title: str) -> str:
        """Convert title to kebab-case slug. Strips slashes and special chars."""
        slug = title.lower()
        slug = slug.replace("/", "-").replace("\\", "-")  # explicit slash handling
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"[\s_]+", "-", slug)
        slug = re.sub(r"-+", "-", slug).strip("-")
        return slug

    def create_permanent(self, title: str, tags: list[str],
                         projects: list[str], content: str = "",
                         draft: bool = True) -> tuple[str, str]:
        """
        Create a permanent note.
        If draft=True, writes to inbox/ for review.
        If draft=False, writes directly to permanent/.
        Returns (slug, full_path).
        """
        slug = self._slug(title)
        target_dir = self.inbox if draft else self.permanent
        self._ensure_dir(target_dir)

        filename = f"{slug}.md"
        path = target_dir / filename

        # Avoid overwrite
        counter = 1
        while path.exists():
            path = target_dir / f"{slug}-{counter}.md"
            counter += 1

        content_str = permanent_note_template(title, tags, projects, content)
        path.write_text(content_str, encoding="utf-8")

        location = "inbox (draft)" if draft else "permanent"
        return slug, str(path)

    def create_session_log(self, project: str,
                           description: str = "") -> tuple[str, str]:
        """
        Create a session log file.
        Returns (filename, full_path).
        """
        log_dir = self.logs / project
        self._ensure_dir(log_dir)

        today = date.today().isoformat()
        desc_slug = (description.lower().replace(" ", "-")
                     if description else "session")
        filename = f"{today}-{desc_slug}.md"
        path = log_dir / filename

        content = session_log_template(project, description)
        path.write_text(content, encoding="utf-8")

        return filename, str(path)

    def move_inbox_to_permanent(self, slug: str) -> tuple[bool, str]:
        """
        Move a note from inbox/ to permanent/.
        Returns (success, message).
        """
        # Find in inbox
        candidates = list(self.inbox.glob(f"{slug}*.md"))
        if not candidates:
            return False, f"No inbox note matching '{slug}'"

        source = candidates[0]
        self._ensure_dir(self.permanent)
        dest = self.permanent / source.name

        if dest.exists():
            return False, f"permanent/{source.name} already exists — rename first"

        source.rename(dest)
        return True, f"Moved to permanent/{source.name}"

    def update_note(self, slug: str, new_body: str,
                    update_date: bool = True) -> tuple[bool, str]:
        """
        Update the body of an existing permanent note.
        Preserves frontmatter, replaces body.
        """
        path = self.permanent / f"{slug}.md"
        if not path.exists():
            matches = list(self.permanent.rglob(f"{slug}.md"))
            if not matches:
                return False, f"Note '{slug}' not found"
            path = matches[0]

        content = path.read_text(encoding="utf-8")

        # Find end of frontmatter
        if content.startswith("---"):
            end = content.find("---", 3)
            if end != -1:
                fm = content[:end + 3]
                if update_date:
                    today = date.today().isoformat()
                    fm = re.sub(
                        r"updated:.*", f"updated: {today}", fm
                    )
                new_content = fm + "\n\n" + new_body
                path.write_text(new_content, encoding="utf-8")
                return True, f"Updated {slug}"

        path.write_text(new_body, encoding="utf-8")
        return True, f"Updated {slug} (no frontmatter preserved)"

    def deprecate_note(self, slug: str) -> tuple[bool, str]:
        """Mark a note as deprecated (never delete)."""
        path = self.permanent / f"{slug}.md"
        if not path.exists():
            return False, f"Note '{slug}' not found"

        content = path.read_text(encoding="utf-8")
        content = re.sub(r"status:\s*\w+", "status: deprecated", content)
        path.write_text(content, encoding="utf-8")
        return True, f"Deprecated {slug}"

    def write_compressed(self, slug: str,
                         compressed: str) -> tuple[bool, str]:
        """Write a compressed (LLM-optimized) version of a note."""
        path = self.permanent / f"{slug}.md"
        if not path.exists():
            return False, f"Note '{slug}' not found"

        # Keep frontmatter, replace body with compressed
        content = path.read_text(encoding="utf-8")
        if content.startswith("---"):
            end = content.find("---", 3)
            if end != -1:
                fm = content[:end + 3]
                new_content = fm + "\n\n" + compressed
                path.write_text(new_content, encoding="utf-8")
                return True, f"Compressed and saved {slug}"

        path.write_text(compressed, encoding="utf-8")
        return True, f"Compressed and saved {slug}"