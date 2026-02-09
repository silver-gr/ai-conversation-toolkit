#!/usr/bin/env python3
"""
Gemini Meta-Indexer: Identifies and renames Gemini conversation files with non-descriptive titles.

Scans extracted Gemini conversations, generates descriptive titles from conversation content,
renames files, and updates YAML frontmatter.

Usage:
    python gemini_meta_indexer.py                      # Scan only (dry-run by default)
    python gemini_meta_indexer.py --rename              # Scan and rename files
    python gemini_meta_indexer.py --rename --json       # Also save JSON manifest
    python gemini_meta_indexer.py -i /path/to/convos    # Custom input directory
"""

import argparse
import json
from pathlib import Path
import re

# Patterns that indicate non-descriptive titles
NON_DESCRIPTIVE_PATTERNS = [
    r'^start-research',
    r'^έναρξη-έρευνας',
    r'^translate',
    r'^please-translate',
    r'^how-long-would',
    r'^how-many-sources',
    r'^ok-now-this-is',
    r'^create-a-meta-prompt',
    r'^there-is-a-small',
    r'^θα-ήθελα-μερικές',
    r'^δημιουργία-ηχητικής',
    r'^δημιούργησε-ένα',
    r'^οδηγίες$',
]

# Stop words for topic extraction (English + common research/prompt words)
STOP_WORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'this',
    'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they',
    'what', 'which', 'who', 'when', 'where', 'why', 'how', 'all', 'each',
    'every', 'both', 'few', 'more', 'most', 'other', 'some', 'such', 'no',
    'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very',
    'just', 'also', 'now', 'me', 'my', 'your', 'please', 'thanks',
    'thank', 'want', 'like', 'know', 'get', 'go', 'see', 'use',
    'using', 'used', 'let', 'about', 'into', 'over', 'after', 'before',
    'between', 'under', 'again', 'start', 'research', 'translate',
    'following', 'text', 'report', 'greek', 'specific', 'focus',
    'specifically', 'need', 'comprehensive', 'deeply', 'researched',
    'analysis', 'conduct', 'explore', 'objective', 'information',
    'seeking', 'understand', 'understanding', 'provide', 'detailed',
}


def get_title_from_filename(filename: str) -> str:
    """Extract the title portion from a filename like 20250930_start-research.md"""
    match = re.match(r'\d{8}_(.+)\.md$', filename)
    if match:
        return match.group(1)
    return filename


def is_non_descriptive(title: str) -> bool:
    """Check if a title matches any non-descriptive pattern."""
    title_lower = title.lower()
    for pattern in NON_DESCRIPTIVE_PATTERNS:
        if re.match(pattern, title_lower):
            return True
    return False


def extract_first_user_message(filepath: Path, max_chars: int = 3000) -> str:
    """Extract the first user message from a conversation file."""
    content = filepath.read_text(encoding='utf-8')

    # Find the first USER message section
    user_match = re.search(r'### USER.*?\n\n(.*?)(?=\n### (?:GEMINI|USER)|$)', content, re.DOTALL)
    if user_match:
        message = user_match.group(1).strip()
        return message[:max_chars]

    # Fallback: first chunk of content after metadata
    lines = content.split('\n')
    text_lines = []
    in_content = False
    for line in lines:
        if line.startswith('## Conversation'):
            in_content = True
            continue
        if in_content:
            text_lines.append(line)
            if len('\n'.join(text_lines)) > max_chars:
                break
    return '\n'.join(text_lines)[:max_chars]


def extract_topic_from_message(msg: str) -> str:
    """Extract a descriptive topic from the first user message."""
    if not msg:
        return ''

    # Clean markdown formatting
    msg = re.sub(r'[>#*_`\[\]]', '', msg)
    msg = re.sub(r'\s+', ' ', msg).strip()

    # Take first meaningful sentence
    sentences = re.split(r'[.\n!?]', msg)
    first_sentence = ''
    for s in sentences:
        s = s.strip()
        if len(s) > 15:
            first_sentence = s
            break
    if not first_sentence:
        first_sentence = msg[:150]

    # Extract key words (supports Latin + Greek)
    words = re.findall(r'[a-zA-Zα-ωά-ώ]{3,}', first_sentence.lower())
    key_words = [w for w in words if w not in STOP_WORDS]

    return ' '.join(key_words[:6])


def slugify(text: str, max_len: int = 50) -> str:
    """Convert text to a URL-safe slug."""
    text = text.lower().strip()
    text = re.sub(r'[^a-z0-9α-ωά-ώ\s-]', '', text)
    text = re.sub(r'[\s-]+', '-', text)
    text = text.strip('-')
    if len(text) > max_len:
        text = text[:max_len].rsplit('-', 1)[0]
    return text


