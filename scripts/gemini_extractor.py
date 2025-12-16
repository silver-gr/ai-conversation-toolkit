#!/usr/bin/env python3
"""
Gemini Activity Extractor
Converts Google Gemini Apps Activity Takeout to readable markdown.

Gemini exports are activity logs (not threaded conversations like ChatGPT/Claude).
Each entry is a standalone query+response pair.
"""

import json
import re
import html
from pathlib import Path
from datetime import datetime, timedelta
from typing import Generator
from collections import defaultdict


def slugify(text: str, max_len: int = 50) -> str:
    """Convert text to a valid filename slug."""
    slug = re.sub(r'[^\w\s-]', '', text.lower())
    slug = re.sub(r'[-\s]+', '-', slug).strip('-')
    return slug[:max_len]


def parse_timestamp(ts: str) -> datetime | None:
    """Parse ISO timestamp."""
    if not ts:
        return None
    try:
        ts = ts.replace('Z', '+00:00')
        if '+' in ts:
            ts = ts.split('+')[0]
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def strip_html(html_content: str) -> str:
    """Convert HTML to plain text/markdown."""
    if not html_content:
        return ''

    # Decode HTML entities
    text = html.unescape(html_content)

    # Convert common HTML to markdown
    text = re.sub(r'<h1[^>]*>(.*?)</h1>', r'# \1\n', text, flags=re.DOTALL)
    text = re.sub(r'<h2[^>]*>(.*?)</h2>', r'## \1\n', text, flags=re.DOTALL)
    text = re.sub(r'<h3[^>]*>(.*?)</h3>', r'### \1\n', text, flags=re.DOTALL)
    text = re.sub(r'<h4[^>]*>(.*?)</h4>', r'#### \1\n', text, flags=re.DOTALL)
    text = re.sub(r'<p[^>]*>(.*?)</p>', r'\1\n\n', text, flags=re.DOTALL)
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'<li[^>]*>(.*?)</li>', r'- \1\n', text, flags=re.DOTALL)
    text = re.sub(r'<strong>(.*?)</strong>', r'**\1**', text, flags=re.DOTALL)
    text = re.sub(r'<b>(.*?)</b>', r'**\1**', text, flags=re.DOTALL)
    text = re.sub(r'<em>(.*?)</em>', r'*\1*', text, flags=re.DOTALL)
    text = re.sub(r'<i>(.*?)</i>', r'*\1*', text, flags=re.DOTALL)
    text = re.sub(r'<code>(.*?)</code>', r'`\1`', text, flags=re.DOTALL)
    text = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r'[\2](\1)', text, flags=re.DOTALL)

    # Remove remaining tags
    text = re.sub(r'<[^>]+>', '', text)

    # Clean up whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    return text


def extract_query_from_title(title: str) -> str:
    """Extract user query from activity title."""
    # Greek: "Υποβλήθηκε το ερώτημα <query>"
    # English equivalent might be: "Submitted query <query>"
    prefix_patterns = [
        'Υποβλήθηκε το ερώτημα ',  # Greek
        'Submitted query ',         # English
        'Query submitted ',
    ]

    for prefix in prefix_patterns:
        if title.startswith(prefix):
            return title[len(prefix):].strip()

    return title


def extract_canvas_title(title: str) -> str:
    """Extract canvas title from activity title."""
    # Greek: "Δημιουργήθηκε Gemini Canvas με τίτλο <title>"
    prefix_patterns = [
        'Δημιουργήθηκε Gemini Canvas με τίτλο ',  # Greek
        'Created Gemini Canvas titled ',          # English
    ]

    for prefix in prefix_patterns:
        if title.startswith(prefix):
            return title[len(prefix):].strip()

    return title


def parse_activity(entry: dict) -> dict | None:
    """Parse a single activity entry."""
    title = entry.get('title', '')
    timestamp = parse_timestamp(entry.get('time'))

    # Determine activity type and extract content
    activity_type = None
    user_query = ''
    response = ''
    canvas_content = ''
    attachments = []

    # Check for query submission
    if 'Υποβλήθηκε το ερώτημα' in title or 'Submitted query' in title.lower():
        activity_type = 'query'
        user_query = extract_query_from_title(title)

        # Extract response from safeHtmlItem
        html_items = entry.get('safeHtmlItem', [])
        if html_items:
            response = strip_html(html_items[0].get('html', ''))

        # Check for attachments info in subtitles
        subtitles = entry.get('subtitles', [])
        for sub in subtitles:
            name = sub.get('name', '')
            if 'συνημμένα αρχεία' in name or 'attached files' in name.lower():
                attachments.append(name)

    # Check for Canvas creation
    elif 'Δημιουργήθηκε Gemini Canvas' in title or 'Created Gemini Canvas' in title:
        activity_type = 'canvas'
        user_query = extract_canvas_title(title)

        # Canvas content is in subtitles
        subtitles = entry.get('subtitles', [])
        if subtitles:
            canvas_content = subtitles[0].get('name', '')

    if not activity_type:
        return None

    return {
        'type': activity_type,
        'timestamp': timestamp,
        'query': user_query,
        'response': response,
        'canvas_content': canvas_content,
        'attachments': attachments,
        'has_image': bool(entry.get('imageFile')),
        'attached_files': entry.get('attachedFiles', [])
    }


