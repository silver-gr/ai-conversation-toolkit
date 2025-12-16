# AI Conversation Export Toolkit

A comprehensive toolkit for extracting, analyzing, and indexing conversations from AI assistants (ChatGPT, Claude, Google Gemini).

## Features

- **Multi-platform support**: ChatGPT, Claude, and Google Gemini
- **Full content extraction**: Preserves complete conversations as markdown
- **Research indexing**: Automatically finds and indexes Deep Research sessions
- **AI-powered analysis**: Optional Claude-based context extraction
- **Memory extraction**: Convert Claude memories to organized files

## Quick Start

```bash
# Clone the repo
git clone https://github.com/yourusername/ai-conversation-toolkit.git
cd ai-conversation-toolkit

# Extract ChatGPT or Claude conversations
python3 scripts/simple_extractor.py path/to/conversations.json -o output/chatgpt

# Extract Google Gemini activity
python3 scripts/gemini_extractor.py path/to/MyActivity.json -o output/gemini

# Create unified research index
python3 scripts/research_index.py
```

## Scripts

| Script | Purpose |
|--------|---------|
| `simple_extractor.py` | Extract ChatGPT/Claude conversations to markdown |
| `gemini_extractor.py` | Extract Google Gemini activity to markdown |
| `memories_to_md.py` | Convert Claude memories to organized files |
| `research_index.py` | Create unified index of research conversations |
| `conversation_summarizer.py` | AI-powered conversation analysis (requires Claude API) |
| `parser.py` | Core parsing library |

## Getting Your Data

### ChatGPT
Settings → Data controls → Export → Download ZIP → Extract `conversations.json`

### Claude
Settings → Export → Download → `conversations.json` and `memories.json`

### Google Gemini
[Google Takeout](https://takeout.google.com/) → Select "My Activity" → "Gemini Apps" → Download

## Documentation

See the [docs/](docs/) folder for detailed documentation:

- [Overview & Quick Start](docs/README.md)
- [ChatGPT & Claude Extractor](docs/chatgpt-claude-extractor.md)
- [Gemini Extractor](docs/gemini-extractor.md)
- [Claude Memories Extractor](docs/claude-memories-extractor.md)
- [Research Index](docs/research-index.md)
- [Conversation Summarizer](docs/conversation-summarizer.md)

## Output Example

```
output/
├── chatgpt-full/
│   ├── INDEX.md
│   └── conversations/*.md
├── claude-full/
│   ├── INDEX.md
│   └── conversations/*.md
├── gemini/
│   ├── INDEX.md
│   └── conversations/*.md
├── memories/
│   └── *.md
└── RESEARCH_INDEX.md
```

## Requirements

- Python 3.10+
- No external dependencies for basic extraction
- Claude CLI for AI-powered analysis (optional)

## License

MIT
