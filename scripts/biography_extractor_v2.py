#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "rich",
# ]
# requires-python = ">=3.11"
# ///

"""
Biographical Profile Extractor v2 - Multi-Model Support
========================================================

Supports Claude, Gemini, and Codex (OpenAI) backends to distribute
load and avoid exhausting any single provider's usage limits.

Usage:
    # Use Claude (default)
    python3 scripts/biography_extractor_v2.py --all-sources --provider claude

    # Use Gemini
    python3 scripts/biography_extractor_v2.py --all-sources --provider gemini

    # Use Codex (OpenAI)
    python3 scripts/biography_extractor_v2.py --all-sources --provider codex

    # Specify model within provider
    python3 scripts/biography_extractor_v2.py --all-sources --provider gemini --model gemini-2.0-flash
"""

import json
import argparse
import hashlib
import sqlite3
import pickle
import subprocess
import re
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

console = Console()

# Conversation directories to scan
CONVERSATION_DIRS = [
    "output/chatgpt-full/conversations",
    "output/claude-full/conversations",
    "output/gemini/conversations",
]

# Provider configurations
PROVIDERS = {
    "claude": {
        "cmd": ["claude", "--print", "--model", "{model}", "--tools", "", "--output-format", "json"],
        "default_model": "haiku",
        "parse_response": "claude",
    },
    "gemini": {
        "cmd": ["gemini", "-o", "json", "-m", "{model}"],
        "default_model": "gemini-2.5-flash",
        "parse_response": "gemini",
    },
    "codex": {
        "cmd": ["codex", "exec", "-m", "{model}"],
        "default_model": "gpt-4.1-mini",  # Use --model to override with gpt-5.1-codex-max
        "parse_response": "codex",
    },
}


