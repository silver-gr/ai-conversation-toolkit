#!/usr/bin/env python3
"""
Build an Obsidian vault from extracted AI conversations.

Creates daily notes, topic MOCs, and a dashboard for any date range.

Usage:
    python build_vault.py --all                          # All conversations
    python build_vault.py --month 2026-01                # January 2026
    python build_vault.py --from 2025-12-01 --to 2025-12-31  # Date range
    python build_vault.py --from 2026-01-01              # From date to now
    python build_vault.py --name "my-vault"              # Custom vault name
"""

import argparse
import calendar
import json
import re
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path


# Topic categories for automatic classification
TOPIC_PATTERNS = {
    "x3lixi & Product Development": [
        r"x3lixi", r"x3lixios", r"mvp", r"saas", r"product", r"market", r"customer",
        r"acquisition", r"greek-professionals", r"greek-b2c", r"subscription"
    ],
    "Flutter & Mobile Development": [
        r"flutter", r"habitify", r"widget", r"android", r"mobile", r"routinery"
    ],
    "AI & LLMs": [
        r"claude", r"gemini", r"gpt", r"llm", r"ai-", r"prompt", r"codex", r"mcp",
        r"frontier-llm", r"claude-code", r"ai-life-coach"
    ],
    "Health & Wellness": [
        r"sleep", r"vitamin", r"supplement", r"fasting", r"fitness", r"exercise",
        r"serotonin", r"dopamine", r"caffeine", r"glaucoma", r"meditation", r"mindfulness"
    ],
    "Productivity & Self-Development": [
        r"productivity", r"procrastination", r"execution", r"habits", r"self-?help",
        r"personal-development", r"learning", r"thinking-fast", r"mental-models",
        r"yearly-review", r"goals", r"obsidian"
    ],
    "Music & DJ": [
        r"psytrance", r"dj", r"bpm", r"behringer", r"audio", r"music"
    ],
    "Relationships & Personal": [
        r"intimacy", r"jealousy", r"relationship", r"compliment", r"breakup"
    ],
    "Technical & Tools": [
        r"chrome-extension", r"google-drive", r"react", r"flutterflow", r"dreamflow",
        r"deepstash", r"telegram", r"neo4j", r"rag"
    ],
    "Research & Analysis": [
        r"research", r"overview", r"comparison", r"analysis", r"benchmark"
    ],
}


def parse_yaml_frontmatter(content: str) -> dict:
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
    # Parse list values (topics)
    in_list_key = None
    list_items = []
    for line in block.split('\n'):
        if line.startswith('  - '):
            list_items.append(line.strip('- ').strip())
        elif ':' in line and not line.startswith(' '):
            if in_list_key and list_items:
                fm[in_list_key] = list_items
            key, _, val = line.partition(':')
            key = key.strip()
            val = val.strip()
            if not val:
                in_list_key = key
                list_items = []
            else:
                in_list_key = None
                list_items = []
    if in_list_key and list_items:
        fm[in_list_key] = list_items
    return fm


def parse_date_from_filename(filename: str) -> str | None:
    """Extract date from YYYYMMDD_title.md filename."""
    match = re.match(r"(\d{8})_", filename)
    if match:
        return datetime.strptime(match.group(1), "%Y%m%d").strftime("%Y-%m-%d")
    return None


def date_in_range(date_str: str, date_from: str | None, date_to: str | None) -> bool:
    """Check if a date string falls within the given range."""
    if not date_str:
        return False
    if date_from and date_str < date_from:
        return False
    if date_to and date_str > date_to:
        return False
    return True


def get_files_in_range(output_dir: Path, date_from: str | None, date_to: str | None) -> list[dict]:
    """Find all conversation files within the date range."""
    sources = {
        "Claude": output_dir / "claude-full" / "conversations",
        "ChatGPT": output_dir / "chatgpt-full" / "conversations",
        "Gemini": output_dir / "gemini" / "conversations",
    }

    files = []
    for source_name, source_dir in sources.items():
        if not source_dir.exists():
            continue
        for f in source_dir.glob("*.md"):
            if f.name == 'CLAUDE.md':
                continue
            date = parse_date_from_filename(f.name)
            if date_in_range(date, date_from, date_to):
                files.append({
                    "path": f,
                    "source": source_name,
                    "filename": f.name,
                    "date": date,
                })
    return sorted(files, key=lambda x: x["filename"])


