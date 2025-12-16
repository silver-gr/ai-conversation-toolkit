# ChatGPT & Claude Conversation Extractor

Convert ChatGPT and Claude conversation exports to readable markdown files with full content preservation.

## Overview

This script (`simple_extractor.py`) processes conversation exports from both ChatGPT and Claude, auto-detecting the format and converting them to organized markdown files. Unlike the AI-powered summarizer, this script preserves **complete conversation content** without any truncation or analysis.

## Features

- **Auto-detection**: Automatically identifies ChatGPT vs Claude export format
- **Full content**: Preserves complete message text (no truncation)
- **Organized output**: Creates individual markdown files per conversation
- **Index generation**: Creates a summary INDEX.md with all conversations
- **Topic extraction**: Simple keyword-based topic detection
- **Chronological naming**: Files named with dates for easy sorting

## Getting Your Data

### ChatGPT Export

1. Go to [ChatGPT](https://chat.openai.com/)
2. Click your profile icon → **Settings**
3. Go to **Data controls**
4. Click **Export data**
5. Wait for email, download the ZIP file
6. Extract and find `conversations.json`

### Claude Export

1. Go to [Claude](https://claude.ai/)
2. Click your profile icon → **Settings**
3. Find the **Export** option
4. Download your data
5. Find `conversations.json` in the export

## Usage

### Basic Usage

```bash
python3 scripts/simple_extractor.py path/to/conversations.json
```

Output goes to `output/` by default.

### Options

```bash
# Specify output directory
python3 scripts/simple_extractor.py conversations.json -o my-export

# Limit conversations processed
python3 scripts/simple_extractor.py conversations.json --max 100

# Summary mode (truncate long messages)
python3 scripts/simple_extractor.py conversations.json --summary
```

### All Options

| Option | Short | Description |
|--------|-------|-------------|
| `--output` | `-o` | Output directory (default: `output`) |
| `--max` | `-m` | Maximum conversations to process |
| `--summary` | | Truncate messages longer than 1000 chars |

## Output Structure

```
output/
├── INDEX.md                    # Summary with stats and links
└── conversations/
    ├── 20251215_my-conversation.md
    ├── 20251214_another-chat.md
    └── ...
```

### INDEX.md Contents

- Export date and time
- Total conversation count
- Total message count
- Total character count
- Average messages per conversation
- Sortable table with all conversations

### Conversation File Format

```markdown
# Conversation Title

## Metadata

- **Date**: 2025-12-15 10:30
- **Source**: CHATGPT
- **Messages**: 24
- **Total Characters**: 15,432
- **Summary**: AI-generated summary (if available)

---

## Conversation

### USER (10:30)

User's message here...

---

### ASSISTANT (10:31)

Assistant's response here...

---
```

## Export Format Differences

### ChatGPT Format

ChatGPT exports use a **tree structure** with parent-child node relationships:

```json
{
  "title": "My Conversation",
  "create_time": 1702656000,
  "mapping": {
    "node-id-1": {
      "message": {...},
      "parent": null,
      "children": ["node-id-2"]
    }
  }
}
```

Key characteristics:
- Timestamps as Unix epoch seconds
- Tree-based message structure
- Hidden system messages (filtered out)
- Model information in metadata

### Claude Format

Claude exports use a **linear array** of messages:

```json
{
  "uuid": "abc-123",
  "name": "Conversation Title",
  "chat_messages": [
    {
      "sender": "human",
      "text": "User message",
      "created_at": "2025-12-15T10:30:00Z"
    }
  ]
}
```

Key characteristics:
- ISO 8601 timestamps
- Linear message array
- Sender field: "human" or "assistant"
- Optional summary field

## File Naming

Files are named: `YYYYMMDD_title-slug.md`

- **Date prefix**: Enables chronological sorting
- **Title slug**: Lowercase, hyphenated, max 40 chars
- **Duplicate handling**: Auto-increments (`_1`, `_2`, etc.)

## Topic Extraction

The script extracts simple topic keywords from conversations:

- Analyzes first 500 chars of the first 5 messages
- Filters common English stop words (50+ words)
- Returns top 10 keywords by frequency
- Word length: 4-15 characters

## Performance

- Handles large exports (1000+ conversations)
- Progress indicator every 50 conversations
- Memory efficient for typical export sizes

For very large files (>50MB), consider using the streaming parser in `parser.py` directly.

## Comparison with Other Tools

| Feature | simple_extractor | conversation_summarizer |
|---------|------------------|------------------------|
| Content | Full (complete) | Analyzed (with AI) |
| Speed | Fast | Slower (API calls) |
| Cost | Free | Uses Claude API |
| Output | Raw markdown | Contextual analysis |
| Caching | None | SQLite cache |

Use `simple_extractor.py` when you want:
- Complete conversation archives
- Fast processing without API costs
- Raw content for manual review

Use `conversation_summarizer.py` when you want:
- AI-analyzed context extraction
- Conversation health assessment
- Continuation strategies

## Troubleshooting

### "Could not detect source format"
The script checks for `"chat_messages"` (Claude) or `"mapping"` (ChatGPT) in the first 2000 characters. Ensure your file is a valid export.

### Empty conversations skipped
Conversations with no user/assistant messages are automatically skipped.

### Unicode/encoding issues
The script uses UTF-8 encoding. Greek text and other Unicode characters are fully supported.

## Requirements

- Python 3.10+
- No external dependencies (standard library only)

## Related Scripts

- `parser.py` - Core parsing module (can be used as library)
- `conversation_summarizer.py` - AI-powered analysis
- `gemini_extractor.py` - Google Gemini exports
- `research_index.py` - Index research conversations
