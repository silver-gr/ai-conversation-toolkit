# Research Index Generator

Create a unified index of all research-related conversations across ChatGPT, Claude, and Gemini exports.

## Overview

The `research_index.py` script scans your extracted conversation markdown files and identifies those that used research tools:

- **ChatGPT Deep Research**: Comprehensive research reports with sources
- **Claude Research Tool**: Web search and research allowance usage
- **Gemini Deep Research**: Research plans and completed research reports
- **Research Discussions**: Conversations with research-heavy content

It creates a single `RESEARCH_INDEX.md` file that serves as a knowledge base directory of all your AI-assisted research.

## Why Use This?

If you've used ChatGPT's Deep Research feature or Claude's web search capabilities, you have valuable research scattered across many conversations. This script:

- Finds all research conversations automatically
- Categorizes by research type
- Provides quick access via linked index
- Shows research queries and topics
- Tracks research output size

## Prerequisites

You must first extract your conversations using:

```bash
# Extract ChatGPT conversations
python3 scripts/simple_extractor.py chatgpt-conversations.json -o output/chatgpt-full

# Extract Claude conversations
python3 scripts/simple_extractor.py claude-conversations.json -o output/claude-full

# Extract Gemini conversations
python3 scripts/gemini_extractor.py gemini-activity.json -o output/gemini
```

## Usage

```bash
python3 scripts/research_index.py
```

The script looks for:
- `output/chatgpt-full/conversations/` - ChatGPT markdown files
- `output/claude-full/conversations/` - Claude markdown files

And creates:
- `output/RESEARCH_INDEX.md` - Unified research index

## Output Structure

```markdown
# Research Conversations Index

*Generated: 2025-12-16 10:30*

## Summary

- **Total Research Conversations**: 280
- **ChatGPT Deep Research**: 76
- **Claude Research**: 104
- **Gemini Deep Research**: 100

### By Research Type

- **ChatGPT Deep Research**: 117 conversations
- **Claude Research Tool**: 28 conversations
- **Gemini Deep Research**: 93 conversations
- **Research Discussion**: 27 conversations
- **Research Topic**: 15 conversations

---

## ChatGPT Deep Research

| Date | Title | Type | Messages | Size |
|------|-------|------|----------|------|
| 2025-12-15 | [AI Architecture Research](chatgpt-full/...) | ChatGPT Deep Research | 12 | 45,000 |

---

## Claude Research

| Date | Title | Type | Messages | Size |
|------|-------|------|----------|------|
| 2025-12-14 | [Market Analysis](claude-full/...) | Claude Research Tool | 8 | 23,000 |

---

## Research Topics Detail

### Recent Research Queries

#### AI Architecture Research

- **Date**: 2025-12-15
- **Source**: CHATGPT
- **Type**: ChatGPT Deep Research
- **Size**: 45,000 characters

> Research the best architecture patterns for...
```

## Detection Patterns

### ChatGPT Deep Research

The script looks for these indicators:
- "deep research"
- "conducted a comprehensive"
- "research report"
- "sources consulted"
- "thorough research"
- "extensive research"

### Claude Research Tool

The script looks for:
- "research allowance"
- "research tool"
- "web_search"
- "searching the web"
- "i'll research this"
- "let me search"

### Gemini Deep Research

The script looks for:
- "here's a research plan"
- "i've completed your research"
- "start research"
- "έναρξη έρευνας" (Greek: "Start research")
- "research plan for that topic"
- "let me know if you need to update it"

### Research Discussion

Fallback detection for general research content:
- Contains "research" AND ("sources" OR "studies" OR "findings")

## Customization

### Adding Detection Patterns

Edit `research_index.py` and add to the pattern lists:

```python
deep_research_patterns = [
    'deep research',
    'conducted a comprehensive',
    # Add your patterns here
]
```

### Changing Output Paths

Edit the `main()` function:

```python
claude_dir = base_dir / 'output' / 'claude-full'
chatgpt_dir = base_dir / 'output' / 'chatgpt-full'
output_path = base_dir / 'output' / 'RESEARCH_INDEX.md'
```

## Metadata Extraction

For each conversation, the script extracts:

| Field | Source |
|-------|--------|
| Title | First `# ` heading |
| Date | `**Date**:` field |
| Source | `**Source**:` field |
| Messages | `**Messages**:` field |
| Characters | `**Total Characters**:` field |
| First Query | First `### USER` section |

## Best Practices

1. **Run after extraction**: Always extract conversations first with `simple_extractor.py`

2. **Regular updates**: Re-run after new exports to keep index current

3. **Use consistent output paths**: The script expects specific directory names

4. **Review detected types**: Some conversations may be miscategorized - the detection is heuristic

## Limitations

- Only scans markdown files created by the extractor scripts
- Pattern matching is keyword-based (not semantic)
- Requires specific directory structure

## Supported Sources

The script automatically scans these directories:

| Source | Directory | Extractor Script |
|--------|-----------|------------------|
| ChatGPT | `output/chatgpt-full/` | `simple_extractor.py` |
| Claude | `output/claude-full/` | `simple_extractor.py` |
| Gemini | `output/gemini/` | `gemini_extractor.py` |

## Requirements

- Python 3.10+
- No external dependencies
- Pre-extracted conversations in expected locations

## Related Scripts

- `simple_extractor.py` - Extract conversations to markdown (required first)
- `gemini_extractor.py` - Extract Gemini conversations
- `conversation_summarizer.py` - AI-powered conversation analysis
