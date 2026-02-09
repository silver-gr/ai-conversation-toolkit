#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "rich",
# ]
# requires-python = ">=3.11"
# ///

"""
Profile Generator
=================

Aggregates biographical extractions and generates a comprehensive profile
with markdown files organized by category.

Usage:
    # Generate profile from default location
    python3 scripts/profile_generator.py

    # Specify input file
    python3 scripts/profile_generator.py --input output/profile/data/extractions.json

    # Specify output directory
    python3 scripts/profile_generator.py --output-dir output/profile
"""

import json
import argparse
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from typing import Any
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()

# Default paths
DEFAULT_INPUT = "output/profile/data/extractions.json"
DEFAULT_OUTPUT_DIR = "output/profile"


class ProfileGenerator:
    def __init__(self, input_file: str, output_dir: str):
        self.input_file = Path(input_file)
        self.output_dir = Path(output_dir)
        self.extractions: list[dict] = []
        self.aggregated: dict[str, dict[str, dict[str, Any]]] = {}
        self.timeline: dict[str, list[dict]] = defaultdict(list)
        self.statistics: dict[str, Any] = {}

    def load_extractions(self) -> bool:
        """Load extractions from JSON file"""
        if not self.input_file.exists():
            console.print(f"[red]Input file not found: {self.input_file}[/red]")
            console.print("[yellow]Run biography_extractor.py first to generate extractions[/yellow]")
            return False

        try:
            with open(self.input_file, "r", encoding="utf-8") as f:
                self.extractions = json.load(f)
            console.print(f"[green]Loaded {len(self.extractions)} extractions[/green]")
            return True
        except json.JSONDecodeError as e:
            console.print(f"[red]Invalid JSON in {self.input_file}: {e}[/red]")
            return False

    def aggregate_data(self):
        """Aggregate data across all extractions with frequency counts and dates"""
        console.print("[cyan]Aggregating data...[/cyan]")

        # Categories to aggregate (excluding context and _metadata)
        categories = [
            "identity", "work", "health", "relationships",
            "interests", "goals", "challenges", "daily_life", "values"
        ]

        # Initialize aggregated structure
        for category in categories:
            self.aggregated[category] = {}

        # Process each extraction
        for extraction in self.extractions:
            metadata = extraction.get("_metadata", {})
            date = metadata.get("conversation_date", "unknown")
            source = metadata.get("source", "unknown")
            file_path = metadata.get("file_path", "")

            # Track for timeline
            context = extraction.get("context", {})
            main_topic = context.get("main_topic", "")
            richness = context.get("biographical_richness", "minimal")

            if main_topic and richness in ["high", "medium"]:
                self.timeline[date].append({
                    "topic": main_topic,
                    "richness": richness,
                    "source": source,
                    "file_path": file_path,
                    "emotional_tone": context.get("emotional_tone", ""),
                })

            # Aggregate each category
            for category in categories:
                cat_data = extraction.get(category, {})
                if not isinstance(cat_data, dict):
                    continue

                for field, values in cat_data.items():
                    if field not in self.aggregated[category]:
                        self.aggregated[category][field] = {}

                    if isinstance(values, list):
                        for value in values:
                            if value and str(value).strip():
                                normalized = str(value).strip()
                                if normalized not in self.aggregated[category][field]:
                                    self.aggregated[category][field][normalized] = {
                                        "count": 0,
                                        "dates": [],
                                        "sources": set(),
                                    }
                                self.aggregated[category][field][normalized]["count"] += 1
                                if date != "unknown":
                                    self.aggregated[category][field][normalized]["dates"].append(date)
                                self.aggregated[category][field][normalized]["sources"].add(source)

        # Convert sources sets to lists for JSON serialization
        for category in self.aggregated:
            for field in self.aggregated[category]:
                for item in self.aggregated[category][field]:
                    self.aggregated[category][field][item]["sources"] = list(
                        self.aggregated[category][field][item]["sources"]
                    )

    def calculate_statistics(self):
        """Calculate overall statistics"""
        console.print("[cyan]Calculating statistics...[/cyan]")

        # Basic counts
        self.statistics["total_extractions"] = len(self.extractions)

        # Source breakdown
        source_counts: dict[str, int] = defaultdict(int)
        for ext in self.extractions:
            source = ext.get("_metadata", {}).get("source", "unknown")
            source_counts[source] += 1
        self.statistics["by_source"] = dict(source_counts)

        # Richness breakdown
        richness_counts: dict[str, int] = defaultdict(int)
        for ext in self.extractions:
            richness = ext.get("context", {}).get("biographical_richness", "minimal")
            richness_counts[richness.lower()] += 1
        self.statistics["by_richness"] = dict(richness_counts)

        # Date range
        dates = []
        for ext in self.extractions:
            date = ext.get("_metadata", {}).get("conversation_date", "")
            if date and date != "unknown":
                dates.append(date)
        if dates:
            dates.sort()
            self.statistics["date_range"] = {
                "earliest": dates[0],
                "latest": dates[-1],
                "total_days": len(set(dates)),
            }

        # Category item counts
        category_counts: dict[str, int] = {}
        for category, fields in self.aggregated.items():
            total = sum(len(items) for items in fields.values())
            category_counts[category] = total
        self.statistics["items_by_category"] = category_counts

        # Top items across categories
        all_items: list[tuple[str, str, str, int]] = []
        for category, fields in self.aggregated.items():
            for field, items in fields.items():
                for item, data in items.items():
                    all_items.append((category, field, item, data["count"]))
        all_items.sort(key=lambda x: x[3], reverse=True)
        self.statistics["top_items"] = [
            {"category": c, "field": f, "item": i, "count": n}
            for c, f, i, n in all_items[:50]
        ]

    def create_directories(self):
        """Create output directory structure"""
        directories = [
            self.output_dir / "work",
            self.output_dir / "health",
            self.output_dir / "relationships",
            self.output_dir / "interests",
            self.output_dir / "goals",
            self.output_dir / "patterns",
            self.output_dir / "values",
            self.output_dir / "data",
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def _format_items_table(
        self,
        items: dict[str, dict],
        show_dates: bool = True,
        max_items: int = 50
    ) -> str:
        """Format items as markdown table with counts"""
        if not items:
            return "_No data available_\n"

        # Sort by count descending
        sorted_items = sorted(items.items(), key=lambda x: x[1]["count"], reverse=True)[:max_items]

        lines = []
        if show_dates:
            lines.append("| Item | Count | First Seen | Last Seen | Sources |")
            lines.append("|------|-------|------------|-----------|---------|")
        else:
            lines.append("| Item | Count | Sources |")
            lines.append("|------|-------|---------|")

        for item, data in sorted_items:
            count = data["count"]
            sources = ", ".join(sorted(data["sources"]))
            dates = sorted(set(data["dates"])) if data["dates"] else []

            # Escape pipe characters in item text
            item_escaped = item.replace("|", "\\|")

            if show_dates:
                first_date = dates[0] if dates else "-"
                last_date = dates[-1] if dates else "-"
                lines.append(f"| {item_escaped} | {count} | {first_date} | {last_date} | {sources} |")
            else:
                lines.append(f"| {item_escaped} | {count} | {sources} |")

        return "\n".join(lines) + "\n"

    def _format_items_list(self, items: dict[str, dict], max_items: int = 30) -> str:
        """Format items as bullet list with counts"""
        if not items:
            return "_No data available_\n"

        sorted_items = sorted(items.items(), key=lambda x: x[1]["count"], reverse=True)[:max_items]

        lines = []
        for item, data in sorted_items:
            count = data["count"]
            sources = ", ".join(sorted(data["sources"]))
            lines.append(f"- **{item}** ({count}x, {sources})")

        return "\n".join(lines) + "\n"

    def _get_field_items(self, category: str, field: str) -> dict:
        """Get items for a specific category/field"""
        return self.aggregated.get(category, {}).get(field, {})

    def _count_total_items(self, category: str) -> int:
        """Count total unique items in a category"""
        total = 0
        for field_items in self.aggregated.get(category, {}).values():
            total += len(field_items)
        return total

    def generate_index(self):
        """Generate INDEX.md master overview"""
        content = """# Profile Index

> Auto-generated comprehensive profile from AI conversation extractions.
> Last updated: {generated_at}

## Statistics

| Metric | Value |
|--------|-------|
| Total Conversations | {total} |
| Date Range | {date_start} to {date_end} |
| Days Covered | {days} |

### By Source

| Source | Count |
|--------|-------|
{source_rows}

### By Biographical Richness

| Richness | Count |
|----------|-------|
{richness_rows}

### Items by Category

| Category | Unique Items |
|----------|--------------|
{category_rows}

## Navigation

### Work & Professional
- [Work Overview](work/overview.md) - Career, projects, business ventures
- [Skills & Tech Stack](work/skills-tech-stack.md) - Technical abilities demonstrated
- [Work Patterns](work/work-patterns.md) - Work style and preferences

### Health & Wellness
- [Health Overview](health/overview.md) - Overall health picture
- [Physical Health](health/physical-health.md) - Body, fitness, conditions
- [Mental Health](health/mental-health.md) - Psychology, therapy, mental state
- [Supplements Stack](health/supplements-stack.md) - Nutrition and supplements
- [Substances](health/substances.md) - Substance use and patterns

### Relationships
- [Relationships Overview](relationships/overview.md) - Social connections
- [Romantic Life](relationships/romantic-life.md) - Dating and partnerships
- [Social Connections](relationships/social-connections.md) - Friends and community
- [Sexuality](relationships/sexuality.md) - Sexual orientation and interests

### Interests & Hobbies
- [Interests Overview](interests/overview.md) - What captures attention
- [Hobbies](interests/hobbies.md) - Active pursuits
- [Intellectual](interests/intellectual.md) - Learning and thinking
- [Creative](interests/creative.md) - Artistic and creative work

### Goals & Aspirations
- [Goals Overview](goals/overview.md) - Direction and purpose
- [Aspirations](goals/aspirations.md) - Dreams and long-term vision

### Patterns & Challenges
- [Patterns Overview](patterns/overview.md) - Behavioral patterns
- [Challenges](patterns/challenges.md) - Problems and blockers
- [Strengths](patterns/strengths.md) - Demonstrated strengths

### Values & Beliefs
- [Values Overview](values/overview.md) - Core principles and worldview

### Data & Timeline
- [Statistics](data/statistics.md) - Detailed data breakdown
- [Timeline](TIMELINE.md) - Chronological evolution

## Top Recurring Themes

{top_items}

---
*Generated from {total} conversations spanning {days} days.*
"""
        # Format source rows
        source_rows = ""
        for source, count in sorted(self.statistics.get("by_source", {}).items()):
            source_rows += f"| {source.title()} | {count} |\n"

        # Format richness rows
        richness_rows = ""
        for richness, count in sorted(
            self.statistics.get("by_richness", {}).items(),
            key=lambda x: ["high", "medium", "low", "minimal"].index(x[0]) if x[0] in ["high", "medium", "low", "minimal"] else 4
        ):
            richness_rows += f"| {richness.title()} | {count} |\n"

        # Format category rows
        category_rows = ""
        for category, count in sorted(
            self.statistics.get("items_by_category", {}).items(),
            key=lambda x: x[1],
            reverse=True
        ):
            category_rows += f"| {category.replace('_', ' ').title()} | {count} |\n"

        # Format top items
        top_items = ""
        for item in self.statistics.get("top_items", [])[:15]:
            top_items += f"- **{item['item']}** ({item['count']}x in {item['category']}/{item['field']})\n"

        # Date range
        date_range = self.statistics.get("date_range", {})

        content = content.format(
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            total=self.statistics.get("total_extractions", 0),
            date_start=date_range.get("earliest", "N/A"),
            date_end=date_range.get("latest", "N/A"),
            days=date_range.get("total_days", 0),
            source_rows=source_rows,
            richness_rows=richness_rows,
            category_rows=category_rows,
            top_items=top_items,
        )

        self._write_file(self.output_dir / "INDEX.md", content)

    def generate_timeline(self):
        """Generate TIMELINE.md chronological narrative"""
        content = """# Timeline

> Chronological view of topics and interests over time.

"""
        # Sort timeline by date
        sorted_dates = sorted(self.timeline.keys())

        if not sorted_dates:
            content += "_No timeline data available. Most conversations have minimal biographical richness._\n"
        else:
            # Group by year-month for readability
            current_month = ""
            for date in sorted_dates:
                year_month = date[:7] if len(date) >= 7 else date
                if year_month != current_month:
                    current_month = year_month
                    content += f"\n## {year_month}\n\n"

                entries = self.timeline[date]
                for entry in entries:
                    richness_badge = f"[{entry['richness'].upper()}]"
                    source_badge = f"({entry['source']})"
                    tone = f" - _{entry['emotional_tone']}_" if entry.get('emotional_tone') else ""
                    content += f"- **{date}** {richness_badge} {source_badge}: {entry['topic']}{tone}\n"

        # Add interest evolution section
        content += """

## Interest Evolution

### How Topics Changed Over Time

"""
        # Analyze topic evolution by looking at first/last appearances
        evolution_data: dict[str, dict[str, Any]] = {}
        for category in ["interests", "work", "health", "goals"]:
            for field, items in self.aggregated.get(category, {}).items():
                for item, data in items.items():
                    dates = sorted(set(data["dates"])) if data["dates"] else []
                    if dates and data["count"] >= 2:
                        if category not in evolution_data:
                            evolution_data[category] = []
                        evolution_data[category].append({
                            "item": item,
                            "first": dates[0],
                            "last": dates[-1],
                            "count": data["count"],
                            "field": field,
                        })

        for category, items in evolution_data.items():
            if items:
                content += f"#### {category.replace('_', ' ').title()}\n\n"
                # Sort by first appearance
                items.sort(key=lambda x: x["first"])
                for item in items[:20]:
                    span = f"{item['first']} - {item['last']}" if item['first'] != item['last'] else item['first']
                    content += f"- **{item['item']}** ({item['count']}x): {span}\n"
                content += "\n"

        self._write_file(self.output_dir / "TIMELINE.md", content)

    def generate_work_files(self):
        """Generate work-related markdown files"""
        work = self.aggregated.get("work", {})

        # Overview
        overview = f"""# Work Overview

> Professional life, career, and business ventures.

## Summary

- **Total unique items**: {self._count_total_items('work')}
- **Occupations mentioned**: {len(work.get('occupation_hints', {}))}
- **Projects mentioned**: {len(work.get('projects_mentioned', {}))}
- **Skills demonstrated**: {len(work.get('skills_demonstrated', {}))}
- **Business ventures**: {len(work.get('business_ventures', {}))}

## Occupations & Roles

{self._format_items_table(work.get('occupation_hints', {}))}

## Projects

{self._format_items_table(work.get('projects_mentioned', {}))}

## Business Ventures

{self._format_items_table(work.get('business_ventures', {}))}

---
See also: [Skills & Tech Stack](skills-tech-stack.md) | [Work Patterns](work-patterns.md)
"""
        self._write_file(self.output_dir / "work" / "overview.md", overview)

        # Skills & Tech Stack
        skills = f"""# Skills & Tech Stack

> Technical and professional skills demonstrated across conversations.

## Skills Demonstrated

{self._format_items_table(work.get('skills_demonstrated', {}))}

---
See also: [Work Overview](overview.md) | [Work Patterns](work-patterns.md)
"""
        self._write_file(self.output_dir / "work" / "skills-tech-stack.md", skills)

        # Work Patterns
        patterns = f"""# Work Patterns

> Work style, preferences, and routines.

## Work Style

{self._format_items_table(work.get('work_style', {}))}

## Tools & Apps Used

{self._format_items_table(self.aggregated.get('daily_life', {}).get('tools_apps', {}))}

---
See also: [Work Overview](overview.md) | [Skills & Tech Stack](skills-tech-stack.md)
"""
        self._write_file(self.output_dir / "work" / "work-patterns.md", patterns)

    def generate_health_files(self):
        """Generate health-related markdown files"""
        health = self.aggregated.get("health", {})

        # Overview
        overview = f"""# Health Overview

> Physical and mental health picture.

## Summary

- **Total unique items**: {self._count_total_items('health')}
- **Physical health items**: {len(health.get('physical_health', {}))}
- **Mental health items**: {len(health.get('mental_health', {}))}
- **Nutrition/diet items**: {len(health.get('nutrition_diet', {}))}
- **Substances mentioned**: {len(health.get('substances', {}))}
- **Medications**: {len(health.get('medications', {}))}

## Quick View

### Physical Health
{self._format_items_list(health.get('physical_health', {}), 10)}

### Mental Health
{self._format_items_list(health.get('mental_health', {}), 10)}

### Sleep Patterns
{self._format_items_list(health.get('sleep_patterns', {}), 10)}

---
See also: [Physical Health](physical-health.md) | [Mental Health](mental-health.md) | [Supplements](supplements-stack.md) | [Substances](substances.md)
"""
        self._write_file(self.output_dir / "health" / "overview.md", overview)

        # Physical Health
        physical = f"""# Physical Health

> Body, fitness, conditions, and physical wellness.

## Physical Health Items

{self._format_items_table(health.get('physical_health', {}))}

## Sleep Patterns

{self._format_items_table(health.get('sleep_patterns', {}))}

---
See also: [Health Overview](overview.md) | [Mental Health](mental-health.md)
"""
        self._write_file(self.output_dir / "health" / "physical-health.md", physical)

        # Mental Health
        mental = f"""# Mental Health

> Psychology, therapy, mental conditions, and emotional patterns.

## Mental Health Items

{self._format_items_table(health.get('mental_health', {}))}

---
See also: [Health Overview](overview.md) | [Physical Health](physical-health.md)
"""
        self._write_file(self.output_dir / "health" / "mental-health.md", mental)

        # Supplements Stack
        supplements = f"""# Supplements & Nutrition

> Diet, nutrition, and supplement stack.

## Nutrition & Diet

{self._format_items_table(health.get('nutrition_diet', {}))}

## Medications

{self._format_items_table(health.get('medications', {}))}

---
See also: [Health Overview](overview.md) | [Substances](substances.md)
"""
        self._write_file(self.output_dir / "health" / "supplements-stack.md", supplements)

        # Substances
        substances = f"""# Substances

> Substance use patterns and history.

## Substances

{self._format_items_table(health.get('substances', {}))}

---
See also: [Health Overview](overview.md) | [Supplements & Nutrition](supplements-stack.md)
"""
        self._write_file(self.output_dir / "health" / "substances.md", substances)

    def generate_relationships_files(self):
        """Generate relationships-related markdown files"""
        relationships = self.aggregated.get("relationships", {})

        # Overview
        overview = f"""# Relationships Overview

> Social connections, romantic life, family, and community.

## Summary

- **Total unique items**: {self._count_total_items('relationships')}
- **Romantic mentions**: {len(relationships.get('romantic', {}))}
- **Family mentions**: {len(relationships.get('family', {}))}
- **Social mentions**: {len(relationships.get('social', {}))}
- **Sexuality mentions**: {len(relationships.get('sexuality', {}))}

## Quick View

### Romantic Life
{self._format_items_list(relationships.get('romantic', {}), 10)}

### Family
{self._format_items_list(relationships.get('family', {}), 10)}

### Social
{self._format_items_list(relationships.get('social', {}), 10)}

---
See also: [Romantic Life](romantic-life.md) | [Social Connections](social-connections.md) | [Sexuality](sexuality.md)
"""
        self._write_file(self.output_dir / "relationships" / "overview.md", overview)

        # Romantic Life
        romantic = f"""# Romantic Life

> Dating, partnerships, and romantic relationships.

## Romantic Mentions

{self._format_items_table(relationships.get('romantic', {}))}

---
See also: [Relationships Overview](overview.md) | [Sexuality](sexuality.md)
"""
        self._write_file(self.output_dir / "relationships" / "romantic-life.md", romantic)

        # Social Connections
        social = f"""# Social Connections

> Friends, community, and social interactions.

## Family

{self._format_items_table(relationships.get('family', {}))}

## Social

{self._format_items_table(relationships.get('social', {}))}

---
See also: [Relationships Overview](overview.md) | [Romantic Life](romantic-life.md)
"""
        self._write_file(self.output_dir / "relationships" / "social-connections.md", social)

        # Sexuality
        sexuality = f"""# Sexuality

> Sexual orientation, interests, and exploration.

## Sexuality Mentions

{self._format_items_table(relationships.get('sexuality', {}))}

---
See also: [Relationships Overview](overview.md) | [Romantic Life](romantic-life.md)
"""
        self._write_file(self.output_dir / "relationships" / "sexuality.md", sexuality)

    def generate_interests_files(self):
        """Generate interests-related markdown files"""
        interests = self.aggregated.get("interests", {})

        # Overview
        overview = f"""# Interests Overview

> Hobbies, intellectual pursuits, entertainment, and creative work.

## Summary

- **Total unique items**: {self._count_total_items('interests')}
- **Hobbies**: {len(interests.get('hobbies', {}))}
- **Intellectual interests**: {len(interests.get('intellectual', {}))}
- **Entertainment**: {len(interests.get('entertainment', {}))}
- **Creative pursuits**: {len(interests.get('creative', {}))}

## Quick View

### Top Hobbies
{self._format_items_list(interests.get('hobbies', {}), 10)}

### Top Intellectual Interests
{self._format_items_list(interests.get('intellectual', {}), 10)}

### Top Entertainment
{self._format_items_list(interests.get('entertainment', {}), 10)}

### Top Creative Pursuits
{self._format_items_list(interests.get('creative', {}), 10)}

---
See also: [Hobbies](hobbies.md) | [Intellectual](intellectual.md) | [Creative](creative.md)
"""
        self._write_file(self.output_dir / "interests" / "overview.md", overview)

        # Hobbies
        hobbies = f"""# Hobbies

> Active hobbies and recreational activities.

## Hobbies

{self._format_items_table(interests.get('hobbies', {}))}

## Entertainment

{self._format_items_table(interests.get('entertainment', {}))}

---
See also: [Interests Overview](overview.md) | [Intellectual](intellectual.md) | [Creative](creative.md)
"""
        self._write_file(self.output_dir / "interests" / "hobbies.md", hobbies)

        # Intellectual
        intellectual = f"""# Intellectual Interests

> Learning, philosophy, science, and intellectual pursuits.

## Intellectual Interests

{self._format_items_table(interests.get('intellectual', {}))}

---
See also: [Interests Overview](overview.md) | [Hobbies](hobbies.md) | [Creative](creative.md)
"""
        self._write_file(self.output_dir / "interests" / "intellectual.md", intellectual)

        # Creative
        creative = f"""# Creative Pursuits

> Art, writing, music, and creative work.

## Creative

{self._format_items_table(interests.get('creative', {}))}

---
See also: [Interests Overview](overview.md) | [Hobbies](hobbies.md) | [Intellectual](intellectual.md)
"""
        self._write_file(self.output_dir / "interests" / "creative.md", creative)

    def generate_goals_files(self):
        """Generate goals-related markdown files"""
        goals = self.aggregated.get("goals", {})

        # Overview
        overview = f"""# Goals Overview

> Direction, purpose, dreams, and aspirations.

## Summary

- **Total unique items**: {self._count_total_items('goals')}
- **Short-term goals**: {len(goals.get('short_term', {}))}
- **Long-term goals**: {len(goals.get('long_term', {}))}
- **Dreams**: {len(goals.get('dreams', {}))}
- **Fears**: {len(goals.get('fears', {}))}

## Quick View

### Short-term Goals
{self._format_items_list(goals.get('short_term', {}), 10)}

### Long-term Goals
{self._format_items_list(goals.get('long_term', {}), 10)}

### Dreams
{self._format_items_list(goals.get('dreams', {}), 10)}

### Fears
{self._format_items_list(goals.get('fears', {}), 10)}

---
See also: [Aspirations](aspirations.md) | [Challenges](../patterns/challenges.md)
"""
        self._write_file(self.output_dir / "goals" / "overview.md", overview)

        # Aspirations
        aspirations = f"""# Aspirations

> Dreams, long-term vision, and life goals.

## Short-term Goals

{self._format_items_table(goals.get('short_term', {}))}

## Long-term Goals

{self._format_items_table(goals.get('long_term', {}))}

## Dreams

{self._format_items_table(goals.get('dreams', {}))}

## Fears & Concerns

{self._format_items_table(goals.get('fears', {}))}

---
See also: [Goals Overview](overview.md) | [Challenges](../patterns/challenges.md)
"""
        self._write_file(self.output_dir / "goals" / "aspirations.md", aspirations)

    def generate_patterns_files(self):
        """Generate patterns-related markdown files"""
        challenges = self.aggregated.get("challenges", {})
        daily_life = self.aggregated.get("daily_life", {})

        # Overview
        overview = f"""# Patterns Overview

> Behavioral patterns, challenges, and strengths.

## Summary

- **Current problems**: {len(challenges.get('current_problems', {}))}
- **Recurring patterns**: {len(challenges.get('recurring_patterns', {}))}
- **Blockers**: {len(challenges.get('blockers', {}))}
- **Seeking help for**: {len(challenges.get('seeking_help_for', {}))}

## Quick View

### Current Problems
{self._format_items_list(challenges.get('current_problems', {}), 10)}

### Recurring Patterns
{self._format_items_list(challenges.get('recurring_patterns', {}), 10)}

---
See also: [Challenges](challenges.md) | [Strengths](strengths.md)
"""
        self._write_file(self.output_dir / "patterns" / "overview.md", overview)

        # Challenges
        challenges_file = f"""# Challenges

> Problems, blockers, and areas seeking help.

## Current Problems

{self._format_items_table(challenges.get('current_problems', {}))}

## Recurring Patterns

{self._format_items_table(challenges.get('recurring_patterns', {}))}

## Blockers

{self._format_items_table(challenges.get('blockers', {}))}

## Seeking Help For

{self._format_items_table(challenges.get('seeking_help_for', {}))}

---
See also: [Patterns Overview](overview.md) | [Strengths](strengths.md)
"""
        self._write_file(self.output_dir / "patterns" / "challenges.md", challenges_file)

        # Strengths (inferred from work skills, interests with high frequency)
        work = self.aggregated.get("work", {})
        strengths = f"""# Strengths

> Demonstrated abilities and positive patterns.

## Skills Demonstrated

{self._format_items_table(work.get('skills_demonstrated', {}))}

## Routines & Habits

{self._format_items_table(daily_life.get('routines', {}))}

## Living Situation

{self._format_items_table(daily_life.get('living_situation', {}))}

## Financial Mentions

{self._format_items_table(daily_life.get('finances', {}))}

---
See also: [Patterns Overview](overview.md) | [Challenges](challenges.md)
"""
        self._write_file(self.output_dir / "patterns" / "strengths.md", strengths)

    def generate_values_files(self):
        """Generate values-related markdown files"""
        values = self.aggregated.get("values", {})
        identity = self.aggregated.get("identity", {})

        # Overview
        overview = f"""# Values Overview

> Core principles, beliefs, and worldview.

## Summary

- **Explicit values**: {len(values.get('explicit_values', {}))}
- **Implicit values**: {len(values.get('implicit_values', {}))}
- **Philosophical views**: {len(values.get('philosophical', {}))}
- **Political/social views**: {len(values.get('political_social', {}))}

## Identity

### Name Mentions
{self._format_items_list(identity.get('name_mentions', {}), 10)}

### Location Mentions
{self._format_items_list(identity.get('location_mentions', {}), 10)}

### Language Indicators
{self._format_items_list(identity.get('language_indicators', {}), 10)}

### Demographic Hints
{self._format_items_list(identity.get('demographic_hints', {}), 10)}

## Explicit Values

{self._format_items_table(values.get('explicit_values', {}))}

## Implicit Values

{self._format_items_table(values.get('implicit_values', {}))}

## Philosophical Views

{self._format_items_table(values.get('philosophical', {}))}

## Political & Social Views

{self._format_items_table(values.get('political_social', {}))}

---
See also: [Goals Overview](../goals/overview.md)
"""
        self._write_file(self.output_dir / "values" / "overview.md", overview)

    def generate_statistics_file(self):
        """Generate statistics.md with detailed data breakdown"""
        content = f"""# Statistics

> Detailed data breakdown from profile extraction.

## Overview

| Metric | Value |
|--------|-------|
| Total Conversations Analyzed | {self.statistics.get('total_extractions', 0)} |
| Date Range | {self.statistics.get('date_range', {}).get('earliest', 'N/A')} to {self.statistics.get('date_range', {}).get('latest', 'N/A')} |
| Days Covered | {self.statistics.get('date_range', {}).get('total_days', 0)} |

## By Source

| Source | Count | Percentage |
|--------|-------|------------|
"""
        total = self.statistics.get("total_extractions", 1)
        for source, count in sorted(self.statistics.get("by_source", {}).items()):
            pct = (count / total) * 100
            content += f"| {source.title()} | {count} | {pct:.1f}% |\n"

        content += """

## By Biographical Richness

| Richness | Count | Percentage |
|----------|-------|------------|
"""
        for richness in ["high", "medium", "low", "minimal"]:
            count = self.statistics.get("by_richness", {}).get(richness, 0)
            pct = (count / total) * 100 if total else 0
            content += f"| {richness.title()} | {count} | {pct:.1f}% |\n"

        content += """

## Items by Category

| Category | Unique Items |
|----------|--------------|
"""
        for category, count in sorted(
            self.statistics.get("items_by_category", {}).items(),
            key=lambda x: x[1],
            reverse=True
        ):
            content += f"| {category.replace('_', ' ').title()} | {count} |\n"

        content += """

## Top 50 Most Frequent Items

| Rank | Category | Field | Item | Count |
|------|----------|-------|------|-------|
"""
        for i, item in enumerate(self.statistics.get("top_items", [])[:50], 1):
            item_escaped = item["item"].replace("|", "\\|")
            content += f"| {i} | {item['category']} | {item['field']} | {item_escaped} | {item['count']} |\n"

        content += """

---
*Statistics generated from biographical extraction data.*
"""
        self._write_file(self.output_dir / "data" / "statistics.md", content)

    def _write_file(self, path: Path, content: str):
        """Write content to file"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def generate_all(self):
        """Generate all profile files"""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Generating profile...", total=12)

            progress.update(task, description="[cyan]Creating directories...")
            self.create_directories()
            progress.advance(task)

            progress.update(task, description="[cyan]Generating INDEX.md...")
            self.generate_index()
            progress.advance(task)

            progress.update(task, description="[cyan]Generating TIMELINE.md...")
            self.generate_timeline()
            progress.advance(task)

            progress.update(task, description="[cyan]Generating work files...")
            self.generate_work_files()
            progress.advance(task)

            progress.update(task, description="[cyan]Generating health files...")
            self.generate_health_files()
            progress.advance(task)

            progress.update(task, description="[cyan]Generating relationships files...")
            self.generate_relationships_files()
            progress.advance(task)

            progress.update(task, description="[cyan]Generating interests files...")
            self.generate_interests_files()
            progress.advance(task)

            progress.update(task, description="[cyan]Generating goals files...")
            self.generate_goals_files()
            progress.advance(task)

            progress.update(task, description="[cyan]Generating patterns files...")
            self.generate_patterns_files()
            progress.advance(task)

            progress.update(task, description="[cyan]Generating values files...")
            self.generate_values_files()
            progress.advance(task)

            progress.update(task, description="[cyan]Generating statistics...")
            self.generate_statistics_file()
            progress.advance(task)

            progress.update(task, description="[green]Done!")
            progress.advance(task)

    def print_summary(self):
        """Print generation summary"""
        console.print()

        table = Table(title="Profile Generation Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Input file", str(self.input_file))
        table.add_row("Output directory", str(self.output_dir))
        table.add_row("Total extractions", str(self.statistics.get("total_extractions", 0)))
        table.add_row("Date range", f"{self.statistics.get('date_range', {}).get('earliest', 'N/A')} to {self.statistics.get('date_range', {}).get('latest', 'N/A')}")

        # Count generated files
        md_files = list(self.output_dir.rglob("*.md"))
        table.add_row("Files generated", str(len(md_files)))

        console.print(table)

        # List generated files
        console.print("\n[bold]Generated Files:[/bold]")
        for md_file in sorted(md_files):
            relative = md_file.relative_to(self.output_dir)
            console.print(f"  {relative}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate comprehensive profile from biographical extractions"
    )
    parser.add_argument(
        "--input",
        type=str,
        default=DEFAULT_INPUT,
        help=f"Input JSON file with extractions (default: {DEFAULT_INPUT})"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory for profile (default: {DEFAULT_OUTPUT_DIR})"
    )

    args = parser.parse_args()

    console.print(Panel.fit(
        "[bold blue]Profile Generator[/bold blue]\n"
        "Aggregating biographical extractions into comprehensive profile",
        border_style="blue"
    ))

    generator = ProfileGenerator(args.input, args.output_dir)

    # Load extractions
    if not generator.load_extractions():
        return

    # Aggregate data
    generator.aggregate_data()

    # Calculate statistics
    generator.calculate_statistics()

    # Generate all files
    generator.generate_all()

    # Print summary
    generator.print_summary()

    console.print(f"\n[green]Profile generated successfully![/green]")
    console.print(f"[blue]Open {args.output_dir}/INDEX.md to view your profile[/blue]")


if __name__ == "__main__":
    main()
