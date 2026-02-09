# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Conversation Export Toolkit - extracts, analyzes, and indexes conversations from ChatGPT, Claude, and Google Gemini into searchable markdown files with optional Obsidian vault generation.

## Commands

```bash
# =============================================================================
# UNIFIED IMPORT CLI (RECOMMENDED)
# =============================================================================
# Main entry point for all imports - orchestrates extraction, logging, and post-processing

# Full import from all sources (auto-detects default paths)
python3 scripts/run_import.py --all

# Incremental import (only new conversations, skip existing)
python3 scripts/run_import.py --all --incremental

# Import specific sources only
python3 scripts/run_import.py --chatgpt ChatGPT/conversations.json
python3 scripts/run_import.py --claude Claude/conversations.json
python3 scripts/run_import.py --gemini "Google/path/to/MyActivity.json"

# Full import with post-processing
python3 scripts/run_import.py --all --research-index --memories

# Preview what would happen (no changes made)
python3 scripts/run_import.py --all --dry-run

# Add notes to import session
python3 scripts/run_import.py --all --notes "Monthly backup import"

# =============================================================================
# INDIVIDUAL EXTRACTORS (for manual/fine-grained control)
# =============================================================================

# Extract ChatGPT or Claude conversations (auto-detects format)
python3 scripts/simple_extractor.py ChatGPT/conversations.json -o output/chatgpt-full
python3 scripts/simple_extractor.py Claude/conversations.json -o output/claude-full

# Extract Gemini activity (groups into sessions by 30-min gaps)
python3 scripts/gemini_extractor.py "Google/Η δραστηριότητά μου/Εφαρμογές Gemini/MyActivity.json" -o output/gemini
python3 scripts/gemini_extractor.py path/to/MyActivity.json -o output/gemini --no-grouping  # Disable session grouping

# Extract Claude memories
python3 scripts/memories_to_md.py

# Build unified research index (scans output/*/conversations/)
python3 scripts/research_index.py

# AI-powered analysis with caching (requires Claude CLI)
uv run scripts/conversation_summarizer.py ChatGPT/conversations.json --output-dir output/chatgpt-full --max 50
uv run scripts/conversation_summarizer.py path/to/conversations.json --no-cache  # Skip cache
uv run scripts/conversation_summarizer.py path/to/conversations.json --clean-cache 7  # Clean entries >7 days

# Build Obsidian vault from extracted conversations
python3 scripts/build_december_vault.py  # Edit VAULT_DIR and date patterns in script

# Import logging (manual control - usually handled by run_import.py)
python3 scripts/import_logger.py status                          # Show current status
python3 scripts/import_logger.py start --notes "Initial import"  # Start new import session
python3 scripts/import_logger.py complete <import_id>            # Mark import complete
python3 scripts/import_logger.py regenerate                      # Rebuild markdown report
```

## Architecture

**Data flow**: Raw exports (`ChatGPT/`, `Claude/`, `Google/`) → Parser scripts → Markdown output (`output/`) → Optional vault generation

### Core Modules

**`parser.py`** - Shared parsing library:
- `Message` and `Conversation` dataclasses normalize all formats
- `parse_timestamp()` handles Unix epoch (ChatGPT) and ISO 8601 (Claude/Gemini)
- Streaming support via `ijson` for large files

**`simple_extractor.py`** - ChatGPT/Claude extraction:
- Auto-detects format from JSON structure (`mapping` dict = ChatGPT, `chat_messages` = Claude)
- ChatGPT tree traversal via parent-child `mapping` dict
- Claude linear `chat_messages` array with `sender` field ("human"/"assistant")

**`gemini_extractor.py`** - Google Gemini extraction:
- Parses flat activity logs (not threaded conversations)
- Queries in `title`, responses in `safeHtmlItem[].html`, Canvas artifacts in `subtitles[].name`
- HTML→Markdown conversion with `strip_html()`
- Groups activities into sessions based on 30-minute time gaps (configurable)

