# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Conversation Export Toolkit - extracts, analyzes, and indexes conversations from ChatGPT, Claude, and Google Gemini into searchable markdown files.

## Commands

```bash
# Extract ChatGPT or Claude conversations
python3 scripts/simple_extractor.py ChatGPT/conversations.json -o output/chatgpt-full

# Extract Gemini activity (groups into sessions by default)
python3 scripts/gemini_extractor.py "Google/Η δραστηριότητά μου/Εφαρμογές Gemini/MyActivity.json" -o output/gemini

# Extract Claude memories
python3 scripts/memories_to_md.py

# Build unified research index (scans all output directories)
python3 scripts/research_index.py

# AI-powered analysis with caching (requires Claude CLI)
uv run scripts/conversation_summarizer.py ChatGPT/conversations.json --output-dir output/chatgpt-full --max 50
```

## Architecture

**Data flow**: Raw exports (`ChatGPT/`, `Claude/`, `Google/`) → Parser scripts → Markdown output (`output/`)

**Core parsing** (`parser.py`):
- `Message` and `Conversation` dataclasses normalize all formats
- ChatGPT uses tree traversal (parent-child mapping), Claude uses linear arrays, Gemini uses activity logs
- `parse_timestamp()` handles Unix epoch (ChatGPT) and ISO 8601 (Claude/Gemini)

**Export format differences**:
- ChatGPT: `mapping` dict with tree structure, timestamps as Unix seconds
- Claude: `chat_messages` array, `sender` field ("human"/"assistant")
- Gemini: Flat activity log, queries in `title`, responses in `safeHtmlItem[].html`, Canvas in `subtitles[].name`

**Research detection** (`research_index.py`):
- Scans `output/*/conversations/` for research patterns
- ChatGPT: "deep research", "sources consulted"
- Claude: "research allowance", "web_search"
- Gemini: "here's a research plan", "i've completed your research"

## Key Patterns

- All scripts auto-detect source format from JSON structure
- Output files named `YYYYMMDD_title-slug.md` for chronological sorting
- Gemini groups activities into sessions based on 30-minute time gaps (configurable via `--no-grouping`)
- `conversation_summarizer.py` uses SQLite cache with SHA256 content hashing for idempotency

## File Locations

- Raw exports: `ChatGPT/`, `Claude/`, `Google/` (gitignored)
- Generated output: `output/` (gitignored)
- Cache DBs: `*.db` files (gitignored)
- Documentation: `docs/*.md`
