"""
librarian.py — Main entry point for the Claude Dev vault librarian.

Usage:
    python librarian.py zk:rr [project]
    python librarian.py zk:ss [project] [description]
    python librarian.py zk:cx [topic]
    python librarian.py zk:lint
    python librarian.py zk:compress [slug]
    python librarian.py zk:process-inbox
    python librarian.py zk:new [title] [tags...] --project [project]

Configuration:
    Set VAULT_PATH environment variable, or create librarian.cfg
    with vault_path = /path/to/your/vault
"""

import sys
import os
import argparse
from pathlib import Path
from datetime import date

# Ensure all sibling modules are importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ── Config ────────────────────────────────────────────────────────────────────

def get_vault_path() -> str:
    """Resolve vault path from env, config file, or prompt."""
    # 1. Environment variable
    vault = os.environ.get("CLAUDE_VAULT_PATH")
    if vault and Path(vault).exists():
        return vault

    # 2. Config file next to librarian.py
    cfg = Path(__file__).parent / "librarian.cfg"
    if cfg.exists():
        for line in cfg.read_text().splitlines():
            if line.startswith("vault_path"):
                _, _, path = line.partition("=")
                path = path.strip()
                if Path(path).exists():
                    return path

    # 3. Common locations
    common = [
        Path.home() / "OneDrive" / "Documents" / "Obsidian" / "claude-dev",
        Path.home() / "Documents" / "Obsidian" / "claude-dev",
        Path.home() / "Obsidian" / "claude-dev",
    ]
    for p in common:
        if p.exists():
            return str(p)

    print("ERROR: Vault not found. Set CLAUDE_VAULT_PATH or create librarian.cfg")
    sys.exit(1)


# ── Command handlers ──────────────────────────────────────────────────────────

def cmd_rr(vault_path: str, args: list[str]) -> None:
    """zk:rr [project] — Load context for a project."""
    from context import build_context

    if not args:
        project = input("Which project? ").strip()
    else:
        project = args[0]

    print(f"\nLoading context for: {project}")
    print("=" * 60)
    result = build_context(vault_path, project)
    print(result)


def cmd_ss(vault_path: str, args: list[str]) -> None:
    """zk:ss [project] [description] — Draft session log."""
    from writer import VaultWriter
    from context import draft_session_log_context
    from schema import session_log_template

    if not args:
        project = input("Which project? ").strip()
    else:
        project = args[0]

    description = " ".join(args[1:]) if len(args) > 1 else ""

    # Show context to help write the log
    ctx = draft_session_log_context(vault_path, project)
    print(ctx)

    # Create log file
    writer = VaultWriter(vault_path)
    filename, path = writer.create_session_log(project, description)

    print(f"\n✓ Session log created: {path}")
    print("Edit it to fill in the details.")
    print("\nInbox candidates to process after session:")
    print("  Run: python librarian.py zk:process-inbox")


def cmd_cx(vault_path: str, args: list[str]) -> None:
    """zk:cx [topic] — Cross-reference topic across all projects."""
    from context import cross_ref_context

    if not args:
        topic = input("Search topic: ").strip()
    else:
        topic = " ".join(args)

    print(f"\nCross-referencing: {topic}")
    print("=" * 60)
    result = cross_ref_context(vault_path, topic)
    print(result)


def cmd_lint(vault_path: str, args: list[str]) -> None:
    """zk:lint — Audit vault quality."""
    from context import audit_vault

    print("\nRunning vault audit...")
    print("=" * 60)
    result = audit_vault(vault_path)
    print(result)


def cmd_compress(vault_path: str, args: list[str]) -> None:
    """zk:compress [slug] [--llm] [--aggressive] — Reformat note."""
    from reader import VaultReader
    from writer import VaultWriter
    from schema import compress_note

    use_llm = "--llm" in args
    aggressive = "--aggressive" in args
    args = [a for a in args if not a.startswith("--")]

    if not args:
        slug = input("Note slug to compress: ").strip()
    else:
        slug = args[0]

    reader = VaultReader(vault_path)
    note = reader.load_note(slug)

    if not note:
        print(f"ERROR: Note '{slug}' not found")
        return

    if use_llm:
        from claude_api import compress_note_llm
        compressed = compress_note_llm(note)
        if not compressed:
            print("LLM compression failed or blocked. Try without --llm.")
            return
        mode = "llm (semantic)"
    else:
        mode = "aggressive" if aggressive else "standard"
        compressed = compress_note(note, mode=mode)

    print(f"\nMode: {mode}")
    print(f"Original: {len(note.body)} chars → {len(compressed)} chars")
    print(f"Savings: {int((1 - len(compressed)/max(len(note.body),1))*100)}%")
    print("=" * 60)
    print(compressed)
    print("=" * 60)

    confirm = input("\nWrite compressed version? [y/N] ").strip().lower()
    if confirm == "y":
        writer = VaultWriter(vault_path)
        ok, msg = writer.write_compressed(slug, compressed)
        print(f"{'✓' if ok else '✗'} {msg}")