class BiographyExtractorV2:
    def __init__(self, cache_file: str = "biography_cache.db", provider: str = "claude", model: str = None):
        self.cache_file = cache_file
        self.cache_hits = 0
        self.cache_misses = 0
        self.provider = provider
        self.provider_config = PROVIDERS.get(provider, PROVIDERS["claude"])
        self.model = model or self.provider_config["default_model"]
        import threading
        self._lock = threading.Lock()
        self._init_cache()

        console.print(f"[cyan]Using provider: {provider}" + (f" (model: {self.model})" if self.model else "") + "[/cyan]")

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
                conversation_date TEXT,
                provider TEXT
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_file_path
            ON biography_cache(file_path)
        """)

        conn.commit()

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
                 created_at, source, conversation_date, provider)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    idempotency_key,
                    file_path,
                    content_hash,
                    pickle.dumps(extraction_data),
                    datetime.now().isoformat(),
                    source,
                    conversation_date,
                    self.provider,
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

            if "chatgpt" in directory.lower():
                source = "chatgpt"
            elif "claude" in directory.lower():
                source = "claude"
            elif "gemini" in directory.lower():
                source = "gemini"
            else:
                source = "unknown"

            md_files = list(dir_path.glob("*.md"))
            md_files = [f for f in md_files if not f.name.upper().startswith("INDEX")]

            for md_file in md_files:
                conversations.append((str(md_file), source))

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

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            console.print(f"[red]Failed to read {file_path}: {e}[/red]")
            return self._empty_extraction(file_path, source)

        idempotency_key = self._generate_idempotency_key(file_path, content)
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        cached = self._get_cached_extraction(idempotency_key)
        if cached:
            return cached

        conversation_date = self.extract_date_from_filename(file_path)

        max_chars = 25000
        if len(content) > max_chars:
            content = content[:12000] + "\n\n[... middle content omitted ...]\n\n" + content[-12000:]

        prompt = self._create_extraction_prompt(content, source, conversation_date)
        extraction = self._call_provider(prompt)

        extraction["_metadata"] = {
            "file_path": file_path,
            "source": source,
            "conversation_date": conversation_date,
            "extracted_at": datetime.now().isoformat(),
            "content_length": len(content),
            "provider": self.provider,
        }

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

OUTPUT FORMAT: Valid JSON only. No markdown, no explanation, no code blocks. Just raw JSON.

EXTRACTION SCHEMA:
{{
    "identity": {{
        "name_mentions": [],
        "location_mentions": [],
        "language_indicators": [],
        "demographic_hints": []
    }},
    "work": {{
        "occupation_hints": [],
        "projects_mentioned": [],
        "skills_demonstrated": [],
        "business_ventures": [],
        "work_style": []
    }},
    "health": {{
        "physical_health": [],
        "mental_health": [],
        "sleep_patterns": [],
        "nutrition_diet": [],
        "substances": [],
        "medications": []
    }},
    "relationships": {{
        "romantic": [],
        "family": [],
        "social": [],
        "sexuality": []
    }},
    "interests": {{
        "hobbies": [],
        "intellectual": [],
        "entertainment": [],
        "creative": []
    }},
    "goals": {{
        "short_term": [],
        "long_term": [],
        "dreams": [],
        "fears": []
    }},
    "challenges": {{
        "current_problems": [],
        "recurring_patterns": [],
        "blockers": [],
        "seeking_help_for": []
    }},
    "daily_life": {{
        "routines": [],
        "tools_apps": [],
        "living_situation": [],
        "finances": []
    }},
    "values": {{
        "explicit_values": [],
        "implicit_values": [],
        "philosophical": [],
        "political_social": []
    }},
    "context": {{
        "main_topic": "",
        "emotional_tone": "",
        "biographical_richness": ""
    }}
}}

RULES:
- Focus ONLY on information about the USER (the human asking questions)
- Extract both explicit statements AND reasonable inferences
- Use empty arrays [] when no relevant information found
- "biographical_richness": rate as "high", "medium", "low", or "minimal"

SOURCE: {source.upper()}
DATE: {date}

CONVERSATION:
{content}

JSON OUTPUT:"""

    def _call_provider(self, prompt: str) -> Dict:
        """Call the configured provider for extraction"""
        max_retries = 2

        for attempt in range(max_retries):
            try:
                if self.provider == "claude":
                    return self._call_claude(prompt)
                elif self.provider == "gemini":
                    return self._call_gemini(prompt)
                elif self.provider == "codex":
                    return self._call_codex(prompt)
                else:
                    console.print(f"[red]Unknown provider: {self.provider}[/red]")
                    return self._empty_extraction_data()
            except Exception as e:
                if attempt < max_retries - 1:
                    console.print(f"[yellow]Retry {attempt + 1}: {e}[/yellow]")
                    continue
                console.print(f"[yellow]Extraction error: {e}[/yellow]")

        return self._empty_extraction_data()

    def _call_claude(self, prompt: str) -> Dict:
        """Call Claude CLI"""
        cmd = ["claude", "--print", "--model", self.model or "haiku", "--tools", "", "--output-format", "json"]

        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=90,
        )

        if result.returncode == 0:
            response_text = result.stdout.strip()
            try:
                wrapper = json.loads(response_text)
                inner_result = wrapper.get("result", "")

                if inner_result.startswith("```"):
                    inner_result = re.sub(r"^```(?:json)?\s*", "", inner_result)
                    inner_result = re.sub(r"\s*```$", "", inner_result)

                return self._clean_extraction(json.loads(inner_result))
            except json.JSONDecodeError:
                return self._parse_json_from_text(response_text)

        raise ValueError(f"Claude CLI error: {result.stderr}")

    def _call_gemini(self, prompt: str) -> Dict:
        """Call Gemini CLI"""
        cmd = ["gemini", "-o", "json"]
        if self.model:
            cmd.extend(["-m", self.model])

        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode == 0:
            response_text = result.stdout.strip()
            try:
                # Gemini JSON output format
                wrapper = json.loads(response_text)
                # Extract the actual response - may be in different fields
                if isinstance(wrapper, dict):
                    content = wrapper.get("response", wrapper.get("result", wrapper.get("text", "")))
                    if isinstance(content, str):
                        return self._parse_json_from_text(content)
                    elif isinstance(content, dict):
                        return self._clean_extraction(content)
                return self._parse_json_from_text(response_text)
            except json.JSONDecodeError:
                return self._parse_json_from_text(response_text)

        raise ValueError(f"Gemini CLI error: {result.stderr}")

    def _call_codex(self, prompt: str) -> Dict:
        """Call Codex CLI"""
        cmd = ["codex", "exec"]
        if self.model:
            cmd.extend(["-m", self.model])

        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode == 0:
            response_text = result.stdout.strip()
            return self._parse_json_from_text(response_text)

        raise ValueError(f"Codex CLI error: {result.stderr}")

    def _parse_json_from_text(self, text: str) -> Dict:
        """Extract JSON from text response"""
        # Remove markdown code blocks
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

        # Try direct parse
        try:
            return self._clean_extraction(json.loads(text))
        except json.JSONDecodeError:
            pass

        # Find JSON in text
        json_start = text.find("{")
        json_end = text.rfind("}") + 1
        if json_start != -1 and json_end > json_start:
            json_str = text[json_start:json_end]
            json_str = re.sub(r"//.*$", "", json_str, flags=re.MULTILINE)
            json_str = re.sub(r"/\*.*?\*/", "", json_str, flags=re.DOTALL)
            try:
                return self._clean_extraction(json.loads(json_str))
            except json.JSONDecodeError:
                pass

        raise ValueError("No valid JSON found in response")

    def _clean_extraction(self, extracted: Dict) -> Dict:
        """Clean and validate extracted data"""
        cleaned = {}

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
                    cleaned[category][field] = [
                        str(item).strip()
                        for item in value
                        if item and str(item).strip()
                    ][:10]
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
            "provider": self.provider,
        }
        return extraction

    async def process_batch_async(
        self, conversations: List[Tuple[str, str]], batch_size: int = 3
    ) -> List[Dict]:
        """Process conversations in batches"""
        all_extractions = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"[cyan]Extracting via {self.provider}...", total=len(conversations)
            )

            for i in range(0, len(conversations), batch_size):
                batch = conversations[i : i + batch_size]

                with ThreadPoolExecutor(max_workers=batch_size) as executor:
                    futures = [
                        executor.submit(self.extract_biographical_data, file_path, source)
                        for file_path, source in batch
                    ]

                    for future in futures:
                        try:
                            extraction = future.result(timeout=180)
                            all_extractions.append(extraction)
                        except Exception as e:
                            console.print(f"[red]Batch error: {e}[/red]")

                        progress.advance(task)

        return all_extractions

    def print_statistics(self, extractions: List[Dict]):
        """Print extraction statistics"""
        console.print()

        table = Table(title=f"Extraction Statistics ({self.provider})")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Total conversations", str(len(extractions)))
        table.add_row("Cache hits", str(self.cache_hits))
        table.add_row("Cache misses", str(self.cache_misses))

        if self.cache_hits + self.cache_misses > 0:
            hit_rate = self.cache_hits / (self.cache_hits + self.cache_misses) * 100
            table.add_row("Cache hit rate", f"{hit_rate:.1f}%")

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
            "SELECT extraction_data FROM biography_cache ORDER BY conversation_date"
        )
        results = cursor.fetchall()
        conn.close()

        extractions = []
        for row in results:
            extraction = pickle.loads(row[0])
            extractions.append(extraction)

        return extractions


