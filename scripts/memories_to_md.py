#!/usr/bin/env python3
"""
Phase 0: Convert Claude memories.json to organized markdown files.
Quick win - immediate readable output from pre-extracted context.
"""

import json
import os
import re
from pathlib import Path
from datetime import datetime


def slugify(text: str) -> str:
    """Convert text to a valid filename slug."""
    # Remove special characters and convert to lowercase
    slug = re.sub(r'[^\w\s-]', '', text.lower())
    # Replace spaces with hyphens
    slug = re.sub(r'[-\s]+', '-', slug).strip('-')
    return slug[:50]  # Limit length


def extract_project_name(memory_content: str) -> str:
    """Extract a project name from the memory content."""
    # Look for **Purpose & context** section and extract key terms
    lines = memory_content.split('\n')

    # Try to find identifiable project names
    project_keywords = {
        'x3lixi': 'x3lixi-platform',
        'x3lixi-os': 'x3lixi-app',
        'wordpress': 'wordpress-platform',
        'dj': 'djing-music',
        'psytrance': 'djing-music',
        'adhd': 'adhd-course',
        'meditation': 'meditation-course',
        'bdsm': 'bdsm-education',
        'journaling': 'journaling-system',
        'obsidian': 'knowledge-management',
        'cognito': 'cognito-ai-system',
        'flutter': 'flutter-development',
        'prompt': 'prompt-engineering',
        'course': 'course-development',
        'translation': 'translation-work',
        'research': 'research-methodology',
    }

    content_lower = memory_content.lower()

    for keyword, project_name in project_keywords.items():
        if keyword in content_lower:
            return project_name

    # Fallback: extract first meaningful words from purpose section
    for line in lines[:10]:
        if line.strip() and not line.startswith('**'):
            words = line.strip().split()[:3]
            if words:
                return slugify(' '.join(words))

    return 'misc'


def memory_to_markdown(memory_id: str, memory_content: str) -> str:
    """Convert a single memory entry to markdown format."""
    lines = []

    # Add header
    project_name = extract_project_name(memory_content)
    lines.append(f"# {project_name.replace('-', ' ').title()}")
    lines.append("")
    lines.append(f"> Memory ID: `{memory_id}`")
    lines.append(f"> Extracted: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Process the content - it's already in a nice format
    # Just clean up and add proper markdown structure
    content = memory_content

    # Convert **Section** to ## Section
    content = re.sub(r'\*\*([^*]+)\*\*\n', r'## \1\n', content)

    lines.append(content)

    return '\n'.join(lines)


def process_memories(input_path: Path, output_dir: Path) -> dict:
    """Process memories.json and create markdown files."""

    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    stats = {
        'total': 0,
        'processed': 0,
        'files_created': [],
    }

    # Handle the structure - it's a list with one object containing memories
    if isinstance(data, list) and len(data) > 0:
        memories_data = data[0]
    else:
        memories_data = data

    # Get project memories
    project_memories = memories_data.get('project_memories', {})
    conversations_memory = memories_data.get('conversations_memory', '')

    # Process main conversations memory
    if conversations_memory:
        stats['total'] += 1
        md_content = memory_to_markdown('main-context', conversations_memory)
        output_file = output_dir / 'main-context.md'
        output_file.write_text(md_content, encoding='utf-8')
        stats['processed'] += 1
        stats['files_created'].append(str(output_file))
        print(f"  Created: main-context.md")

    # Process project memories
    for memory_id, memory_content in project_memories.items():
        stats['total'] += 1

        project_name = extract_project_name(memory_content)

        # Check if file already exists (multiple memories might map to same project)
        base_name = project_name
        counter = 1
        output_file = output_dir / f"{base_name}.md"

        while output_file.exists():
            output_file = output_dir / f"{base_name}-{counter}.md"
            counter += 1

        md_content = memory_to_markdown(memory_id, memory_content)
        output_file.write_text(md_content, encoding='utf-8')

        stats['processed'] += 1
        stats['files_created'].append(str(output_file))
        print(f"  Created: {output_file.name}")

    return stats


def main():
    """Main entry point."""
    # Paths
    base_dir = Path(__file__).parent.parent
    input_path = base_dir / 'Claude' / 'memories.json'
    output_dir = base_dir / 'output' / 'memories'

    print("=" * 60)
    print("Phase 0: Converting Claude Memories to Markdown")
    print("=" * 60)
    print(f"\nInput:  {input_path}")
    print(f"Output: {output_dir}")
    print()

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        return 1

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Processing memories...")
    stats = process_memories(input_path, output_dir)

    print()
    print("=" * 60)
    print("COMPLETE")
    print("=" * 60)
    print(f"Total memories:    {stats['total']}")
    print(f"Files created:     {stats['processed']}")
    print(f"Output directory:  {output_dir}")
    print()
    print("Files created:")
    for f in stats['files_created']:
        print(f"  - {Path(f).name}")

    return 0


if __name__ == '__main__':
    exit(main())