def cmd_compress_all(vault_path: str, args: list[str]) -> None:
    """zk:compress-all [--llm] — Batch compress all safe notes."""
    from reader import VaultReader
    from writer import VaultWriter

    use_llm = "--llm" in args

    reader = VaultReader(vault_path)
    writer = VaultWriter(vault_path)
    notes = reader.all_permanent()

    if use_llm:
        from claude_api import compress_vault
        results = compress_vault(notes, writer)
        print("\n── Results ──")
        for slug, msg in results.items():
            print(f"  {slug}: {msg}")
    else:
        from schema import compress_note
        safe = [n for n in notes if n.llm_safe and n.status != "deprecated"]
        print(f"Compressing {len(safe)} notes (regex mode)...")
        for note in safe:
            compressed = compress_note(note, mode="aggressive")
            ok, msg = writer.write_compressed(note.slug, compressed)
            print(f"  {'✓' if ok else '✗'} {note.slug}: {msg}")


def cmd_plan(vault_path: str, args: list[str]) -> None:
    """zk:plan [description] — Generate project plan from vault context."""
    from reader import VaultReader
    from context import cross_ref_context
    from claude_api import plan_project, get_api_key

    if not get_api_key():
        print("ERROR: ANTHROPIC_API_KEY not set")
        return

    if not args:
        description = input("Project description: ").strip()
    else:
        description = " ".join(args)

    print(f"\nSearching vault for relevant context...")
    reader = VaultReader(vault_path)

    # Get relevant notes via cross-ref
    related = reader.cross_ref(description)
    safe_related = [n for n in related if n.llm_safe][:8]

    if safe_related:
        print(f"Found {len(safe_related)} relevant notes")
        vault_ctx = "\n\n---\n\n".join(
            f"# {n.title}\n{n.body[:800]}" for n in safe_related
        )
    else:
        print("No relevant vault notes found — planning from description only")
        vault_ctx = "No relevant prior context found."

    plan = plan_project(description, vault_ctx)

    if plan:
        print("\n" + "=" * 60)
        print(plan)
        print("=" * 60)
        print("\nPost this plan to Claude chat for refinement.")

        # Optionally save to inbox
        save = input("\nSave to inbox? [y/N] ").strip().lower()
        if save == "y":
            from writer import VaultWriter
            writer = VaultWriter(vault_path)
            slug, path = writer.create_permanent(
                title=f"Plan: {description[:50]}",
                tags=["plan", "project"],
                projects=[],
                content=plan,
                draft=True
            )
            print(f"✓ Saved to inbox: {path}")


def cmd_synthesize(vault_path: str, args: list[str]) -> None:
    """zk:synthesize [project] — Synthesize notes into dense context block."""
    from reader import VaultReader
    from claude_api import synthesize_context, get_api_key

    if not get_api_key():
        print("ERROR: ANTHROPIC_API_KEY not set")
        return

    if not args:
        project = input("Project: ").strip()
    else:
        project = args[0]

    reader = VaultReader(vault_path)
    notes = reader.find_project_notes(project)

    if not notes:
        print(f"No notes found for project: {project}")
        return

    print(f"Found {len(notes)} notes. Synthesizing...")
    result = synthesize_context(notes, project)

    if result:
        print("\n" + "=" * 60)
        print(result)
        print("=" * 60)
        char_count = len(result)
        print(f"\nSynthesized context: {char_count} chars "
              f"(vs ~{sum(len(n.body) for n in notes)} original)")


def cmd_process_inbox(vault_path: str, args: list[str]) -> None:
    """zk:process-inbox — Review and process inbox notes."""
    from reader import VaultReader
    from writer import VaultWriter
    from schema import validate_frontmatter, lint_note

    reader = VaultReader(vault_path)
    writer = VaultWriter(vault_path)
    inbox_notes = reader.list_inbox()

    if not inbox_notes:
        print("Inbox is empty. Nothing to process.")
        return

    print(f"\nInbox: {len(inbox_notes)} notes\n")

    for note in inbox_notes:
        print(f"─" * 60)
        print(f"Note: {note.slug}")
        print(f"Title: {note.title}")
        print(f"Tags: {note.tags}")
        print(f"Body preview: {note.body[:200]}...")

        val_errors = validate_frontmatter(note)
        if val_errors:
            print(f"Issues: {val_errors}")

        print("\nOptions:")
        print("  [m] Move to permanent")
        print("  [s] Skip for now")
        print("  [d] Discard (mark deprecated)")
        choice = input("Choice: ").strip().lower()

        if choice == "m":
            ok, msg = writer.move_inbox_to_permanent(note.slug)
            print(f"{'✓' if ok else '✗'} {msg}")
        elif choice == "d":
            ok, msg = writer.deprecate_note(note.slug)
            print(f"{'✓' if ok else '✗'} {msg}")
        else:
            print("Skipped.")

    print("\nInbox processing complete.")


