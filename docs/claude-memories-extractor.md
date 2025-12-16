# Claude Memories Extractor

Convert Claude's `memories.json` export to organized, readable markdown files.

## Overview

Claude maintains "memories" - contextual information it has learned about you across conversations. When you export your Claude data, these memories are stored in `memories.json`. This script converts them into organized markdown files, grouped by detected project or topic.

## What Are Claude Memories?

Claude memories include:

- **Conversations Memory**: General context about you, your preferences, and working style
- **Project Memories**: Context specific to individual projects you've worked on

These memories help Claude provide more personalized and contextually aware responses.

## Getting Your Memories Data

1. Go to [Claude](https://claude.ai/)
2. Click your profile icon → **Settings**
3. Find the **Export** option
4. Download your data
5. Find `memories.json` in the export

The file structure looks like:

```json
[{
  "conversations_memory": "General context about you...",
  "project_memories": {
    "project-id-1": "Context about project 1...",
    "project-id-2": "Context about project 2..."
  }
}]
```

## Usage

### Basic Usage

```bash
python3 scripts/memories_to_md.py
```

The script expects:
- Input: `Claude/memories.json` (relative to project root)
- Output: `output/memories/` directory

### Custom Paths

Edit the `main()` function in the script to change paths:

```python
input_path = base_dir / 'Claude' / 'memories.json'
output_dir = base_dir / 'output' / 'memories'
```

## Output Structure

```
output/memories/
├── main-context.md           # General conversations memory
├── x3lixi-platform.md        # Detected project
├── wordpress-platform.md     # Another project
├── djing-music.md
├── adhd-course.md
└── misc.md                   # Unclassified memories
```

## Project Detection

The script automatically categorizes memories by detecting keywords:

| Keyword | Project Name |
|---------|--------------|
| x3lixi | x3lixi-platform |
| wordpress | wordpress-platform |
| dj, psytrance | djing-music |
| adhd | adhd-course |
| meditation | meditation-course |
| bdsm | bdsm-education |
| journaling | journaling-system |
| obsidian | knowledge-management |
| cognito | cognito-ai-system |
| flutter | flutter-development |
| prompt | prompt-engineering |
| course | course-development |
| translation | translation-work |
| research | research-methodology |

### Adding Custom Keywords

Edit the `extract_project_name()` function:

```python
project_keywords = {
    'x3lixi': 'x3lixi-platform',
    'your-keyword': 'your-project-name',
    # Add more mappings
}
```

## Output Format

Each markdown file includes:

```markdown
# Project Name

> Memory ID: `abc-123-def`
> Extracted: 2025-12-16 10:30

---

## Purpose & Context

What Claude remembers about this project...

## Technical Details

Specific technical context...

## Preferences

Your preferences for this project...
```

### Content Processing

The script:
- Converts `**Section**` headers to `## Section`
- Preserves original formatting
- Adds metadata header with memory ID and extraction date

## Handling Duplicates

If multiple memories map to the same project name, files are numbered:
- `x3lixi-platform.md`
- `x3lixi-platform-1.md`
- `x3lixi-platform-2.md`

## Use Cases

### Knowledge Backup
Export your Claude memories as readable documents you can store, search, and reference.

### Context Transfer
Share project context with team members or transfer to other AI tools.

### Memory Audit
Review what Claude has learned about you and your projects.

### Project Documentation
Use extracted memories as a starting point for project documentation.

## Example Output

### main-context.md

```markdown
# Main Context

> Memory ID: `main-context`
> Extracted: 2025-12-16 10:30

---

## Purpose & Context

User is a developer and content creator working on multiple
personal development and education platforms...

## Technical Preferences

- Prefers TypeScript over JavaScript
- Uses VS Code and Obsidian
- Follows clean architecture principles

## Communication Style

- Appreciates direct, technical explanations
- Values code examples over lengthy descriptions
```

### x3lixi-platform.md

```markdown
# X3lixi Platform

> Memory ID: `proj-x3lixi-abc123`
> Extracted: 2025-12-16 10:30

---

## Purpose & Context

x3lixi is a personal development platform focusing on
self-improvement, habit tracking, and wellness...

## Technical Stack

- Frontend: React/Next.js with TypeScript
- Backend: Node.js with Express
- Database: PostgreSQL with Prisma

## Current Focus

Building the habit tracking module with integration
to mood logging features...
```

## Troubleshooting

### "Input file not found"
Ensure `memories.json` is in the `Claude/` directory relative to the script location.

### Empty output
Your memories export may be empty if you haven't used Claude extensively or haven't enabled memory features.

### Miscategorized memories
The keyword detection is simple - edit the keywords dict for better categorization for your specific projects.

## Requirements

- Python 3.10+
- No external dependencies

## Related Scripts

- `simple_extractor.py` - Extract conversations (not memories)
- `conversation_summarizer.py` - AI-powered conversation analysis