def extract_metadata_from_file(file_path: Path) -> dict:
    """Extract title, summary, and topics from a conversation file."""
    content = file_path.read_text(encoding='utf-8')
    fm = parse_yaml_frontmatter(content)

    # Title: YAML > H1 > filename
    title = fm.get('title', '')
    if not title:
        match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        title = match.group(1).strip() if match else ''
    if not title:
        title = file_path.stem.split('_', 1)[-1].replace('-', ' ').title()

    # Summary: YAML > inline metadata
    summary = fm.get('summary', '')
    if not summary:
        match = re.search(r'\*\*Summary\*\*:\s*(.+?)(?=\n---|\n\n##)', content, re.DOTALL)
        if match:
            summary = match.group(1).strip()
            paragraphs = summary.split('\n\n')
            summary = paragraphs[0][:500] if paragraphs else summary[:500]

    # Topics from YAML frontmatter
    yaml_topics = fm.get('topics', [])
    if isinstance(yaml_topics, str):
        yaml_topics = [yaml_topics] if yaml_topics else []

    return {
        'title': title,
        'summary': summary or None,
        'yaml_topics': yaml_topics,
        'characters': int(fm.get('characters', 0) or 0),
        'messages': int(fm.get('messages', 0) or 0),
    }


def classify_topics(title: str, filename: str) -> list[str]:
    """Classify conversation into topics based on title and filename."""
    topics = []
    text = (title + " " + filename).lower()
    for topic, patterns in TOPIC_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                topics.append(topic)
                break
    return topics if topics else ["General"]


def create_vault_structure(vault_dir: Path) -> None:
    """Create the Obsidian vault folder structure."""
    if vault_dir.exists():
        shutil.rmtree(vault_dir)

    vault_dir.mkdir(parents=True)
    (vault_dir / "Daily").mkdir()
    (vault_dir / "Conversations" / "Claude").mkdir(parents=True)
    (vault_dir / "Conversations" / "ChatGPT").mkdir(parents=True)
    (vault_dir / "Conversations" / "Gemini").mkdir(parents=True)
    (vault_dir / "Topics").mkdir()
    (vault_dir / ".obsidian").mkdir()

    workspace = {
        "main": {
            "id": "main",
            "type": "split",
            "children": [{
                "id": "leaf1",
                "type": "leaf",
                "state": {"type": "markdown", "state": {"file": "Home.md"}}
            }]
        }
    }
    (vault_dir / ".obsidian" / "workspace.json").write_text(
        json.dumps(workspace, indent=2), encoding='utf-8'
    )
    (vault_dir / ".obsidian" / "app.json").write_text(json.dumps({
        "showLineNumber": True,
        "defaultViewMode": "preview",
        "livePreview": True,
        "showFrontmatter": False,
    }, indent=2), encoding='utf-8')


def copy_conversation_file(
    file_info: dict,
    vault_dir: Path,
    conversations_by_date: dict,
    conversations_by_topic: dict,
) -> None:
    """Copy and enhance a conversation file to the vault."""
    source_path = file_info["path"]
    source_name = file_info["source"]
    filename = file_info["filename"]
    date = file_info["date"]

    meta = extract_metadata_from_file(source_path)
    title = meta['title']
    summary = meta['summary']

    # Topics: use classified topics (broader categories)
    topics = classify_topics(title, filename)

    content = source_path.read_text(encoding='utf-8')

    # Strip existing YAML frontmatter (we'll add our own)
    if content.startswith('---'):
        end = content.find('\n---', 3)
        if end != -1:
            content = content[end + 4:].lstrip('\n')

    # Create vault frontmatter
    frontmatter = f"""---
date: {date}
source: {source_name}
topics: {json.dumps(topics)}
aliases:
  - "{title}"
---

"""

    nav_links = f"""[[Home|🏠 Home]] | [[Daily/{date}|📅 {date}]] | [[Topics/By Source#{source_name}|💬 {source_name}]]

---

"""

    dest_path = vault_dir / "Conversations" / source_name / filename
    dest_path.write_text(frontmatter + nav_links + content, encoding='utf-8')

    conv_info = {
        "path": f"Conversations/{source_name}/{filename}",
        "title": title,
        "source": source_name,
        "summary": summary,
        "topics": topics,
        "link_name": filename.replace('.md', ''),
    }

    if date:
        conversations_by_date[date].append(conv_info)
    for topic in topics:
        conversations_by_topic[topic].append({**conv_info, "date": date})