**`conversation_summarizer.py`** - AI-powered analysis:
- Uses `uv run` with inline script dependencies (rich, pandas, openpyxl)
- SQLite cache with SHA256 content hashing for idempotency
- Requires Claude CLI for LLM analysis

**`research_index.py`** - Research detection:
- Scans `output/*/conversations/` for research patterns
- ChatGPT: "deep research", "sources consulted"
- Claude: "research allowance", "web_search"
- Gemini: "here's a research plan", "i've completed your research", "έναρξη έρευνας"

**`run_import.py`** - Unified import orchestrator (main entry point):
- Single CLI to process all sources with consistent workflow
- Auto-detects default export paths (ChatGPT, Claude, Gemini)
- Integrates ImportLogger for session tracking
- Post-processing: research index, memories extraction, biography extraction
- Dry-run mode for previewing operations
- Rich terminal output (with fallback to plain text)

**`import_logger.py`** - Import tracking system:
- `ImportLogger` class tracks import sessions across sources (ChatGPT, Claude, Gemini)
- JSON log (`imports/import_log.json`) stores per-import stats and conversation IDs
- Auto-generates markdown report (`imports/IMPORT_LOG.md`) with summary tables
- `get_imported_ids(source)` returns all previously imported IDs for deduplication
- CLI interface for manual import management: `python3 scripts/import_logger.py status`

### Export Format Differences

| Source | Structure | Timestamps | Messages |
|--------|-----------|------------|----------|
| ChatGPT | `mapping` dict with tree structure | Unix seconds | Parent-child traversal |
| Claude | `chat_messages` array | ISO 8601 | Linear array, `sender` field |
| Gemini | Flat activity log | ISO 8601 | `title` (query) + `safeHtmlItem` (response) |

## Output Structure

```
output/
├── chatgpt-full/
│   ├── INDEX.md
│   └── conversations/YYYYMMDD_title-slug.md
├── claude-full/
│   ├── INDEX.md
│   └── conversations/YYYYMMDD_title-slug.md
├── gemini/
│   ├── INDEX.md
│   └── conversations/YYYYMMDD_title-slug.md
├── memories/
│   └── *.md
├── RESEARCH_INDEX.md
└── december-2025-vault/  # Optional Obsidian vault
    ├── Home.md
    ├── Daily/YYYY-MM-DD.md
    ├── Topics/*.md
    └── Conversations/{Claude,ChatGPT,Gemini}/*.md

imports/
├── import_log.json       # JSON log of all imports (schema below)
└── IMPORT_LOG.md         # Auto-generated markdown report
```

## Key Patterns

- All scripts use `slugify()` for safe filenames: lowercase, no special chars, max 50 chars
- Output files named `YYYYMMDD_title-slug.md` for chronological sorting
- Metadata block at top of each markdown with Date, Source, Messages, Total Characters
- Cache databases (`*.db`) use SQLite WAL mode for concurrent access

## File Locations

- Raw exports: `ChatGPT/`, `Claude/`, `Google/` (gitignored)
- Generated output: `output/` (gitignored)
- Import logs: `imports/` (tracked in git)
- Cache DBs: `*_cache.db` files (gitignored)
- Documentation: `docs/*.md`

## Import Log Schema

```json
{
  "imports": [
    {
      "id": "import_20251216_173900",
      "started_at": "2025-12-16T17:39:00Z",
      "completed_at": "2025-12-16T18:15:00Z",
      "status": "completed",
      "sources": {
        "chatgpt": {
          "file": "conversations.json",
          "total_in_export": 1247,
          "new_imported": 1247,
          "skipped_existing": 0,
          "conversation_ids": ["conv_abc123", "..."]
        },
        "claude": { "..." },
        "gemini": { "..." }
      },
      "post_processing": ["research_index", "biography_extractor"],
      "notes": ""
    }
  ],
  "metadata": {
    "last_updated": "...",
    "total_imports": 1,
    "schema_version": "1.0.0"
  }
}
```