def group_into_conversations(
    activities: list[dict],
    session_gap_minutes: int = 30
) -> list[dict]:
    """
    Group activities into conversation sessions.
    Activities within `session_gap_minutes` of each other are grouped together.
    """
    if not activities:
        return []

    # Sort by timestamp
    sorted_activities = sorted(
        [a for a in activities if a['timestamp']],
        key=lambda x: x['timestamp'],
        reverse=True  # Most recent first
    )

    conversations = []
    current_conv = None
    last_timestamp = None
    gap = timedelta(minutes=session_gap_minutes)

    for activity in sorted_activities:
        ts = activity['timestamp']

        # Start new conversation if gap is too large
        if last_timestamp is None or (last_timestamp - ts) > gap:
            if current_conv:
                conversations.append(current_conv)

            # Create new conversation
            current_conv = {
                'id': ts.isoformat() if ts else 'unknown',
                'title': activity['query'][:80] if activity['query'] else 'Gemini Session',
                'created_at': ts,
                'updated_at': ts,
                'activities': [],
                'source': 'gemini'
            }

        current_conv['activities'].append(activity)
        current_conv['updated_at'] = ts
        last_timestamp = ts

    if current_conv:
        conversations.append(current_conv)

    # Reverse activities within each conversation to be chronological
    for conv in conversations:
        conv['activities'] = list(reversed(conv['activities']))

    return conversations


def activity_to_markdown(conv: dict) -> str:
    """Convert a conversation/activity group to markdown."""
    lines = []

    title = conv['title']
    created = conv['created_at']
    activities = conv['activities']

    # Header
    lines.append(f"# {title}")
    lines.append("")

    # Metadata
    lines.append("## Metadata")
    lines.append("")
    if created:
        lines.append(f"- **Date**: {created.strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"- **Source**: GEMINI")
    lines.append(f"- **Activities**: {len(activities)}")

    # Calculate stats
    total_chars = sum(
        len(a['query']) + len(a['response']) + len(a['canvas_content'])
        for a in activities
    )
    lines.append(f"- **Total Characters**: {total_chars:,}")

    lines.append("")
    lines.append("---")
    lines.append("")

    # Content
    lines.append("## Conversation")
    lines.append("")

    for i, activity in enumerate(activities, 1):
        # User query
        if activity['query']:
            timestamp = activity['timestamp']
            time_str = f" ({timestamp.strftime('%H:%M')})" if timestamp else ""
            lines.append(f"### USER{time_str}")
            lines.append("")
            lines.append(activity['query'])
            lines.append("")

            if activity['attachments']:
                lines.append(f"*Attachments: {', '.join(activity['attachments'])}*")
                lines.append("")

            if activity['has_image']:
                lines.append("*[Image attached]*")
                lines.append("")

        lines.append("---")
        lines.append("")

        # Response or Canvas content
        if activity['type'] == 'canvas' and activity['canvas_content']:
            lines.append("### GEMINI (Canvas)")
            lines.append("")
            lines.append(activity['canvas_content'])
        elif activity['response']:
            lines.append("### GEMINI")
            lines.append("")
            lines.append(activity['response'])

        lines.append("")
        lines.append("---")
        lines.append("")

    return '\n'.join(lines)


def parse_gemini_export(filepath: Path) -> Generator[dict, None, None]:
    """Parse Gemini activity export."""
    print(f"  Loading {filepath}...")

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"  Found {len(data)} activity entries")

    # Parse all activities
    activities = []
    for entry in data:
        parsed = parse_activity(entry)
        if parsed:
            activities.append(parsed)

    print(f"  Parsed {len(activities)} valid activities")

    # Group into conversations
    conversations = group_into_conversations(activities)
    print(f"  Grouped into {len(conversations)} conversation sessions")

    for conv in conversations:
        yield conv


