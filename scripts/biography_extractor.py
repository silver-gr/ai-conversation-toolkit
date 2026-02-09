#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "rich",
# ]
# requires-python = ">=3.11"
# ///

"""
Biographical Profile Extractor
==============================

Extracts biographical information from AI conversation markdown files.
Processes ChatGPT, Claude, and Gemini conversation exports to build
a comprehensive profile across all life domains.

Usage:
    # Extract from all sources
    python3 scripts/biography_extractor.py --all-sources

    # Extract from specific directory
    python3 scripts/biography_extractor.py output/chatgpt-full/conversations

    # Sample mode (for testing)
    python3 scripts/biography_extractor.py --all-sources --sample 20

    # Export extractions to JSON
    python3 scripts/biography_extractor.py --all-sources --export profile_data.json
"""

import json
import argparse
import hashlib
import sqlite3
import pickle
import subprocess
import re
import os
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich.panel import Panel

console = Console()

# Conversation directories to scan
CONVERSATION_DIRS = [
    "output/chatgpt-full/conversations",
    "output/claude-full/conversations",
    "output/gemini/conversations",
]


class BiographyExtractor:
    def __init__(self, cache_file: str = "biography_cache.db"):
        self.cache_file = cache_file
        self.cache_hits = 0
        self.cache_misses = 0
        self.extractions = []
        import threading
        self._lock = threading.Lock()
        self._init_cache()

    def _get_connection(self):
        """Get a thread-local database connection"""
        return sqlite3.connect(self.cache_file)

    def _init_cache(self):
        """Initialize SQLite cache for biographical extractions"""
        conn = self._get_connection()
        conn.execute("PRAGMA journal_mode=WAL")
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS biography_cache (
                idempotency_key TEXT PRIMARY KEY,
                file_path TEXT,
                content_hash TEXT,
                extraction_data BLOB,
                created_at TEXT,
                source TEXT,
                conversation_date TEXT
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_file_path
            ON biography_cache(file_path)
        """)

        conn.commit()

        # Report cache status
        cursor.execute("SELECT COUNT(*) FROM biography_cache")
        cache_count = cursor.fetchone()[0]
        if cache_count > 0:
            console.print(f"[blue]Using cache with {cache_count} existing extractions[/blue]")

        conn.close()

    def _generate_idempotency_key(self, file_path: str, content: str) -> str:
        """Generate unique key based on file path and content hash"""
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        key_parts = [file_path, content_hash]
        combined = "|".join(key_parts)
        return hashlib.sha256(combined.encode()).hexdigest()

    def _get_cached_extraction(self, idempotency_key: str) -> Optional[Dict]:
        """Retrieve cached extraction if exists"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT extraction_data FROM biography_cache WHERE idempotency_key = ?",
                (idempotency_key,),
            )
            result = cursor.fetchone()
            conn.close()
        except Exception as e:
            console.print(f"[yellow]Cache read failed: {e}[/yellow]")
            return None

        if result:
            with self._lock:
                self.cache_hits += 1
            return pickle.loads(result[0])

        with self._lock:
            self.cache_misses += 1
        return None

    def _save_to_cache(
        self,
        idempotency_key: str,
        file_path: str,
        content_hash: str,
        extraction_data: Dict,
        source: str,
        conversation_date: str,
    ):
        """Save extraction to cache"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO biography_cache
                (idempotency_key, file_path, content_hash, extraction_data,
                 created_at, source, conversation_date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    idempotency_key,
                    file_path,
                    content_hash,
                    pickle.dumps(extraction_data),
                    datetime.now().isoformat(),
                    source,
                    conversation_date,
                ),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            console.print(f"[yellow]Failed to save to cache: {e}[/yellow]")

    def discover_conversations(self, directories: List[str]) -> List[Tuple[str, str]]:
        """Discover all conversation markdown files"""
        conversations = []

        for directory in directories:
            dir_path = Path(directory)
            if not dir_path.exists():
                console.print(f"[yellow]Directory not found: {directory}[/yellow]")
                continue

            # Determine source from directory name
            if "chatgpt" in directory.lower():
                source = "chatgpt"
            elif "claude" in directory.lower():
                source = "claude"
            elif "gemini" in directory.lower():
                source = "gemini"
            else:
                source = "unknown"

            # Find all markdown files
            md_files = list(dir_path.glob("*.md"))

            # Exclude index files
            md_files = [f for f in md_files if not f.name.upper().startswith("INDEX")]

            for md_file in md_files:
                conversations.append((str(md_file), source))

        # Sort by filename (which includes date) for chronological processing
        conversations.sort(key=lambda x: Path(x[0]).name)

        return conversations

    def extract_date_from_filename(self, filename: str) -> str:
        """Extract date from YYYYMMDD_title.md format"""
        name = Path(filename).stem
        match = re.match(r"(\d{8})", name)
        if match:
            date_str = match.group(1)
            try:
                date = datetime.strptime(date_str, "%Y%m%d")
                return date.strftime("%Y-%m-%d")
            except ValueError:
                pass
        return "unknown"

    def extract_biographical_data(self, file_path: str, source: str) -> Dict:
        """Extract biographical information from a conversation file"""

        # Read file content
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            console.print(f"[red]Failed to read {file_path}: {e}[/red]")
            return self._empty_extraction(file_path, source)

        # Generate idempotency key
        idempotency_key = self._generate_idempotency_key(file_path, content)
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        # Check cache
        cached = self._get_cached_extraction(idempotency_key)
        if cached:
            return cached

        # Extract date from filename
        conversation_date = self.extract_date_from_filename(file_path)

        # Prepare content for analysis (truncate if needed)
        max_chars = 25000
        if len(content) > max_chars:
            # Keep beginning and end
            content = content[:12000] + "\n\n[... middle content omitted ...]\n\n" + content[-12000:]

        # Create biographical extraction prompt
        prompt = self._create_extraction_prompt(content, source, conversation_date)

        # Call Claude CLI
        extraction = self._call_claude(prompt)

        # Add metadata
        extraction["_metadata"] = {
            "file_path": file_path,
            "source": source,
            "conversation_date": conversation_date,
            "extracted_at": datetime.now().isoformat(),
            "content_length": len(content),
        }

        # Save to cache
        self._save_to_cache(
            idempotency_key,
            file_path,
            content_hash,
            extraction,
            source,
            conversation_date,
        )

        return extraction

    def _create_extraction_prompt(self, content: str, source: str, date: str) -> str:
        """Create the biographical extraction prompt"""
        return f"""You are extracting biographical information about the USER from an AI conversation.