def create_daily_notes(vault_dir: Path, conversations_by_date: dict) -> None:
    """Create daily notes with links to that day's conversations."""
    all_dates = sorted(conversations_by_date.keys())

    for i, date in enumerate(all_dates):
        convs = conversations_by_date[date]
        prev_date = all_dates[i - 1] if i > 0 else None
        next_date = all_dates[i + 1] if i < len(all_dates) - 1 else None

        nav = "[[Home|🏠 Home]]"
        if prev_date:
            nav += f" | [[Daily/{prev_date}|← {prev_date}]]"
        if next_date:
            nav += f" | [[Daily/{next_date}|{next_date} →]]"

        dt = datetime.strptime(date, "%Y-%m-%d")
        content = f"""---
date: {date}
type: daily
---

{nav}

---

# {dt.strftime('%A')}, {dt.strftime('%B %d, %Y')}

## Conversations ({len(convs)})

"""

        by_source = defaultdict(list)
        for conv in convs:
            by_source[conv["source"]].append(conv)

        for source in ["Claude", "ChatGPT", "Gemini"]:
            if source in by_source:
                content += f"### 💬 {source}\n\n"
                for conv in by_source[source]:
                    link = f"[[{conv['path']}|{conv['title']}]]"
                    if conv.get("summary"):
                        short = conv["summary"][:150].strip()
                        if len(conv["summary"]) > 150:
                            short += "..."
                        content += f"- {link}\n  > {short}\n\n"
                    else:
                        content += f"- {link}\n"
                content += "\n"

        all_topics = set()
        for conv in convs:
            all_topics.update(conv["topics"])
        if all_topics and "General" not in all_topics:
            content += "## Topics Discussed\n\n"
            for topic in sorted(all_topics):
                content += f"- [[Topics/{topic}|{topic}]]\n"

        (vault_dir / "Daily" / f"{date}.md").write_text(content, encoding='utf-8')


def create_topic_mocs(vault_dir: Path, conversations_by_topic: dict) -> None:
    """Create Maps of Content for each topic."""
    for topic, convs in conversations_by_topic.items():
        convs_sorted = sorted(convs, key=lambda x: x.get("date", ""), reverse=True)

        content = f"""---
type: topic
conversations: {len(convs)}
---

[[Home|🏠 Home]] | [[Topics/By Source|📊 By Source]]

---

# {topic}

*{len(convs)} conversations*

## Recent Conversations

"""

        for conv in convs_sorted[:30]:
            date = conv.get("date", "")
            link = f"[[{conv['path']}|{conv['title']}]]"
            icon = {"Claude": "🟣", "ChatGPT": "🟢", "Gemini": "🔵"}.get(conv["source"], "💬")
            content += f"- {icon} `{date}` {link}\n"

        if len(convs) > 30:
            content += f"\n*... and {len(convs) - 30} more*\n"

        safe_topic = topic.replace(" & ", " and ").replace("/", "-")
        (vault_dir / "Topics" / f"{safe_topic}.md").write_text(content, encoding='utf-8')

    # By Source MOC
    source_convs_map = defaultdict(list)
    for topic, convs in conversations_by_topic.items():
        for conv in convs:
            source_convs_map[conv["source"]].append(conv)

    content = """---
type: index
---

[[Home|🏠 Home]]

---

# Conversations by Source

"""

    for source in ["Claude", "ChatGPT", "Gemini"]:
        seen = set()
        unique = []
        for conv in source_convs_map.get(source, []):
            if conv["path"] not in seen:
                seen.add(conv["path"])
                unique.append(conv)

        icon = {"Claude": "🟣", "ChatGPT": "🟢", "Gemini": "🔵"}[source]
        content += f"## {source} {icon}\n\n*{len(unique)} conversations*\n\n"

        for conv in sorted(unique, key=lambda x: x.get("date", ""), reverse=True)[:20]:
            content += f"- `{conv.get('date', '')}` [[{conv['path']}|{conv['title'][:60]}]]\n"

        if len(unique) > 20:
            content += f"\n*... and {len(unique) - 20} more*\n"
        content += "\n"

    (vault_dir / "Topics" / "By Source.md").write_text(content, encoding='utf-8')


