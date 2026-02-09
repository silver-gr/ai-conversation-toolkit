#!/usr/bin/env python3
"""
Build an Obsidian vault for December 2025 AI conversations.
Creates daily notes, topic MOCs, and a dashboard.
"""

import json
import os
import re
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Configuration
OUTPUT_DIR = Path("/Users/silver/Projects/AI-Conversations-Export-Toolkit/output")
VAULT_DIR = OUTPUT_DIR / "december-2025-vault"

# Source directories
SOURCES = {
    "Claude": OUTPUT_DIR / "claude-full" / "conversations",
    "ChatGPT": OUTPUT_DIR / "chatgpt-full" / "conversations",
    "Gemini": OUTPUT_DIR / "gemini" / "conversations",
}

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


def get_december_files():
    """Find all December 2025 conversation files."""
    files = []
    for source_name, source_dir in SOURCES.items():
        if not source_dir.exists():
            continue
        for f in source_dir.glob("202512*.md"):
            files.append({
                "path": f,
                "source": source_name,
                "filename": f.name
            })
    return sorted(files, key=lambda x: x["filename"])


def parse_date_from_filename(filename):
    """Extract date from YYYYMMDD_title.md filename."""
    match = re.match(r"(\d{8})_", filename)
    if match:
        date_str = match.group(1)
        return datetime.strptime(date_str, "%Y%m%d").strftime("%Y-%m-%d")
    return None


def extract_title_from_file(file_path):
    """Extract title from markdown file (first # heading)."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read(2000)  # First 2000 chars should have title
        match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        if match:
            return match.group(1).strip()
    except Exception as e:
        pass
    # Fallback: use filename
    return file_path.stem.split('_', 1)[-1].replace('-', ' ').title()


def extract_summary_from_file(file_path):
    """Extract summary from Claude file metadata if present."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read(5000)
        # Look for Summary field in metadata
        match = re.search(r'\*\*Summary\*\*:\s*(.+?)(?=\n---|\n\n##)', content, re.DOTALL)
        if match:
            summary = match.group(1).strip()
            # Take first paragraph if too long
            paragraphs = summary.split('\n\n')
            return paragraphs[0][:500] if paragraphs else summary[:500]
    except Exception:
        pass
    return None


def classify_topics(title, filename):
    """Classify conversation into topics based on title and filename."""
    topics = []
    text = (title + " " + filename).lower()
    for topic, patterns in TOPIC_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                topics.append(topic)
                break
    return topics if topics else ["General"]


def create_vault_structure():
    """Create the Obsidian vault folder structure."""
    # Clean and create vault directory
    if VAULT_DIR.exists():
        shutil.rmtree(VAULT_DIR)

    VAULT_DIR.mkdir(parents=True)
    (VAULT_DIR / "Daily").mkdir()
    (VAULT_DIR / "Conversations" / "Claude").mkdir(parents=True)
    (VAULT_DIR / "Conversations" / "ChatGPT").mkdir(parents=True)
    (VAULT_DIR / "Conversations" / "Gemini").mkdir(parents=True)
    (VAULT_DIR / "Topics").mkdir()
    (VAULT_DIR / ".obsidian").mkdir()

    # Create basic Obsidian config
    workspace = {
        "main": {
            "id": "main",
            "type": "split",
            "children": [
                {
                    "id": "leaf1",
                    "type": "leaf",
                    "state": {
                        "type": "markdown",
                        "state": {"file": "Home.md"}
                    }
                }
            ]
        }
    }

    with open(VAULT_DIR / ".obsidian" / "workspace.json", 'w') as f:
        json.dump(workspace, f, indent=2)

    # App settings
    app_settings = {
        "showLineNumber": True,
        "defaultViewMode": "preview",
        "livePreview": True,
        "showFrontmatter": False
    }

    with open(VAULT_DIR / ".obsidian" / "app.json", 'w') as f:
        json.dump(app_settings, f, indent=2)