def cmd_add_tags(vault_path: str, args: list[str]) -> None:
    """zk:add-tags — Add unknown tags from lint to schema taxonomy."""
    from reader import VaultReader
    from schema import validate_frontmatter, ALL_TAGS, TAG_TAXONOMY
    import ast

    # Run lint to find unknown tags
    reader = VaultReader(vault_path)
    notes = reader.all_permanent()

    unknown = set()
    for note in notes:
        errors = validate_frontmatter(note)
        for error in errors:
            if "Unknown tags" in error:
                # Extract tags from error message
                start = error.find("[") 
                end = error.find("]")
                if start != -1 and end != -1:
                    tag_str = error[start:end+1]
                    try:
                        tags = ast.literal_eval(tag_str)
                        unknown.update(tags)
                    except Exception:
                        pass

    if not unknown:
        print("No unknown tags found. Taxonomy is complete.")
        return

    print(f"\nUnknown tags found ({len(unknown)}):")
    for tag in sorted(unknown):
        print(f"  {tag}")

    print("\nFor each tag, enter the category to add it to:")
    print("  tools / concepts / domains / or new category name")
    print("  Press enter to skip a tag\n")

    additions: dict[str, list] = {}

    for tag in sorted(unknown):
        category = input(f"  [{tag}] category: ").strip()
        if not category:
            continue
        if category not in additions:
            additions[category] = []
        additions[category].append(tag)

    if not additions:
        print("No tags to add.")
        return

    # Read and update schema.py
    schema_path = Path(__file__).parent / "schema.py"
    content = schema_path.read_text(encoding="utf-8")

    for category, tags in additions.items():
        tags_str = ", ".join(f'"{t}"' for t in tags)

        if f'"{category}": [' in content:
            # Add to existing category
            old = f'"{category}": ['
            new = f'"{category}": [\n        {tags_str},'
            content = content.replace(old, new, 1)
            print(f"  Added to {category}: {tags}")
        else:
            # Add new category before closing brace of TAG_TAXONOMY
            insertion = f'    "{category}": [\n        {tags_str},\n    ],\n'
            content = content.replace(
                "}\n\nALL_TAGS",
                f"    {insertion}}}\n\nALL_TAGS"
            )
            print(f"  Created new category {category}: {tags}")

    schema_path.write_text(content, encoding="utf-8")
    print(f"\n✓ schema.py updated. Run zk:lint to verify.")
    """zk:new [title] — Create a new permanent note draft."""
    from writer import VaultWriter

    if not args:
        title = input("Note title: ").strip()
    else:
        title = " ".join(args)

    tags_input = input("Tags (comma-separated): ").strip()
    tags = [t.strip() for t in tags_input.split(",") if t.strip()]

    project = input("Project(s) (comma-separated, or enter to skip): ").strip()
    projects = [p.strip() for p in project.split(",") if p.strip()]

    content = input("Initial pattern/content (or enter to skip): ").strip()

    writer = VaultWriter(vault_path)
    slug, path = writer.create_permanent(
        title=title,
        tags=tags,
        projects=projects,
        content=content,
        draft=True
    )

    print(f"\n✓ Draft created: {path}")
    print(f"  Slug: {slug}")
    print(f"  Run `zk:process-inbox` to move to permanent when ready.")


# ── Main ──────────────────────────────────────────────────────────────────────

COMMANDS = {
    "zk:rr": cmd_rr,
    "zk:ss": cmd_ss,
    "zk:cx": cmd_cx,
    "zk:lint": cmd_lint,
    "zk:compress": cmd_compress,
    "zk:compress-all": cmd_compress_all,
    "zk:plan": cmd_plan,
    "zk:synthesize": cmd_synthesize,
    "zk:process-inbox": cmd_process_inbox,
    "zk:add-tags": cmd_add_tags,
    "zk:new": cmd_new,
}


def main():
    # Fix Windows cp1252 encoding issues with Unicode output
    import sys
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding="utf-8", errors="replace"
        )
    if len(sys.argv) < 2:
        print("Usage: python librarian.py [command] [args...]")
        print("\nCommands:")
        for cmd, fn in COMMANDS.items():
            print(f"  {cmd:25} {fn.__doc__.split(chr(10))[0].strip()}")
        sys.exit(0)

    command = sys.argv[1]
    args = sys.argv[2:]

    if command not in COMMANDS:
        print(f"Unknown command: {command}")
        print(f"Available: {', '.join(COMMANDS.keys())}")
        sys.exit(1)

    vault_path = get_vault_path()
    COMMANDS[command](vault_path, args)


if __name__ == "__main__":
    main()