def create_calendar_section(conversations_by_date: dict, date_from: str, date_to: str) -> str:
    """Generate monthly calendar views for the date range."""
    content = ""

    start = datetime.strptime(date_from, "%Y-%m-%d")
    end = datetime.strptime(date_to, "%Y-%m-%d")

    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        month_name = datetime(year, month, 1).strftime("%B %Y")
        content += f"### {month_name}\n\n"
        content += "| Mon | Tue | Wed | Thu | Fri | Sat | Sun |\n"
        content += "|:---:|:---:|:---:|:---:|:---:|:---:|:---:|\n"

        first_weekday = calendar.weekday(year, month, 1)
        days_in_month = calendar.monthrange(year, month)[1]
        row = [""] * first_weekday

        for day in range(1, days_in_month + 1):
            date_str = f"{year}-{month:02d}-{day:02d}"
            if date_str in conversations_by_date:
                count = len(conversations_by_date[date_str])
                row.append(f"[[Daily/{date_str}|{day}]] ({count})")
            else:
                row.append(str(day))
            if len(row) == 7:
                content += "| " + " | ".join(row) + " |\n"
                row = []

        if row:
            row.extend([""] * (7 - len(row)))
            content += "| " + " | ".join(row) + " |\n"

        content += "\n"
        month += 1
        if month > 12:
            month = 1
            year += 1

    return content


def create_dashboard(
    vault_dir: Path,
    vault_title: str,
    conversations_by_date: dict,
    conversations_by_topic: dict,
    date_from: str,
    date_to: str,
) -> None:
    """Create the main Home dashboard."""
    total_convs = sum(len(c) for c in conversations_by_date.values())
    unique_dates = len(conversations_by_date)
    all_dates = sorted(conversations_by_date.keys())

    claude_count = sum(1 for d in conversations_by_date.values() for c in d if c["source"] == "Claude")
    chatgpt_count = sum(1 for d in conversations_by_date.values() for c in d if c["source"] == "ChatGPT")
    gemini_count = sum(1 for d in conversations_by_date.values() for c in d if c["source"] == "Gemini")

    content = f"""---
type: home
---

# {vault_title}

*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*

---

## Overview

| Metric | Value |
|--------|-------|
| 📅 Days with conversations | {unique_dates} |
| 💬 Total conversations | {total_convs} |
| 🟣 Claude | {claude_count} |
| 🟢 ChatGPT | {chatgpt_count} |
| 🔵 Gemini | {gemini_count} |

---

## Calendar

"""

    content += create_calendar_section(conversations_by_date, date_from, date_to)

    content += "---\n\n## Topics\n\n"
    for topic in sorted(TOPIC_PATTERNS.keys()):
        if topic in conversations_by_topic:
            count = len(conversations_by_topic[topic])
            safe_topic = topic.replace(" & ", " and ").replace("/", "-")
            content += f"- [[Topics/{safe_topic}|{topic}]] ({count})\n"
    if "General" in conversations_by_topic:
        content += f"- [[Topics/General|General]] ({len(conversations_by_topic['General'])})\n"
    content += f"\n- [[Topics/By Source|📊 All by Source]]\n"

    content += "\n---\n\n## Quick Navigation\n\n"
    if all_dates:
        content += f"- [[Daily/{all_dates[0]}|First day ({all_dates[0]})]]\n"
        content += f"- [[Daily/{all_dates[-1]}|Last day ({all_dates[-1]})]]\n"

    # Highlights: conversations with summaries
    highlighted = []
    for date, convs in conversations_by_date.items():
        for conv in convs:
            if conv.get("summary"):
                highlighted.append({**conv, "date": date})

    if highlighted:
        highlighted = sorted(highlighted, key=lambda x: x["date"], reverse=True)[:5]
        content += "\n---\n\n## Highlights\n\n"
        for h in highlighted:
            content += f"### [[{h['path']}|{h['title']}]]\n"
            content += f"*{h['date']} via {h['source']}*\n\n"
            if h.get("summary"):
                content += f"> {h['summary'][:200]}...\n\n"

    content += "\n---\n\n*Generated with AI-Conversations-Export-Toolkit*\n"

    (vault_dir / "Home.md").write_text(content, encoding='utf-8')


