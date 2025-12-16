#!/usr/bin/env python3
"""
Simple Conversation Extractor - No AI Analysis Required
Converts ChatGPT and Claude exports to readable markdown with FULL content.
"""

import json
import os
import re
from pathlib import Path
from datetime import datetime
from typing import Generator
from collections import defaultdict
import hashlib


def slugify(text: str, max_len: int = 50) -> str:
    """Convert text to a valid filename slug."""
    slug = re.sub(r'[^\w\s-]', '', text.lower())
    slug = re.sub(r'[-\s]+', '-', slug).strip('-')
    return slug[:max_len]


def parse_timestamp(ts) -> datetime | None:
    """Parse various timestamp formats."""
    if not ts:
        return None
    if isinstance(ts, (int, float)):
        try:
            return datetime.fromtimestamp(ts)
        except (ValueError, OSError):
            return None
    if isinstance(ts, str):
        try:
            ts = ts.replace('Z', '+00:00')
            if '+' in ts:
                ts = ts.split('+')[0]
            return datetime.fromisoformat(ts)
        except ValueError:
            return None
    return None


# =============================================================================
# CLAUDE PARSER
# =============================================================================

def extract_claude_messages(conv: dict) -> list[dict]:
    """Extract messages from Claude conversation."""
    messages = []
    for msg in conv.get('chat_messages', []):
        sender = msg.get('sender', '')
        role = 'user' if sender == 'human' else 'assistant'

        content = msg.get('text', '')
        if not content and 'content' in msg:
            content_arr = msg.get('content', [])
            if isinstance(content_arr, list):
                content = ' '.join(
                    c.get('text', '') for c in content_arr
                    if isinstance(c, dict) and c.get('text')
                )

        if content and content.strip():
            messages.append({
                'role': role,
                'content': content,
                'timestamp': parse_timestamp(msg.get('created_at'))
            })
    return messages


def parse_claude_export(filepath: Path) -> Generator[dict, None, None]:
    """Parse Claude conversations.json."""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    for conv in data:
        messages = extract_claude_messages(conv)
        if not messages:
            continue

        yield {
            'id': conv.get('uuid', ''),
            'title': conv.get('name', '') or 'Untitled',
            'created_at': parse_timestamp(conv.get('created_at')),
            'updated_at': parse_timestamp(conv.get('updated_at')),
            'messages': messages,
            'source': 'claude',
            'summary': conv.get('summary', '')
        }


# =============================================================================
# CHATGPT PARSER
# =============================================================================

def traverse_chatgpt_tree(mapping: dict, node_id: str, visited: set = None) -> list[dict]:
    """Traverse ChatGPT's tree structure."""
    if visited is None:
        visited = set()

    if node_id in visited or node_id not in mapping:
        return []

    visited.add(node_id)
    node = mapping[node_id]
    messages = []

    msg_data = node.get('message')
    if msg_data:
        author = msg_data.get('author', {})
        role = author.get('role', 'unknown')

        # Skip hidden system messages
        metadata = msg_data.get('metadata', {})
        if metadata.get('is_visually_hidden_from_conversation'):
            role = 'system_hidden'

        content_obj = msg_data.get('content', {})
        content_type = content_obj.get('content_type', '')
        content = ''

        if content_type == 'text':
            parts = content_obj.get('parts', [])
            content = '\n'.join(str(p) for p in parts if p)

        if content.strip() and role in ('user', 'assistant'):
            messages.append({
                'role': role,
                'content': content,
                'timestamp': parse_timestamp(msg_data.get('create_time')),
                'model': metadata.get('model_slug', '')
            })

    # Build children map and traverse
    children = node.get('children', [])
    for child_id in children:
        messages.extend(traverse_chatgpt_tree(mapping, child_id, visited))

    return messages


def parse_chatgpt_export(filepath: Path) -> Generator[dict, None, None]:
    """Parse ChatGPT conversations.json."""
    print(f"  Loading {filepath}...")
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"  Found {len(data)} conversations")

    for conv in data:
        mapping = conv.get('mapping', {})

        # Find root node
        root_id = None
        for node_id, node in mapping.items():
            if node.get('parent') is None:
                root_id = node_id
                break

        messages = []
        if root_id:
            messages = traverse_chatgpt_tree(mapping, root_id)

        if not messages:
            continue

        yield {
            'id': conv.get('id', conv.get('conversation_id', '')),
            'title': conv.get('title', '') or 'Untitled',
            'created_at': parse_timestamp(conv.get('create_time')),
            'updated_at': parse_timestamp(conv.get('update_time')),
            'messages': messages,
            'source': 'chatgpt',
            'gizmo_id': conv.get('gizmo_id'),
        }


# =============================================================================
# MARKDOWN GENERATOR
# =============================================================================