Focus on learning about the person who is asking questions/making requests.

OUTPUT FORMAT: Valid JSON only. No additional text.

EXTRACTION SCHEMA:
{{
    // PERSONAL IDENTITY
    "identity": {{
        "name_mentions": [],        // Names used or mentioned as self
        "location_mentions": [],    // Cities, countries, regions
        "language_indicators": [],  // Languages spoken/written
        "demographic_hints": []     // Age, gender, ethnicity hints
    }},

    // PROFESSIONAL/WORK
    "work": {{
        "occupation_hints": [],     // Job titles, roles mentioned
        "projects_mentioned": [],   // Project names or descriptions
        "skills_demonstrated": [],  // Technical or professional skills shown
        "business_ventures": [],    // Companies, startups, businesses
        "work_style": []           // Remote, schedule, preferences
    }},

    // HEALTH & WELLNESS
    "health": {{
        "physical_health": [],      // Conditions, fitness, body
        "mental_health": [],        // Psychology, therapy, conditions
        "sleep_patterns": [],       // Sleep issues, schedule
        "nutrition_diet": [],       // Food, supplements, diet
        "substances": [],           // Drugs, alcohol, smoking, quitting
        "medications": []           // Prescribed or researched
    }},

    // RELATIONSHIPS
    "relationships": {{
        "romantic": [],             // Dating, partners, relationship style
        "family": [],               // Parents, siblings, children
        "social": [],               // Friends, community, loneliness
        "sexuality": []             // Orientation, interests, exploration
    }},

    // INTERESTS & HOBBIES
    "interests": {{
        "hobbies": [],              // Active hobbies, activities
        "intellectual": [],         // Philosophy, science, learning areas
        "entertainment": [],        // Music, movies, games, media
        "creative": []              // Art, writing, music production
    }},

    // GOALS & ASPIRATIONS
    "goals": {{
        "short_term": [],           // Immediate goals
        "long_term": [],            // Life goals, vision
        "dreams": [],               // Aspirations, wishes
        "fears": []                 // Worries, anxieties about future
    }},

    // CHALLENGES & STRUGGLES
    "challenges": {{
        "current_problems": [],     // Active issues being faced
        "recurring_patterns": [],   // Repeated struggles
        "blockers": [],             // What's holding them back
        "seeking_help_for": []      // Why they're asking AI
    }},

    // DAILY LIFE
    "daily_life": {{
        "routines": [],             // Daily habits, schedules
        "tools_apps": [],           // Software, apps, systems used
        "living_situation": [],     // Housing, location, lifestyle
        "finances": []              // Income, spending, money concerns
    }},

    // VALUES & BELIEFS
    "values": {{
        "explicit_values": [],      // Stated beliefs, principles
        "implicit_values": [],      // Inferred from behavior/choices
        "philosophical": [],        // Worldview, philosophy
        "political_social": []      // Political leanings, social views
    }},

    // CONVERSATION CONTEXT
    "context": {{
        "main_topic": "",           // What this conversation is about
        "emotional_tone": "",       // User's apparent mood
        "biographical_richness": "" // high/medium/low/minimal
    }}
}}