def parse_args() -> argparse.Namespace:
    base_dir = Path(__file__).parent.parent
    default_output = base_dir / 'output'

    parser = argparse.ArgumentParser(
        description='Build an Obsidian vault from extracted AI conversations.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
    %(prog)s --all                               # All conversations
    %(prog)s --month 2026-01                     # January 2026
    %(prog)s --from 2025-12-01 --to 2025-12-31   # Date range
    %(prog)s --from 2026-01-01                   # From date to now
    %(prog)s --all --name "full-archive"         # Custom vault name
        '''
    )
    parser.add_argument('--all', action='store_true', help='Include all conversations')
    parser.add_argument('--month', type=str, help='Month to include (YYYY-MM)')
    parser.add_argument('--from', dest='date_from', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--to', dest='date_to', type=str, help='End date (YYYY-MM-DD)')
    parser.add_argument('--name', type=str, help='Custom vault name (default: auto-generated)')
    parser.add_argument('--output-dir', type=Path, default=default_output,
                        help=f'Output base directory (default: {default_output})')
    return parser.parse_args()


def main():
    args = parse_args()

    # Determine date range
    if args.all:
        date_from = '2000-01-01'
        date_to = '2099-12-31'
        range_label = 'all'
    elif args.month:
        year, month = args.month.split('-')
        year, month = int(year), int(month)
        days = calendar.monthrange(year, month)[1]
        date_from = f"{year}-{month:02d}-01"
        date_to = f"{year}-{month:02d}-{days:02d}"
        range_label = args.month
    elif args.date_from:
        date_from = args.date_from
        date_to = args.date_to or datetime.now().strftime('%Y-%m-%d')
        range_label = f"{date_from}_to_{date_to}"
    else:
        print("Error: Specify --all, --month YYYY-MM, or --from YYYY-MM-DD")
        return 1

    # Vault directory
    vault_name = args.name or f"vault-{range_label}"
    vault_dir = args.output_dir / vault_name

    # Vault title
    if args.all:
        vault_title = "AI Conversations Archive"
    elif args.month:
        dt = datetime(int(args.month.split('-')[0]), int(args.month.split('-')[1]), 1)
        vault_title = f"AI Conversations — {dt.strftime('%B %Y')}"
    else:
        vault_title = f"AI Conversations — {date_from} to {date_to}"

    print(f"Building Obsidian vault: {vault_name}")
    print(f"Date range: {date_from} to {date_to}")

    # Find files
    files = get_files_in_range(args.output_dir, date_from, date_to)
    print(f"Found {len(files)} conversation files")

    if not files:
        print("No conversations found in the specified range.")
        return 0

    # Build vault
    print("Creating vault structure...")
    create_vault_structure(vault_dir)

    conversations_by_date = defaultdict(list)
    conversations_by_topic = defaultdict(list)

    print("Processing conversations...")
    for file_info in files:
        copy_conversation_file(file_info, vault_dir, conversations_by_date, conversations_by_topic)

    print("Creating daily notes...")
    create_daily_notes(vault_dir, conversations_by_date)

    print("Creating topic MOCs...")
    create_topic_mocs(vault_dir, conversations_by_topic)

    print("Creating dashboard...")
    create_dashboard(vault_dir, vault_title, conversations_by_date, conversations_by_topic,
                     date_from, date_to)

    # Clamp display dates to actual data
    actual_from = min(conversations_by_date.keys())
    actual_to = max(conversations_by_date.keys())

    print(f"\nVault created: {vault_dir}")
    print(f"  Period:        {actual_from} to {actual_to}")
    print(f"  Daily notes:   {len(conversations_by_date)}")
    print(f"  Topics:        {len(conversations_by_topic)}")
    print(f"  Conversations: {sum(len(c) for c in conversations_by_date.values())}")
    return 0


if __name__ == "__main__":
    exit(main())
