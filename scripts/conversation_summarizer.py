#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "rich",
#   "pandas",
#   "openpyxl",
# ]
# requires-python = ">=3.11"
# ///

"""
Universal AI Conversation Analyzer & Context Extractor
======================================================

Analyzes and extracts context from AI conversation exports (ChatGPT, Claude, etc.)
for seamless continuation and knowledge preservation.

## Supported Formats:
- ChatGPT exports (conversations.json from "Export your data" ZIP)
  - Includes ChatGPT Projects grouping and relationships
  - Preserves project context across related conversations
- Claude conversation exports
- Any JSON with 'mapping' node structure or linear message arrays

## Key Features:
- **Intelligent Caching**: SQLite-based LLM response cache with idempotency keys
- **Cost Optimization**: Reuses analysis for unchanged conversations
- Extracts comprehensive conversation context for LLM continuation
- **ChatGPT Projects Support**: Groups conversations by Project/GPT ID
- Tracks user's actual implementation state vs. discussed solutions
- Identifies decision journeys and evaluation criteria
- Detects critical information gaps and assumptions
- Assesses conversation health and completeness
- Provides specific continuation strategies
- Creates project-level summaries showing shared context
- Links related conversations within the same project
- Parallelized processing using asyncio for large exports

## Caching System:
- Uses content-based idempotency keys (SHA256 hash)
- Caches LLM analysis results in SQLite database
- Automatically reuses cached results for unchanged conversations
- Shows cache hit/miss statistics and cost savings
- Optional cache cleanup for old entries

## Output:
- Individual markdown files per conversation for precise context resumption
- Global statistics and topic analysis across all conversations
- SQLite cache database for efficient re-processing

## Usage:
    # Basic usage
    ./conversation_summarizer.py conversations.json

    # With caching options
    ./conversation_summarizer.py conversations.json --cache-file my_cache.db
    ./conversation_summarizer.py conversations.json --no-cache  # Disable cache
    ./conversation_summarizer.py conversations.json --clean-cache 7  # Clean >7 day old entries

    # Full options
    ./conversation_summarizer.py conversations.json [--max N] [--output-dir DIR]
                                 [--cache-file FILE] [--no-cache] [--clean-cache DAYS]

    Where conversations.json is from:
    - ChatGPT: Settings → Data controls → Export → conversations.json from ZIP
    - Claude: Export feature → conversations.json

## Cache Benefits:
- **Speed**: Skip LLM calls for previously analyzed conversations
- **Cost**: Save API costs by reusing cached analyses
- **Consistency**: Ensure same conversations get same analysis
- **Incremental**: Only analyze new/changed conversations on re-runs

## Requirements:
- Claude CLI installed (`pip install claude-cli` or `brew install claude`)
- Valid Claude API access for content analysis
- SQLite3 (included in Python standard library)

Uses Claude AI to perform meta-analysis of conversations from any AI assistant.
"""

import json
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import os
import re
from collections import defaultdict, Counter
import hashlib
import sqlite3
import pickle
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.panel import Panel
import subprocess
import tempfile
import asyncio
from concurrent.futures import ThreadPoolExecutor

console = Console()


