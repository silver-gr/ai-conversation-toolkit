#!/usr/bin/env python3
"""Show actual extraction content to compare quality."""

import sqlite3
import pickle
import json

def show_extraction(file_path, extraction, provider):
    """Display extraction in readable format."""
    print(f"\n{'='*80}")
    print(f"Provider: {provider.upper()}")
    print(f"File: {file_path}")
    print(f"Richness: {extraction.get('context', {}).get('biographical_richness', 'unknown')}")
    print(f"Main topic: {extraction.get('context', {}).get('main_topic', 'N/A')}")
    print(f"{'='*80}")

    # Show all non-empty content
    categories = ['demographics', 'work', 'health', 'interests', 'goals', 'challenges', 'relationships']

    for cat in categories:
        cat_data = extraction.get(cat, {})
        has_content = False

        for field, values in cat_data.items():
            if values:
                if isinstance(values, list) and len(values) > 0:
                    has_content = True
                elif isinstance(values, str) and values.strip():
                    has_content = True

        if has_content:
            print(f"\n{cat.upper()}:")
            for field, values in cat_data.items():
                if values:
                    if isinstance(values, list) and len(values) > 0:
                        print(f"  {field}:")
                        for v in values[:5]:  # Show first 5 items
                            print(f"    - {v}")
                        if len(values) > 5:
                            print(f"    ... and {len(values) - 5} more")
                    elif isinstance(values, str) and values.strip():
                        print(f"  {field}: {values}")

def main():
    conn = sqlite3.connect('/Users/silver/Projects/Psyence.gr/biography_cache.db')
    cursor = conn.cursor()

    print("="*80)
    print("GEMINI EXAMPLES (showing different richness levels)")
    print("="*80)

    # Get one example from each richness category for Gemini
    for richness in ['high', 'medium', 'low', 'minimal']:
        cursor.execute("""
            SELECT file_path, extraction_data
            FROM biography_cache
            WHERE provider='gemini'
            LIMIT 1000
        """)

        found = False
        for file_path, data in cursor.fetchall():
            extraction = pickle.loads(data)
            if extraction.get('context', {}).get('biographical_richness') == richness:
                show_extraction(file_path, extraction, 'gemini')
                found = True
                break

        if not found:
            print(f"\n(No {richness} examples found for Gemini)")

    print("\n\n" + "="*80)
    print("CLAUDE EXAMPLES (for comparison)")
    print("="*80)

    # Get one example from each richness category for Claude
    for richness in ['high', 'medium', 'low', 'minimal']:
        cursor.execute("""
            SELECT file_path, extraction_data
            FROM biography_cache
            WHERE provider='claude'
            LIMIT 1000
        """)

        found = False
        for file_path, data in cursor.fetchall():
            extraction = pickle.loads(data)
            extr_richness = extraction.get('context', {}).get('biographical_richness', '')

            # Handle Claude's verbose richness values
            if richness == 'high' and extr_richness.startswith('high'):
                show_extraction(file_path, extraction, 'claude')
                found = True
                break
            elif richness == 'medium' and extr_richness.startswith('medium'):
                show_extraction(file_path, extraction, 'claude')
                found = True
                break
            elif richness == 'low' and extr_richness.startswith('low'):
                show_extraction(file_path, extraction, 'claude')
                found = True
                break
            elif richness == 'minimal' and extr_richness == 'minimal':
                show_extraction(file_path, extraction, 'claude')
                found = True
                break

        if not found:
            print(f"\n(No {richness} examples found for Claude)")

    conn.close()

if __name__ == '__main__':
    main()
