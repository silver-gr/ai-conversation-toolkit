# Gemini Activity Extractor

Convert Google Gemini Apps Activity Takeout exports to readable markdown files.

## Overview

Google Gemini exports your activity as a flat activity log (not threaded conversations like ChatGPT or Claude). Each entry represents a single interaction - either a query you submitted or a Canvas you created.

This script:
- Parses the Gemini activity JSON export
- Groups related activities into conversation sessions based on time proximity
- Converts HTML responses to clean markdown
- Extracts Gemini Canvas content (code, reports, documents)
- Creates an index file with statistics and links to all conversations

## Getting Your Gemini Data

1. Go to [Google Takeout](https://takeout.google.com/)
2. Click "Deselect all"
3. Find and select **"My Activity"**
4. Click "All activity data included" and select only **"Gemini Apps"**
5. Choose your export format (JSON) and delivery method
6. Download and extract the archive

Your data will be in a path like:
```
Takeout/My Activity/Gemini Apps/MyActivity.json
```

Or in Greek:
```
Takeout/Η δραστηριότητά μου/Εφαρμογές Gemini/Ηδραστηριότητάμου.json
```

## Usage

### Basic Usage

```bash
python3 scripts/gemini_extractor.py path/to/MyActivity.json
```

This outputs to `output/gemini/` by default.

### Options

```bash
# Specify output directory
python3 scripts/gemini_extractor.py MyActivity.json -o my-gemini-export

# Limit number of conversations processed
python3 scripts/gemini_extractor.py MyActivity.json --max 50

# Keep each activity separate (disable session grouping)
python3 scripts/gemini_extractor.py MyActivity.json --no-grouping
```

### Full Options

| Option | Short | Description |
|--------|-------|-------------|
| `--output` | `-o` | Output directory (default: `output/gemini`) |
| `--max` | `-m` | Maximum conversations to process |
| `--no-grouping` | | Keep each activity as a separate file instead of grouping into sessions |

## Output Structure

```
output/gemini/
├── INDEX.md                    # Summary with stats and links
└── conversations/
    ├── 20251215_my-query-title.md
    ├── 20251214_another-session.md
    └── ...
```

### INDEX.md

Contains:
- Total activity count
- Number of conversation sessions
- Total character count
- Canvas creation count
- Table of all conversations with dates, titles, and sizes

### Conversation Files

Each markdown file includes:
- **Metadata**: Date, source, activity count, character count
- **Conversation**: Full query/response pairs with timestamps
- **Canvas Content**: Complete code, reports, or documents from Gemini Canvas

## Gemini Export Format

Unlike ChatGPT and Claude which export threaded conversations, Gemini exports an activity log where each entry is standalone:

### Query Entry
```json
{
  "header": "Gemini Apps",
  "title": "Submitted query How do I...",
  "time": "2025-12-15T10:30:00.000Z",
  "safeHtmlItem": [{"html": "<p>Response content...</p>"}]
}
```

### Canvas Entry
```json
{
  "header": "Gemini Apps",
  "title": "Created Gemini Canvas titled My Document",
  "time": "2025-12-15T10:35:00.000Z",
  "subtitles": [{"name": "# Full canvas content..."}]
}
```

## Session Grouping

By default, the script groups activities into "conversation sessions" based on time:
- Activities within **30 minutes** of each other are grouped together
- This recreates the feel of a conversation thread
- Use `--no-grouping` to keep each activity separate

## Example Output

### Conversation Markdown

```markdown
# How to build a REST API

## Metadata

- **Date**: 2025-12-15 10:30
- **Source**: GEMINI
- **Activities**: 3
- **Total Characters**: 5,432

---

## Conversation

### USER (10:30)

How do I build a REST API in Python?

---

### GEMINI

Here's how to build a REST API using FastAPI...

---

### USER (10:32)

Can you add authentication?

---

### GEMINI

Sure! Here's how to add JWT authentication...
```

## Comparison with Other Exporters

| Feature | ChatGPT | Claude | Gemini |
|---------|---------|--------|--------|
| Export format | Threaded conversations | Threaded conversations | Activity log |
| Message linking | Parent-child tree | Sequential array | Time-based grouping |
| Timestamps | Unix epoch | ISO 8601 | ISO 8601 |
| Response format | JSON parts | Text/content array | HTML |
| Special content | GPT mentions | Attachments, files | Canvas, images |

## Troubleshooting

### "File not found" error
Make sure the path to your JSON file is correct. The filename may be in your system's language (e.g., Greek).

### Empty or few conversations
- Check that you selected "Gemini Apps" in Google Takeout
- The export only includes activities with your Gemini history enabled

### Missing responses
Some activities (like image generations) may not have text responses in the export.

## Requirements

- Python 3.10+
- No external dependencies (uses only standard library)

## Related Scripts

- `simple_extractor.py` - Extract ChatGPT and Claude conversations
- `parser.py` - Core parsing module for ChatGPT/Claude formats
- `conversation_summarizer.py` - AI-powered conversation analysis
- `research_index.py` - Index research conversations across all sources
