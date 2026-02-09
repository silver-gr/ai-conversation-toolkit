#!/usr/bin/env python3
"""Check quality of Gemini biographical extractions vs Claude."""

import sqlite3
import pickle
from collections import defaultdict

def analyze_extraction(extraction):
    """Analyze the content of an extraction."""
    stats = {
        'richness': extraction.get('context', {}).get('biographical_richness', 'unknown'),
        'main_topic': extraction.get('context', {}).get('main_topic', 'unknown'),
        'categories_with_data': [],
        'total_items': 0,
        'fields_with_data': []
    }

    categories = ['work', 'health', 'interests', 'goals', 'challenges', 'relationships', 'demographics']

    for category in categories:
        cat_data = extraction.get(category, {})
        category_has_data = False

        for field, values in cat_data.items():
            if values:
                if isinstance(values, list) and len(values) > 0:
                    stats['total_items'] += len(values)
                    stats['fields_with_data'].append(f"{category}.{field}")
                    category_has_data = True
                elif isinstance(values, str) and values.strip():
                    stats['total_items'] += 1
                    stats['fields_with_data'].append(f"{category}.{field}")
                    category_has_data = True

        if category_has_data:
            stats['categories_with_data'].append(category)

    return stats

def print_extraction_details(file_path, extraction):
    """Print detailed information about an extraction."""
    print(f"\n{'='*80}")
    print(f"File: {file_path}")
    print(f"{'='*80}")

    context = extraction.get('context', {})
    print(f"\nContext:")
    print(f"  Richness: {context.get('biographical_richness', 'unknown')}")
    print(f"  Main topic: {context.get('main_topic', 'unknown')}")

    categories = ['work', 'health', 'interests', 'goals', 'challenges', 'relationships', 'demographics']

    has_content = False
    for category in categories:
        cat_data = extraction.get(category, {})
        category_items = []

        for field, values in cat_data.items():
            if values:
                if isinstance(values, list) and len(values) > 0:
                    has_content = True
                    # Show first 2 items as examples
                    examples = values[:2]
                    count_str = f" ({len(values)} total)" if len(values) > 2 else ""
                    category_items.append(f"    {field}: {examples}{count_str}")
                elif isinstance(values, str) and values.strip():
                    has_content = True
                    preview = values[:100] + "..." if len(values) > 100 else values
                    category_items.append(f"    {field}: {preview}")

        if category_items:
            print(f"\n  {category.upper()}:")
            for item in category_items:
                print(item)

    if not has_content:
        print("\n  [NO BIOGRAPHICAL CONTENT EXTRACTED]")

