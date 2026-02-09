#!/usr/bin/env python3
"""
Migrate existing conversation markdown files from inline metadata to YAML frontmatter.

Walks output/ subdirectories and converts files in-place.
Idempotent: skips files that already have YAML frontmatter.
"""

import re
import sys
from pathlib import Path
from collections import defaultdict

# Support running from different directories
sys.path.insert(0, str(Path(__file__).parent))
from simple_extractor import extract_topics


# Directories to scan for conversation files
CONVERSATION_DIRS = [
    'output/chatgpt-full/conversations',
    'output/claude-full/conversations',
    'output/gemini/conversations',
]


def _escape_yaml_string(s: str) -> str:
    """Escape a string for safe YAML output (double-quoted scalar)."""
    if not s:
        return '""'
    s = s.replace('\\', '\\\\').replace('"', '\\"')
    return f'"{s}"'


def _detect_has_code(content: str) -> bool:
    """Check if content contains code fences."""
    return '```' in content


def _extract_topics_from_content(content: str) -> list[str]:
    """Extract topic keywords from conversation content."""
    stop_words = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
        'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
        'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'need',
        'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we',
        'they', 'what', 'which', 'who', 'when', 'where', 'why', 'how', 'all',
        'each', 'every', 'both', 'few', 'more', 'most', 'other', 'some', 'such',
        'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very',
        'just', 'also', 'now', 'here', 'there', 'then', 'if', 'my', 'your',
        'me', 'like', 'want', 'think', 'know', 'make', 'get', 'go', 'see',
        'use', 'using', 'used', 'let', 'please', 'thanks', 'thank', 'help',
        'about', 'into', 'over', 'after', 'before', 'between', 'under', 'again',
        'user', 'assistant',
    }

    # Get text from first ~2500 chars of conversation content
    # Skip the title and metadata to focus on actual conversation
    words = re.findall(r'\b[a-zA-Z]{4,15}\b', content[:2500].lower())

    word_counts = defaultdict(int)
    for word in words:
        if word not in stop_words:
            word_counts[word] += 1

    sorted_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)
    return [word for word, count in sorted_words[:5] if count >= 1]


def _parse_inline_metadata(content: str) -> dict:
    """Parse inline ## Metadata section from a markdown file."""
    metadata = {
        'date': None,
        'source': None,
        'messages': None,
        'characters': None,
        'summary': None,
    }

    # Match Date: YYYY-MM-DD HH:MM
    date_match = re.search(r'\*\*Date\*\*:\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})', content)
    if date_match:
        date_str = date_match.group(1).strip()
        # Convert "2025-07-02 14:30" to "2025-07-02T14:30:00"
        metadata['date'] = date_str.replace(' ', 'T') + ':00'

    # Match Source
    source_match = re.search(r'\*\*Source\*\*:\s*(\w+)', content)
    if source_match:
        metadata['source'] = source_match.group(1).strip().lower()

    # Match Messages or Activities count
    msg_match = re.search(r'\*\*(Messages|Activities)\*\*:\s*(\d+)', content)
    if msg_match:
        metadata['messages'] = int(msg_match.group(2))

    # Match Total Characters (may have commas)
    chars_match = re.search(r'\*\*Total Characters\*\*:\s*([\d,]+)', content)
    if chars_match:
        metadata['characters'] = int(chars_match.group(1).replace(',', ''))

    # Match Summary
    summary_match = re.search(r'\*\*Summary\*\*:\s*(.+?)$', content, re.MULTILINE)
    if summary_match:
        metadata['summary'] = summary_match.group(1).strip()

    return metadata


def _extract_title(content: str) -> str:
    """Extract the H1 title from the markdown file."""
    title_match = re.match(r'^#\s+(.+?)$', content, re.MULTILINE)
    if title_match:
        return title_match.group(1).strip()
    return 'Untitled'