def rename_file(filepath: Path, new_filename: str, new_title: str) -> None:
    """Rename a file and update its YAML frontmatter and H1 heading."""
    content = filepath.read_text(encoding='utf-8')

    # Update title in YAML frontmatter
    if content.startswith('---'):
        content = re.sub(
            r'^(title:\s*)(".*?"|.*?)$',
            f'\\1"{new_title}"',
            content,
            count=1,
            flags=re.MULTILINE,
        )

    # Update the H1 heading
    content = re.sub(
        r'^# .+$',
        f'# {new_title}',
        content,
        count=1,
        flags=re.MULTILINE,
    )

    new_path = filepath.parent / new_filename
    new_path.write_text(content, encoding='utf-8')

    if filepath != new_path:
        filepath.unlink()


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    base_dir = Path(__file__).parent.parent
    default_input = base_dir / 'output' / 'gemini' / 'conversations'
    default_output = base_dir / 'output' / 'gemini_files_to_reindex.json'

    parser = argparse.ArgumentParser(
        description='Identify and rename Gemini conversations with non-descriptive titles.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
    %(prog)s                           # Dry-run: show what would be renamed
    %(prog)s --rename                  # Rename files in-place
    %(prog)s --rename --json           # Rename and save JSON manifest
    %(prog)s -i /path/to/conversations # Custom input directory
        '''
    )
    parser.add_argument(
        '-i', '--input',
        type=Path,
        default=default_input,
        help=f'Input directory (default: {default_input})'
    )
    parser.add_argument(
        '-o', '--output',
        type=Path,
        default=default_output,
        help=f'Output JSON manifest (default: {default_output})'
    )
    parser.add_argument(
        '--rename',
        action='store_true',
        help='Actually rename files (default: dry-run)'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Save JSON manifest of processed files'
    )
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    gemini_dir = args.input
    output_path = args.output

    if not gemini_dir.exists():
        print(f"Error: Input directory does not exist: {gemini_dir}")
        return 1

    # Track existing filenames for collision detection
    existing_files = {f.name for f in gemini_dir.glob('*.md')}
    used_names = set(existing_files)

    files_to_process = []

    for filepath in sorted(gemini_dir.glob('*.md')):
        title = get_title_from_filename(filepath.name)
        if not is_non_descriptive(title):
            continue

        first_message = extract_first_user_message(filepath)
        topic = extract_topic_from_message(first_message)
        if not topic:
            topic = title.replace('-', ' ')

        new_slug = slugify(topic)
        if not new_slug or len(new_slug) < 5:
            new_slug = slugify(title)

        # Build new filename preserving date prefix
        date_match = re.match(r'(\d{8})_', filepath.name)
        date_prefix = date_match.group(1) if date_match else ''
        new_filename = f"{date_prefix}_{new_slug}.md" if date_prefix else f"{new_slug}.md"

        # Handle collisions
        if new_filename in used_names and new_filename != filepath.name:
            base = new_filename.replace('.md', '')
            prefix_match = re.match(r'(\d{8}_)', base)
            prefix = prefix_match.group(1) if prefix_match else ''
            slug = base[len(prefix):] if prefix else base

            n = 2
            while f"{prefix}{slug}_{n}.md" in used_names:
                n += 1
            new_filename = f"{prefix}{slug}_{n}.md"

        # Derive display title from slug
        slug_part = re.sub(r'^\d{8}_', '', new_filename.replace('.md', ''))
        new_title = slug_part.replace('-', ' ').title()

        files_to_process.append({
            'filepath': str(filepath),
            'filename': filepath.name,
            'current_title': title.replace('-', ' ').title(),
            'new_filename': new_filename,
            'new_title': new_title,
            'first_message': first_message,
            'size': filepath.stat().st_size,
        })

        # Reserve the new name
        used_names.discard(filepath.name)
        used_names.add(new_filename)

    print(f"Found {len(files_to_process)} files with non-descriptive titles")

    if not files_to_process:
        print("Nothing to do.")
        return 0

    # Show preview
    print(f"\n{'Old Title':<40} → {'New Title':<50}")
    print('─' * 95)
    for entry in files_to_process[:15]:
        old = entry['current_title'][:38]
        new = entry['new_title'][:48]
        print(f"{old:<40} → {new:<50}")
    if len(files_to_process) > 15:
        print(f"... and {len(files_to_process) - 15} more")

    # Rename if requested
    if args.rename:
        renamed = 0
        skipped = 0
        for entry in files_to_process:
            old_path = Path(entry['filepath'])
            if not old_path.exists():
                continue
            if entry['new_filename'] == entry['filename']:
                skipped += 1
                continue
            rename_file(old_path, entry['new_filename'], entry['new_title'])
            renamed += 1

        print(f"\nRenamed: {renamed}")
        if skipped:
            print(f"Skipped (same name): {skipped}")
        print(f"Final file count: {len(list(gemini_dir.glob('*.md')))}")
    else:
        print(f"\nDry-run mode. Use --rename to apply changes.")

    # Save JSON manifest if requested
    if args.json:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        manifest = {'total_files': len(files_to_process), 'files': files_to_process}
        output_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f"Manifest written to: {output_path}")

    return 0


if __name__ == '__main__':
    exit(main())