def copy_conversation_file(file_info, conversations_by_date, conversations_by_topic):
    """Copy and enhance a conversation file to the vault."""
    source_path = file_info["path"]
    source_name = file_info["source"]
    filename = file_info["filename"]

    date = parse_date_from_filename(filename)
    title = extract_title_from_file(source_path)
    summary = extract_summary_from_file(source_path)
    topics = classify_topics(title, filename)

    # Read original content
    with open(source_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Create enhanced frontmatter
    frontmatter = f"""---
date: {date}
source: {source_name}
topics: {json.dumps(topics)}
aliases:
  - "{title}"
---

"""

    # Add navigation links at the top
    nav_links = f"""[[Home|🏠 Home]] | [[Daily/{date}|📅 {date}]] | [[Topics/By Source#{source_name}|💬 {source_name}]]

---

"""

    # Write enhanced file
    dest_path = VAULT_DIR / "Conversations" / source_name / filename
    with open(dest_path, 'w', encoding='utf-8') as f:
        f.write(frontmatter + nav_links + content)

    # Track for daily notes and topic MOCs
    conv_info = {
        "path": f"Conversations/{source_name}/{filename}",
        "title": title,
        "source": source_name,
        "summary": summary,
        "topics": topics,
        "link_name": filename.replace('.md', '')
    }

    if date:
        conversations_by_date[date].append(conv_info)

    for topic in topics:
        conversations_by_topic[topic].append({**conv_info, "date": date})


def create_daily_notes(conversations_by_date):
    """Create daily notes with links to that day's conversations."""
    all_dates = sorted(conversations_by_date.keys())

    for i, date in enumerate(all_dates):
        convs = conversations_by_date[date]

        # Navigation
        prev_date = all_dates[i-1] if i > 0 else None
        next_date = all_dates[i+1] if i < len(all_dates) - 1 else None

        nav = "[[Home|🏠 Home]]"
        if prev_date:
            nav += f" | [[Daily/{prev_date}|← {prev_date}]]"
        if next_date:
            nav += f" | [[Daily/{next_date}|{next_date} →]]"

        # Format date nicely
        dt = datetime.strptime(date, "%Y-%m-%d")
        day_name = dt.strftime("%A")
        formatted_date = dt.strftime("%B %d, %Y")

        content = f"""---
date: {date}
type: daily
---

{nav}

---

# {day_name}, {formatted_date}

## Conversations ({len(convs)})

"""

        # Group by source
        by_source = defaultdict(list)
        for conv in convs:
            by_source[conv["source"]].append(conv)

        for source in ["Claude", "ChatGPT", "Gemini"]:
            if source in by_source:
                content += f"### 💬 {source}\n\n"
                for conv in by_source[source]:
                    link = f"[[{conv['path']}|{conv['title']}]]"
                    if conv.get("summary"):
                        # Truncate summary to ~100 chars
                        short_summary = conv["summary"][:150].strip()
                        if len(conv["summary"]) > 150:
                            short_summary += "..."
                        content += f"- {link}\n  > {short_summary}\n\n"
                    else:
                        content += f"- {link}\n"
                content += "\n"

        # Add topics mentioned that day
        all_topics = set()
        for conv in convs:
            all_topics.update(conv["topics"])

        if all_topics and "General" not in all_topics:
            content += "## Topics Discussed\n\n"
            for topic in sorted(all_topics):
                content += f"- [[Topics/{topic}|{topic}]]\n"

        with open(VAULT_DIR / "Daily" / f"{date}.md", 'w') as f:
            f.write(content)


def create_topic_mocs(conversations_by_topic):
    """Create Maps of Content for each topic."""
    for topic, convs in conversations_by_topic.items():
        # Sort by date
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

        for conv in convs_sorted[:20]:  # Top 20
            date = conv.get("date", "")
            link = f"[[{conv['path']}|{conv['title']}]]"
            source_icon = {"Claude": "🟣", "ChatGPT": "🟢", "Gemini": "🔵"}.get(conv["source"], "💬")
            content += f"- {source_icon} `{date}` {link}\n"

        if len(convs) > 20:
            content += f"\n*... and {len(convs) - 20} more*\n"

        # Safe filename
        safe_topic = topic.replace(" & ", " and ").replace("/", "-")
        with open(VAULT_DIR / "Topics" / f"{safe_topic}.md", 'w') as f:
            f.write(content)

    # Create By Source MOC
    source_counts = defaultdict(int)
    for topic, convs in conversations_by_topic.items():
        for conv in convs:
            source_counts[conv["source"]] += 1

    by_source_content = f"""---
type: index
---

[[Home|🏠 Home]]

---

# Conversations by Source

## Claude 🟣

*{source_counts.get("Claude", 0)} conversations*

"""

    for source in ["Claude", "ChatGPT", "Gemini"]:
        source_convs = []
        for topic, convs in conversations_by_topic.items():
            for conv in convs:
                if conv["source"] == source:
                    source_convs.append(conv)

        # Dedupe
        seen = set()
        unique_convs = []
        for conv in source_convs:
            if conv["path"] not in seen:
                seen.add(conv["path"])
                unique_convs.append(conv)

        icon = {"Claude": "🟣", "ChatGPT": "🟢", "Gemini": "🔵"}[source]
        by_source_content += f"## {source} {icon}\n\n"
        by_source_content += f"*{len(unique_convs)} conversations*\n\n"

        for conv in sorted(unique_convs, key=lambda x: x.get("date", ""), reverse=True)[:15]:
            by_source_content += f"- `{conv.get('date', '')}` [[{conv['path']}|{conv['title'][:50]}]]\n"

        by_source_content += "\n"

    with open(VAULT_DIR / "Topics" / "By Source.md", 'w') as f:
        f.write(by_source_content)


def create_dashboard(conversations_by_date, conversations_by_topic):
    """Create the main Home dashboard."""
    total_convs = sum(len(c) for c in conversations_by_date.values())
    unique_dates = len(conversations_by_date)

    content = f"""---
type: home
---

# December 2025 AI Conversations

*Your AI conversation archive from December 2025*

---

## Overview

| Metric | Value |
|--------|-------|
| 📅 Days with conversations | {unique_dates} |
| 💬 Total conversations | {total_convs} |
| 🟣 Claude | {sum(1 for d in conversations_by_date.values() for c in d if c["source"] == "Claude")} |
| 🟢 ChatGPT | {sum(1 for d in conversations_by_date.values() for c in d if c["source"] == "ChatGPT")} |
| 🔵 Gemini | {sum(1 for d in conversations_by_date.values() for c in d if c["source"] == "Gemini")} |

---

## Daily Notes

Navigate by date to see all conversations from each day.

"""

    # Create a calendar-like view
    content += "### December 2025\n\n"
    content += "| Mon | Tue | Wed | Thu | Fri | Sat | Sun |\n"
    content += "|:---:|:---:|:---:|:---:|:---:|:---:|:---:|\n"

    # December 2025 starts on Monday
    from calendar import monthrange, weekday
    first_weekday = weekday(2025, 12, 1)  # 0 = Monday
    days_in_month = 31

    # Pad first week
    row = [""] * first_weekday

    for day in range(1, days_in_month + 1):
        date_str = f"2025-12-{day:02d}"
        if date_str in conversations_by_date:
            count = len(conversations_by_date[date_str])
            row.append(f"[[Daily/{date_str}|{day}]] ({count})")
        else:
            row.append(str(day))

        if len(row) == 7:
            content += "| " + " | ".join(row) + " |\n"
            row = []

    # Pad last week
    if row:
        row.extend([""] * (7 - len(row)))
        content += "| " + " | ".join(row) + " |\n"

    content += "\n---\n\n"

    # Topics section
    content += "## Topics\n\n"

    for topic in sorted(TOPIC_PATTERNS.keys()):
        if topic in conversations_by_topic:
            count = len(conversations_by_topic[topic])
            safe_topic = topic.replace(" & ", " and ").replace("/", "-")
            content += f"- [[Topics/{safe_topic}|{topic}]] ({count})\n"

    if "General" in conversations_by_topic:
        content += f"- [[Topics/General|General]] ({len(conversations_by_topic['General'])})\n"

    content += f"\n- [[Topics/By Source|📊 All by Source]]\n"

    content += """

---

## Quick Navigation

- [[Daily/2025-12-01|Start of December]]
- [[Daily/2025-12-16|Latest Extracted]]

---

## Highlights

Some notable conversations this month:

"""

    # Pick a few highlighted conversations (ones with summaries)
    highlighted = []
    for date, convs in conversations_by_date.items():
        for conv in convs:
            if conv.get("summary"):
                highlighted.append({**conv, "date": date})

    highlighted = sorted(highlighted, key=lambda x: x["date"], reverse=True)[:5]

    for h in highlighted:
        content += f"### [[{h['path']}|{h['title']}]]\n"
        content += f"*{h['date']} via {h['source']}*\n\n"
        if h.get("summary"):
            content += f"> {h['summary'][:200]}...\n\n"

    content += """
---

*Generated with AI-Conversations-Export-Toolkit*
"""

    with open(VAULT_DIR / "Home.md", 'w') as f:
        f.write(content)


def main():
    print("🚀 Building December 2025 Obsidian Vault...")

    # Get all December files
    files = get_december_files()
    print(f"📄 Found {len(files)} December 2025 conversation files")

    # Create vault structure
    print("📁 Creating vault structure...")
    create_vault_structure()

    # Process files
    print("⚙️ Processing conversations...")
    conversations_by_date = defaultdict(list)
    conversations_by_topic = defaultdict(list)

    for file_info in files:
        copy_conversation_file(file_info, conversations_by_date, conversations_by_topic)

    # Create daily notes
    print("📅 Creating daily notes...")
    create_daily_notes(conversations_by_date)

    # Create topic MOCs
    print("🏷️ Creating topic MOCs...")
    create_topic_mocs(conversations_by_topic)

    # Create dashboard
    print("🏠 Creating dashboard...")
    create_dashboard(conversations_by_date, conversations_by_topic)

    # Summary
    print("\n✅ Vault created successfully!")
    print(f"   📍 Location: {VAULT_DIR}")
    print(f"   📅 Daily notes: {len(conversations_by_date)}")
    print(f"   🏷️ Topics: {len(conversations_by_topic)}")
    print(f"   💬 Conversations: {sum(len(c) for c in conversations_by_date.values())}")
    print("\n💡 Open in Obsidian: File → Open vault → Select the folder")


if __name__ == "__main__":
    main()