async def main():
    parser = argparse.ArgumentParser(description="Extract biographical information using multiple AI providers")
    parser.add_argument("directory", nargs="?", help="Directory containing conversation markdown files")
    parser.add_argument("--all-sources", action="store_true", help="Process all conversation sources")
    parser.add_argument("--sample", type=int, help="Only process N random conversations")
    parser.add_argument("--export", type=str, help="Export extractions to JSON file")
    parser.add_argument("--cache-file", type=str, default="biography_cache.db", help="Cache database file")
    parser.add_argument("--batch-size", type=int, default=3, help="Parallel batch size")
    parser.add_argument("--export-cached", action="store_true", help="Export all cached extractions")
    parser.add_argument("--provider", type=str, default="claude", choices=["claude", "gemini", "codex"],
                       help="AI provider to use (claude, gemini, codex)")
    parser.add_argument("--model", type=str, help="Model to use (provider-specific)")

    args = parser.parse_args()

    extractor = BiographyExtractorV2(
        cache_file=args.cache_file,
        provider=args.provider,
        model=args.model
    )

    if args.export_cached:
        extractions = extractor.get_all_cached_extractions()
        output_file = args.export or "output/profile/data/extractions.json"
        extractor.export_to_json(extractions, output_file)
        return

    if args.all_sources:
        directories = CONVERSATION_DIRS
    elif args.directory:
        directories = [args.directory]
    else:
        console.print("[red]Please specify a directory or use --all-sources[/red]")
        return

    console.print("[cyan]Discovering conversation files...[/cyan]")
    conversations = extractor.discover_conversations(directories)
    console.print(f"[green]Found {len(conversations)} conversation files[/green]")

    if not conversations:
        console.print("[yellow]No conversations found[/yellow]")
        return

    if args.sample:
        import random
        conversations = random.sample(conversations, min(args.sample, len(conversations)))
        console.print(f"[blue]Sampling {len(conversations)} conversations[/blue]")

    extractions = await extractor.process_batch_async(conversations, batch_size=args.batch_size)
    extractor.print_statistics(extractions)

    if args.export:
        extractor.export_to_json(extractions, args.export)


if __name__ == "__main__":
    asyncio.run(main())
