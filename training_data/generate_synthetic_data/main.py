#!/usr/bin/env python3
import sys
from typing import Collection

from generate_archetypes import * 
from generate_article_qa import * 
from generate_budget_alternatives import * 
from generate_card_search_queries import * 
from generate_color_identity_questions import * 
from generate_color_staples import * 
from generate_combo_queries import * 
from generate_commander_building import * 
from generate_commander_knowledge import * 
from generate_comparison_questions import * 
from generate_deckbuilding_theory import * 
from generate_game_theory import * 
from generate_glossary_with_examples import * 
from generate_guide_qa import * 
from generate_meta_knowledge import * 
from generate_multi_card_usage import * 
from generate_quick_guidelines import * 
from generate_reverse_lookup_questions import * 
from generate_rule_edge_cases import * 
from generate_rule_explanations import * 
from generate_rule_interactions import * 
from generate_rule_why_questions import * 
from generate_rules_scenarios import * 
from generate_salt_questions import * 
from generate_staple_analysis import * 
from generate_synergy_questions import * 
from generate_terminology_questions import *
from dotenv import load_dotenv
# Load environment variables from .env file
load_dotenv()

"""
Synthetic Query Generator - Saves to MongoDB

Generates natural query examples using Qwen 14B and stores them in MongoDB.
The main extraction script then treats these as another data source!

Process:
1. Use Qwen 14B to generate Q&A from existing MongoDB data
2. Validate outputs
3. Save to synthetic_queries.queries collection
4. Main extraction script pulls from this collection like any other source

MongoDB Schema:
{
  "question": "What combos can I do with Pitiless Plunderer?",
  "answer": "Pitiless Plunderer combos with...",
  "category": "combo_query",  // or "card_search", "commander_rules", "multi_card"
  "source_data": ["card_name", ...],  // Cards/combos referenced
  "validated": true,
  "needs_review": false,
  "generated_at": "2026-02-13T..."
}
"""

from pymongo import MongoClient
import json
import random
import re
from datetime import datetime
import argparse
import time
import ollama
from common import *
from scryfall_mongodb import ScryfallMongo

# =============================================================================
# MONGODB SETUP
# =============================================================================

def get_mongo_collections(uri, username, password):
    """Connect and get all collections"""
    client = MongoClient(uri, username=username, password=password, authSource='admin')
    
    # Existing collections (source data)
    cards = client['mtg_json']['cards']
    combos = client['commander_spellbook']['variants']
    
    # New collection (synthetic data)
    synthetic = client['synthetic_queries']['queries']
    
    commanders = client['edhrec']['commanders']
    articles = client['edhrec']['articles']
    guides = client['edhrec']['guides']
    game_changers = client['edhrec']['game-changers']

    # Top cards by color
    top_cards = {
        'black':     client['edhrec']['top-black'],
        'blue':      client['edhrec']['top-blue'],
        'colorless': client['edhrec']['top-colorless'],
        'green':     client['edhrec']['top-green'],
        'red':       client['edhrec']['top-red'],
        'white':     client['edhrec']['top-white'],
    }

    # Rules collections
    rules = client['mtg_rules']['rules']
    glossary = client['mtg_rules']['glossary']

    return cards, combos, synthetic, commanders, rules, glossary, articles, guides, game_changers, top_cards, ScryfallMongo(client=client)


def save_to_mongo(synthetic_collection, examples, batch_size=500):
    """
    Save synthetic examples to MongoDB, skipping exact duplicates.

    Uses a hash of (question, answer) as a unique key so re-running
    the script never creates duplicate entries.
    """
    import hashlib

    if not examples:
        return

    print(f"\nSaving {len(examples):,} examples to MongoDB (dedup-safe)...")

    # Ensure unique index exists on content_hash (idempotent)
    try:
        synthetic_collection.create_index('content_hash', unique=True, background=True)
    except Exception:
        pass  # Index may already exist

    inserted = 0
    skipped = 0

    for i in range(0, len(examples), batch_size):
        batch = examples[i:i+batch_size]

        # Add metadata and content hash
        for ex in batch:
            q = ex.get('question', '')
            a = ex.get('answer', '')
            ex['content_hash'] = hashlib.sha256(f"{q}||{a}".encode()).hexdigest()
            ex['generated_at'] = datetime.utcnow()
            ex['version'] = 1

        # Insert only documents whose hash doesn't already exist
        from pymongo import UpdateOne
        ops = [
            UpdateOne(
                {'content_hash': ex['content_hash']},
                {'$setOnInsert': ex},
                upsert=True
            )
            for ex in batch
        ]

        try:
            result = synthetic_collection.bulk_write(ops, ordered=False)
            batch_inserted = result.upserted_count
            batch_skipped = len(batch) - batch_inserted
            inserted += batch_inserted
            skipped += batch_skipped
            print(f"  → Batch {i//batch_size + 1}: {batch_inserted} inserted, {batch_skipped} skipped (already existed)")
        except Exception as e:
            print(f"  ⚠️  Batch error: {e}")

    print(f"  ✓ Done: {inserted:,} inserted, {skipped:,} skipped as duplicates")




# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mongo-uri', default='mongodb://localhost:27017/')
    parser.add_argument('--mongo-user', default='root')
    parser.add_argument('--mongo-pass', default='whatever')
    
    # Original formats
    parser.add_argument('--combo-queries', type=int, default=0)
    parser.add_argument('--card-search', type=int, default=0)
    parser.add_argument('--commander', type=int, default=0)
    parser.add_argument('--multi-card', type=int, default=0)
    parser.add_argument('--model', type=str, default='qwen2.5:14b', help='Ollama model name for generation')
    parser.add_argument('--validation-model', type=str, default='qwen2.5:14b', help='Ollama model name for validation')
    
    # Phase 1 formats
    parser.add_argument('--comparison', type=int, default=0, help='Card comparison questions')
    parser.add_argument('--reverse-lookup', type=int, default=0, help='Feature-to-card lookup')
    parser.add_argument('--synergy', type=int, default=0, help='Card synergy discovery')
    parser.add_argument('--budget', type=int, default=0, help='Budget alternatives')
    parser.add_argument('--color-identity', type=int, default=0, help='Color identity questions')
    parser.add_argument('--guidelines', type=int, default=0, help='Deckbuilding guidelines')
    parser.add_argument('--terminology', type=int, default=0, help='MTG terminology/slang')

    # Phase 2 formats (new)
    parser.add_argument('--deckbuilding-theory', type=int, default=0, help='Deckbuilding theory and card evaluation')
    parser.add_argument('--commander-building', type=int, default=0, help='Commander archetype construction')
    parser.add_argument('--rules-scenarios', type=int, default=0, help='Scenario-based rules reasoning questions')
    parser.add_argument('--archetypes', type=int, default=0, help='Deck archetype strategy questions')
    parser.add_argument('--game-theory', type=int, default=0, help='In-game decision making and sequencing')
    parser.add_argument('--meta-knowledge', type=int, default=0, help='cEDH, power levels, meta evaluation')

    # Rules-grounded formats (Phase 3)
    parser.add_argument('--rule-explanations', type=int, default=0, help='Q&A grounded in specific rule text')
    parser.add_argument('--rule-interactions', type=int, default=0, help='Scenarios where two rules interact')
    parser.add_argument('--glossary-examples', type=int, default=0, help='Glossary terms with in-game examples')
    parser.add_argument('--rule-edge-cases', type=int, default=0, help='Tricky edge case questions from complex rules')
    parser.add_argument('--rule-why', type=int, default=0, help='Backward-reasoning why-does-this-work questions')

    # EDHREC-grounded formats (Phase 4)
    parser.add_argument('--article-qa', type=int, default=0, help='Q&A synthesized from EDHREC articles')
    parser.add_argument('--guide-qa', type=int, default=0, help='Q&A synthesized from EDHREC guides')
    parser.add_argument('--staple-analysis', type=int, default=0, help='Why game-changer cards are Commander staples')
    parser.add_argument('--color-staples', type=int, default=0, help='Top cards by color in Commander')
    parser.add_argument('--salt-questions', type=int, default=0, help='Controversial/salty card analysis')

    # Preset modes
    parser.add_argument('--phase1', action='store_true', help='Generate all Phase 1 formats (15K total)')
    parser.add_argument('--phase2', action='store_true', help='Generate all Phase 2 formats (13K total) - strategy/theory focus')
    parser.add_argument('--phase3', action='store_true', help='Generate all Phase 3 formats (8K total) - rules-grounded')
    parser.add_argument('--phase4', action='store_true', help='Generate all Phase 4 formats (9K total) - EDHREC grounded')
    parser.add_argument('--all', action='store_true', help='Generate all formats (Phase 1 + Phase 2 + Phase 3 + Phase 4)')
    
    args = parser.parse_args()
    
    models: dict[ModelType, Model] = {
        ModelType.GENERATION: Model(name=args.model, type=ModelType.GENERATION),
        ModelType.VALIDATION: Model(name=args.validation_model, type=ModelType.VALIDATION)
    }
    
    print(f"\n⚡ Using {models[ModelType.GENERATION].name} for text generation and {models[ModelType.VALIDATION].name} for validation")
    
    # Apply presets
    if args.phase1: #args.phase1:
        args.comparison = 2000
        args.reverse_lookup = 3000
        args.synergy = 3000
        args.budget = 2000
        args.color_identity = 2000
        args.guidelines = 2000
        args.terminology = 1000
        print("\n🔥 PHASE 1 MODE: Generating 15K high-value examples")

    if args.phase2:
        args.deckbuilding_theory = 2000
        args.commander_building = 3000
        args.rules_scenarios = 3000
        args.archetypes = 1500
        args.game_theory = 1500
        args.meta_knowledge = 1000
        print("\n🔥 PHASE 2 MODE: Generating 13K strategy/theory examples")

    if args.phase3:
        args.rule_explanations = 2000
        args.rule_interactions = 2000
        args.glossary_examples = 1500
        args.rule_edge_cases = 1500
        args.rule_why = 1000
        print("\n🔥 PHASE 3 MODE: Generating 8K rules-grounded examples")

    if args.phase4:
        args.article_qa = 2000
        args.guide_qa = 2000
        args.staple_analysis = 2000
        args.color_staples = 2000
        args.salt_questions = 1000
        print("\n🔥 PHASE 4 MODE: Generating 9K EDHREC-grounded examples")

    if args.all:
        args.combo_queries = 5000
        args.card_search = 3000
        args.commander = 200
        args.multi_card = 2000
        args.comparison = 2000
        args.reverse_lookup = 3000
        args.synergy = 4000
        args.budget = 2000
        args.color_identity = 2000
        args.guidelines = 3000
        args.terminology = 1000
        args.deckbuilding_theory = 2000
        args.commander_building = 3000
        args.rules_scenarios = 3000
        args.archetypes = 1500
        args.game_theory = 1500
        args.meta_knowledge = 1000
        args.rule_explanations = 2000
        args.rule_interactions = 2000
        args.glossary_examples = 1500
        args.rule_edge_cases = 1500
        args.rule_why = 1000
        args.article_qa = 2000
        args.guide_qa = 2000
        args.staple_analysis = 2000
        args.color_staples = 2000
        args.salt_questions = 1000
        print("\n🚀 ALL MODE: Generating 57K+ examples (Phase 1 + Phase 2 + Phase 3 + Phase 4)")
    
    print("="*80)
    print("SYNTHETIC QUERY GENERATION → MongoDB")
    print("="*80)
    
    # Connect to MongoDB
    print("\nConnecting to MongoDB...")
    cards, combos, synthetic, commanders, rules, glossary, articles, guides, game_changers, top_cards, scryfall_client = get_mongo_collections(args.mongo_uri, args.mongo_user, args.mongo_pass)
    print("  ✓ Connected")
    
    # Generate all synthetic data
    all_documents = []
    
    # Original formats
    if args.combo_queries > 0:
        generate_combo_queries(
            combos, 
            cards, 
            scryfall_client, 
            lambda doc: save_to_mongo(synthetic, [doc]), 
            models, 
            target_count=args.combo_queries)
        #save_to_mongo(synthetic, docs)  # Save incrementally after each format
    
    if args.card_search > 0:
        docs = generate_card_search_queries(cards, args.card_search)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} card search documents")
        save_to_mongo(synthetic, docs)  # Save incrementally after each format
    
    if args.commander > 0:
        docs = generate_commander_knowledge(args.commander)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} commander knowledge documents")
        save_to_mongo(synthetic, docs)  # Save incrementally after each format
    
    if args.multi_card > 0:
        docs = generate_multi_card_usage(combos, args.multi_card)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} multi-card usage documents")
        save_to_mongo(synthetic, docs)  # Save incrementally after each format
    
    if args.comparison > 0:
        docs = generate_comparison_questions(cards, args.comparison)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} comparison question documents")
        save_to_mongo(synthetic, docs)  # Save incrementally after each format
    
    if args.reverse_lookup > 0:
        docs = generate_reverse_lookup_questions(cards, args.reverse_lookup)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} reverse lookup question documents")
        save_to_mongo(synthetic, docs)  # Save incrementally after each format
    
    if args.synergy > 0:
        docs = generate_synergy_questions(cards, combos, args.synergy)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} synergy question documents")
        save_to_mongo(synthetic, docs)  # Save incrementally after each format
    
    if args.budget > 0:
        docs = generate_budget_alternatives(cards, args.budget)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} budget alternative question documents")
        save_to_mongo(synthetic, docs)  # Save incrementally after each format
    
    if args.color_identity > 0:
        docs = generate_color_identity_questions(cards, commanders, args.color_identity)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} color identity question documents")
        save_to_mongo(synthetic, docs)  # Save incrementally after each format
    
    if args.guidelines > 0:
        docs = generate_quick_guidelines(args.guidelines)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} guideline question documents")
        save_to_mongo(synthetic, docs)  # Save incrementally after each format
    
    if args.terminology > 0:
        docs = generate_terminology_questions(args.terminology)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} terminology question documents")
        save_to_mongo(synthetic, docs)  # Save incrementally after each format

    # Phase 2: Strategy/Theory formats
    if args.deckbuilding_theory > 0:
        docs = generate_deckbuilding_theory(args.deckbuilding_theory)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} deckbuilding theory documents")
        save_to_mongo(synthetic, docs)

    if args.commander_building > 0:
        docs = generate_commander_building(args.commander_building)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} commander building documents")
        save_to_mongo(synthetic, docs)

    if args.rules_scenarios > 0:
        docs = generate_rules_scenarios(args.rules_scenarios)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} rules scenario documents")
        save_to_mongo(synthetic, docs)

    if args.archetypes > 0:
        docs = generate_archetypes(args.archetypes)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} archetype documents")
        save_to_mongo(synthetic, docs)

    if args.game_theory > 0:
        docs = generate_game_theory(args.game_theory)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} game theory documents")
        save_to_mongo(synthetic, docs)

    if args.meta_knowledge > 0:
        docs = generate_meta_knowledge(args.meta_knowledge)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} meta knowledge documents")
        save_to_mongo(synthetic, docs)

    # Phase 3: Rules-grounded formats
    if args.rule_explanations > 0:
        docs = generate_rule_explanations(rules, args.rule_explanations)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} rule explanation documents")
        save_to_mongo(synthetic, docs)

    if args.rule_interactions > 0:
        docs = generate_rule_interactions(rules, args.rule_interactions)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} rule interaction documents")
        save_to_mongo(synthetic, docs)

    if args.glossary_examples > 0:
        docs = generate_glossary_with_examples(glossary, args.glossary_examples)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} glossary with examples documents")
        save_to_mongo(synthetic, docs)

    if args.rule_edge_cases > 0:
        docs = generate_rule_edge_cases(rules, args.rule_edge_cases)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} rule edge case documents")
        save_to_mongo(synthetic, docs)

    if args.rule_why > 0:
        docs = generate_rule_why_questions(rules, args.rule_why)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} rule why question documents")
        save_to_mongo(synthetic, docs)

    # Phase 4: EDHREC-grounded formats
    if args.article_qa > 0:
        docs = generate_article_qa(articles, args.article_qa)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} article Q&A documents")
        save_to_mongo(synthetic, docs)

    if args.guide_qa > 0:
        docs = generate_guide_qa(guides, args.guide_qa)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} guide Q&A documents")
        save_to_mongo(synthetic, docs)

    if args.staple_analysis > 0:
        docs = generate_staple_analysis(game_changers, args.staple_analysis)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} staple analysis documents")
        save_to_mongo(synthetic, docs)

    if args.color_staples > 0:
        docs = generate_color_staples(top_cards, args.color_staples)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} color staple documents")
        save_to_mongo(synthetic, docs)

    if args.salt_questions > 0:
        docs = generate_salt_questions(game_changers, args.salt_questions)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} salt question documents")
        save_to_mongo(synthetic, docs)
    
    # Summary
    print("\n" + "="*80)
    print("✓ SAVED TO MongoDB: synthetic_queries.queries")
    print("="*80)
    print(f"Total documents: {len(all_documents):,}")
    print(f"\nBreakdown by category:")
    
    from collections import Counter
    categories = Counter(d['category'] for d in all_documents)
    for category, count in sorted(categories.items()):
        print(f"  {category:20s}: {count:,}")
    
    needs_review = sum(1 for d in all_documents if d.get('needs_review', False))
    print(f"\n⚠️  Needs manual review: {needs_review:,}")
    
    print(f"\n✅ Ready to extract!")
    print("="*80)


if __name__ == "__main__":
    main()