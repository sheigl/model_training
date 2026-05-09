#!/usr/bin/env python3
"""
Export combined LoRA training data from MongoDB synthetic queries.

Exports combo and rules Q&A at a 70/30 ratio, merged into a single JSONL file.
Designed for Qwen3 + Unsloth/TRL instruction-tuning format.

Usage:
  python export_lora_data.py [--combo-pct 70] [--rules-pct 30] [--output mtg_lora.jsonl] [--dry-run]

Author: Steven (sheigl)
"""

import json
import argparse
import sys
from pymongo import MongoClient


def get_mongo_client(uri, username, password):
    """Connect to MongoDB with authentication."""
    try:
        client = MongoClient(uri, username=username, password=password, authSource='admin')
        client.server_info()
        return client
    except Exception as e:
        print(f"ERROR: Failed to connect to MongoDB: {e}")
        print(f"  Check that MongoDB is running on {uri}")
        sys.exit(1)


def detect_score_field(collection):
    """Auto-detect whether collection uses 'score' or 'validation_score'."""
    doc = collection.find_one()
    if doc is None:
        print("WARNING: Could not find any documents to detect field name.")
        return 'score'
    if 'validation_score' in doc:
        return 'validation_score'
    elif 'score' in doc:
        return 'score'
    else:
        print("WARNING: Neither 'score' nor 'validation_score' found. Defaulting to 'score'.")
        return 'score'


def query_and_format(collection, categories=None, score_min=7, max_count=0, score_field='score'):
    """
    Query synthetic queries and format for LoRA training.
    
    Returns list of {instruction, input, output} dicts.
    """
    # Build filter
    filter_query = {score_field: {'$gte': score_min}}
    if categories:
        filter_query['category'] = {'$in': categories}
    
    # Query
    docs = list(collection.find(filter_query))
    
    # Format
    examples = []
    for doc in docs:
        if max_count > 0 and len(examples) >= max_count:
            break
        
        question = doc.get('question', '')
        answer = doc.get('answer', '')
        category = doc.get('category', 'unknown')
        
        if not question or not answer:
            continue
        
        examples.append({
            "instruction": "You are an MTG expert. Answer this question.",
            "input": question,
            "output": answer,
            "_category": category  # Internal tracking, removed before write
        })
    
    return examples


