#!/usr/bin/env python3
"""
Parser module for ChatGPT and Claude conversation exports.
Converts both formats to a normalized structure for processing.
"""

import json
import re
import ijson
from pathlib import Path
from datetime import datetime
from typing import Generator, Optional, Any
from dataclasses import dataclass, field


def slugify(text: str, max_len: int = 50) -> str:
    """Convert text to a valid filename slug."""
    slug = re.sub(r'[^\w\s-]', '', text.lower())
    slug = re.sub(r'[-\s]+', '-', slug).strip('-')
    return slug[:max_len]


# ChatGPT citation marker pattern: 【...】 brackets with any content inside
_CITATION_RE = re.compile(r'【[^】]*】')


def strip_chatgpt_citations(text: str) -> str:
    """Remove ChatGPT citation markers like 【turn0search2】 from text."""
    return _CITATION_RE.sub('', text)


@dataclass
class Message:
    """Normalized message structure."""
    id: str
    role: str  # 'user', 'assistant', 'system'
    content: str
    timestamp: Optional[datetime] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class Conversation:
    """Normalized conversation structure."""
    id: str
    title: str
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    messages: list[Message]
    source: str  # 'chatgpt' or 'claude'
    metadata: dict = field(default_factory=dict)

    @property
    def total_chars(self) -> int:
        """Total character count of all messages."""
        return sum(len(m.content) for m in self.messages)

    @property
    def message_count(self) -> int:
        """Number of messages."""
        return len(self.messages)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'title': self.title,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'messages': [
                {
                    'id': m.id,
                    'role': m.role,
                    'content': m.content,
                    'timestamp': m.timestamp.isoformat() if m.timestamp else None,
                    'metadata': m.metadata
                }
                for m in self.messages
            ],
            'source': self.source,
            'metadata': self.metadata,
            'total_chars': self.total_chars,
            'message_count': self.message_count
        }


def parse_timestamp(ts: Any) -> Optional[datetime]:
    """Parse various timestamp formats to datetime."""
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts
    if isinstance(ts, (int, float)):
        # Unix timestamp
        try:
            return datetime.fromtimestamp(ts)
        except (ValueError, OSError):
            return None
    if isinstance(ts, str):
        # ISO format
        try:
            # Handle various ISO formats
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

def parse_claude_conversation(conv_data: dict) -> Conversation:
    """Parse a single Claude conversation from JSON data."""
    messages = []

    for msg in conv_data.get('chat_messages', []):
        # Map Claude sender to normalized role
        sender = msg.get('sender', '')
        role = 'user' if sender == 'human' else 'assistant'

        # Get content - Claude has both 'text' and 'content' fields
        content = msg.get('text', '')
        if not content and 'content' in msg:
            # Extract from content array
            content_arr = msg.get('content', [])
            if content_arr and isinstance(content_arr, list):
                content = ' '.join(
                    c.get('text', '')
                    for c in content_arr
                    if isinstance(c, dict) and c.get('text')
                )

        if not content.strip():
            continue

        messages.append(Message(
            id=msg.get('uuid', ''),
            role=role,
            content=content,
            timestamp=parse_timestamp(msg.get('created_at')),
            metadata={
                'has_attachments': bool(msg.get('attachments')),
                'has_files': bool(msg.get('files'))
            }
        ))

    return Conversation(
        id=conv_data.get('uuid', ''),
        title=conv_data.get('name', '') or 'Untitled',
        created_at=parse_timestamp(conv_data.get('created_at')),
        updated_at=parse_timestamp(conv_data.get('updated_at')),
        messages=messages,
        source='claude',
        metadata={
            'summary': conv_data.get('summary', '')
        }
    )


