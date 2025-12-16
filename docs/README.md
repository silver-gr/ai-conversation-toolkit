# AI Conversation Export Toolkit

A comprehensive toolkit for extracting, analyzing, and indexing conversations from AI assistants (ChatGPT, Claude, Google Gemini).

## Quick Start

```bash
# Extract ChatGPT or Claude conversations
python3 scripts/simple_extractor.py conversations.json -o output/chatgpt

# Extract Google Gemini activity
python3 scripts/gemini_extractor.py MyActivity.json -o output/gemini

# Extract Claude memories
python3 scripts/memories_to_md.py

# Create research index
python3 scripts/research_index.py

# AI-powered analysis (requires Claude API)
python3 scripts/conversation_summarizer.py conversations.json
```

## Scripts Overview

| Script | Purpose | AI Required | Speed |
|--------|---------|-------------|-------|
| `simple_extractor.py` | Extract ChatGPT/Claude conversations | No | Fast |
| `gemini_extractor.py` | Extract Google Gemini activity | No | Fast |
| `memories_to_md.py` | Extract Claude memories | No | Fast |
| `research_index.py` | Index research conversations | No | Fast |
| `conversation_summarizer.py` | AI-powered analysis | Yes (Claude) | Slow |
| `parser.py` | Core parsing library | No | N/A |

## Workflow

### 1. Export Your Data

**ChatGPT:**
- Settings → Data controls → Export → Download ZIP → Extract `conversations.json`

**Claude:**
- Settings → Export → Download → `conversations.json` and `memories.json`

**Google Gemini:**
- [Google Takeout](https://takeout.google.com/) → Select "My Activity" → "Gemini Apps" → Download

### 2. Extract Conversations

```bash
# ChatGPT
python3 scripts/simple_extractor.py ~/Downloads/conversations.json -o output/chatgpt-full

# Claude
python3 scripts/simple_extractor.py ~/Downloads/claude-export/conversations.json -o output/claude-full

# Gemini
python3 scripts/gemini_extractor.py ~/Downloads/Takeout/MyActivity.json -o output/gemini
```

### 3. Extract Memories (Claude only)

```bash
# Place memories.json in Claude/ directory first
python3 scripts/memories_to_md.py
```

### 4. Create Research Index

After extracting both ChatGPT and Claude:

```bash
python3 scripts/research_index.py
```

### 5. Optional: AI Analysis

For deep context extraction and continuation strategies:

```bash
python3 scripts/conversation_summarizer.py output/chatgpt-full/conversations.json
```

## Output Structure

```
output/
├── chatgpt-full/
│   ├── INDEX.md
│   └── conversations/
│       ├── 20251215_conversation-title.md
│       └── ...
├── claude-full/
│   ├── INDEX.md
│   └── conversations/
│       └── ...
├── gemini/
│   ├── INDEX.md
│   └── conversations/
│       └── ...
├── memories/
│   ├── main-context.md
│   ├── project-name.md
│   └── ...
└── RESEARCH_INDEX.md
```

## Supported Export Formats

### ChatGPT

- **Format**: Tree-structured JSON with parent-child node mapping
- **Timestamps**: Unix epoch (seconds)
- **Features**: Projects/GPTs grouping, model metadata

### Claude

- **Format**: Linear array of messages
- **Timestamps**: ISO 8601
- **Features**: Summaries, attachments, memories export

### Google Gemini

- **Format**: Activity log (not threaded conversations)
- **Timestamps**: ISO 8601
- **Features**: Canvas content, image attachments, research reports

## Detailed Documentation

- [ChatGPT & Claude Extractor](chatgpt-claude-extractor.md) - Full conversation extraction
- [Gemini Extractor](gemini-extractor.md) - Google Gemini activity extraction
- [Claude Memories Extractor](claude-memories-extractor.md) - Memory context extraction
- [Research Index](research-index.md) - Research conversation indexing
- [Conversation Summarizer](conversation-summarizer.md) - AI-powered analysis

## Common Use Cases

### Archive All Conversations

```bash
python3 scripts/simple_extractor.py chatgpt.json -o archive/chatgpt
python3 scripts/simple_extractor.py claude.json -o archive/claude
python3 scripts/gemini_extractor.py gemini.json -o archive/gemini
```

### Find Research I've Done

```bash
# First extract, then index
python3 scripts/simple_extractor.py conversations.json -o output/chatgpt-full
python3 scripts/research_index.py
# Open output/RESEARCH_INDEX.md
```

### Prepare Context for Continuation

```bash
# Use AI analyzer for deep context
python3 scripts/conversation_summarizer.py conversations.json
# Review output for implementation state and continuation strategies
```

### Export Claude's Knowledge About Me

```bash
python3 scripts/memories_to_md.py
# Review output/memories/*.md
```

## Requirements

### All Scripts

- Python 3.10+
- No external dependencies for basic extraction

### Conversation Summarizer

- Python 3.11+
- Claude CLI (`pip install claude-cli`)
- Dependencies: `rich`, `pandas`, `openpyxl` (auto-installed via `uv`)

## Tips

1. **Start with simple extraction** - Use `simple_extractor.py` first, it's fast and free

2. **Use AI analysis selectively** - The summarizer is powerful but costs money; use for important conversations

3. **Cache is your friend** - The summarizer caches results; re-runs are fast and free

4. **Organize by source** - Keep ChatGPT, Claude, and Gemini exports in separate directories

5. **Regular exports** - Export periodically to keep your archive current

## Troubleshooting

### "Could not detect source format"

Your JSON file may not be a valid export. Check that it contains either:
- `"chat_messages"` (Claude)
- `"mapping"` (ChatGPT)

### "File too large"

For very large exports (>50MB), the parser automatically uses streaming. If you still have issues:
```bash
python3 scripts/simple_extractor.py large-file.json --max 500
```

### Greek/Unicode characters

All scripts use UTF-8 encoding and fully support non-ASCII characters.

## Contributing

Scripts are designed to be:
- Single-file (no complex dependencies)
- Well-documented (docstrings and comments)
- Extensible (clear functions for customization)

To add support for a new AI platform:
1. Study the export format
2. Create a new parser function
3. Add to the unified workflow

## License

These scripts are provided as-is for personal use.