def process_gemini_export(
    input_path: Path,
    output_dir: Path,
    max_conversations: int = None,
    no_grouping: bool = False
):
    """Process Gemini export and create markdown files."""

    print(f"Processing Gemini export: {input_path}")

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    conv_dir = output_dir / 'conversations'
    conv_dir.mkdir(exist_ok=True)

    # Load and parse
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"  Found {len(data)} activity entries")

    # Parse activities
    activities = []
    for entry in data:
        parsed = parse_activity(entry)
        if parsed:
            activities.append(parsed)

    print(f"  Parsed {len(activities)} valid activities")

    # Group or keep individual
    if no_grouping:
        # Each activity as its own "conversation"
        conversations = []
        for act in activities:
            if act['timestamp']:
                conversations.append({
                    'id': act['timestamp'].isoformat(),
                    'title': act['query'][:80] if act['query'] else 'Gemini Activity',
                    'created_at': act['timestamp'],
                    'updated_at': act['timestamp'],
                    'activities': [act],
                    'source': 'gemini'
                })
    else:
        conversations = group_into_conversations(activities)

    print(f"  Created {len(conversations)} conversation files")

    # Process stats
    stats = {
        'total': len(conversations),
        'processed': 0,
        'total_activities': len(activities),
        'total_chars': 0,
    }

    summaries = []

    for conv in conversations:
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
        md_content = activity_to_markdown(conv)
        filepath.write_text(md_content, encoding='utf-8')

        # Calculate stats
        char_count = sum(
            len(a['query']) + len(a['response']) + len(a['canvas_content'])
            for a in conv['activities']
        )
        stats['processed'] += 1
        stats['total_chars'] += char_count

        summaries.append({
            'title': conv['title'],
            'date': created.isoformat() if created else None,
            'activities': len(conv['activities']),
            'chars': char_count,
            'file': filepath.name,
            'has_canvas': any(a['type'] == 'canvas' for a in conv['activities'])
        })

        if stats['processed'] % 50 == 0:
            print(f"  Processed {stats['processed']} conversations...")

    # Create index file
    index_path = output_dir / 'INDEX.md'
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write("# GEMINI Conversation Export\n\n")
        f.write(f"*Extracted: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n")
        f.write("## Statistics\n\n")
        f.write(f"- **Total Activities**: {stats['total_activities']}\n")
        f.write(f"- **Conversation Sessions**: {stats['processed']}\n")
        f.write(f"- **Total Characters**: {stats['total_chars']:,}\n")
        f.write(f"- **Canvas Creations**: {sum(1 for s in summaries if s['has_canvas'])}\n")
        f.write("\n---\n\n")

        f.write("## Conversations\n\n")
        f.write("| Date | Title | Activities | Size | Canvas |\n")
        f.write("|------|-------|------------|------|--------|\n")

        # Sort by date descending
        summaries.sort(key=lambda x: x['date'] or '', reverse=True)

        for s in summaries:
            date = s['date'][:10] if s['date'] else 'Unknown'
            title = s['title'][:50]
            canvas = '📄' if s['has_canvas'] else ''
            f.write(f"| {date} | [{title}](conversations/{s['file']}) | {s['activities']} | {s['chars']:,} | {canvas} |\n")

    print(f"\nComplete!")
    print(f"  Conversation sessions: {stats['processed']}")
    print(f"  Total activities: {stats['total_activities']}")
    print(f"  Total characters: {stats['total_chars']:,}")
    print(f"  Output: {output_dir}")

    return stats


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Extract Gemini activity to markdown'
    )
    parser.add_argument('input', help='Path to Gemini activity JSON file')
    parser.add_argument('--output', '-o', default='output/gemini',
                       help='Output directory')
    parser.add_argument('--max', '-m', type=int,
                       help='Maximum conversations to process')
    parser.add_argument('--no-grouping', action='store_true',
                       help='Keep each activity separate (no session grouping)')

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: File not found: {input_path}")
        return 1

    output_dir = Path(args.output)

    print("=" * 60)
    print("Gemini Activity Extractor")
    print("=" * 60)
    print(f"Input: {input_path}")
    print(f"Output: {output_dir}")
    if args.max:
        print(f"Max conversations: {args.max}")
    print()

    process_gemini_export(
        input_path,
        output_dir,
        max_conversations=args.max,
        no_grouping=args.no_grouping
    )

    return 0


if __name__ == '__main__':
    exit(main())