EXTRACTION RULES:
- Focus ONLY on information about the USER (the human asking questions)
- Extract both explicit statements AND reasonable inferences
- Include context that helps understand the person
- Use empty arrays [] when no relevant information found
- Be specific: "learning React" not just "programming"
- Include emotional/psychological insights when evident
- Note patterns of thinking, communication style
- Capture both struggles and strengths
- "biographical_richness": rate how much personal info is in this conversation

SOURCE: {source.upper()}
DATE: {date}

CONVERSATION:
{content}

JSON OUTPUT:"""

    def _call_claude(self, prompt: str) -> Dict:
        """Call Claude CLI for extraction"""
        max_retries = 2

        for attempt in range(max_retries):
            try:
                result = subprocess.run(
                    [
                        "claude",
                        "--print",
                        "--model",
                        "haiku",
                        "--tools",
                        "",  # Disable tools for pure extraction
                        "--output-format",
                        "json",
                    ],
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=90,
                )

                if result.returncode == 0:
                    response_text = result.stdout.strip()

                    try:
                        # Parse wrapper JSON from Claude CLI
                        wrapper = json.loads(response_text)
                        inner_result = wrapper.get("result", "")

                        # Remove markdown code blocks if present
                        if inner_result.startswith("```"):
                            # Remove ```json and ``` markers
                            inner_result = re.sub(r"^```(?:json)?\s*", "", inner_result)
                            inner_result = re.sub(r"\s*```$", "", inner_result)

                        # Parse the JSON from the result
                        extracted = json.loads(inner_result)

                    except json.JSONDecodeError:
                        # Fallback: find JSON in response
                        # Check both wrapper and inner result
                        search_text = response_text
                        if "result" in response_text:
                            try:
                                w = json.loads(response_text)
                                search_text = w.get("result", response_text)
                            except:
                                pass

                        json_start = search_text.find("{")
                        json_end = search_text.rfind("}") + 1
                        if json_start != -1 and json_end > json_start:
                            json_str = search_text[json_start:json_end]
                            # Clean up comments
                            json_str = re.sub(r"//.*$", "", json_str, flags=re.MULTILINE)
                            json_str = re.sub(r"/\*.*?\*/", "", json_str, flags=re.DOTALL)
                            extracted = json.loads(json_str)
                        else:
                            raise ValueError("No valid JSON found in response")

                    return self._clean_extraction(extracted)

                else:
                    if attempt < max_retries - 1:
                        continue
                    console.print(f"[yellow]Claude CLI error: {result.stderr}[/yellow]")

            except subprocess.TimeoutExpired:
                console.print(f"[yellow]Timeout on attempt {attempt + 1}[/yellow]")
            except json.JSONDecodeError as e:
                console.print(f"[yellow]JSON parse error: {e}[/yellow]")
            except Exception as e:
                console.print(f"[yellow]Extraction error: {e}[/yellow]")

        return self._empty_extraction_data()

    def _clean_extraction(self, extracted: Dict) -> Dict:
        """Clean and validate extracted data"""
        cleaned = {}

        # Define expected structure
        categories = {
            "identity": ["name_mentions", "location_mentions", "language_indicators", "demographic_hints"],
            "work": ["occupation_hints", "projects_mentioned", "skills_demonstrated", "business_ventures", "work_style"],
            "health": ["physical_health", "mental_health", "sleep_patterns", "nutrition_diet", "substances", "medications"],
            "relationships": ["romantic", "family", "social", "sexuality"],
            "interests": ["hobbies", "intellectual", "entertainment", "creative"],
            "goals": ["short_term", "long_term", "dreams", "fears"],
            "challenges": ["current_problems", "recurring_patterns", "blockers", "seeking_help_for"],
            "daily_life": ["routines", "tools_apps", "living_situation", "finances"],
            "values": ["explicit_values", "implicit_values", "philosophical", "political_social"],
            "context": ["main_topic", "emotional_tone", "biographical_richness"],
        }

        for category, fields in categories.items():
            if category not in cleaned:
                cleaned[category] = {}

            cat_data = extracted.get(category, {})
            if not isinstance(cat_data, dict):
                cat_data = {}

            for field in fields:
                value = cat_data.get(field, [] if field not in ["main_topic", "emotional_tone", "biographical_richness"] else "")

                if isinstance(value, list):
                    # Clean list values
                    cleaned[category][field] = [
                        str(item).strip()
                        for item in value
                        if item and str(item).strip()
                    ][:10]  # Max 10 items per field
                else:
                    cleaned[category][field] = str(value).strip() if value else ""

        return cleaned

    def _empty_extraction_data(self) -> Dict:
        """Return empty extraction structure"""
        return {
            "identity": {"name_mentions": [], "location_mentions": [], "language_indicators": [], "demographic_hints": []},
            "work": {"occupation_hints": [], "projects_mentioned": [], "skills_demonstrated": [], "business_ventures": [], "work_style": []},
            "health": {"physical_health": [], "mental_health": [], "sleep_patterns": [], "nutrition_diet": [], "substances": [], "medications": []},
            "relationships": {"romantic": [], "family": [], "social": [], "sexuality": []},
            "interests": {"hobbies": [], "intellectual": [], "entertainment": [], "creative": []},
            "goals": {"short_term": [], "long_term": [], "dreams": [], "fears": []},
            "challenges": {"current_problems": [], "recurring_patterns": [], "blockers": [], "seeking_help_for": []},
            "daily_life": {"routines": [], "tools_apps": [], "living_situation": [], "finances": []},
            "values": {"explicit_values": [], "implicit_values": [], "philosophical": [], "political_social": []},
            "context": {"main_topic": "", "emotional_tone": "", "biographical_richness": "minimal"},
        }

    def _empty_extraction(self, file_path: str, source: str) -> Dict:
        """Return empty extraction with metadata"""
        extraction = self._empty_extraction_data()
        extraction["_metadata"] = {
            "file_path": file_path,
            "source": source,
            "conversation_date": self.extract_date_from_filename(file_path),
            "extracted_at": datetime.now().isoformat(),
            "content_length": 0,
            "error": True,
        }
        return extraction

    async def process_batch_async(
        self, conversations: List[Tuple[str, str]], batch_size: int = 5
    ) -> List[Dict]:
        """Process conversations in batches with async"""
        all_extractions = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                "[cyan]Extracting biographical data...", total=len(conversations)
            )

            # Process in batches
            for i in range(0, len(conversations), batch_size):
                batch = conversations[i : i + batch_size]

                # Use ThreadPoolExecutor for parallel processing
                with ThreadPoolExecutor(max_workers=batch_size) as executor:
                    futures = [
                        executor.submit(self.extract_biographical_data, file_path, source)
                        for file_path, source in batch
                    ]

                    for future in futures:
                        try:
                            extraction = future.result(timeout=120)
                            all_extractions.append(extraction)
                        except Exception as e:
                            console.print(f"[red]Batch error: {e}[/red]")

                        progress.advance(task)

        return all_extractions

    def print_statistics(self, extractions: List[Dict]):
        """Print extraction statistics"""
        console.print()

        # Cache statistics
        table = Table(title="Extraction Statistics")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Total conversations", str(len(extractions)))
        table.add_row("Cache hits", str(self.cache_hits))
        table.add_row("Cache misses", str(self.cache_misses))

        if self.cache_hits + self.cache_misses > 0:
            hit_rate = self.cache_hits / (self.cache_hits + self.cache_misses) * 100
            table.add_row("Cache hit rate", f"{hit_rate:.1f}%")

        # Count richness levels
        richness_counts = {"high": 0, "medium": 0, "low": 0, "minimal": 0}
        for ext in extractions:
            richness = ext.get("context", {}).get("biographical_richness", "minimal").lower()
            if richness in richness_counts:
                richness_counts[richness] += 1
            else:
                richness_counts["minimal"] += 1

        table.add_row("High richness", str(richness_counts["high"]))
        table.add_row("Medium richness", str(richness_counts["medium"]))
        table.add_row("Low richness", str(richness_counts["low"]))
        table.add_row("Minimal richness", str(richness_counts["minimal"]))

        console.print(table)

        # Source breakdown
        source_counts = {}
        for ext in extractions:
            source = ext.get("_metadata", {}).get("source", "unknown")
            source_counts[source] = source_counts.get(source, 0) + 1

        console.print("\n[bold]By Source:[/bold]")
        for source, count in sorted(source_counts.items()):
            console.print(f"  {source}: {count}")

    def export_to_json(self, extractions: List[Dict], output_file: str):
        """Export all extractions to JSON file"""
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(extractions, f, indent=2, ensure_ascii=False)
        console.print(f"[green]Exported {len(extractions)} extractions to {output_file}[/green]")

    def get_all_cached_extractions(self) -> List[Dict]:
        """Retrieve all cached extractions from database"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT extraction_data, source, conversation_date FROM biography_cache ORDER BY conversation_date"
        )
        results = cursor.fetchall()
        conn.close()

        extractions = []
        for row in results:
            extraction = pickle.loads(row[0])
            extractions.append(extraction)

        return extractions


