#!/usr/bin/env python3
"""
Create an index of Research conversations from ChatGPT, Claude, and Gemini exports.
Detects Deep Research (ChatGPT, Gemini) and Research tool (Claude) usage.
"""

import os
import re
from pathlib import Path
from datetime import datetime


# Minimum character count for a file to be considered substantial research
MIN_RESEARCH_SIZE = 5000

# Patterns that indicate a conversation should be EXCLUDED from research index
EXCLUSION_PATTERNS = [
    # Cancelled/failed tasks
    r'task cancelled by user',
    r'η εργασία ακυρώθηκε',
    r'research cancelled',
    
    # Reminder/task management (not research)
    r'google tasks',
    r'θύμισε μου',
    r'remind me tomorrow',
    r'υπενθύμιση',
    r'θα σας υπενθυμίσω',
    
    # Generic list requests (not deep research)
    r'generate a comprehensive list of subreddits',
    r'list of subreddits',
    
    # Meta-questions about research tools (not actual research)
    r'how long would it take for me to manually do the research',
    r'how many sources did you check',
]

# Titles/filenames that are non-research content
EXCLUDED_TITLES = [
    'οδηγίες',  # Instructions/reminders
    'new-chat',  # Generic untitled chats that got misclassified
]


def is_excluded_content(filepath: Path) -> bool:
    """Check if file content matches exclusion patterns."""
    content = filepath.read_text(encoding='utf-8').lower()
    
    for pattern in EXCLUSION_PATTERNS:
        if re.search(pattern, content):
            return True
    
    # Check filename for excluded titles
    filename = filepath.stem.lower()
    for title in EXCLUDED_TITLES:
        if title in filename:
            return True
    
    return False


def _parse_yaml_frontmatter(content: str) -> dict:
    """Parse YAML frontmatter from markdown content."""
    fm = {}
    if not content.startswith('---'):
        return fm
    end = content.find('\n---', 3)
    if end == -1:
        return fm
    block = content[4:end]
    for line in block.split('\n'):
        if ':' in line and not line.startswith(' '):
            key, _, val = line.partition(':')
            val = val.strip().strip('"')
            fm[key.strip()] = val
    return fm


def extract_metadata_from_md(filepath: Path, source_hint: str = '') -> dict:
    """Extract metadata and first user query from markdown file."""
    content = filepath.read_text(encoding='utf-8')

    metadata = {
        'file': filepath.name,
        'path': str(filepath),
        'title': '',
        'date': '',
        'source': source_hint.upper() if source_hint else '',
        'messages': 0,
        'activities': 0,  # For Gemini
        'chars': 0,
        'first_query': '',
        'research_type': '',
    }

    # Try YAML frontmatter first
    fm = _parse_yaml_frontmatter(content)
    if fm:
        if fm.get('title'):
            metadata['title'] = fm['title']
        date_val = fm.get('date', '')
        if date_val:
            metadata['date'] = date_val[:10]
        source_val = fm.get('source', '')
        if source_val:
            metadata['source'] = source_val.upper()
        try:
            metadata['messages'] = int(fm.get('messages', 0))
        except (ValueError, TypeError):
            pass
        try:
            metadata['chars'] = int(fm.get('characters', 0))
        except (ValueError, TypeError):
            pass

    # Fallback to inline metadata patterns
    if not metadata['title']:
        title_match = re.search(r'^# (.+)$', content, re.MULTILINE)
        if title_match:
            metadata['title'] = title_match.group(1)

    if not metadata['date']:
        date_match = re.search(r'\*\*Date\*\*: (\d{4}-\d{2}-\d{2})', content)
        if date_match:
            metadata['date'] = date_match.group(1)

    if metadata['source'] == (source_hint.upper() if source_hint else ''):
        source_match = re.search(r'\*\*Source\*\*: (\w+)', content)
        if source_match:
            metadata['source'] = source_match.group(1)

    if not metadata['messages']:
        msg_match = re.search(r'\*\*Messages\*\*: (\d+)', content)
        if msg_match:
            metadata['messages'] = int(msg_match.group(1))

    if not metadata['chars']:
        char_match = re.search(r'\*\*Total Characters\*\*: ([\d,]+)', content)
        if char_match:
            metadata['chars'] = int(char_match.group(1).replace(',', ''))

    # Extract activities count (Gemini)
    act_match = re.search(r'\*\*Activities\*\*: (\d+)', content)
    if act_match:
        metadata['activities'] = int(act_match.group(1))

    # Extract first user message
    user_match = re.search(r'### USER.*?\n\n(.+?)(?=\n\n---|\n\n###)', content, re.DOTALL)
    if user_match:
        first_query = user_match.group(1).strip()
        metadata['first_query'] = first_query[:300] + '...' if len(first_query) > 300 else first_query

    return metadata