def _remove_metadata_section(content: str) -> str:
    """Remove the inline ## Metadata section and the following --- separator."""
    # Pattern: ## Metadata\n\n- items...\n\n---\n\n
    pattern = r'## Metadata\s*\n(?:- \*\*[^*]+\*\*:[^\n]*\n)*\s*\n---\s*\n\s*'
    result = re.sub(pattern, '', content, count=1)
    return result


def migrate_file(filepath: Path) -> bool:
    """
    Migrate a single file from inline metadata to YAML frontmatter.
    Returns True if file was migrated, False if skipped.
    """
    content = filepath.read_text(encoding='utf-8')

    # Skip files that already have YAML frontmatter
    if content.startswith('---'):
        return False

    # Parse existing inline metadata
    metadata = _parse_inline_metadata(content)

    # Extract title
    title = _extract_title(content)

    # Detect has_code from full content
    has_code = _detect_has_code(content)

    # Find the conversation content section for topic extraction
    conv_start = content.find('## Conversation')
    if conv_start >= 0:
        conv_content = content[conv_start:]
    else:
        conv_content = content
    topics = _extract_topics_from_content(conv_content)

    # Determine source from metadata or filepath
    source = metadata.get('source') or 'unknown'

    # Build YAML frontmatter
    fm_lines = []
    fm_lines.append("---")
    fm_lines.append("type: conversation")
    fm_lines.append(f"title: {_escape_yaml_string(title)}")
    if metadata['date']:
        fm_lines.append(f"date: {metadata['date']}")
    else:
        fm_lines.append("date: null")
    fm_lines.append(f"source: {source}")
    fm_lines.append("model: null")
    if metadata['messages'] is not None:
        fm_lines.append(f"messages: {metadata['messages']}")
    else:
        fm_lines.append("messages: 0")
    if metadata['characters'] is not None:
        fm_lines.append(f"characters: {metadata['characters']}")
    else:
        fm_lines.append("characters: 0")
    fm_lines.append(f"has_code: {'true' if has_code else 'false'}")
    if topics:
        fm_lines.append("topics:")
        for topic in topics[:5]:
            fm_lines.append(f"  - {topic}")
    else:
        fm_lines.append("topics: []")
    fm_lines.append("research_type: null")
    fm_lines.append("---")
    fm_lines.append("")

    frontmatter = '\n'.join(fm_lines)

    # Remove the inline metadata section from content
    new_content = _remove_metadata_section(content)

    # Combine frontmatter with cleaned content
    final_content = frontmatter + new_content

    # Write back
    filepath.write_text(final_content, encoding='utf-8')
    return True


def main():
    """Migrate all conversation files in output/ subdirectories."""
    project_root = Path(__file__).parent.parent

    total_files = 0
    migrated_files = 0
    skipped_files = 0

    for conv_dir_rel in CONVERSATION_DIRS:
        conv_dir = project_root / conv_dir_rel
        if not conv_dir.exists():
            print(f"  Skipping {conv_dir_rel} (not found)")
            continue

        md_files = sorted(conv_dir.glob('*.md'))
        if not md_files:
            print(f"  Skipping {conv_dir_rel} (no .md files)")
            continue

        print(f"\n  Processing {conv_dir_rel}/ ({len(md_files)} files)")

        for filepath in md_files:
            total_files += 1
            if migrate_file(filepath):
                migrated_files += 1
            else:
                skipped_files += 1

            # Progress every 100 files
            if total_files % 100 == 0:
                print(f"    Migrated {migrated_files}/{total_files} files...")

    print(f"\n{'=' * 50}")
    print(f"Migration complete!")
    print(f"  Total files scanned: {total_files}")
    print(f"  Migrated: {migrated_files}")
    print(f"  Skipped (already migrated): {skipped_files}")
    return 0


if __name__ == '__main__':
    print("=" * 50)
    print("YAML Frontmatter Migration")
    print("=" * 50)
    exit(main())