def parse_claude_export(filepath: Path) -> Generator[Conversation, None, None]:
    """
    Parse Claude conversations.json export.
    Yields conversations one at a time for memory efficiency.
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    for conv_data in data:
        conv = parse_claude_conversation(conv_data)
        if conv.messages:  # Skip empty conversations
            yield conv


# =============================================================================
# CHATGPT PARSER
# =============================================================================

def traverse_chatgpt_tree(mapping: dict, node_id: str, visited: set = None) -> list[Message]:
    """
    Traverse ChatGPT's tree structure to extract messages in order.
    ChatGPT uses a tree structure where messages are linked via parent-child relationships.
    """
    if visited is None:
        visited = set()

    if node_id in visited or node_id not in mapping:
        return []

    visited.add(node_id)
    node = mapping[node_id]
    messages = []

    # Extract message from this node
    msg_data = node.get('message')
    if msg_data:
        author = msg_data.get('author', {})
        role = author.get('role', 'unknown')

        # Skip system messages that are hidden
        metadata = msg_data.get('metadata', {})
        if metadata.get('is_visually_hidden_from_conversation'):
            role = 'system_hidden'

        # Get content
        content_obj = msg_data.get('content', {})
        content_type = content_obj.get('content_type', '')
        content = ''

        if content_type == 'text':
            parts = content_obj.get('parts', [])
            content = '\n'.join(str(p) for p in parts if p)
            content = strip_chatgpt_citations(content)
        elif content_type == 'user_editable_context':
            # User profile/instructions - extract but mark as system
            profile = content_obj.get('user_profile', '')
            instructions = content_obj.get('user_instructions', '')
            content = f"[User Profile]\n{profile}\n\n[User Instructions]\n{instructions}"
            role = 'system'

        if content.strip() and role not in ('system_hidden', 'unknown'):
            messages.append(Message(
                id=msg_data.get('id', ''),
                role='user' if role == 'user' else ('assistant' if role == 'assistant' else 'system'),
                content=content,
                timestamp=parse_timestamp(msg_data.get('create_time')),
                metadata={
                    'model': metadata.get('model_slug', ''),
                    'finish_reason': metadata.get('finish_details', {}).get('type', '')
                }
            ))

    # Recurse to children
    for child_id in node.get('children', []):
        messages.extend(traverse_chatgpt_tree(mapping, child_id, visited))

    return messages


def parse_chatgpt_conversation(conv_data: dict) -> Conversation:
    """Parse a single ChatGPT conversation from JSON data."""
    mapping = conv_data.get('mapping', {})

    # Find root node (one with no parent)
    root_id = None
    for node_id, node in mapping.items():
        if node.get('parent') is None:
            root_id = node_id
            break

    messages = []
    if root_id:
        messages = traverse_chatgpt_tree(mapping, root_id)

    # Filter to only user/assistant messages for main content
    main_messages = [m for m in messages if m.role in ('user', 'assistant')]

    return Conversation(
        id=conv_data.get('id', conv_data.get('conversation_id', '')),
        title=conv_data.get('title', '') or 'Untitled',
        created_at=parse_timestamp(conv_data.get('create_time')),
        updated_at=parse_timestamp(conv_data.get('update_time')),
        messages=main_messages,
        source='chatgpt',
        metadata={
            'has_system_messages': any(m.role == 'system' for m in messages),
            'total_nodes': len(mapping)
        }
    )


def parse_chatgpt_export_streaming(filepath: Path) -> Generator[Conversation, None, None]:
    """
    Parse ChatGPT conversations.json using streaming for large files.
    Uses ijson for memory-efficient parsing of massive JSON files.
    """
    try:
        with open(filepath, 'rb') as f:
            # Stream parse the array elements
            parser = ijson.items(f, 'item')
            for conv_data in parser:
                conv = parse_chatgpt_conversation(conv_data)
                if conv.messages:
                    yield conv
    except Exception as e:
        # Fallback to regular parsing if streaming fails
        print(f"  Warning: Streaming parse failed ({e}), falling back to standard parse")
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for conv_data in data:
            conv = parse_chatgpt_conversation(conv_data)
            if conv.messages:
                yield conv


def parse_chatgpt_export(filepath: Path) -> Generator[Conversation, None, None]:
    """
    Parse ChatGPT conversations.json export.
    Automatically uses streaming for large files.
    """
    file_size = filepath.stat().st_size

    # Use streaming for files larger than 50MB
    if file_size > 50 * 1024 * 1024:
        print(f"  Large file detected ({file_size / 1024 / 1024:.1f} MB), using streaming parser...")
        yield from parse_chatgpt_export_streaming(filepath)
    else:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for conv_data in data:
            conv = parse_chatgpt_conversation(conv_data)
            if conv.messages:
                yield conv


# =============================================================================
# UNIFIED PARSER
# =============================================================================

def detect_source(filepath: Path) -> str:
    """Detect whether file is ChatGPT or Claude export."""
    with open(filepath, 'r', encoding='utf-8') as f:
        # Read first 2000 chars to detect format
        sample = f.read(2000)

    if '"chat_messages"' in sample:
        return 'claude'
    elif '"mapping"' in sample:
        return 'chatgpt'
    else:
        raise ValueError(f"Could not detect source format for {filepath}")


def parse_export(filepath: Path) -> Generator[Conversation, None, None]:
    """
    Parse any conversation export file.
    Auto-detects format and uses appropriate parser.
    """
    source = detect_source(filepath)

    if source == 'claude':
        yield from parse_claude_export(filepath)
    else:
        yield from parse_chatgpt_export(filepath)


# =============================================================================
# CLI
# =============================================================================

def main():
    """Test the parser with sample data."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python parser.py <conversations.json>")
        return 1

    filepath = Path(sys.argv[1])
    if not filepath.exists():
        print(f"File not found: {filepath}")
        return 1

    print(f"Parsing: {filepath}")
    print(f"Detected format: {detect_source(filepath)}")
    print()

    count = 0
    total_messages = 0
    total_chars = 0

    for conv in parse_export(filepath):
        count += 1
        total_messages += conv.message_count
        total_chars += conv.total_chars

        if count <= 5:  # Show first 5 conversations
            print(f"[{count}] {conv.title}")
            print(f"    Messages: {conv.message_count}, Chars: {conv.total_chars}")
            print(f"    Created: {conv.created_at}")
            if conv.messages:
                preview = conv.messages[0].content[:100].replace('\n', ' ')
                print(f"    Preview: {preview}...")
            print()

    print("=" * 60)
    print(f"Total conversations: {count}")
    print(f"Total messages:      {total_messages}")
    print(f"Total characters:    {total_chars:,}")
    print(f"Avg chars/conv:      {total_chars // max(count, 1):,}")

    return 0


if __name__ == '__main__':
    exit(main())