def detect_research_type(filepath: Path, source_hint: str = '') -> str:
    """Detect what type of research tool was used."""
    content = filepath.read_text(encoding='utf-8').lower()

    # Gemini Deep Research indicators (check first for Gemini files)
    gemini_research_patterns = [
        "here's a research plan",
        "i've completed your research",
        "start research",
        "έναρξη έρευνας",  # Greek: "Start research"
        "research plan for that topic",
        "let me know if you need to update it",
        "feel free to ask me follow-up questions",  # Gemini completion pattern
    ]

    # ChatGPT Deep Research indicators
    chatgpt_research_patterns = [
        'deep research',
        'conducted a comprehensive',
        'sources consulted',
        'i conducted a deep',
        'thorough research',
        'extensive research',
    ]

    # Claude Research tool indicators
    claude_research_patterns = [
        'research allowance',
        'research tool',
        'web_search',
        'searching the web',
        "i'll research this",
        'let me search',
    ]

    # Detect source from YAML frontmatter or inline metadata
    source_match = re.search(r'^source:\s*(\w+)', content[:500], re.MULTILINE)
    if not source_match:
        source_match = re.search(r'\*\*source\*\*: (\w+)', content[:500].lower())
    detected_source = source_match.group(1).lower() if source_match else source_hint.lower()

    # Check source-specific patterns based on detected source
    if detected_source == 'gemini':
        for pattern in gemini_research_patterns:
            if pattern in content:
                return 'Gemini Deep Research'

    if detected_source == 'claude':
        for pattern in claude_research_patterns:
            if pattern in content:
                return 'Claude Research Tool'

    if detected_source == 'chatgpt':
        for pattern in chatgpt_research_patterns:
            if pattern in content:
                return 'ChatGPT Deep Research'

    # Fallback: check all patterns if source not detected
    if not detected_source:
        for pattern in gemini_research_patterns:
            if pattern in content:
                return 'Gemini Deep Research'
        for pattern in chatgpt_research_patterns:
            if pattern in content:
                return 'ChatGPT Deep Research'
        for pattern in claude_research_patterns:
            if pattern in content:
                return 'Claude Research Tool'

    # Check for research-heavy content by topic
    if 'research' in content and ('sources' in content or 'studies' in content or 'findings' in content):
        return 'Research Discussion'

    return 'Research Topic'


def find_research_conversations(output_dir: Path, source_name: str = '') -> list[dict]:
    """Find all research-related conversations."""
    research_convs = []

    # Search patterns - expanded to include Gemini
    search_patterns = [
        r'deep research',
        r'research allowance',
        r'conducted.*research',
        r'research report',
        r'research tool',
        r"i'll research",
        r'comprehensive research',
        r'research findings',
        r'sources consulted',
        # Gemini-specific patterns
        r"here's a research plan",
        r"i've completed your research",
        r'start research',
        r'έναρξη έρευνας',  # Greek
        r'research plan for that topic',
    ]

    combined_pattern = '|'.join(search_patterns)

    conv_dir = output_dir / 'conversations'
    if not conv_dir.exists():
        return []

    for md_file in conv_dir.glob('*.md'):
        content = md_file.read_text(encoding='utf-8').lower()

        if re.search(combined_pattern, content):
            # Check exclusion patterns first
            if is_excluded_content(md_file):
                continue
            
            metadata = extract_metadata_from_md(md_file, source_name)
            
            # Filter out very small files (likely not real research)
            # Exception: files with file links (ChatGPT returns {{file:...}})
            has_file_link = '{{file:' in content or 'artifacts created' in content
            if metadata['chars'] < MIN_RESEARCH_SIZE and not has_file_link:
                continue
            
            metadata['research_type'] = detect_research_type(md_file, source_name)
            research_convs.append(metadata)

    return research_convs


