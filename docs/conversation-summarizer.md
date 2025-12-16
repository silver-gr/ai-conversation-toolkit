# AI Conversation Analyzer & Context Extractor

Analyze AI conversation exports using Claude to extract actionable context, track implementation states, and generate continuation strategies.

## Overview

The `conversation_summarizer.py` script goes beyond simple extraction - it uses Claude AI to perform meta-analysis of your conversations, identifying:

- What was actually implemented vs. just discussed
- Decision journeys and evaluation criteria
- Information gaps and assumptions
- Conversation health and completeness
- Specific strategies for continuing conversations

## Key Features

- **AI-Powered Analysis**: Uses Claude API for deep contextual understanding
- **Intelligent Caching**: SQLite-based cache prevents redundant API calls
- **Cost Optimization**: Content-hashed idempotency keys ensure same content = cached result
- **ChatGPT Projects Support**: Groups and links related conversations
- **Parallel Processing**: Async execution for large exports
- **Progress Tracking**: Rich console output with progress bars

## When to Use This vs. Simple Extractor

| Use Case | Script |
|----------|--------|
| Archive conversations | `simple_extractor.py` |
| Search/grep content | `simple_extractor.py` |
| Understand context for continuation | `conversation_summarizer.py` |
| Track implementation status | `conversation_summarizer.py` |
| Identify what was decided vs. discussed | `conversation_summarizer.py` |

## Prerequisites

- **Claude CLI**: Must be installed and authenticated
  ```bash
  pip install claude-cli
  # or
  brew install claude
  ```
- **Valid API access**: Working Claude API credentials
- **Python 3.11+**

## Installation

The script uses `uv` for dependency management (auto-installed on first run):

```bash
# Dependencies are embedded in the script header:
# - rich (console output)
# - pandas (data handling)
# - openpyxl (Excel support)
```

## Usage

### Basic Usage

```bash
./scripts/conversation_summarizer.py conversations.json
```

Or:

```bash
python3 scripts/conversation_summarizer.py conversations.json
```

### With Options

```bash
# Specify output directory
./conversation_summarizer.py conversations.json --output-dir my-analysis

# Limit conversations analyzed
./conversation_summarizer.py conversations.json --max 50

# Custom cache file
./conversation_summarizer.py conversations.json --cache-file my_cache.db

# Disable caching (re-analyze everything)
./conversation_summarizer.py conversations.json --no-cache

# Clean old cache entries (older than N days)
./conversation_summarizer.py conversations.json --clean-cache 7
```

### All Options

| Option | Description |
|--------|-------------|
| `--max N` | Maximum conversations to analyze |
| `--output-dir DIR` | Output directory for markdown files |
| `--cache-file FILE` | SQLite cache file path |
| `--no-cache` | Disable caching entirely |
| `--clean-cache DAYS` | Remove cache entries older than N days |

## Caching System

### How It Works

1. **Content Hash**: Each conversation's content is hashed (SHA256)
2. **Idempotency Key**: Hash becomes the cache lookup key
3. **Cache Hit**: If key exists, return cached analysis (no API call)
4. **Cache Miss**: Call Claude API, store result with key

### Benefits

- **Speed**: Skip API calls for unchanged conversations
- **Cost**: Save money on repeated analyses
- **Consistency**: Same content always gets same analysis
- **Incremental**: Only analyze new/changed conversations

### Cache Statistics

The script reports:
```
Cache Statistics:
  Hits: 45 (cached results reused)
  Misses: 5 (new API calls)
  Hit Rate: 90%
  Estimated Savings: $2.34
```

### Cache Database Schema

```sql
CREATE TABLE llm_cache (
    idempotency_key TEXT PRIMARY KEY,
    conversation_id TEXT,
    messages_hash TEXT,
    response_data BLOB,
    created_at TEXT,
    model_used TEXT,
    prompt_tokens INTEGER,
    response_tokens INTEGER
)
```

## Output Structure

```
output/
├── analysis/
│   ├── 20251215_project-discussion.md
│   ├── 20251214_code-review.md
│   └── ...
├── projects/
│   ├── project-abc123-summary.md    # Project-level summaries
│   └── ...
├── statistics.md                     # Global stats
└── topics.md                         # Topic analysis
```

## Analysis Output Format

Each analyzed conversation includes:

```markdown
# Conversation Title

## Context Summary

Brief summary of what the conversation was about...

## Implementation State

### Actually Implemented
- Feature X was fully coded and tested
- Database schema was created

### Discussed But Not Implemented
- Feature Y was designed but not built
- Authentication flow was planned

## Decision Journey

### Decisions Made
- Chose React over Vue for frontend
- Selected PostgreSQL for database

### Evaluation Criteria Used
- Performance requirements
- Team familiarity
- Long-term maintainability

## Information Gaps

- User requirements for feature Z unclear
- Performance benchmarks not established
- Security requirements not discussed

## Assumptions Made

- Assumed single-tenant architecture
- Assumed < 10,000 users initially

## Conversation Health

- **Completeness**: 75%
- **Clarity**: High
- **Actionability**: Medium

## Continuation Strategy

To continue this conversation effectively:

1. Clarify the user requirements for feature Z
2. Establish performance benchmarks
3. Review security requirements before implementation
4. Consider multi-tenant implications
```

## ChatGPT Projects Support

The script recognizes ChatGPT Project/GPT groupings:

- Groups conversations by `gizmo_id` (Project/GPT identifier)
- Creates project-level summaries
- Links related conversations
- Tracks shared context across project conversations

## Performance

### Parallel Processing

Uses `asyncio` with `ThreadPoolExecutor` for concurrent API calls:
- Multiple conversations analyzed simultaneously
- Respects API rate limits
- Progress tracking for each conversation

### Memory Efficiency

- Streams large files when needed
- Processes conversations incrementally
- Caches to disk (not memory)

## Cost Considerations

Each conversation analysis uses Claude API tokens:
- Input: Conversation content (varies by length)
- Output: ~500-1000 tokens per analysis
- Estimate: $0.01-0.05 per conversation

**Use caching** to minimize costs on re-runs.

## Troubleshooting

### "Claude CLI not found"

Install the Claude CLI:
```bash
pip install claude-cli
```

### "API authentication failed"

Ensure Claude CLI is authenticated:
```bash
claude auth login
```

### Cache corruption

Delete the cache file and re-run:
```bash
rm conversation_cache.db
./conversation_summarizer.py conversations.json
```

### Rate limiting

The script handles rate limits with retries. For large exports, consider:
- Using `--max` to limit conversations
- Running in batches
- Using a longer delay between calls

## Advanced Usage

### As a Library

```python
from conversation_summarizer import ConversationSummarizer

summarizer = ConversationSummarizer(
    input_file='conversations.json',
    cache_file='my_cache.db'
)

# Analyze single conversation
analysis = summarizer.analyze_conversation(conv_data)

# Get cache statistics
stats = summarizer.get_cache_stats()
```

### Custom Analysis Prompts

Edit the `ANALYSIS_PROMPT` constant in the script to customize what Claude extracts from conversations.

## Requirements

- Python 3.11+
- Claude CLI (installed and authenticated)
- Dependencies: `rich`, `pandas`, `openpyxl`

## Related Scripts

- `simple_extractor.py` - Fast extraction without AI analysis
- `parser.py` - Core parsing module
- `research_index.py` - Index research conversations
- `memories_to_md.py` - Extract Claude memories