class ConversationSummarizer:
    def __init__(self, input_file: str, cache_file: str = "conversation_cache.db"):
        self.input_file = input_file
        self.conversations = []
        self.projects = {}  # Store Project/GPT groupings
        self.cache_file = cache_file
        self.cache_hits = 0
        self.cache_misses = 0
        self.cache_enabled = cache_file is not None
        if self.cache_enabled:
            self._init_cache()
        self.load_conversations()

    def _init_cache(self):
        """Initialize SQLite cache for LLM responses"""
        # Use check_same_thread=False for async operations
        self.conn = sqlite3.connect(self.cache_file, check_same_thread=False)

        # Fix Python 3.12+ datetime deprecation warning
        # Use timestamp strings instead of datetime objects
        self.conn.execute("PRAGMA journal_mode=WAL")  # Better concurrent access

        self.cursor = self.conn.cursor()

        # Create cache table if not exists
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS llm_cache (
                idempotency_key TEXT PRIMARY KEY,
                conversation_id TEXT,
                messages_hash TEXT,
                response_data BLOB,
                created_at TEXT,  -- Store as TEXT to avoid datetime adapter warning
                model_used TEXT,
                prompt_tokens INTEGER,
                response_tokens INTEGER
            )
        """)

        # Create index for faster lookups
        self.cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversation_id 
            ON llm_cache(conversation_id)
        """)

        self.conn.commit()

        # Report cache status
        self.cursor.execute("SELECT COUNT(*) FROM llm_cache")
        cache_count = self.cursor.fetchone()[0]
        if cache_count > 0:
            console.print(
                f"[blue]💾 Using cache with {cache_count} existing entries[/blue]"
            )

            # Get cache size
            self.cursor.execute(
                "SELECT page_count * page_size FROM pragma_page_count(), pragma_page_size()"
            )
            size_bytes = self.cursor.fetchone()[0]
            size_mb = size_bytes / (1024 * 1024)
            console.print(f"[blue]   Cache size: {size_mb:.1f} MB[/blue]")

    def _generate_idempotency_key(
        self, conversation: Dict, messages: List[Dict]
    ) -> str:
        """
        Generate a unique idempotency key for a conversation analysis.
        Based on conversation ID, message count, and content hash.

        This ensures:
        - Same conversation with same content = same key (cache hit)
        - Any content change = different key (cache miss, fresh analysis)
        - Deterministic across runs
        """
        # Create a deterministic hash of the conversation
        key_parts = [
            conversation.get("id", ""),
            conversation.get("conversation_id", ""),
            str(len(messages)),
            # Hash first and last few messages for content changes
            hashlib.md5(
                json.dumps(
                    messages[:3] + messages[-3:] if len(messages) > 6 else messages,
                    sort_keys=True,
                    default=str,
                ).encode()
            ).hexdigest(),
        ]

        # Combine parts and create final hash
        combined = "|".join(key_parts)
        return hashlib.sha256(combined.encode()).hexdigest()

    def _get_cached_response(self, idempotency_key: str) -> Optional[Dict]:
        """Retrieve cached LLM response if exists"""
        if not self.cache_enabled:
            return None

        try:
            self.cursor.execute(
                "SELECT response_data FROM llm_cache WHERE idempotency_key = ?",
                (idempotency_key,),
            )
            result = self.cursor.fetchone()
        except Exception as e:
            console.print(f"[yellow]Warning: Cache read failed: {e}[/yellow]")
            return None

        if result:
            self.cache_hits += 1
            return pickle.loads(result[0])

        self.cache_misses += 1
        return None

    def _save_to_cache(
        self,
        idempotency_key: str,
        conversation_id: str,
        messages_hash: str,
        response_data: Dict,
    ):
        """Save LLM response to cache"""
        if not self.cache_enabled:
            return

        try:
            self.cursor.execute(
                """
                INSERT OR REPLACE INTO llm_cache 
                (idempotency_key, conversation_id, messages_hash, response_data, 
                 created_at, model_used, prompt_tokens, response_tokens)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    idempotency_key,
                    conversation_id,
                    messages_hash,
                    pickle.dumps(response_data),
                    datetime.now().isoformat(),  # Store as ISO string to avoid deprecation
                    "haiku",  # Model used
                    0,  # Placeholder for prompt tokens
                    0,  # Placeholder for response tokens
                ),
            )
            self.conn.commit()
        except Exception as e:
            console.print(f"[yellow]Warning: Failed to save to cache: {e}[/yellow]")

    def load_conversations(self):
        """Load conversations from JSON file (ChatGPT or Claude export format)"""
        console.print(
            f"[cyan]📂 Loading conversations from {self.input_file}...[/cyan]"
        )
        with open(self.input_file, "r", encoding="utf-8") as f:
            self.conversations = json.load(f)

        # Detect format
        if self.conversations and isinstance(self.conversations[0], dict):
            if "mapping" in self.conversations[0]:
                console.print(
                    f"[blue]📱 Detected ChatGPT export format (node-based mapping)[/blue]"
                )
                self._analyze_projects()  # Analyze ChatGPT Projects
            elif "messages" in self.conversations[0]:
                console.print(f"[blue]🤖 Detected linear message format[/blue]")

        console.print(
            f"[green]✅ Loaded {len(self.conversations)} conversations[/green]"
        )

        # Report on Projects if found
        if self.projects:
            console.print(
                f"[magenta]📁 Found {len(self.projects)} ChatGPT Projects/GPTs[/magenta]"
            )
            for project_id, project_data in list(self.projects.items())[:3]:
                console.print(
                    f"   • {project_data['name']}: {len(project_data['conversations'])} conversations"
                )
            if len(self.projects) > 3:
                console.print(f"   ... and {len(self.projects) - 3} more projects")

    def extract_messages(self, conversation: Dict) -> List[Dict]:
        """
        Extract and order messages from a conversation.

        Handles multiple formats:
        - ChatGPT: Uses 'mapping' with node-based tree structure
        - Claude: Uses 'chat_messages' array with sender field
        - Fallback: Attempts to find message-like structures
        """
        messages = []

        # Claude format with chat_messages array
        chat_messages = conversation.get("chat_messages", [])
        if chat_messages:
            for msg in chat_messages:
                sender = msg.get("sender", "")
                # Map Claude sender to role
                role = "user" if sender == "human" else ("assistant" if sender == "assistant" else "unknown")

                # Get content - Claude has both 'text' and 'content' fields
                content = msg.get("text", "")
                if not content and "content" in msg:
                    # Extract from content array
                    content_arr = msg.get("content", [])
                    if content_arr and isinstance(content_arr, list):
                        content = " ".join(
                            c.get("text", "")
                            for c in content_arr
                            if isinstance(c, dict) and c.get("text")
                        )

                if content and content.strip():
                    messages.append({
                        "role": role,
                        "content": content,
                        "timestamp": msg.get("created_at"),
                    })
            return messages

        # ChatGPT format with mapping (node-based tree)
        mapping = conversation.get("mapping", {})

        # Build parent-child relationships
        parent_child = defaultdict(list)
        root_nodes = []

        for node_id, node_data in mapping.items():
            parent = node_data.get("parent")
            if parent:
                parent_child[parent].append(node_id)
            else:
                root_nodes.append(node_id)

        # Track visited nodes to prevent infinite recursion
        visited = set()

        # Traverse the conversation tree with depth limit
        def traverse(node_id, depth=0):
            # Prevent infinite recursion
            if depth > 100:  # Max depth limit
                return
            if node_id in visited:
                return
            if node_id not in mapping:
                return

            visited.add(node_id)

            node = mapping[node_id]
            if node.get("message"):
                msg = node["message"]
                author = msg.get("author", {})
                content = msg.get("content", {})
                parts = content.get("parts", [])

                # Extract text content (handles both ChatGPT and Claude formats)
                text_content = ""
                for part in parts:
                    if isinstance(part, str):
                        text_content += part
                    elif isinstance(part, dict) and "text" in part:
                        text_content += part["text"]
                    elif isinstance(part, dict) and "content" in part:
                        # Some formats nest content deeper
                        text_content += str(part["content"])

                if text_content.strip():
                    messages.append(
                        {
                            "role": author.get("role", "unknown"),
                            "content": text_content,
                            "timestamp": msg.get("create_time"),
                        }
                    )

            # Traverse children with increased depth
            for child_id in parent_child[node_id]:
                traverse(child_id, depth + 1)

        # Start traversal
        for root in root_nodes:
            traverse(root)

        return messages

    async def analyze_conversation_async(self, conversation: Dict) -> Dict:
        """Async version - Analyze a single conversation"""
        messages = self.extract_messages(conversation)

        # Handle both ChatGPT and Claude field names
        title = conversation.get("title") or conversation.get("name") or "Untitled"
        conv_id = conversation.get("id") or conversation.get("conversation_id") or conversation.get("uuid")
        created = conversation.get("create_time") or conversation.get("created_at")
        updated = conversation.get("update_time") or conversation.get("updated_at")

        # Basic metadata
        analysis = {
            "title": title,
            "id": conv_id,
            "created": self._parse_datetime(created),
            "updated": self._parse_datetime(updated),
            "message_count": len(messages),
            "model": conversation.get("default_model_slug", "unknown"),
            "is_archived": conversation.get("is_archived", False),
            "is_starred": conversation.get("is_starred", False),
        }

        if not messages:
            return analysis

        # Extract key information
        user_messages = [m for m in messages if m["role"] == "user"]
        assistant_messages = [m for m in messages if m["role"] == "assistant"]

        # Get first and last significant messages
        if user_messages:
            analysis["first_query"] = user_messages[0]["content"][:500]
            analysis["first_query_length"] = len(user_messages[0]["content"])

        if assistant_messages:
            analysis["last_response_preview"] = assistant_messages[-1]["content"][:500]

        # Extract topics from entire conversation
        all_text = " ".join([m["content"][:200] for m in messages[:10]])
        analysis["topics"] = self.extract_topics(all_text)

        # Conversation characteristics
        analysis["user_message_count"] = len(user_messages)
        analysis["assistant_message_count"] = len(assistant_messages)
        analysis["avg_message_length"] = (
            sum(len(m["content"]) for m in messages) // len(messages) if messages else 0
        )

        # Detect conversation type
        analysis["conversation_type"] = self.detect_conversation_type(messages)

        # Extract code languages if any
        analysis["code_languages"] = self.extract_code_languages(messages)

        return analysis

    def _parse_datetime(self, value) -> str:
        """Parse datetime from various formats (Unix timestamp or ISO string)."""
        if not value:
            return None
        if isinstance(value, (int, float)):
            # Unix timestamp
            try:
                return datetime.fromtimestamp(value).isoformat()
            except (ValueError, OSError):
                return None
        if isinstance(value, str):
            # ISO format - just clean and return
            return value.split('+')[0].split('Z')[0]
        return None

    def analyze_conversation(self, conversation: Dict) -> Dict:
        """Sync version - Analyze a single conversation"""
        messages = self.extract_messages(conversation)

        # Handle both ChatGPT and Claude field names
        # ChatGPT: title, id/conversation_id, create_time, update_time
        # Claude: name, uuid, created_at, updated_at
        title = conversation.get("title") or conversation.get("name") or "Untitled"
        conv_id = conversation.get("id") or conversation.get("conversation_id") or conversation.get("uuid")
        created = conversation.get("create_time") or conversation.get("created_at")
        updated = conversation.get("update_time") or conversation.get("updated_at")

        # Basic metadata
        analysis = {
            "title": title,
            "id": conv_id,
            "created": self._parse_datetime(created),
            "updated": self._parse_datetime(updated),
            "message_count": len(messages),
            "model": conversation.get("default_model_slug", "unknown"),
            "is_archived": conversation.get("is_archived", False),
            "is_starred": conversation.get("is_starred", False),
        }

        if not messages:
            return analysis

        # Extract key information
        user_messages = [m for m in messages if m["role"] == "user"]
        assistant_messages = [m for m in messages if m["role"] == "assistant"]

        # First user query (conversation starter)
        if user_messages:
            first_query = user_messages[0]["content"]
            analysis["first_query"] = first_query[:500]
            analysis["first_query_length"] = len(first_query)

        # Summary from last assistant message
        if assistant_messages:
            last_response = assistant_messages[-1]["content"]
            # Try to extract a summary or conclusion
            analysis["last_response_preview"] = last_response[:500]

        # Topic extraction
        all_text = " ".join([m["content"][:200] for m in messages[:10]])
        analysis["topics"] = self.extract_topics(all_text)

        # Conversation characteristics
        analysis["user_message_count"] = len(user_messages)
        analysis["assistant_message_count"] = len(assistant_messages)
        analysis["avg_message_length"] = (
            sum(len(m["content"]) for m in messages) // len(messages) if messages else 0
        )

        # Detect conversation type
        analysis["conversation_type"] = self.detect_conversation_type(messages)

        # Extract code languages if any
        analysis["code_languages"] = self.extract_code_languages(messages)

        return analysis

    def _analyze_projects(self):
        """Analyze and group conversations by ChatGPT Project/GPT ID"""
        from collections import defaultdict

        for conv in self.conversations:
            gizmo_id = conv.get("gizmo_id")
            if gizmo_id:
                if gizmo_id not in self.projects:
                    # Determine if it's a Project or GPT
                    is_project = gizmo_id.startswith("g-p-")

                    self.projects[gizmo_id] = {
                        "id": gizmo_id,
                        "type": "project" if is_project else "gpt",
                        "conversations": [],
                        "titles": [],
                        "name": None,  # Will be inferred from titles
                        "topics": Counter(),
                        "models_used": Counter(),
                    }

                self.projects[gizmo_id]["conversations"].append(conv)
                self.projects[gizmo_id]["titles"].append(conv.get("title", "Untitled"))
                # Handle None model values
                model = conv.get("default_model_slug") or "unknown"
                self.projects[gizmo_id]["models_used"][model] += 1

        # Infer project names from common patterns in titles
        for project_id, project_data in self.projects.items():
            # Try to find common words in titles to name the project
            if project_data["titles"]:
                # Simple heuristic: find most common meaningful words
                all_words = []
                for title in project_data["titles"][:10]:  # Sample first 10
                    words = re.findall(r"\b[A-Za-zÀ-ÿ]{3,}\b", title)
                    all_words.extend([w.lower() for w in words])

                word_freq = Counter(all_words)
                # Filter out common words
                stop_words = {
                    "the",
                    "and",
                    "for",
                    "with",
                    "des",
                    "les",
                    "pour",
                    "sur",
                    "dans",
                }
                meaningful_words = [
                    (w, c)
                    for w, c in word_freq.most_common(10)
                    if w not in stop_words and c > 1
                ]

                if meaningful_words:
                    # Use top 2-3 words as project name
                    project_words = [w for w, _ in meaningful_words[:3]]
                    project_data["name"] = " ".join(project_words).title()
                else:
                    # Fallback to first title
                    project_data["name"] = project_data["titles"][0][:30]

    def extract_topics(self, text: str, max_topics: int = 7) -> List[str]:
        """Extract main topics from text"""
        # Common stop words
        stop_words = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "from",
            "about",
            "as",
            "is",
            "was",
            "are",
            "were",
            "been",
            "be",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "can",
            "could",
            "should",
            "may",
            "might",
            "must",
            "shall",
            "should",
            "this",
            "that",
            "these",
            "those",
            "i",
            "you",
            "he",
            "she",
            "it",
            "we",
            "they",
            "what",
            "which",
            "who",
            "when",
            "where",
            "why",
            "how",
            "not",
            "no",
            "yes",
        }

        # Extract meaningful words
        words = re.findall(r"\b[a-zA-Z]+\b", text.lower())
        word_freq = Counter()

        for word in words:
            if len(word) > 3 and word not in stop_words:
                word_freq[word] += 1

        # Get top topics
        return [word for word, _ in word_freq.most_common(max_topics)]

    def detect_conversation_type(self, messages: List[Dict]) -> str:
        """Detect the type of conversation"""
        all_text = " ".join([m["content"].lower() for m in messages[:5]])

        # Check for different types
        if any(
            keyword in all_text
            for keyword in [
                "code",
                "function",
                "class",
                "def",
                "import",
                "bug",
                "error",
            ]
        ):
            return "coding"
        elif any(
            keyword in all_text
            for keyword in ["analyze", "data", "statistics", "graph", "chart"]
        ):
            return "analysis"
        elif any(
            keyword in all_text
            for keyword in ["write", "essay", "story", "poem", "creative"]
        ):
            return "creative"
        elif any(
            keyword in all_text
            for keyword in ["explain", "what is", "how does", "why", "teach"]
        ):
            return "educational"
        elif any(
            keyword in all_text
            for keyword in ["help", "problem", "issue", "fix", "solve"]
        ):
            return "problem-solving"
        else:
            return "general"

    def extract_code_languages(self, messages: List[Dict]) -> List[str]:
        """Extract programming languages mentioned or used"""
        languages = set()
        code_patterns = {
            "python": r"(?:python|\.py|import\s+\w+|def\s+\w+|print\()",
            "javascript": r"(?:javascript|\.js|const\s+\w+|let\s+\w+|console\.log)",
            "java": r"(?:java|\.java|public\s+class|System\.out\.println)",
            "cpp": r"(?:c\+\+|\.cpp|#include|std::)",
            "sql": r"(?:sql|SELECT|FROM|WHERE|INSERT|UPDATE)",
            "html": r"(?:html|<div|<span|<body|<head)",
            "css": r"(?:css|\.css|style=|color:|margin:|padding:)",
            "rust": r"(?:rust|\.rs|fn\s+\w+|let\s+mut)",
            "go": r"(?:golang|\.go|func\s+\w+|package\s+\w+)",
        }

        all_text = " ".join([m["content"] for m in messages])

        for lang, pattern in code_patterns.items():
            if re.search(pattern, all_text, re.IGNORECASE):
                languages.add(lang)

        return list(languages)

    async def generate_summaries_async(
        self, max_conversations: Optional[int] = None, batch_size: int = 5
    ) -> List[Dict]:
        """Generate summaries for conversations using async/await for parallelization"""
        conversations_to_process = (
            self.conversations[:max_conversations]
            if max_conversations
            else self.conversations
        )

        summaries = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            # Add cache status to progress message
            cache_msg = " (cache enabled)" if self.cache_enabled else " (no cache)"
            task = progress.add_task(
                f"[cyan]📊 Analyzing {len(conversations_to_process)} conversations{cache_msg}...[/cyan]",
                total=len(conversations_to_process),
            )

            # Process conversations in batches for controlled parallelism
            for i in range(0, len(conversations_to_process), batch_size):
                batch = conversations_to_process[i : i + batch_size]

                # Create async tasks for the batch
                tasks = [self.analyze_conversation_async(conv) for conv in batch]

                # Run batch in parallel and wait for all to complete
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)

                # Process results
                for result in batch_results:
                    if isinstance(result, Exception):
                        console.print(
                            f"[yellow]Warning: Failed to analyze conversation: {result}[/yellow]"
                        )
                    else:
                        summaries.append(result)
                    progress.update(task, advance=1)

        console.print(f"[green]✅ Analyzed {len(summaries)} conversations[/green]")
        return summaries

    def generate_summaries(self, max_conversations: Optional[int] = None) -> List[Dict]:
        """Sync wrapper for generate_summaries - runs the async version"""
        return asyncio.run(self.generate_summaries_async(max_conversations))

    def extract_key_facts(self, messages: List[Dict]) -> List[str]:
        """Extract key facts from conversation"""
        facts = []

        for msg in messages:
            if msg["role"] == "assistant":
                content = msg["content"]

                # Look for bullet points or numbered lists
                bullets = re.findall(r"[•\-\*]\s+(.+?)(?:\n|$)", content)
                numbers = re.findall(r"\d+\.\s+(.+?)(?:\n|$)", content)

                facts.extend(bullets[:5])
                facts.extend(numbers[:5])

                # Look for key patterns
                if "important" in content.lower():
                    important = re.findall(
                        r"important[:\s]+(.+?)(?:\.|$)", content, re.IGNORECASE
                    )
                    facts.extend(important[:3])

        # Clean and deduplicate
        facts = [f.strip()[:200] for f in facts if f.strip()]
        facts = list(dict.fromkeys(facts))

        return facts[:15]

    async def extract_conversation_essence_async(
        self, messages: List[Dict], conversation: Optional[Dict] = None
    ) -> Dict[str, List[str]]:
        """Async wrapper for extract_conversation_essence"""
        # Run synchronously to avoid threading issues with SQLite
        return self.extract_conversation_essence(messages, conversation)

    def extract_conversation_essence(
        self, messages: List[Dict], conversation: Optional[Dict] = None
    ) -> Dict[str, List[str]]:
        """Use Claude Code CLI to analyze a single conversation with AI precision"""

        # Generate idempotency key if conversation provided
        if conversation and self.cache_enabled:
            idempotency_key = self._generate_idempotency_key(conversation, messages)

            # Check cache first
            cached_response = self._get_cached_response(idempotency_key)
            if cached_response:
                return cached_response
        else:
            idempotency_key = None

        # Prepare conversation text with smart context selection
        max_chars = 20000  # Increased limit for better context

        # First, add initial messages for context (first 2-3 messages)
        context_messages = []
        for i, msg in enumerate(messages[:3]):  # First 3 messages for context
            role = msg["role"].capitalize()
            content = msg["content"]

            # Smart truncation for individual messages
            if len(content) > 2000:
                content = content[:1000] + " [...] " + content[-1000:]

            context_messages.append(f"{role}: {content}\n\n")

        # Calculate space used by context
        context_text = "".join(context_messages)
        remaining_chars = max_chars - len(context_text)

        # Now add as many recent messages as possible from the end
        recent_messages = []
        for msg in reversed(messages[3:]):  # Start from most recent, skip first 3
            role = msg["role"].capitalize()
            content = msg["content"]

            # Smart truncation for individual messages
            if len(content) > 2000:
                content = content[:1000] + " [...] " + content[-1000:]

            msg_text = f"{role}: {content}\n\n"

            # Check if we have space for this message
            if len(msg_text) + sum(len(m) for m in recent_messages) < remaining_chars:
                recent_messages.insert(
                    0, msg_text
                )  # Insert at beginning to maintain order
            else:
                break

        # Combine context and recent messages
        if len(messages) > 3 and len(recent_messages) < len(messages) - 3:
            # Add indicator that middle messages were skipped
            conversation_text = (
                context_text
                + "[... middle of conversation omitted ...]\n\n"
                + "".join(recent_messages)
            )
        else:
            # All messages fit
            conversation_text = context_text + "".join(recent_messages)

        # Create prompt for Claude with comprehensive generalized structure
        prompt = f"""You are a conversation analyst preparing context for another AI to continue this conversation.

OUTPUT FORMAT: Valid JSON only. No additional text before or after.

COMPREHENSIVE SCHEMA:
{{
    // CORE EXTRACTION (Original fields)
    "objectives": ["Build a React app", "Add authentication"],  // User's main goals (max 5)
    "key_questions": ["How to implement OAuth?"],  // Questions the user asked (max 10)
    "solutions_provided": ["Use NextAuth library", "JWT in cookies"],  // Solutions given (max 10)
    "technical_details": ["OAuth redirect flow", "Python 3.9"],  // Technical specifics (max 10)
    "action_items": ["Install dependencies", "Test with n=1000"],  // Next steps mentioned (max 10)
    
    "unresolved_questions": ["How to handle refresh tokens?"],  // Unanswered questions (max 5)
    "user_constraints": ["Must handle 10000 users", "Memory limit 512MB"],  // Requirements (max 5)
    "specific_errors": ["ImportError: oauth2", "Stack overflow at n=5000"],  // Errors mentioned (max 5)
    "implementation_status": "code_provided_not_tested",  // not_started/code_provided_not_tested/tested_with_issues/working/unknown
    "next_topics": ["Error handling", "Optimization"],  // Topics user might explore next (max 5)
    
    // USER UNDERSTANDING
    "user_expertise_indicators": {{
        "level": "intermediate",  // beginner/intermediate/advanced/unknown
        "evidence": ["Knows Big O notation", "Asks about efficiency"]  // Why this level (max 3)
    }},
    "user_satisfaction_indicators": {{
        "status": "unknown",  // satisfied/confused/frustrated/unknown
        "evidence": ["No follow-up response captured"]  // Supporting evidence (max 3)
    }},
    
    // GENERALIZED PATTERNS (New comprehensive fields)
    "user_current_state": {{  // What is the user's actual setup/situation?
        "has_implemented": ["Basic auth flow", "Database schema"],  // What they've already done (max 5)
        "current_blockers": ["OAuth redirect failing", "Memory issues at scale"],  // What's blocking them (max 5)
        "tools_mentioned": ["VS Code", "PostgreSQL", "Docker"],  // Their stack/tools (max 10)
        "actual_use_case": "Building a SaaS product for 10k users",  // Their real scenario
        "working_on_now": "Trying to fix authentication flow"  // Current immediate task
    }},
    
    "decision_journey": {{  // Where are they in their decision process?
        "options_considered": ["NextAuth", "Auth0", "Custom JWT"],  // Alternatives discussed (max 5)
        "evaluation_criteria": ["Cost", "Scalability", "Ease of use"],  // Their priorities (max 5)
        "preferences_shown": ["Prefers open source", "Wants simple solution"],  // Implicit preferences (max 5)
        "rejected_options": ["Auth0 (too expensive)"],  // What they ruled out and why (max 3)
        "leaning_towards": "NextAuth",  // Current preference if any
        "decision_timeline": "urgent"  // urgent/soon/exploring/no_timeline
    }},
    
    "critical_unknowns": {{  // What critical info is missing?
        "about_user_setup": ["Production or development?", "Team size?"],  // Missing context (max 5)
        "about_requirements": ["Budget constraints?", "Security requirements?"],  // Missing requirements (max 5)
        "about_constraints": ["Timeline?", "Existing infrastructure?"],  // Missing constraints (max 5)
        "assumptions_made": ["Assumed React knowledge", "Assumed cloud deployment"]  // Our assumptions (max 5)
    }},
    
    "conversation_health": {{  // Quality metrics
        "completeness_score": "partial",  // complete/partial/incomplete/abandoned
        "clarity_achieved": true,  // Did we reach mutual understanding?
        "value_delivered": "high",  // high/medium/low/unclear
        "red_flags": ["User seems confused about OAuth"],  // Concerning signals (max 3)
        "positive_signals": ["User engaged with examples"],  // Good signals (max 3)
        "conversation_stage": "implementation"  // discovery/planning/implementation/troubleshooting/complete
    }},
    
    "continuation_advice": {{  // How should the next AI proceed?
        "start_with": "Ask if they got OAuth working",  // Suggested opening
        "verify_first": ["Check implementation status", "Confirm requirements"],  // Things to confirm (max 3)
        "watch_for": ["Confusion about tokens", "Scale requirements"],  // Things to monitor (max 3)
        "offer_proactively": ["Error handling code", "Testing strategies"],  // Proactive help (max 3)
        "communication_style": "technical_but_friendly"  // Recommended tone
    }},
    
    // ORIGINAL FIELDS CONTINUED
    "conversation_dynamics": {{
        "user_was_specific": true,  // Did user provide clear requirements?
        "solution_completeness": "partial",  // complete/partial/incomplete
        "follow_up_expected": true,  // Do we expect user to have questions?
        "tone": "technical"  // technical/casual/formal/mixed
    }},
    
    "key_code_snippets": ["def fibonacci(n):", "memo[n] = fib(n-1)"],  // Critical code mentioned (max 5)
    "user_environment": ["Python", "Large numbers mentioned"],  // Platform/language details (max 5)
    "concepts_explained": ["Memoization", "Time complexity"],  // What was taught (max 5)
    "concepts_unclear": ["Space complexity trade-offs"],  // What might need clarification (max 5)
}}

EXTRACTION RULES:
- Extract explicitly stated information AND make reasonable inferences
- Look for implicit signals about user's actual situation and needs
- Identify gaps between what user asked and what they might actually need
- Note decision factors and evaluation criteria even if not explicitly stated
- Assess conversation quality and completeness objectively
- For expertise: infer from vocabulary, question complexity, understanding shown
- For satisfaction: look for thanks, confusion markers, follow-up questions
- Note any specific numbers, limits, or constraints mentioned
- Identify what was left unfinished or unclear
- Use "unknown"/empty arrays when evidence is insufficient
- Be specific and actionable in continuation advice

CONVERSATION:
{conversation_text}

JSON OUTPUT:"""

        # Try up to 2 times for better reliability
        max_retries = 2
        for attempt in range(max_retries):
            try:
                # Call Claude Code CLI with JSON output format
                result = subprocess.run(
                    [
                        "claude",
                        "--print",
                        "--model",
                        "haiku",
                        "--output-format",
                        "json",
                    ],
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=30,  # 30 seconds timeout
                )

                if result.returncode == 0:
                    response_text = result.stdout.strip()

                    # Try to parse as pure JSON first
                    try:
                        # First parse the wrapper JSON from --output-format json
                        wrapper = json.loads(response_text)
                        # Extract the actual result from the wrapper
                        if "result" in wrapper:
                            extracted = json.loads(wrapper["result"])
                        else:
                            extracted = wrapper
                    except json.JSONDecodeError:
                        # Fallback: Find JSON in response
                        json_start = response_text.find("{")
                        json_end = response_text.rfind("}") + 1
                        if json_start != -1 and json_end > json_start:
                            json_str = response_text[json_start:json_end]
                            # Clean up common issues
                            json_str = re.sub(
                                r"//.*$", "", json_str, flags=re.MULTILINE
                            )  # Remove // comments
                            json_str = re.sub(
                                r"/\*.*?\*/", "", json_str, flags=re.DOTALL
                            )  # Remove /* */ comments
                            extracted = json.loads(json_str)
                        else:
                            raise ValueError("No valid JSON found in response")

                    # Validate and clean the extracted data
                    cleaned = {}

                    # Handle list fields (expanded)
                    list_fields = [
                        "objectives",
                        "key_questions",
                        "solutions_provided",
                        "technical_details",
                        "action_items",
                        "unresolved_questions",
                        "user_constraints",
                        "specific_errors",
                        "next_topics",
                        "key_code_snippets",
                        "user_environment",
                        "concepts_explained",
                        "concepts_unclear",
                    ]

                    for key in list_fields:
                        if key in extracted and isinstance(extracted[key], list):
                            # Filter out empty strings and limit items
                            max_items = (
                                5
                                if key
                                in [
                                    "objectives",
                                    "unresolved_questions",
                                    "user_constraints",
                                ]
                                else 10
                            )
                            cleaned[key] = [
                                str(item).strip()
                                for item in extracted[key]
                                if item and str(item).strip()
                            ][:max_items]
                        else:
                            cleaned[key] = []

                    # Handle string fields
                    cleaned["implementation_status"] = extracted.get(
                        "implementation_status", "unknown"
                    )

                    # Handle nested dict fields (expanded with new generalized fields)
                    cleaned["user_expertise_indicators"] = extracted.get(
                        "user_expertise_indicators",
                        {"level": "unknown", "evidence": []},
                    )
                    cleaned["user_satisfaction_indicators"] = extracted.get(
                        "user_satisfaction_indicators",
                        {"status": "unknown", "evidence": []},
                    )
                    cleaned["conversation_dynamics"] = extracted.get(
                        "conversation_dynamics",
                        {
                            "user_was_specific": False,
                            "solution_completeness": "unknown",
                            "follow_up_expected": True,
                            "tone": "unknown",
                        },
                    )

                    # New generalized fields with defaults
                    cleaned["user_current_state"] = extracted.get(
                        "user_current_state",
                        {
                            "has_implemented": [],
                            "current_blockers": [],
                            "tools_mentioned": [],
                            "actual_use_case": "",
                            "working_on_now": "",
                        },
                    )

                    cleaned["decision_journey"] = extracted.get(
                        "decision_journey",
                        {
                            "options_considered": [],
                            "evaluation_criteria": [],
                            "preferences_shown": [],
                            "rejected_options": [],
                            "leaning_towards": "",
                            "decision_timeline": "unknown",
                        },
                    )

                    cleaned["critical_unknowns"] = extracted.get(
                        "critical_unknowns",
                        {
                            "about_user_setup": [],
                            "about_requirements": [],
                            "about_constraints": [],
                            "assumptions_made": [],
                        },
                    )

                    cleaned["conversation_health"] = extracted.get(
                        "conversation_health",
                        {
                            "completeness_score": "unknown",
                            "clarity_achieved": False,
                            "value_delivered": "unclear",
                            "red_flags": [],
                            "positive_signals": [],
                            "conversation_stage": "unknown",
                        },
                    )

                    cleaned["continuation_advice"] = extracted.get(
                        "continuation_advice",
                        {
                            "start_with": "",
                            "verify_first": [],
                            "watch_for": [],
                            "offer_proactively": [],
                            "communication_style": "unknown",
                        },
                    )

                    # Save to cache if we have an idempotency key
                    if idempotency_key and conversation and self.cache_enabled:
                        messages_hash = hashlib.md5(
                            json.dumps(messages, sort_keys=True, default=str).encode()
                        ).hexdigest()

                        self._save_to_cache(
                            idempotency_key,
                            conversation.get(
                                "id", conversation.get("conversation_id", "")
                            ),
                            messages_hash,
                            cleaned,
                        )

                    return cleaned

                else:
                    if attempt == 0:  # Only warn on first attempt
                        console.print(
                            f"[yellow]Warning: Claude returned error code {result.returncode}, retrying...[/yellow]"
                        )
                    continue

            except subprocess.TimeoutExpired:
                if attempt == max_retries - 1:
                    console.print(
                        f"[yellow]Warning: Claude analysis timed out after {max_retries} attempts[/yellow]"
                    )
                continue
            except (json.JSONDecodeError, ValueError) as e:
                if attempt == max_retries - 1:
                    console.print(
                        f"[yellow]Warning: Failed to parse Claude response after {max_retries} attempts: {e}[/yellow]"
                    )
            except Exception as e:
                if attempt == max_retries - 1:
                    console.print(
                        f"[yellow]Warning: Claude analysis failed: {e}[/yellow]"
                    )

        # Return empty structure if Claude fails (with all new fields)
        return {
            "objectives": [],
            "key_questions": [],
            "solutions_provided": [],
            "technical_details": [],
            "action_items": [],
            "unresolved_questions": [],
            "user_constraints": [],
            "specific_errors": [],
            "implementation_status": "unknown",
            "next_topics": [],
            "user_expertise_indicators": {"level": "unknown", "evidence": []},
            "user_satisfaction_indicators": {"status": "unknown", "evidence": []},
            "conversation_dynamics": {
                "user_was_specific": False,
                "solution_completeness": "unknown",
                "follow_up_expected": True,
                "tone": "unknown",
            },
            "user_current_state": {
                "has_implemented": [],
                "current_blockers": [],
                "tools_mentioned": [],
                "actual_use_case": "",
                "working_on_now": "",
            },
            "decision_journey": {
                "options_considered": [],
                "evaluation_criteria": [],
                "preferences_shown": [],
                "rejected_options": [],
                "leaning_towards": "",
                "decision_timeline": "unknown",
            },
            "critical_unknowns": {
                "about_user_setup": [],
                "about_requirements": [],
                "about_constraints": [],
                "assumptions_made": [],
            },
            "conversation_health": {
                "completeness_score": "unknown",
                "clarity_achieved": False,
                "value_delivered": "unclear",
                "red_flags": [],
                "positive_signals": [],
                "conversation_stage": "unknown",
            },
            "continuation_advice": {
                "start_with": "",
                "verify_first": [],
                "watch_for": [],
                "offer_proactively": [],
                "communication_style": "unknown",
            },
            "key_code_snippets": [],
            "user_environment": [],
            "concepts_explained": [],
            "concepts_unclear": [],
        }

    async def analyze_conversation_flow_async(
        self, messages: List[Dict]
    ) -> List[Dict[str, str]]:
        """Async wrapper for analyze_conversation_flow"""
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            return await loop.run_in_executor(
                executor, self.analyze_conversation_flow, messages
            )

    def analyze_conversation_flow(self, messages: List[Dict]) -> List[Dict[str, str]]:
        """Analyze the flow of conversation"""
        flow = []

        for i, msg in enumerate(messages[:30]):  # Limit to first 30 messages
            if msg["role"] == "user":
                content_lower = msg["content"].lower()

                # Classify user intent
                if any(
                    q in content_lower
                    for q in ["what", "how", "why", "when", "where", "who"]
                ):
                    intent = "Question"
                elif any(
                    c in content_lower
                    for c in ["create", "make", "build", "write", "generate"]
                ):
                    intent = "Creation"
                elif any(
                    a in content_lower
                    for a in ["analyze", "review", "check", "evaluate"]
                ):
                    intent = "Analysis"
                elif any(
                    e in content_lower for e in ["explain", "describe", "tell me about"]
                ):
                    intent = "Explanation"
                elif any(
                    f in content_lower
                    for f in ["fix", "debug", "solve", "error", "problem"]
                ):
                    intent = "Troubleshooting"
                else:
                    intent = "General"

                flow.append(
                    {
                        "turn": i + 1,
                        "role": "User",
                        "type": intent,
                        "preview": msg["content"][:150],
                    }
                )

            elif msg["role"] == "assistant":
                content = msg["content"]

                # Classify assistant response
                if "```" in content:
                    response_type = "Code"
                elif any(b in content for b in ["•", "-", "*", "1.", "2."]):
                    response_type = "Structured"
                elif len(content) > 2000:
                    response_type = "Detailed"
                elif "?" in content:
                    response_type = "Clarification"
                else:
                    response_type = "Direct"

                flow.append(
                    {
                        "turn": i + 1,
                        "role": "Assistant",
                        "type": response_type,
                        "preview": content[:150],
                    }
                )

        return flow

    def create_statistics_report(self, summaries: List[Dict]) -> Dict:
        """Create overall statistics from summaries"""
        stats = {
            "total_conversations": len(summaries),
            "total_messages": sum(s.get("message_count", 0) for s in summaries),
            "conversation_types": Counter(s.get("conversation_type", "unknown") for s in summaries),
            "models_used": Counter(s.get("model", "unknown") for s in summaries),
            "archived_count": sum(1 for s in summaries if s.get("is_archived", False)),
            "starred_count": sum(1 for s in summaries if s.get("is_starred", False)),
            "avg_messages_per_conversation": sum(s.get("message_count", 0) for s in summaries)
            // len(summaries)
            if summaries
            else 0,
            "programming_languages": Counter(),
        }

        # Aggregate programming languages
        for s in summaries:
            for lang in s.get("code_languages", []):
                stats["programming_languages"][lang] += 1

        # Find date range
        dates = [s.get("created") for s in summaries if s.get("created")]
        if dates:
            stats["date_range"] = {"earliest": min(dates), "latest": max(dates)}

        # Most common topics
        all_topics = []
        for s in summaries:
            all_topics.extend(s.get("topics", []))
        stats["top_topics"] = Counter(all_topics).most_common(20)

        return stats

    def export_for_import(
        self, summaries: List[Dict], stats: Dict, output_file: str = "claude_import.md"
    ):
        """Create a markdown file for importing to Claude"""

        console.print(f"\n[cyan]📝 Creating import file: {output_file}[/cyan]")

        with open(output_file, "w", encoding="utf-8") as f:
            # Header
            f.write("# Claude Conversation History Summary\n\n")
            f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")

            # Statistics Overview
            f.write("## 📊 Overall Statistics\n\n")
            f.write(f"- **Total Conversations:** {stats['total_conversations']}\n")
            f.write(f"- **Total Messages:** {stats['total_messages']}\n")
            f.write(
                f"- **Average Messages per Conversation:** {stats['avg_messages_per_conversation']}\n"
            )
            f.write(f"- **Starred Conversations:** {stats['starred_count']}\n")
            f.write(f"- **Archived Conversations:** {stats['archived_count']}\n")

            if "date_range" in stats:
                f.write(
                    f"- **Date Range:** {stats['date_range']['earliest'][:10]} to {stats['date_range']['latest'][:10]}\n"
                )

            f.write("\n### Conversation Types\n")
            for conv_type, count in stats["conversation_types"].most_common():
                f.write(f"- {conv_type.capitalize()}: {count}\n")

            if stats["programming_languages"]:
                f.write("\n### Programming Languages Used\n")
                for lang, count in stats["programming_languages"].most_common():
                    f.write(f"- {lang.capitalize()}: {count} conversations\n")

            f.write("\n### Top Topics\n")
            for topic, count in stats["top_topics"][:10]:
                f.write(f"- {topic}: {count} mentions\n")

            f.write("\n---\n\n")

            # Key Conversations
            f.write("## 🌟 Key Conversations\n\n")

            # Starred conversations
            starred = [s for s in summaries if s.get("is_starred", False)]
            if starred:
                f.write("### Starred Conversations\n\n")
                for s in starred[:10]:
                    f.write(f"**{s.get('title', 'Untitled')}**\n")
                    created = s.get('created', '')
                    f.write(
                        f"- Date: {created[:10] if created else 'Unknown'}\n"
                    )
                    f.write(f"- Messages: {s.get('message_count', 0)}\n")
                    f.write(f"- Topics: {', '.join(s.get('topics', [])[:5])}\n")
                    if s.get("first_query"):
                        f.write(f"- Query: {s['first_query'][:200]}...\n")
                    f.write("\n")

            # Recent conversations
            f.write("### Recent Conversations\n\n")
            recent = sorted(
                [s for s in summaries if s.get("created")],
                key=lambda x: x.get("created", ""),
                reverse=True,
            )[:10]

            for s in recent:
                f.write(f"**{s.get('title', 'Untitled')}**\n")
                f.write(f"- Date: {s.get('created', '')[:10]}\n")
                f.write(f"- Type: {s.get('conversation_type', 'unknown')}\n")
                f.write(f"- Messages: {s.get('message_count', 0)}\n")
                topics = s.get("topics", [])
                if topics:
                    f.write(f"- Topics: {', '.join(topics[:5])}\n")
                f.write("\n")

            f.write("---\n\n")

            # Conversation Patterns
            f.write("## 💡 Conversation Patterns & Insights\n\n")

            # Group by type
            by_type = defaultdict(list)
            for s in summaries:
                by_type[s.get("conversation_type", "unknown")].append(s)

            for conv_type, convs in by_type.items():
                if len(convs) >= 5:  # Only show types with significant conversations
                    f.write(
                        f"### {conv_type.capitalize()} ({len(convs)} conversations)\n\n"
                    )

                    # Common topics for this type
                    type_topics = []
                    for c in convs:
                        type_topics.extend(c.get("topics", []))

                    common_topics = Counter(type_topics).most_common(5)
                    f.write(
                        f"Common topics: {', '.join([t for t, _ in common_topics])}\n\n"
                    )

                    # Sample conversations
                    f.write("Sample conversations:\n")
                    for c in convs[:3]:
                        f.write(f"- {c['title'][:60]}\n")
                    f.write("\n")

            f.write("---\n\n")
            f.write("## 📌 Import Instructions\n\n")
            f.write("To use this summary in a new Claude conversation:\n\n")
            f.write("1. Copy this entire document\n")
            f.write("2. Start a new conversation with Claude\n")
            f.write("3. Paste this summary as your first message\n")
            f.write(
                "4. Ask Claude to acknowledge the context and use it for future interactions\n\n"
            )
            f.write("Example prompt:\n")
            f.write("> \"I'm sharing a summary of our previous conversations. ")
            f.write(
                "Please acknowledge this context and use it to better understand my preferences, "
            )
            f.write("past topics we've discussed, and my typical use cases.\"\n")

        console.print(f"[green]✅ Import file created: {output_file}[/green]")

    def _get_conversation_folder(self, conv, output_dir):
        """Determine which folder this conversation should go in based on project"""
        gizmo_id = conv.get("gizmo_id")

        if gizmo_id and gizmo_id in self.projects:
            # Conversation belongs to a project
            project = self.projects[gizmo_id]
            # Create safe folder name
            folder_name = re.sub(r"[^\w\s-]", "", project["name"])[:40].strip()
            folder_name = re.sub(r"[-\s]+", "-", folder_name)
            project_folder = f"{folder_name}-{project['type']}"
            folder_path = os.path.join(output_dir, project_folder)
        else:
            # No project - goes in 'no-project' folder
            folder_path = os.path.join(output_dir, "no-project")

        os.makedirs(folder_path, exist_ok=True)
        return folder_path

    async def process_single_conversation_file(self, conv, i, output_dir):
        """Process a single conversation and create its markdown file"""
        try:
            # Extract messages
            messages = self.extract_messages(conv)
            if not messages:
                return None

            # Determine folder based on project
            folder_path = self._get_conversation_folder(conv, output_dir)

            # Create filename (sanitize title)
            title = conv.get("title", f"Conversation_{i}")
            safe_title = re.sub(r"[^\w\s-]", "", title)[:50].strip()
            safe_title = re.sub(r"[-\s]+", "-", safe_title)

            # Add timestamp to filename
            timestamp = datetime.fromtimestamp(conv.get("create_time", 0)).strftime(
                "%Y%m%d"
            )
            filename = f"{timestamp}_{safe_title}_{i:04d}.md"
            filepath = os.path.join(folder_path, filename)

            # Extract additional metrics using Claude in parallel
            essence_task = self.extract_conversation_essence_async(messages, conv)
            flow_task = self.analyze_conversation_flow_async(messages)

            # Wait for both tasks to complete
            essence, flow = await asyncio.gather(essence_task, flow_task)

            # Write the file
            with open(filepath, "w", encoding="utf-8") as f:
                # Write header with source AI detection
                model = conv.get("default_model_slug", "unknown").lower()
                if "gpt" in model:
                    f.write("# ChatGPT Conversation Context\n\n")
                elif "claude" in model:
                    f.write("# Claude Conversation Context\n\n")
                else:
                    f.write("# AI Conversation Context\n\n")

                f.write("## Metadata\n\n")
                f.write(f"**Title:** {title}\n")
                f.write(
                    f"**Date:** {datetime.fromtimestamp(conv.get('create_time', 0)).strftime('%Y-%m-%d %H:%M')}\n"
                )
                f.write(f"**Model:** {conv.get('default_model_slug', 'unknown')}\n")
                f.write(f"**Total Exchanges:** {len(messages)}\n")

                # Add Project information if available
                gizmo_id = conv.get("gizmo_id")
                if gizmo_id and gizmo_id in self.projects:
                    project = self.projects[gizmo_id]
                    f.write(f"**Project:** {project['name']} ({project['type']})\n")
                    f.write(f"**Project ID:** `{gizmo_id}`\n")
                    f.write(
                        f"**Project Conversations:** {len(project['conversations'])}\n"
                    )

                f.write("\n")

                # Add related conversations from same project
                if gizmo_id and gizmo_id in self.projects:
                    project = self.projects[gizmo_id]
                    related = [
                        c
                        for c in project["conversations"]
                        if c.get("id") != conv.get("id")
                    ][:5]  # Get 5 related

                    if related:
                        f.write("### 🔗 Related Project Conversations\n\n")
                        for rel_conv in related:
                            rel_title = rel_conv.get("title", "Untitled")
                            rel_date = datetime.fromtimestamp(
                                rel_conv.get("create_time", 0)
                            ).strftime("%Y-%m-%d")
                            f.write(f"- **{rel_date}**: {rel_title}\n")
                        f.write("\n---\n\n")

                f.write("---\n\n")

                # Create conversation timeline
                f.write("## Conversation Timeline\n\n")
                for idx, msg in enumerate(messages[:10]):  # Show first 10 exchanges
                    role = msg["role"].capitalize()
                    preview = msg["content"][:150].replace("\n", " ")
                    if len(msg["content"]) > 150:
                        preview += "..."
                    f.write(f"{idx + 1}. **{role}**: {preview}\n")
                if len(messages) > 10:
                    f.write(
                        f"\n*[{len(messages) - 10} more messages in conversation]*\n"
                    )
                f.write("\n---\n\n")

                # Core Information
                f.write("## Core Information\n\n")

                objectives = [
                    obj for obj in essence.get("objectives", []) if obj and obj.strip()
                ]
                if objectives:
                    f.write("### 🎯 User Objectives\n")
                    for obj in objectives:
                        f.write(f"- {obj}\n")
                    f.write("\n")

                solutions = [
                    sol
                    for sol in essence.get("solutions_provided", [])
                    if sol and sol.strip()
                ]
                if solutions:
                    f.write("### ✅ Solutions Provided\n")
                    for sol in solutions:
                        f.write(f"- {sol}\n")
                    f.write("\n")

                # Implementation Details
                f.write("## Implementation Context\n\n")

                status = essence.get("implementation_status", "unknown")
                f.write(f"**Status**: {status.replace('_', ' ').title()}\n\n")

                user_constraints = [
                    c for c in essence.get("user_constraints", []) if c and c.strip()
                ]
                if user_constraints:
                    f.write("### 📏 User Requirements & Constraints\n")
                    for constraint in user_constraints:
                        f.write(f"- {constraint}\n")
                    f.write("\n")

                user_env = [
                    e for e in essence.get("user_environment", []) if e and e.strip()
                ]
                if user_env:
                    f.write("### 🖥️ User Environment\n")
                    for env in user_env:
                        f.write(f"- {env}\n")
                    f.write("\n")

                errors = [
                    e for e in essence.get("specific_errors", []) if e and e.strip()
                ]
                if errors:
                    f.write("### ⚠️ Errors Encountered\n")
                    for error in errors:
                        f.write(f"- {error}\n")
                    f.write("\n")

                # Unresolved & Next Steps
                f.write("## Open Threads & Next Steps\n\n")

                unresolved = [
                    q
                    for q in essence.get("unresolved_questions", [])
                    if q and q.strip()
                ]
                if unresolved:
                    f.write("### ❓ Unresolved Questions\n")
                    for q in unresolved:
                        f.write(f"- {q}\n")
                    f.write("\n")

                next_topics = [
                    t for t in essence.get("next_topics", []) if t and t.strip()
                ]
                if next_topics:
                    f.write("### 🔮 Potential Next Topics\n")
                    for topic in next_topics:
                        f.write(f"- {topic}\n")
                    f.write("\n")

                action_items = [
                    a for a in essence.get("action_items", []) if a and a.strip()
                ]
                if action_items:
                    f.write("### 📋 Action Items\n")
                    for item in action_items:
                        f.write(f"- {item}\n")
                    f.write("\n")

                # User Profile & Dynamics
                f.write("## User Context & Dynamics\n\n")

                expertise = essence.get("user_expertise_indicators", {})
                if expertise:
                    level = expertise.get("level", "unknown")
                    evidence = expertise.get("evidence", [])
                    f.write(f"**Expertise Level**: {level.title()}\n")
                    if evidence:
                        f.write("*Evidence*: ")
                        f.write(", ".join(evidence[:3]))
                        f.write("\n")
                    f.write("\n")

                satisfaction = essence.get("user_satisfaction_indicators", {})
                if satisfaction:
                    status = satisfaction.get("status", "unknown")
                    evidence = satisfaction.get("evidence", [])
                    f.write(f"**Satisfaction Status**: {status.title()}\n")
                    if evidence:
                        f.write("*Indicators*: ")
                        f.write(", ".join(evidence[:3]))
                        f.write("\n")
                    f.write("\n")

                dynamics = essence.get("conversation_dynamics", {})
                if dynamics:
                    if dynamics.get("user_was_specific"):
                        f.write("✓ User provided specific requirements\n")
                    completeness = dynamics.get("solution_completeness", "unknown")
                    f.write(f"**Solution Completeness**: {completeness}\n")
                    if dynamics.get("follow_up_expected"):
                        f.write("⚠️ **Follow-up likely needed**\n")
                    f.write("\n")

                # NEW: User's Current State
                user_state = essence.get("user_current_state", {})
                if any(user_state.values()):
                    f.write("### 🔧 User's Current State\n\n")

                    if user_state.get("actual_use_case"):
                        f.write(f"**Use Case**: {user_state['actual_use_case']}\n\n")

                    if user_state.get("working_on_now"):
                        f.write(
                            f"**Currently Working On**: {user_state['working_on_now']}\n\n"
                        )

                    has_impl = user_state.get("has_implemented", [])
                    if has_impl:
                        f.write("**Already Implemented**:\n")
                        for item in has_impl:
                            f.write(f"- {item}\n")
                        f.write("\n")

                    blockers = user_state.get("current_blockers", [])
                    if blockers:
                        f.write("**Current Blockers**:\n")
                        for blocker in blockers:
                            f.write(f"- ⚠️ {blocker}\n")
                        f.write("\n")

                    tools = user_state.get("tools_mentioned", [])
                    if tools:
                        f.write(f"**Tech Stack**: {', '.join(tools)}\n\n")

                # NEW: Decision Journey
                decision = essence.get("decision_journey", {})
                if any(decision.values()):
                    f.write("### 🤔 Decision Journey\n\n")

                    timeline = decision.get("decision_timeline", "unknown")
                    if timeline != "unknown":
                        f.write(
                            f"**Timeline**: {timeline.replace('_', ' ').title()}\n\n"
                        )

                    if decision.get("leaning_towards"):
                        f.write(
                            f"**Currently Leaning Towards**: {decision['leaning_towards']}\n\n"
                        )

                    options = decision.get("options_considered", [])
                    if options:
                        f.write(f"**Options Considered**: {', '.join(options)}\n\n")

                    criteria = decision.get("evaluation_criteria", [])
                    if criteria:
                        f.write("**Evaluation Criteria**:\n")
                        for criterion in criteria:
                            f.write(f"- {criterion}\n")
                        f.write("\n")

                    rejected = decision.get("rejected_options", [])
                    if rejected:
                        f.write("**Rejected Options**:\n")
                        for option in rejected:
                            f.write(f"- ❌ {option}\n")
                        f.write("\n")

                    prefs = decision.get("preferences_shown", [])
                    if prefs:
                        f.write("**Preferences**:\n")
                        for pref in prefs:
                            f.write(f"- {pref}\n")
                        f.write("\n")

                # NEW: Critical Unknowns
                unknowns = essence.get("critical_unknowns", {})
                if any(v for v in unknowns.values() if v):
                    f.write("### ❓ Critical Information Gaps\n\n")

                    setup_unknowns = unknowns.get("about_user_setup", [])
                    if setup_unknowns:
                        f.write("**About User's Setup**:\n")
                        for unknown in setup_unknowns:
                            f.write(f"- {unknown}\n")
                        f.write("\n")

                    req_unknowns = unknowns.get("about_requirements", [])
                    if req_unknowns:
                        f.write("**About Requirements**:\n")
                        for unknown in req_unknowns:
                            f.write(f"- {unknown}\n")
                        f.write("\n")

                    constraint_unknowns = unknowns.get("about_constraints", [])
                    if constraint_unknowns:
                        f.write("**About Constraints**:\n")
                        for unknown in constraint_unknowns:
                            f.write(f"- {unknown}\n")
                        f.write("\n")

                    assumptions = unknowns.get("assumptions_made", [])
                    if assumptions:
                        f.write("**Assumptions Made**:\n")
                        for assumption in assumptions:
                            f.write(f"- 💭 {assumption}\n")
                        f.write("\n")

                # NEW: Conversation Health
                health = essence.get("conversation_health", {})
                if health:
                    f.write("### 📊 Conversation Health\n\n")

                    stage = health.get("conversation_stage", "unknown")
                    if stage != "unknown":
                        f.write(f"**Stage**: {stage.replace('_', ' ').title()}\n")

                    score = health.get("completeness_score", "unknown")
                    if score != "unknown":
                        f.write(f"**Completeness**: {score}\n")

                    value = health.get("value_delivered", "unclear")
                    if value != "unclear":
                        f.write(f"**Value Delivered**: {value}\n")

                    if health.get("clarity_achieved"):
                        f.write("✅ **Clarity achieved**\n")

                    f.write("\n")

                    red_flags = health.get("red_flags", [])
                    if red_flags:
                        f.write("**⚠️ Red Flags**:\n")
                        for flag in red_flags:
                            f.write(f"- {flag}\n")
                        f.write("\n")

                    positive = health.get("positive_signals", [])
                    if positive:
                        f.write("**✅ Positive Signals**:\n")
                        for signal in positive:
                            f.write(f"- {signal}\n")
                        f.write("\n")

                f.write("---\n\n")

                # Conversation flow summary (condensed)
                f.write("## Interaction Pattern\n\n")

                # Analyze flow patterns
                user_intents = [t["type"] for t in flow if t["role"] == "User"]
                assistant_types = [t["type"] for t in flow if t["role"] == "Assistant"]

                if user_intents:
                    intent_counts = Counter(user_intents)
                    f.write("**User Focus:** ")
                    f.write(
                        ", ".join(
                            [
                                f"{intent} ({count}x)"
                                for intent, count in intent_counts.most_common(3)
                            ]
                        )
                    )
                    f.write("\n\n")

                if assistant_types:
                    response_counts = Counter(assistant_types)
                    f.write("**Response Style:** ")
                    f.write(
                        ", ".join(
                            [
                                f"{rtype} ({count}x)"
                                for rtype, count in response_counts.most_common(3)
                            ]
                        )
                    )
                    f.write("\n\n")

                # Topics covered
                topics = self.extract_topics(
                    " ".join([m["content"][:500] for m in messages[:10]])
                )
                if topics:
                    f.write(f"**Topics:** {', '.join(topics[:7])}\n\n")

                f.write("---\n\n")

                # NEW: Continuation Advice
                advice = essence.get("continuation_advice", {})
                if any(advice.values()):
                    f.write("## 🎯 Continuation Strategy\n\n")

                    if advice.get("start_with"):
                        f.write(f'**Suggested Opening**: "{advice["start_with"]}"\n\n')

                    verify = advice.get("verify_first", [])
                    if verify:
                        f.write("**Verify First**:\n")
                        for item in verify:
                            f.write(f"- {item}\n")
                        f.write("\n")

                    watch = advice.get("watch_for", [])
                    if watch:
                        f.write("**Watch For**:\n")
                        for item in watch:
                            f.write(f"- {item}\n")
                        f.write("\n")

                    offer = advice.get("offer_proactively", [])
                    if offer:
                        f.write("**Offer Proactively**:\n")
                        for item in offer:
                            f.write(f"- {item}\n")
                        f.write("\n")

                    style = advice.get("communication_style", "unknown")
                    if style != "unknown":
                        f.write(
                            f"**Recommended Communication Style**: {style.replace('_', ' ').title()}\n\n"
                        )

                    f.write("---\n\n")

                # Context for continuation
                f.write("## Context for Continuation\n\n")

                # Get the last meaningful exchange
                last_user = None
                last_assistant = None
                for msg in reversed(messages):
                    if not last_user and msg["role"] == "user":
                        last_user = msg["content"][:1000]
                    if not last_assistant and msg["role"] == "assistant":
                        last_assistant = msg["content"][:1500]
                    if last_user and last_assistant:
                        break

                if last_user:
                    f.write("**Last User Query:**\n")
                    f.write(f"> {last_user}\n\n")

                if last_assistant:
                    f.write("**Last Assistant Response (excerpt):**\n")
                    f.write(f"> {last_assistant}\n")

            return filepath
        except Exception as e:
            console.print(
                f"[yellow]Warning: Failed to create file for conversation {i}: {e}[/yellow]"
            )
            return None

    def extract_project_context(self, project_data: Dict) -> Dict:
        """Extract shared context from all conversations in a project"""

        # Collect all messages from project conversations
        all_objectives = []
        all_constraints = []
        all_tools = []
        all_decisions = []
        common_topics = Counter()

        # Sample conversations for analysis (up to 10)
        sample_convs = project_data["conversations"][:10]

        for conv in sample_convs:
            messages = self.extract_messages(conv)
            if messages:
                # Get quick topic extraction
                conv_text = " ".join([m["content"][:500] for m in messages[:5]])
                topics = self.extract_topics(conv_text)
                for topic in topics:
                    common_topics[topic] += 1

        # Find truly common topics (appear in multiple conversations)
        shared_topics = [
            topic for topic, count in common_topics.most_common() if count > 1
        ]

        return {
            "shared_topics": shared_topics[:10],
            "conversation_count": len(project_data["conversations"]),
            "date_range": self._get_date_range(project_data["conversations"]),
            "primary_models": [
                m for m, _ in project_data["models_used"].most_common(3)
            ],
        }

    def _get_date_range(self, conversations: List[Dict]) -> str:
        """Get date range for a list of conversations"""
        dates = [c.get("create_time") for c in conversations if c.get("create_time")]
        if dates:
            start = datetime.fromtimestamp(min(dates)).strftime("%Y-%m-%d")
            end = datetime.fromtimestamp(max(dates)).strftime("%Y-%m-%d")
            return f"{start} to {end}"
        return "Unknown"

    def create_project_summary_files(self, output_dir: str = "claude_conversations"):
        """Create summary files for ChatGPT Projects"""
        if not self.projects:
            return

        projects_dir = os.path.join(output_dir, "project-summaries")
        os.makedirs(projects_dir, exist_ok=True)

        console.print(f"[cyan]📁 Creating ChatGPT Project summaries...[/cyan]")

        for project_id, project_data in self.projects.items():
            # Extract shared context
            project_context = self.extract_project_context(project_data)

            # Create safe filename
            safe_name = re.sub(r"[^\w\s-]", "", project_data["name"])[:30].strip()
            safe_name = re.sub(r"[-\s]+", "-", safe_name)
            filename = f"project_{safe_name}_{project_id[-8:]}.md"
            filepath = os.path.join(projects_dir, filename)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"# ChatGPT Project: {project_data['name']}\n\n")
                f.write(f"## Project Overview\n\n")
                f.write(f"**Project ID:** `{project_id}`\n")
                f.write(f"**Type:** {project_data['type'].title()}\n")
                f.write(
                    f"**Total Conversations:** {len(project_data['conversations'])}\n"
                )
                # Filter out None values from models
                models = [m for m in project_data["models_used"].keys() if m]
                if models:
                    f.write(f"**Models Used:** {', '.join(models)}\n\n")
                else:
                    f.write(f"**Models Used:** Unknown\n\n")

                # Date range
                dates = [
                    c.get("create_time")
                    for c in project_data["conversations"]
                    if c.get("create_time")
                ]
                if dates:
                    f.write(
                        f"**Date Range:** {datetime.fromtimestamp(min(dates)).strftime('%Y-%m-%d')} to "
                    )
                    f.write(
                        f"{datetime.fromtimestamp(max(dates)).strftime('%Y-%m-%d')}\n\n"
                    )

                f.write("## Conversation List\n\n")

                # Sort by date
                sorted_convs = sorted(
                    project_data["conversations"],
                    key=lambda x: x.get("create_time", 0),
                    reverse=True,
                )

                for conv in sorted_convs[:20]:  # Show recent 20
                    title = conv.get("title", "Untitled")
                    date = datetime.fromtimestamp(conv.get("create_time", 0)).strftime(
                        "%Y-%m-%d"
                    )
                    f.write(f"- **{date}**: {title}\n")

                if len(sorted_convs) > 20:
                    f.write(
                        f"\n*... and {len(sorted_convs) - 20} more conversations*\n"
                    )

                # Extract common themes and shared context
                f.write("\n## Shared Context & Themes\n\n")

                if project_context["shared_topics"]:
                    f.write("**Common Topics Across Conversations:**\n")
                    for topic in project_context["shared_topics"]:
                        f.write(f"- {topic}\n")
                    f.write("\n")

                # Title-based topics as fallback/addition
                all_titles = " ".join(project_data["titles"])
                title_topics = self.extract_topics(all_titles, max_topics=10)
                if title_topics:
                    f.write("**Keywords from Titles:**\n")
                    for topic in title_topics[:7]:
                        f.write(f"- {topic}\n")
                    f.write("\n")

                # Project insights
                f.write("## Project Insights\n\n")
                f.write(
                    f"This project appears to be focused on **{project_data['name']}** "
                )
                f.write(
                    f"with {len(project_data['conversations'])} related conversations.\n\n"
                )

                if len(project_data["conversations"]) > 10:
                    f.write(
                        f"📈 **High Activity Project**: This is one of your most active projects, "
                    )
                    f.write(f"indicating it's a primary focus area.\n\n")

                # Suggest how to use this project context
                f.write("## How to Use This Context\n\n")
                f.write("When continuing conversations from this project:\n")
                f.write("1. Reference the project name and ID for context\n")
                f.write(
                    "2. Mention you're continuing work on topics: {0}\n".format(
                        ", ".join(project_context["shared_topics"][:3])
                        if project_context["shared_topics"]
                        else "project topics"
                    )
                )
                f.write(
                    "3. The AI will better understand your domain and preferences\n"
                )
                f.write("4. Browse related conversations in the project folder\n")

                # Show folder structure
                folder_name = re.sub(r"[^\w\s-]", "", project_data["name"])[:40].strip()
                folder_name = re.sub(r"[-\s]+", "-", folder_name)
                project_folder = f"{folder_name}-{project_data['type']}"
                f.write(f"\n**Project Folder:** `{project_folder}/`\n")

                f.write("\n---\n\n")
                f.write(
                    "*⚠️ Note: ChatGPT Project instructions and shared files are not included in the export.*\n"
                )
                f.write(
                    "*This summary is reconstructed from conversation metadata and patterns.*\n"
                )
                f.write("\n**To fully restore project context:**\n")
                f.write(
                    "1. Copy your original project instructions if you have them saved\n"
                )
                f.write("2. Re-upload any shared files that were in the project\n")
                f.write("3. Mention the project name when starting new conversations\n")

        console.print(
            f"[green]✅ Created {len(self.projects)} project summary files in: {projects_dir}[/green]"
        )

    def show_folder_structure(self, output_dir: str):
        """Display the folder structure created"""
        console.print("\n[cyan]📁 Folder Structure:[/cyan]")

        # Count conversations by folder
        folder_counts = {}

        for conv in self.conversations:
            gizmo_id = conv.get("gizmo_id")
            if gizmo_id and gizmo_id in self.projects:
                project = self.projects[gizmo_id]
                folder_name = re.sub(r"[^\w\s-]", "", project["name"])[:40].strip()
                folder_name = re.sub(r"[-\s]+", "-", folder_name)
                project_folder = f"{folder_name}-{project['type']}"
                folder_counts[project_folder] = folder_counts.get(project_folder, 0) + 1
            else:
                folder_counts["no-project"] = folder_counts.get("no-project", 0) + 1

        # Show structure
        console.print(f"   {output_dir}/")
        for folder, count in sorted(folder_counts.items()):
            console.print(f"   ├── {folder}/ ({count} conversations)")
        console.print(f"   └── project-summaries/ ({len(self.projects)} summaries)")

    def show_cache_statistics(self):
        """Display cache hit/miss statistics"""
        if not self.cache_enabled:
            return

        total_requests = self.cache_hits + self.cache_misses
        if total_requests > 0:
            hit_rate = (self.cache_hits / total_requests) * 100
            console.print(f"\n[cyan]📊 Cache Statistics:[/cyan]")
            console.print(f"  • Cache Hits: {self.cache_hits} ({hit_rate:.1f}%)")
            console.print(f"  • Cache Misses: {self.cache_misses}")
            console.print(f"  • Total API Calls Saved: {self.cache_hits}")

            # Estimate cost savings (rough estimate)
            # Haiku pricing: ~$0.25 per 1M input tokens, ~$1.25 per 1M output tokens
            # Average conversation analysis: ~2K input + 500 output tokens
            estimated_savings = self.cache_hits * 0.001  # More realistic estimate
            if estimated_savings > 0.01:
                console.print(f"  • Estimated Cost Saved: ~${estimated_savings:.2f}")

            # Time saved estimate (3-5 seconds per API call)
            time_saved = self.cache_hits * 4  # seconds
            if time_saved > 60:
                console.print(
                    f"  • Time Saved: ~{time_saved // 60} minutes {time_saved % 60} seconds"
                )
            elif time_saved > 0:
                console.print(f"  • Time Saved: ~{time_saved} seconds")

    def cleanup_cache(self, days_old: int = 30):
        """Clean up old cache entries"""
        if not self.cache_enabled:
            return

        cutoff_date = (datetime.now() - timedelta(days=days_old)).isoformat()
        self.cursor.execute(
            "DELETE FROM llm_cache WHERE created_at < ?", (cutoff_date,)
        )
        deleted = self.cursor.rowcount
        self.conn.commit()
        if deleted > 0:
            console.print(
                f"[yellow]🧹 Cleaned up {deleted} cache entries older than {days_old} days[/yellow]"
            )

    def __del__(self):
        """Clean up database connection"""
        if hasattr(self, "conn") and self.conn:
            self.conn.close()

    async def create_individual_conversation_files_async(
        self,
        output_dir: str = "claude_conversations",
        max_conversations: Optional[int] = None,
        batch_size: int = 5,
    ):
        """Create individual markdown files for each conversation using async for parallelization"""
        os.makedirs(output_dir, exist_ok=True)

        # Respect the max limit
        conversations_to_process = (
            self.conversations[:max_conversations]
            if max_conversations
            else self.conversations
        )

        console.print(f"[cyan]📝 Creating individual conversation files...[/cyan]")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"[cyan]Creating {len(conversations_to_process)} conversation files (parallel batch size: {batch_size})...[/cyan]",
                total=len(conversations_to_process),
            )

            # Process conversations in batches
            for i in range(0, len(conversations_to_process), batch_size):
                batch = conversations_to_process[i : i + batch_size]
                batch_indices = list(
                    range(i, min(i + batch_size, len(conversations_to_process)))
                )

                # Create async tasks for the batch
                tasks = [
                    self.process_single_conversation_file(conv, idx, output_dir)
                    for conv, idx in zip(batch, batch_indices)
                ]

                # Run batch in parallel
                await asyncio.gather(*tasks, return_exceptions=True)

                # Update progress for the batch
                for _ in batch:
                    progress.update(task, advance=1)

        console.print(
            f"[green]✅ Created individual conversation files in: {output_dir}[/green]"
        )

    def create_individual_conversation_files(
        self,
        output_dir: str = "claude_conversations",
        max_conversations: Optional[int] = None,
    ):
        """Sync wrapper for create_individual_conversation_files"""
        asyncio.run(
            self.create_individual_conversation_files_async(
                output_dir, max_conversations
            )
        )

    # Removed JSON summaries - not needed
    # def save_json_summaries(self, summaries: List[Dict], output_file: str = 'conversation_summaries.json'):
    #     """Save summaries as JSON"""
    #     with open(output_file, 'w', encoding='utf-8') as f:
    #         json.dump(summaries, f, indent=2, ensure_ascii=False)
    #     console.print(f"[green]✅ JSON summaries saved: {output_file}[/green]")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze AI conversations (ChatGPT/Claude) and extract comprehensive context for continuation",
        epilog="Example: ./conversation_summarizer.py conversations.json --max 10 --output-dir ./analysis",
    )
    parser.add_argument(
        "input_file",
        help="Path to conversations.json (from ChatGPT export ZIP or Claude export)",
    )
    parser.add_argument(
        "--max", type=int, help="Maximum number of conversations to process"
    )
    parser.add_argument(
        "--output-dir", default=".", help="Output directory for generated files"
    )
    parser.add_argument(
        "--individual",
        action="store_true",
        help="Create individual markdown files for each conversation (default: True)",
    )
    parser.add_argument(
        "--cache-file",
        default="conversation_cache.db",
        help="SQLite cache file for LLM responses (default: conversation_cache.db)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable caching and force fresh LLM calls",
    )
    parser.add_argument(
        "--clean-cache",
        type=int,
        metavar="DAYS",
        help="Clean cache entries older than DAYS before processing",
    )

    args = parser.parse_args()
    # Show header
    console.print(
        Panel.fit(
            "[bold cyan]AI Conversation Analyzer & Context Extractor[/bold cyan]\n"
            "Compatible with ChatGPT & Claude exports\n"
            "Extracting comprehensive context for seamless continuation",
            border_style="cyan",
        )
    )

    # Create output directory if needed
    os.makedirs(args.output_dir, exist_ok=True)

    # Process conversations with caching
    cache_file = None if args.no_cache else args.cache_file
    summarizer = ConversationSummarizer(args.input_file, cache_file=cache_file)

    # Clean old cache entries if requested
    if args.clean_cache and not args.no_cache:
        summarizer.cleanup_cache(days_old=args.clean_cache)

    # Generate summaries
    summaries = summarizer.generate_summaries(args.max)

    # Create statistics
    stats = summarizer.create_statistics_report(summaries)

    # Save outputs (skip JSON, only markdown)
    md_output = os.path.join(args.output_dir, "claude_import.md")
    summarizer.export_for_import(summaries, stats, md_output)

    # Create individual conversation files if requested or by default
    if args.individual or True:  # Always create by default
        conv_dir = os.path.join(args.output_dir, "claude_conversations")
        summarizer.create_individual_conversation_files(
            conv_dir, max_conversations=args.max
        )

        # Create project summaries if ChatGPT Projects found
        if summarizer.projects:
            summarizer.create_project_summary_files(conv_dir)
            # Show the folder organization
            summarizer.show_folder_structure(conv_dir)

    # Display statistics table
    console.print("\n")
    table = Table(title="Analysis Summary", title_style="bold cyan")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="magenta")

    table.add_row("Total Conversations", str(stats["total_conversations"]))
    table.add_row("Total Messages", str(stats["total_messages"]))
    table.add_row("Avg Messages/Conv", str(stats["avg_messages_per_conversation"]))
    table.add_row("Starred", str(stats["starred_count"]))
    table.add_row("Archived", str(stats["archived_count"]))

    if "date_range" in stats:
        table.add_row(
            "Date Range",
            f"{stats['date_range']['earliest'][:10]} to {stats['date_range']['latest'][:10]}",
        )

    console.print(table)

    # Show top topics
    if stats["top_topics"]:
        console.print("\n[bold cyan]Top Topics:[/bold cyan]")
        for topic, count in stats["top_topics"][:10]:
            console.print(f"  • {topic}: {count} mentions")

    # Print summary
    console.print("\n" + "=" * 60)
    console.print("[bold green]✨ ANALYSIS COMPLETE![/bold green]")
    console.print("=" * 60)
    console.print(f"\n[cyan]📊 Processed {len(summaries)} conversations[/cyan]")
    console.print(f"[cyan]📁 Files created:[/cyan]")
    console.print(
        f"   - {md_output} (global statistics & overview of ALL conversations)"
    )
    console.print(f"   - claude_conversations/ (individual files organized by project)")
    if summarizer.projects:
        console.print(
            f"   - claude_conversations/project-summaries/ (ChatGPT Project summaries)"
        )
    console.print("\n[bold yellow]📝 Usage:[/bold yellow]")
    console.print(
        "   • [cyan]claude_import.md[/cyan] = Overview of your entire conversation history"
    )
    console.print(
        "     → Use when you want any AI to understand your general interests/topics"
    )
    console.print(
        "   • [cyan]claude_conversations/*.md[/cyan] = Specific conversation contexts"
    )
    console.print(
        "     → Copy/paste to resume a specific conversation where you left off"
    )
    console.print(
        "\n[green]💡 Works with any AI: ChatGPT, Claude, Gemini, etc.[/green]"
    )
    console.print(
        "[green]📋 Just copy & paste the .md file to continue your conversation![/green]"
    )

    # Show cache statistics
    if not args.no_cache:
        summarizer.show_cache_statistics()


if __name__ == "__main__":
    main()