def main():
    conn = sqlite3.connect('/Users/silver/Projects/Psyence.gr/biography_cache.db')
    cursor = conn.cursor()

    # Get samples from both providers
    print("\n" + "="*80)
    print("GEMINI EXTRACTIONS (3 random samples)")
    print("="*80)

    cursor.execute("""
        SELECT file_path, extraction_data
        FROM biography_cache
        WHERE provider='gemini'
        ORDER BY RANDOM()
        LIMIT 3
    """)
    gemini_samples = cursor.fetchall()

    for file_path, data in gemini_samples:
        extraction = pickle.loads(data)
        print_extraction_details(file_path, extraction)

    print("\n\n" + "="*80)
    print("CLAUDE EXTRACTIONS (3 random samples for comparison)")
    print("="*80)

    cursor.execute("""
        SELECT file_path, extraction_data
        FROM biography_cache
        WHERE provider='claude'
        ORDER BY RANDOM()
        LIMIT 3
    """)
    claude_samples = cursor.fetchall()

    for file_path, data in claude_samples:
        extraction = pickle.loads(data)
        print_extraction_details(file_path, extraction)

    # Statistical comparison
    print("\n\n" + "="*80)
    print("STATISTICAL COMPARISON")
    print("="*80)

    # Analyze all Gemini extractions
    cursor.execute("SELECT extraction_data FROM biography_cache WHERE provider='gemini'")
    gemini_all = cursor.fetchall()

    gemini_stats = {
        'total': len(gemini_all),
        'empty': 0,
        'low': 0,
        'moderate': 0,
        'high': 0,
        'rich': 0,
        'avg_items': 0,
        'avg_categories': 0
    }

    total_items = 0
    total_categories = 0

    for (data,) in gemini_all:
        extraction = pickle.loads(data)
        stats = analyze_extraction(extraction)
        richness = stats['richness']

        if richness == 'none':
            gemini_stats['empty'] += 1
        elif richness == 'low':
            gemini_stats['low'] += 1
        elif richness == 'moderate':
            gemini_stats['moderate'] += 1
        elif richness == 'high':
            gemini_stats['high'] += 1
        elif richness == 'rich':
            gemini_stats['rich'] += 1

        total_items += stats['total_items']
        total_categories += len(stats['categories_with_data'])

    gemini_stats['avg_items'] = total_items / gemini_stats['total'] if gemini_stats['total'] > 0 else 0
    gemini_stats['avg_categories'] = total_categories / gemini_stats['total'] if gemini_stats['total'] > 0 else 0

    # Analyze all Claude extractions
    cursor.execute("SELECT extraction_data FROM biography_cache WHERE provider='claude'")
    claude_all = cursor.fetchall()

    claude_stats = {
        'total': len(claude_all),
        'empty': 0,
        'low': 0,
        'moderate': 0,
        'high': 0,
        'rich': 0,
        'avg_items': 0,
        'avg_categories': 0
    }

    total_items = 0
    total_categories = 0

    for (data,) in claude_all:
        extraction = pickle.loads(data)
        stats = analyze_extraction(extraction)
        richness = stats['richness']

        if richness == 'none':
            claude_stats['empty'] += 1
        elif richness == 'low':
            claude_stats['low'] += 1
        elif richness == 'moderate':
            claude_stats['moderate'] += 1
        elif richness == 'high':
            claude_stats['high'] += 1
        elif richness == 'rich':
            claude_stats['rich'] += 1

        total_items += stats['total_items']
        total_categories += len(stats['categories_with_data'])

    claude_stats['avg_items'] = total_items / claude_stats['total'] if claude_stats['total'] > 0 else 0
    claude_stats['avg_categories'] = total_categories / claude_stats['total'] if claude_stats['total'] > 0 else 0

    # Print comparison
    print(f"\nGEMINI ({gemini_stats['total']} extractions):")
    print(f"  Empty (none):     {gemini_stats['empty']:4d} ({gemini_stats['empty']/gemini_stats['total']*100:5.1f}%)")
    print(f"  Low:              {gemini_stats['low']:4d} ({gemini_stats['low']/gemini_stats['total']*100:5.1f}%)")
    print(f"  Moderate:         {gemini_stats['moderate']:4d} ({gemini_stats['moderate']/gemini_stats['total']*100:5.1f}%)")
    print(f"  High:             {gemini_stats['high']:4d} ({gemini_stats['high']/gemini_stats['total']*100:5.1f}%)")
    print(f"  Rich:             {gemini_stats['rich']:4d} ({gemini_stats['rich']/gemini_stats['total']*100:5.1f}%)")
    print(f"  Avg items/extraction: {gemini_stats['avg_items']:.1f}")
    print(f"  Avg categories/extraction: {gemini_stats['avg_categories']:.1f}")

    print(f"\nCLAUDE ({claude_stats['total']} extractions):")
    print(f"  Empty (none):     {claude_stats['empty']:4d} ({claude_stats['empty']/claude_stats['total']*100:5.1f}%)")
    print(f"  Low:              {claude_stats['low']:4d} ({claude_stats['low']/claude_stats['total']*100:5.1f}%)")
    print(f"  Moderate:         {claude_stats['moderate']:4d} ({claude_stats['moderate']/claude_stats['total']*100:5.1f}%)")
    print(f"  High:             {claude_stats['high']:4d} ({claude_stats['high']/claude_stats['total']*100:5.1f}%)")
    print(f"  Rich:             {claude_stats['rich']:4d} ({claude_stats['rich']/claude_stats['total']*100:5.1f}%)")
    print(f"  Avg items/extraction: {claude_stats['avg_items']:.1f}")
    print(f"  Avg categories/extraction: {claude_stats['avg_categories']:.1f}")

    conn.close()

if __name__ == '__main__':
    main()
