#!/usr/bin/env python3
"""Show detailed content from Gemini extractions to assess quality."""

import sqlite3
import pickle
import json

def main():
    conn = sqlite3.connect('/Users/silver/Projects/Psyence.gr/biography_cache.db')
    cursor = conn.cursor()

    # Get a few high-richness Gemini extractions
    print("="*80)
    print("HIGH-RICHNESS GEMINI EXTRACTIONS")
    print("="*80)

    cursor.execute("""
        SELECT file_path, extraction_data
        FROM biography_cache
        WHERE provider='gemini'
        ORDER BY RANDOM()
        LIMIT 2
    """)

    for file_path, data in cursor.fetchall():
        extraction = pickle.loads(data)
        richness = extraction.get('context', {}).get('biographical_richness', 'unknown')

        if richness in ['high', 'rich']:
            print(f"\n{'='*80}")
            print(f"File: {file_path}")
            print(f"Richness: {richness}")
            print(f"{'='*80}")
            print(json.dumps(extraction, indent=2, ensure_ascii=False)[:2000])
            print("\n... (truncated)")

    # Get a low-richness example
    print("\n\n" + "="*80)
    print("LOW-RICHNESS GEMINI EXTRACTION")
    print("="*80)

    cursor.execute("""
        SELECT file_path, extraction_data
        FROM biography_cache
        WHERE provider='gemini'
        ORDER BY RANDOM()
        LIMIT 1
    """)

    for file_path, data in cursor.fetchall():
        extraction = pickle.loads(data)
        richness = extraction.get('context', {}).get('biographical_richness', 'unknown')

        if richness == 'low':
            print(f"\nFile: {file_path}")
            print(f"Richness: {richness}")
            print(json.dumps(extraction, indent=2, ensure_ascii=False)[:2000])
            print("\n... (truncated)")

    # Compare to a Claude extraction
    print("\n\n" + "="*80)
    print("CLAUDE EXTRACTION (for comparison)")
    print("="*80)

    cursor.execute("""
        SELECT file_path, extraction_data
        FROM biography_cache
        WHERE provider='claude'
        ORDER BY RANDOM()
        LIMIT 1
    """)

    for file_path, data in cursor.fetchall():
        extraction = pickle.loads(data)
        richness = extraction.get('context', {}).get('biographical_richness', 'unknown')

        if richness in ['high', 'rich', 'moderate']:
            print(f"\nFile: {file_path}")
            print(f"Richness: {richness}")
            print(json.dumps(extraction, indent=2, ensure_ascii=False)[:2000])
            print("\n... (truncated)")

    # Get distribution by richness level
    print("\n\n" + "="*80)
    print("RICHNESS DISTRIBUTION")
    print("="*80)

    for provider in ['gemini', 'claude']:
        print(f"\n{provider.upper()}:")
        cursor.execute("""
            SELECT extraction_data FROM biography_cache WHERE provider=?
        """, (provider,))

        richness_counts = {'none': 0, 'minimal': 0, 'low': 0, 'moderate': 0, 'high': 0, 'rich': 0, 'unknown': 0}

        for (data,) in cursor.fetchall():
            extraction = pickle.loads(data)
            richness = extraction.get('context', {}).get('biographical_richness', 'unknown')
            richness_counts[richness] = richness_counts.get(richness, 0) + 1

        total = sum(richness_counts.values())
        for level, count in sorted(richness_counts.items()):
            pct = count/total*100 if total > 0 else 0
            print(f"  {level:12s}: {count:4d} ({pct:5.1f}%)")

    conn.close()

if __name__ == '__main__':
    main()