async def main():
    parser = argparse.ArgumentParser(description="Extract biographical information from AI conversations")
    parser.add_argument("directory", nargs="?", help="Directory containing conversation markdown files")
    parser.add_argument("--all-sources", action="store_true", help="Process all conversation sources")
    parser.add_argument("--sample", type=int, help="Only process N random conversations (for testing)")
    parser.add_argument("--export", type=str, help="Export extractions to JSON file")
    parser.add_argument("--cache-file", type=str, default="biography_cache.db", help="Cache database file")
    parser.add_argument("--batch-size", type=int, default=5, help="Parallel batch size")
    parser.add_argument("--export-cached", action="store_true", help="Export all cached extractions without processing")

    args = parser.parse_args()

    # Initialize extractor
    extractor = BiographyExtractor(cache_file=args.cache_file)

    # If just exporting cached data
    if args.export_cached:
        extractions = extractor.get_all_cached_extractions()
        if args.export:
            extractor.export_to_json(extractions, args.export)
        else:
            extractor.export_to_json(extractions, "output/profile/data/extractions.json")
        return

    # Determine directories to scan
    if args.all_sources:
        directories = CONVERSATION_DIRS
    elif args.directory:
        directories = [args.directory]
    else:
        console.print("[red]Please specify a directory or use --all-sources[/red]")
        return

    # Discover conversations
    console.print("[cyan]Discovering conversation files...[/cyan]")
    conversations = extractor.discover_conversations(directories)
    console.print(f"[green]Found {len(conversations)} conversation files[/green]")

    if not conversations:
        console.print("[yellow]No conversations found[/yellow]")
        return

    # Sample if requested
    if args.sample:
        import random
        conversations = random.sample(conversations, min(args.sample, len(conversations)))
        console.print(f"[blue]Sampling {len(conversations)} conversations[/blue]")

    # Process conversations
    extractions = await extractor.process_batch_async(conversations, batch_size=args.batch_size)

    # Print statistics
    extractor.print_statistics(extractions)

    # Export if requested
    if args.export:
        extractor.export_to_json(extractions, args.export)


if __name__ == "__main__":
    asyncio.run(main())