def conversation_to_markdown(conv: dict, include_full_content: bool = True) -> str:
    """Convert a conversation to markdown with FULL content."""
    lines = []

    title = conv['title']
    created = conv['created_at']
    messages = conv['messages']

    # Header
    lines.append(f"# {title}")
    lines.append("")

    # Metadata
    lines.append("## Metadata")
    lines.append("")
    if created:
        lines.append(f"- **Date**: {created.strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"- **Source**: {conv['source'].upper()}")
    lines.append(f"- **Messages**: {len(messages)}")

    # Calculate total chars
    total_chars = sum(len(m['content']) for m in messages)
    lines.append(f"- **Total Characters**: {total_chars:,}")

    if conv.get('summary'):
        lines.append(f"- **Summary**: {conv['summary']}")

    lines.append("")
    lines.append("---")
    lines.append("")

    # Full Conversation
    lines.append("## Conversation")
    lines.append("")

    for i, msg in enumerate(messages, 1):
        role = msg['role'].upper()
        content = msg['content']

        # Message header
        timestamp = msg.get('timestamp')
        if timestamp:
            lines.append(f"### {role} ({timestamp.strftime('%H:%M')})")
        else:
            lines.append(f"### {role}")
        lines.append("")

        if include_full_content:
            # Include full content
            lines.append(content)
        else:
            # Truncate for summary view
            if len(content) > 1000:
                lines.append(content[:1000] + "\n\n*[... truncated ...]*")
            else:
                lines.append(content)

        lines.append("")
        lines.append("---")
        lines.append("")

    return '\n'.join(lines)


def extract_topics(messages: list[dict]) -> list[str]:
    """Extract simple topic keywords from messages."""
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
    }

    # Get text from first few messages
    text = ' '.join(m['content'][:500] for m in messages[:5])

    # Extract words
    words = re.findall(r'\b[a-zA-Z]{4,15}\b', text.lower())

    # Count and filter
    word_counts = defaultdict(int)
    for word in words:
        if word not in stop_words:
            word_counts[word] += 1

    # Return top topics
    sorted_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)
    return [word for word, count in sorted_words[:10] if count >= 1]


# =============================================================================
# MAIN PROCESSOR
# =============================================================================

def process_export(
    input_path: Path,
    output_dir: Path,
    max_conversations: int = None,
    full_content: bool = True
):
    """Process an export file and create markdown files."""

    # Detect format
    with open(input_path, 'r', encoding='utf-8') as f:
        sample = f.read(2000)

    if '"chat_messages"' in sample:
        source = 'claude'
        parser = parse_claude_export
    else:
        source = 'chatgpt'
        parser = parse_chatgpt_export

    print(f"Detected format: {source.upper()}")

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    conv_dir = output_dir / 'conversations'
    conv_dir.mkdir(exist_ok=True)

    # Process conversations
    stats = {
        'total': 0,
        'processed': 0,
        'total_messages': 0,
        'total_chars': 0,
    }

    summaries = []

    for conv in parser(input_path):
        stats['total'] += 1

        if max_conversations and stats['processed'] >= max_conversations:
            break

        # Generate filename
        created = conv['created_at']
        date_str = created.strftime('%Y%m%d') if created else '00000000'
        title_slug = slugify(conv['title'], 40)
        filename = f"{date_str}_{title_slug}.md"

        # Avoid duplicates
        filepath = conv_dir / filename
        counter = 1
        while filepath.exists():
            filepath = conv_dir / f"{date_str}_{title_slug}_{counter}.md"
            counter += 1

        # Generate markdown
        md_content = conversation_to_markdown(conv, include_full_content=full_content)
        filepath.write_text(md_content, encoding='utf-8')

        # Update stats
        stats['processed'] += 1
        msg_count = len(conv['messages'])
        char_count = sum(len(m['content']) for m in conv['messages'])
        stats['total_messages'] += msg_count
        stats['total_chars'] += char_count

        # Store summary
        summaries.append({
            'title': conv['title'],
            'date': created.isoformat() if created else None,
            'messages': msg_count,
            'chars': char_count,
            'topics': extract_topics(conv['messages']),
            'file': filepath.name
        })

        if stats['processed'] % 50 == 0:
            print(f"  Processed {stats['processed']} conversations...")

    # Create index file
    index_path = output_dir / 'INDEX.md'
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(f"# {source.upper()} Conversation Export\n\n")
        f.write(f"*Extracted: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n")
        f.write("## Statistics\n\n")
        f.write(f"- **Total Conversations**: {stats['processed']}\n")
        f.write(f"- **Total Messages**: {stats['total_messages']:,}\n")
        f.write(f"- **Total Characters**: {stats['total_chars']:,}\n")
        f.write(f"- **Avg Messages/Conv**: {stats['total_messages'] // max(stats['processed'], 1)}\n")
        f.write("\n---\n\n")

        f.write("## Conversations\n\n")
        f.write("| Date | Title | Messages | Size |\n")
        f.write("|------|-------|----------|------|\n")

        # Sort by date descending
        summaries.sort(key=lambda x: x['date'] or '', reverse=True)

        for s in summaries:
            date = s['date'][:10] if s['date'] else 'Unknown'
            title = s['title'][:50]
            f.write(f"| {date} | [{title}](conversations/{s['file']}) | {s['messages']} | {s['chars']:,} chars |\n")

    print(f"\nComplete!")
    print(f"  Processed: {stats['processed']} conversations")
    print(f"  Messages: {stats['total_messages']:,}")
    print(f"  Characters: {stats['total_chars']:,}")
    print(f"  Output: {output_dir}")

    return stats


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Extract AI conversations to markdown')
    parser.add_argument('input', help='Path to conversations.json')
    parser.add_argument('--output', '-o', default='output', help='Output directory')
    parser.add_argument('--max', '-m', type=int, help='Maximum conversations to process')
    parser.add_argument('--summary', action='store_true', help='Truncate long messages')

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: File not found: {input_path}")
        return 1

    output_dir = Path(args.output)

    print("=" * 60)
    print("Simple Conversation Extractor")
    print("=" * 60)
    print(f"Input: {input_path}")
    print(f"Output: {output_dir}")
    if args.max:
        print(f"Max conversations: {args.max}")
    print()

    process_export(
        input_path,
        output_dir,
        max_conversations=args.max,
        full_content=not args.summary
    )

    return 0


if __name__ == '__main__':
    exit(main())