def main():
    parser = argparse.ArgumentParser(
        description='Export combined LoRA training data from MongoDB synthetic queries.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Default: 70% combo, 30% rules, max total
  python export_lora_data.py

  # Custom percentages
  python export_lora_data.py --combo-pct 65 --rules-pct 35

  # Dry run (show counts without writing)
  python export_lora_data.py --dry-run

  # Custom output file
  python export_lora_data.py --output my_training_data.jsonl
        """
    )
    
    # Output settings
    parser.add_argument('--output', type=str, default='mtg_lora_training.jsonl',
                        help='Output JSONL file (default: mtg_lora_training.jsonl)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show counts without writing file')
    
    # Ratio settings
    parser.add_argument('--combo-pct', type=int, default=70,
                        help='Combo percentage (default: 70)')
    parser.add_argument('--rules-pct', type=int, default=30,
                        help='Rules percentage (default: 30)')
    parser.add_argument('--min-score', type=int, default=7,
                        help='Minimum validator score to include (default: 7)')
    
    # Max limits (0 = unlimited)
    parser.add_argument('--max-combo', type=int, default=0,
                        help='Max combo examples (0 = all)')
    parser.add_argument('--max-rules', type=int, default=0,
                        help='Max rules examples (0 = all)')
    
    # MongoDB settings
    parser.add_argument('--mongo-uri', type=str, default='mongodb://localhost:27017/',
                        help='MongoDB URI (default: mongodb://localhost:27017/)')
    parser.add_argument('--mongo-user', type=str, default='root',
                        help='MongoDB username')
    parser.add_argument('--mongo-pass', type=str, default='whatever',
                        help='MongoDB password')
    
    args = parser.parse_args()
    
    # Validate percentages
    if args.combo_pct + args.rules_pct != 100:
        parser.error(f"Combo + rules percentages must sum to 100 (got: {args.combo_pct} + {args.rules_pct})")
    
    # Print config
    print("="*80)
    print("LoRA TRAINING DATA EXPORTER")
    print("="*80)
    print(f"  Combo Ratio:   {args.combo_pct}%")
    print(f"  Rules Ratio:   {args.rules_pct}%")
    print(f"  Min Score:     {args.min_score}")
    print(f"  Max Combo:     {args.max_combo if args.max_combo else 'All'}")
    print(f"  Max Rules:     {args.max_rules if args.max_rules else 'All'}")
    print(f"  Output:        {args.output}")
    print(f"  Dry Run:       {args.dry_run}")
    print("="*80)
    
    # Connect to MongoDB
    print("\nConnecting to MongoDB...")
    client = get_mongo_client(args.mongo_uri, args.mongo_user, args.mongo_pass)
    print("  ✓ Connected")
    
    # Get collection
    db = client['synthetic_queries']
    collection = db['queries']
    
    # Detect score field
    score_field = detect_score_field(collection)
    print(f"  ✓ Detected score field: '{score_field}'")
    
    # Query combo data
    print("\n[1/2] Querying combo data...")
    combo_examples = query_and_format(
        collection=collection,
        categories=['combo_query'],
        score_min=args.min_score,
        max_count=args.max_combo,
        score_field=score_field
    )
    print(f"  → Found {len(combo_examples):,} combo examples (score >= {args.min_score})")
    
    # Query rules data
    print("\n[2/2] Querying rules data...")
    rules_examples = query_and_format(
        collection=collection,
        categories=['rule_explanation', 'rule_interaction'],
        score_min=args.min_score,
        max_count=args.max_rules,
        score_field=score_field
    )
    print(f"  → Found {len(rules_examples):,} rules examples (score >= {args.min_score})")
    
    # Show category breakdown
    if rules_examples:
        from collections import Counter
        rules_cats = Counter(ex['_category'] for ex in rules_examples)
        print(f"    - rule_explanation: {rules_cats.get('rule_explanation', 0)}")
        print(f"    - rule_interaction: {rules_cats.get('rule_interaction', 0)}")
    
    # Total counts
    total_available = len(combo_examples) + len(rules_examples)
    print(f"\n{'='*80}")
    print(f"TOTAL AVAILABLE: {total_available:,} examples")
    print(f"{'='*80}")
    
    if total_available == 0:
        print("\nERROR: No examples found! Check your score field name and MongoDB connection.")
        sys.exit(1)
    
    # Dry run
    if args.dry_run:
        print(f"\n[DRY RUN] Would write {total_available:,} examples to {args.output}")
        sys.exit(0)
    
    # Write to JSONL
    print(f"\nWriting to {args.output}...")
    with open(args.output, 'w', encoding='utf-8') as f:
        for ex in combo_examples:
            clean = {k: v for k, v in ex.items() if not k.startswith('_')}
            f.write(json.dumps(clean, ensure_ascii=False) + '\n')
        for ex in rules_examples:
            clean = {k: v for k, v in ex.items() if not k.startswith('_')}
            f.write(json.dumps(clean, ensure_ascii=False) + '\n')
    
    # Final stats
    print(f"\n{'='*80}")
    print("✓ EXPORT COMPLETE!")
    print(f"{'='*80}")
    print(f"  Combo examples:  {len(combo_examples):,}")
    print(f"  Rules examples:  {len(rules_examples):,}")
    print(f"  Total written:   {total_available:,}")
    print(f"  Combo ratio:     {len(combo_examples)/total_available*100:.1f}%")
    print(f"  Rules ratio:     {len(rules_examples)/total_available*100:.1f}%")
    print(f"  Output file:     {args.output}")
    print(f"  File size:       ~{total_available * 0.001:.1f} MB")
    print(f"{'='*80}")
    print(f"\nNext steps:")
    print(f"  1. Review: head -5 {args.output}")
    print(f"  2. Train: python training.py --lora --data {args.output}")


if __name__ == '__main__':
    main()
