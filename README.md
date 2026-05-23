# Librarian — Claude Dev Vault Manager

Manages the LLM zettelkasten vault. Handles context injection,
note creation, session logging, vault auditing, and Claude API integration.

## Setup

1. Copy `librarian.cfg` and set your vault path:
```
vault_path = C:\Users\bodee\OneDrive\Documents\Obsidian\claude-dev
```

2. Set API key (optional — only needed for --llm commands):
```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```

3. Install optional dependency for better YAML parsing:
```powershell
pip install pyyaml
```

## Commands

### zk:rr [project]
Load context for a project. Reads MOC + recent logs + relevant notes.
```powershell
python librarian.py zk:rr my-project
```

### zk:ss [project] [description]
Draft a session log.
```powershell
python librarian.py zk:ss my-project feature-implementation
```

### zk:cx [topic]
Cross-reference a topic across ALL projects.
```powershell
python librarian.py zk:cx renpy
python librarian.py zk:cx "game loop"
```

### zk:lint
Audit vault quality. Flags prose notes, missing frontmatter, unknown tags.
```powershell
python librarian.py zk:lint
```

### zk:compress [slug] [--llm] [--aggressive]
Reformat a note to LLM-directive format.
```powershell
python librarian.py zk:compress my-note-slug
python librarian.py zk:compress my-note-slug --aggressive
python librarian.py zk:compress my-note-slug --llm    # best
```

### zk:compress-all [--llm]
Batch compress all llm_safe notes in the vault.
```powershell
python librarian.py zk:compress-all --llm
```

### zk:plan [description]
Generate a project plan informed by vault context.
Post result to Claude chat for refinement.
```powershell
python librarian.py zk:plan "new Python project with SQLite"
```

### zk:synthesize [project]
Synthesize all project notes into one dense context block.
```powershell
python librarian.py zk:synthesize my-project
```

### zk:process-inbox
Review inbox notes — move to permanent, skip, or deprecate.
```powershell
python librarian.py zk:process-inbox
```

### zk:new
Create a new permanent note draft in inbox.
```powershell
python librarian.py zk:new
```

## llm_safe field

Notes with llm_safe: false are NEVER sent to the Anthropic API.
Use for proprietary, client-specific, or sensitive content.

```yaml
---
title: Client X Billing Quirks
llm_safe: false
---
```

Notes without the field default to llm_safe: true.
Generalize work-specific content before adding to this vault.

## File structure

```
librarian/
├── librarian.py     ← entry point + command handlers
├── reader.py        ← vault search and note loading
├── writer.py        ← note creation and updates
├── context.py       ← context assembly for LLM injection
├── schema.py        ← templates, taxonomy, validation, compression
├── claude_api.py    ← Anthropic API integration
├── librarian.cfg    ← vault path config (machine-specific)
└── README.md        ← this file
```

## Adding to any project CLAUDE.md

```markdown
## Memory
python C:/path/to/librarian/librarian.py zk:rr [project-name]
```

One line. Full cross-project context. Every session.