def create_research_index(
    claude_dir: Path,
    chatgpt_dir: Path,
    gemini_dir: Path,
    output_path: Path
):
    """Create a unified research index markdown file."""

    print("Scanning for research conversations...")

    # Find research conversations from all sources
    claude_research = find_research_conversations(claude_dir, 'claude')
    chatgpt_research = find_research_conversations(chatgpt_dir, 'chatgpt')
    gemini_research = find_research_conversations(gemini_dir, 'gemini')

    print(f"  Claude: {len(claude_research)} research conversations")
    print(f"  ChatGPT: {len(chatgpt_research)} research conversations")
    print(f"  Gemini: {len(gemini_research)} research conversations")

    # Sort by date (newest first)
    claude_research.sort(key=lambda x: x['date'], reverse=True)
    chatgpt_research.sort(key=lambda x: x['date'], reverse=True)
    gemini_research.sort(key=lambda x: x['date'], reverse=True)

    total_count = len(claude_research) + len(chatgpt_research) + len(gemini_research)

    # Generate markdown
    lines = []
    lines.append("# Research Conversations Index")
    lines.append("")
    lines.append(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Total Research Conversations**: {total_count}")
    lines.append(f"- **ChatGPT Deep Research**: {len(chatgpt_research)}")
    lines.append(f"- **Claude Research**: {len(claude_research)}")
    lines.append(f"- **Gemini Deep Research**: {len(gemini_research)}")
    lines.append("")

    # Categorize by research type
    all_research = claude_research + chatgpt_research + gemini_research
    by_type = {}
    for conv in all_research:
        rtype = conv['research_type']
        if rtype not in by_type:
            by_type[rtype] = []
        by_type[rtype].append(conv)

    lines.append("### By Research Type")
    lines.append("")
    for rtype, convs in sorted(by_type.items()):
        lines.append(f"- **{rtype}**: {len(convs)} conversations")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ChatGPT Deep Research section
    lines.append("## ChatGPT Deep Research")
    lines.append("")
    if chatgpt_research:
        lines.append("| Date | Title | Type | Messages | Size |")
        lines.append("|------|-------|------|----------|------|")
        for conv in chatgpt_research:
            title = conv['title'][:50] + '...' if len(conv['title']) > 50 else conv['title']
            rel_path = f"chatgpt-full/conversations/{conv['file']}"
            lines.append(f"| {conv['date']} | [{title}]({rel_path}) | {conv['research_type']} | {conv['messages']} | {conv['chars']:,} |")
        lines.append("")
    else:
        lines.append("*No ChatGPT Deep Research conversations found.*")
        lines.append("")

    lines.append("---")
    lines.append("")

    # Claude Research section
    lines.append("## Claude Research")
    lines.append("")
    if claude_research:
        lines.append("| Date | Title | Type | Messages | Size |")
        lines.append("|------|-------|------|----------|------|")
        for conv in claude_research:
            title = conv['title'][:50] + '...' if len(conv['title']) > 50 else conv['title']
            rel_path = f"claude-full/conversations/{conv['file']}"
            lines.append(f"| {conv['date']} | [{title}]({rel_path}) | {conv['research_type']} | {conv['messages']} | {conv['chars']:,} |")
        lines.append("")
    else:
        lines.append("*No Claude Research conversations found.*")
        lines.append("")

    lines.append("---")
    lines.append("")

    # Gemini Deep Research section
    lines.append("## Gemini Deep Research")
    lines.append("")
    if gemini_research:
        lines.append("| Date | Title | Type | Activities | Size |")
        lines.append("|------|-------|------|------------|------|")
        for conv in gemini_research:
            title = conv['title'][:50] + '...' if len(conv['title']) > 50 else conv['title']
            rel_path = f"gemini/conversations/{conv['file']}"
            # Use activities count for Gemini, fallback to messages
            count = conv['activities'] if conv['activities'] > 0 else conv['messages']
            lines.append(f"| {conv['date']} | [{title}]({rel_path}) | {conv['research_type']} | {count} | {conv['chars']:,} |")
        lines.append("")
    else:
        lines.append("*No Gemini Deep Research conversations found.*")
        lines.append("")

    lines.append("---")
    lines.append("")

    # Detailed list with queries
    lines.append("## Research Topics Detail")
    lines.append("")
    lines.append("### Recent Research Queries")
    lines.append("")

    all_research_sorted = sorted(all_research, key=lambda x: x['date'], reverse=True)

    for conv in all_research_sorted[:30]:  # Top 30 most recent
        lines.append(f"#### {conv['title']}")
        lines.append("")
        lines.append(f"- **Date**: {conv['date']}")
        lines.append(f"- **Source**: {conv['source']}")
        lines.append(f"- **Type**: {conv['research_type']}")
        lines.append(f"- **Size**: {conv['chars']:,} characters")
        lines.append("")
        if conv['first_query']:
            # Handle multi-line queries in blockquote
            query_lines = conv['first_query'].split('\n')
            lines.append(f"> {query_lines[0]}")
            for qline in query_lines[1:]:
                lines.append(f"> {qline}")
            lines.append("")
        lines.append("---")
        lines.append("")

    # Write output
    output_path.write_text('\n'.join(lines), encoding='utf-8')
    print(f"\nCreated: {output_path}")
    print(f"Total research conversations indexed: {len(all_research)}")


def main():
    base_dir = Path(__file__).parent.parent

    claude_dir = base_dir / 'output' / 'claude-full'
    chatgpt_dir = base_dir / 'output' / 'chatgpt-full'
    gemini_dir = base_dir / 'output' / 'gemini'
    output_path = base_dir / 'output' / 'RESEARCH_INDEX.md'

    create_research_index(claude_dir, chatgpt_dir, gemini_dir, output_path)


if __name__ == '__main__':
    main()
