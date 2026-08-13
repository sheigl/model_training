#!/usr/bin/env python3
import sys
import uuid
from typing import Collection

from .generate_archetypes import * 
from .generate_article_qa import * 
from .generate_budget_alternatives import * 
from .generate_card_search_queries import GenerateCardSearchQueries 
from .generate_color_identity_questions import * 
from .generate_color_staples import * 
from .generate_combo_queries import * 
from .generate_commander_building import * 
from .generate_commander_knowledge import * 
from .generate_comparison_questions import * 
from .generate_deckbuilding_theory import * 
from .generate_game_theory import * 
from .generate_glossary_with_examples import * 
from .generate_guide_qa import * 
from .generate_meta_knowledge import * 
from .generate_multi_card_usage import * 
from .generate_quick_guidelines import * 
from .generate_reverse_lookup_questions import * 
from .generate_rule_edge_cases import * 
from .generate_rule_explanations import * 
from .generate_rule_interactions import * 
from .generate_rules_scenarios import * 
from .generate_rule_why_questions import * 
from .generate_salt_questions import * 
from .generate_staple_analysis import * 
from .generate_synergy_questions import GenerateSynergyQuestions, GenerateSynergyQuestionsLegacy 
from .generate_terminology_questions import *
from dotenv import load_dotenv;
sys.stdout.reconfigure(line_buffering=True); sys.stderr.reconfigure(line_buffering=True) # type: ignore
# Load environment variables from .env file
load_dotenv()

# Register generator categories for class-level TEMPLATES access
from .base_generator import BaseGenerator
BaseGenerator._CATEGORY_MAP.update({
    "GenerateArchetypes": "archetype",
    "GenerateArticleQa": "article_qa",
    "GenerateBudgetAlternatives": "budget_alternative",
    "GenerateCardSearchQueries": "card_search",
    "GenerateColorIdentityQuestions": "color_identity",
    "GenerateColorStaples": "color_staples",
    "GenerateComboQueries": "combo_query",
    "GenerateCommanderBuilding": "commander_building",
    "GenerateCommanderKnowledge": "commander_rules",
    "GenerateComparisonQuestions": "comparison",
    "GenerateDeckbuildingTheory": "deckbuilding_theory",
    "GenerateGameTheory": "game_theory",
    "GenerateGlossaryWithExamples": "glossary_with_examples",
    "GenerateGuideQa": "guide_qa",
    "GenerateMetaKnowledge": "meta_knowledge",
    "GenerateMultiCardUsage": "multi_card_usage",
    "GenerateQuickGuidelines": "quick_guideline",
    "GenerateReverseLookupQuestions": "reverse_lookup",
    "GenerateRuleEdgeCases": "rule_edge_case",
    "GenerateRuleExplanations": "rule_explanation",
    "GenerateRuleInteractions": "rule_interaction",
    "GenerateRulesScenarios": "rules_scenario",
    "GenerateRuleWhyQuestions": "rule_why",
    "GenerateSaltQuestions": "salt_analysis",
    "GenerateStapleAnalysis": "staple_analysis",
    "GenerateSynergyQuestions": "synergy",
    "GenerateTerminologyQuestions": "terminology",
})

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
  "generation_model": "qwen2.5:14b",  // Model that generated the Q&A pair
  "validation_model": "qwen2.5:14b",  // Model that validated it (null if not validated)
  "generated_at": "2026-02-13T..."
}
"""

from pymongo import MongoClient
import random
import re
from datetime import datetime
import argparse
import json
import time
import ollama
from pathlib import Path
from .common import *
from .models import ValidationMetrics, QuestionAnswerEnhanced, GenerationTrace
from .data_access import MTGDataAccess
from .yaml_template_loader import YamlTemplateLoader
from .common import init_scaffolding

# =============================================================================
# GENERATOR FLAGS REGISTRY
# =============================================================================
# Maps (slug, category, class_name, argparse_dest) for each generator.
# slug matches the existing --<slug> count flag exactly.
# category is the return value of get_source_category() on the generator.
# class_name is the class as used in main.py (for documentation).
# argparse_dest is the prefix for --<dest>-template-version / --<dest>-validator-template-version.
GENERATOR_FLAGS: list[tuple[str, str, str, str]] = [
    ("combo-queries", "combo_query", "GenerateComboQueries", "combo_queries"),
    ("card-search", "card_search", "GenerateCardSearchQueries", "card_search"),
    ("commander", "commander_rules", "GenerateCommanderKnowledge", "commander"),
    ("multi-card", "multi_card_usage", "GenerateMultiCardUsage", "multi_card"),
    ("comparison", "comparison", "GenerateComparisonQuestions", "comparison"),
    ("reverse-lookup", "reverse_lookup", "GenerateReverseLookupQuestions", "reverse_lookup"),
    ("synergy", "synergy", "GenerateSynergyQuestions", "synergy"),
    ("budget", "budget_alternative", "GenerateBudgetAlternatives", "budget"),
    ("color-identity", "color_identity", "GenerateColorIdentityQuestions", "color_identity"),
    ("guidelines", "quick_guideline", "GenerateQuickGuidelines", "guidelines"),
    ("terminology", "terminology", "GenerateTerminologyQuestions", "terminology"),
    ("deckbuilding-theory", "deckbuilding_theory", "GenerateDeckbuildingTheory", "deckbuilding_theory"),
    ("commander-building", "commander_building", "GenerateCommanderBuilding", "commander_building"),
    ("rules-scenarios", "rules_scenario", "GenerateRulesScenarios", "rules_scenarios"),
    ("archetypes", "archetype", "GenerateArchetypes", "archetypes"),
    ("game-theory", "game_theory", "GenerateGameTheory", "game_theory"),
    ("meta-knowledge", "meta_knowledge", "GenerateMetaKnowledge", "meta_knowledge"),
    ("rule-explanations", "rule_explanation", "GenerateRuleExplanations", "rule_explanations"),
    ("rule-interactions", "rule_interaction", "GenerateRuleInteractions", "rule_interactions"),
    ("glossary-examples", "glossary_with_examples", "GenerateGlossaryWithExamples", "glossary_examples"),
    ("rule-edge-cases", "rule_edge_case", "GenerateRuleEdgeCases", "rule_edge_cases"),
    ("rule-why", "rule_why", "GenerateRuleWhyQuestions", "rule_why"),
    ("article-qa", "article_qa", "GenerateArticleQa", "article_qa"),
    ("guide-qa", "guide_qa", "GenerateGuideQa", "guide_qa"),
    ("staple-analysis", "staple_analysis", "GenerateStapleAnalysis", "staple_analysis"),
    ("color-staples", "color_staples", "GenerateColorStaples", "color_staples"),
    ("salt-questions", "salt_analysis", "GenerateSaltQuestions", "salt_questions"),
]


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
    archetypes = client['mtg_archetypes']['archetypes']

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

    # Metrics collection (separate DB so concurrent generators don't collide)
    metrics_collection = client['synthetic_metrics']['generator_runs']
    generation_traces = client['synthetic_metrics']['generation_traces']
    generation_errors = client['synthetic_metrics']['generation_errors']

    return (cards, combos, synthetic, commanders, rules, glossary, articles, guides, 
            game_changers, top_cards, archetypes, metrics_collection, generation_traces, generation_errors)


def save_to_mongo(synthetic_collection, examples: list[QuestionAnswerEnhanced], batch_size=500):
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
            q = ex.question
            a = ex.answer
            ex.content_hash = hashlib.sha256(f"{q}||{a}".encode()).hexdigest()
            ex.generated_at = datetime.utcnow()
            ex.version = 1

        # Insert only documents whose hash doesn't already exist
        from pymongo import UpdateOne
        ops = [
            UpdateOne(
                {'content_hash': ex.content_hash},
                {'$setOnInsert': ex.__dict__},
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

def build_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser.

    Extracted so that tests can import and exercise flag parsing without
    running the full pipeline.
    """
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
    parser.add_argument('--shadow-validation-model', type=str, default=None,
                        help='Optional second validator (shadow). Its verdict is recorded on traces '
                             'ONLY for analysis — it never affects acceptance, regeneration, or metrics.')
    
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
    parser.add_argument('--validation-pct', type=float, default=1, help='Set the percentage of QA pairs to validate')
    parser.add_argument("--dry-run", action="store_true", help="Run in dry-run mode (no MongoDB writes)")
    parser.add_argument('--metrics-path', type=str, default=None, help='Path to write validation metrics JSON file')
    parser.add_argument('--log-traces', action='store_true', default=True,
                        help='Log full generation/validation traces (default: on)')
    parser.add_argument('--no-log-traces', action='store_false', dest='log_traces',
                        help='Disable trace logging')

    parser.add_argument(
        "--templates-dir",
        default=None,
        help="Path to directory containing YAML template files (default: package templates/)",
    )
    parser.add_argument(
        "--observer-model",
        type=str,
        default=None,
        help="Model for observer analysis (default: same as --validation-model)",
    )
    parser.add_argument(
        "--first-pass-threshold",
        type=float,
        default=50.0,
        help="First-pass rate threshold that triggers generation template improvement (default: 50.0)",
    )
    parser.add_argument(
        "--observation-interval",
        type=int,
        default=10,
        help="Items per generator before observer analysis runs (default: 10)",
    )
    parser.add_argument(
        "--starting-template-versions",
        type=str,
        default=None,
        help='JSON dict of category→version overrides at run start, e.g. \'{"combo_query": 2}\'',
    )
    parser.add_argument(
        "--enable-observer",
        action="store_true",
        default=False,
        help="Enable the observer step (template improvement after generation)",
    )

    return parser


def main():
    parser = build_parser()

    args = parser.parse_args()
    
    models: dict[ModelType, Model] = {
        ModelType.GENERATION: Model(name=args.model, type=ModelType.GENERATION),
        ModelType.VALIDATION: Model(name=args.validation_model, type=ModelType.VALIDATION)
    }

    # Story 049 — optional shadow validator. It rides in the shared models dict
    # so every generator picks it up without per-generator wiring. Its verdicts
    # are recorded on traces only and never affect validation outcomes.
    shadow_validation_model: Model | None = None
    if args.shadow_validation_model:
        shadow_validation_model = Model(
            name=args.shadow_validation_model, type=ModelType.SHADOW_VALIDATION
        )
        models[ModelType.SHADOW_VALIDATION] = shadow_validation_model

    print(f"\n⚡ Using {models[ModelType.GENERATION].name} for text generation and {models[ModelType.VALIDATION].name} for validation"
          + (f" (shadow validator: {shadow_validation_model.name})" if shadow_validation_model else ""))
    
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
    (cards, combos, synthetic, commanders, rules, glossary, articles, guides, 
     game_changers, top_cards, archetypes, metrics_collection, generation_traces, generation_errors) = get_mongo_collections(args.mongo_uri, args.mongo_user, args.mongo_pass)
    print("  ✓ Connected")

    # Create single MTGDataAccess instance for new generators
    data_access = MTGDataAccess(
        uri=args.mongo_uri,
        username=args.mongo_user,
        password=args.mongo_pass,
    )
    data_access.connect()
    print("  ✓ MTGDataAccess connected")

    templates_dir = args.templates_dir or (Path(__file__).parent / "templates")
    yaml_loader = YamlTemplateLoader(templates_dir)
    init_scaffolding(yaml_loader=yaml_loader)
    print(f"  ✓ Templates loaded from {templates_dir}")

    # Create trace indexes
    try:
        generation_traces.create_index(
            [("run_id", 1), ("category", 1), ("final_outcome", 1)],
            background=True
        )
        generation_traces.create_index("item_id", background=True)
        # Story 045 — template version indexes
        generation_traces.create_index(
            [("category", 1), ("template_version", 1)],
            name="idx_category_version", background=True)
        generation_traces.create_index(
            [("run_id", 1), ("template_version", 1)],
            name="idx_run_version", background=True)
        # Story 048 — generation_error traces live in a separate collection
        generation_errors.create_index(
            [("run_id", 1), ("category", 1), ("generation_model", 1)],
            background=True)
    except Exception:
        pass

    # Unique run ID shared by all generators in this process
    run_id = str(uuid.uuid4())

    # Create observer for post-generation template improvement (only when enabled)
    from .observer import Observer
    templates_dir = Path(__file__).parent / "templates"
    if args.enable_observer:
        obs_model_name = args.observer_model or args.validation_model
        observer_model = Model(name=obs_model_name, type=ModelType.VALIDATION)
        observer = Observer(
            models=models,
            yaml_loader=yaml_loader,
            templates_dir=templates_dir,
            first_pass_threshold=args.first_pass_threshold,
            observation_interval=args.observation_interval,
            run_id=run_id,
            observer_model=observer_model,
        )
        print(f"  ✓ Observer enabled (threshold={args.first_pass_threshold}%, interval={args.observation_interval})")
    else:
        observer = None

    # Parse starting template version overrides
    starting_versions: dict[str, int] = {}
    if args.starting_template_versions:
        import json as _json
        try:
            starting_versions = _json.loads(args.starting_template_versions)
        except json.JSONDecodeError as e:
            print(f"⚠️  Invalid --starting-template-versions JSON: {e}")

    active_metrics: list[ValidationMetrics] = []
    all_documents: list[dict] = []

    def make_metrics(generator_name: str) -> ValidationMetrics:
        m = ValidationMetrics(
            metrics_collection=metrics_collection,
            run_id=run_id,
            generator_name=generator_name,
            generation_model=models[ModelType.GENERATION].name,
            validation_model=models[ModelType.VALIDATION].name,
        )
        active_metrics.append(m)
        return m

    def save_item(doc: QuestionAnswerEnhanced) -> None:
        save_to_mongo(synthetic, [doc])
        all_documents.append(doc.__dict__)

    from dataclasses import asdict
    traces_buffer: list[dict] = []
    error_traces_buffer: list[dict] = []
    TRACE_BATCH_SIZE = 1

    def save_trace(trace: 'GenerationTrace') -> None:
        # generation_error traces (template-level, no QAs) go to a separate
        # collection so validator analysis is never polluted by them (Story 048).
        if trace.final_outcome == "generation_error":
            error_traces_buffer.append(asdict(trace))
        else:
            traces_buffer.append(asdict(trace))
        print(f"  📝 Trace queued ({trace.final_outcome}) — {len(traces_buffer)} validated, {len(error_traces_buffer)} errors buffered")
        if len(traces_buffer) + len(error_traces_buffer) >= TRACE_BATCH_SIZE:
            flush_traces()

    def flush_traces():
        if traces_buffer:
            generation_traces.insert_many(traces_buffer, ordered=False)
            print(f"  📝 Flushed {len(traces_buffer)} traces to synthetic_metrics.generation_traces")
            traces_buffer.clear()
        if error_traces_buffer:
            generation_errors.insert_many(error_traces_buffer, ordered=False)
            print(f"  📝 Flushed {len(error_traces_buffer)} generation errors to synthetic_metrics.generation_errors")
            error_traces_buffer.clear()

    # Generate all synthetic data

    if args.dry_run:
        print(f"\nDry run complete. Templates loaded from: {templates_dir}")

    # Original formats (old pattern - pass collections directly)
    if args.combo_queries > 0:
        GenerateComboQueries(
            data_access=data_access,
            models=models,
            validation_pct=args.validation_pct,
            target_count=args.combo_queries,
            save_item=save_item,
            metrics=make_metrics("GenerateComboQueries"),
            trace_callback=save_trace if args.log_traces else None,
            yaml_loader=yaml_loader,
            observer=observer,
            template_version_override=starting_versions.get("combo_query"),
        ).generate()

    if args.card_search > 0:
        GenerateCardSearchQueries(
            data_access=data_access,
            models=models,
            validation_pct=args.validation_pct,
            target_count=args.card_search,
            save_item=save_item,
            metrics=make_metrics("GenerateCardSearchQueries"),
            dry_run=args.dry_run if hasattr(args, 'dry_run') else False,
            trace_callback=save_trace if args.log_traces else None,
            yaml_loader=yaml_loader,
            observer=observer,
            template_version_override=starting_versions.get("card_search"),
        ).generate()
    
    if args.commander > 0:
        GenerateCommanderKnowledge(
            data_access=data_access,
            models=models,
            validation_pct=args.validation_pct,
            target_count=args.commander,
            save_item=save_item,
            metrics=make_metrics("GenerateCommanderKnowledge"),
            dry_run=args.dry_run if hasattr(args, 'dry_run') else False,
            trace_callback=save_trace if args.log_traces else None,
            yaml_loader=yaml_loader,
            observer=observer,
            template_version_override=starting_versions.get("commander_rules"),
        ).generate()
    
    if args.multi_card > 0:
        GenerateMultiCardUsage(
            data_access=data_access,
            models=models,
            validation_pct=args.validation_pct,
            target_count=args.multi_card,
            save_item=save_item,
            metrics=make_metrics("GenerateMultiCardUsage"),
            dry_run=args.dry_run if hasattr(args, 'dry_run') else False,
            trace_callback=save_trace if args.log_traces else None,
            yaml_loader=yaml_loader,
            observer=observer,
            template_version_override=starting_versions.get("multi_card_usage"),
        ).generate()
    
    if args.comparison > 0:
        GenerateComparisonQuestions(
            data_access=data_access,
            models=models,
            validation_pct=args.validation_pct,
            target_count=args.comparison,
            save_item=save_item,
            metrics=make_metrics("GenerateComparisonQuestions"),
            dry_run=args.dry_run if hasattr(args, 'dry_run') else False,
            trace_callback=save_trace if args.log_traces else None,
            yaml_loader=yaml_loader,
            observer=observer,
            template_version_override=starting_versions.get("comparison"),
        ).generate()
    
    if args.reverse_lookup > 0:
        GenerateReverseLookupQuestions(
            data_access=data_access,
            models=models,
            validation_pct=args.validation_pct,
            target_count=args.reverse_lookup,
            save_item=save_item,
            metrics=make_metrics("GenerateReverseLookupQuestions"),
            dry_run=args.dry_run if hasattr(args, 'dry_run') else False,
            trace_callback=save_trace if args.log_traces else None,
            yaml_loader=yaml_loader,
            observer=observer,
            template_version_override=starting_versions.get("reverse_lookup"),
        ).generate()
    
    if args.synergy > 0:
        GenerateSynergyQuestions(
            data_access=data_access,
            models=models,
            validation_pct=args.validation_pct,
            target_count=args.synergy,
            save_item=save_item,
            metrics=make_metrics("GenerateSynergyQuestions"),
            dry_run=args.dry_run if hasattr(args, 'dry_run') else False,
            trace_callback=save_trace if args.log_traces else None,
            yaml_loader=yaml_loader,
            observer=observer,
            template_version_override=starting_versions.get("synergy"),
        ).generate()
    
    if args.budget > 0:
        GenerateBudgetAlternatives(
            data_access=data_access,
            models=models,
            validation_pct=args.validation_pct,
            target_count=args.budget,
            save_item=save_item,
            metrics=make_metrics("GenerateBudgetAlternatives"),
            dry_run=args.dry_run if hasattr(args, 'dry_run') else False,
            trace_callback=save_trace if args.log_traces else None,
            yaml_loader=yaml_loader,
            observer=observer,
            template_version_override=starting_versions.get("budget_alternative"),
        ).generate()
    
    if args.color_identity > 0:
        GenerateColorIdentityQuestions(
            data_access=data_access,
            models=models,
            validation_pct=args.validation_pct,
            target_count=args.color_identity,
            save_item=save_item,
            metrics=make_metrics("GenerateColorIdentityQuestions"),
            dry_run=args.dry_run if hasattr(args, 'dry_run') else False,
            trace_callback=save_trace if args.log_traces else None,
            yaml_loader=yaml_loader,
            observer=observer,
            template_version_override=starting_versions.get("color_identity"),
        ).generate()
    
    if args.guidelines > 0:
        from .generate_quick_guidelines import GenerateQuickGuidelines as GenerateQuickGuidelinesNew
        GenerateQuickGuidelinesNew(
            data_access=data_access,
            models=models,
            validation_pct=args.validation_pct,
            target_count=args.guidelines,
            save_item=save_item,
            metrics=make_metrics("GenerateQuickGuidelines"),
            dry_run=args.dry_run if hasattr(args, 'dry_run') else False,
            trace_callback=save_trace if args.log_traces else None,
            yaml_loader=yaml_loader,
            observer=observer,
            template_version_override=starting_versions.get("quick_guideline"),
        ).generate()

    if args.terminology > 0:
        GenerateTerminologyQuestions(
            models=models,
            validation_pct=args.validation_pct,
            target_count=args.terminology,
            save_item=save_item,
            metrics=make_metrics("GenerateTerminologyQuestions"),
            dry_run=args.dry_run if hasattr(args, 'dry_run') else False,
            trace_callback=save_trace if args.log_traces else None,
            yaml_loader=yaml_loader,
            observer=observer,
            template_version_override=starting_versions.get("terminology"),
        ).generate()

    # Phase 2: Strategy/Theory formats
    if args.deckbuilding_theory > 0:
        GenerateDeckbuildingTheory(
            models=models,
            validation_pct=args.validation_pct,
            target_count=args.deckbuilding_theory,
            save_item=save_item,
            metrics=make_metrics("GenerateDeckbuildingTheory"),
            dry_run=args.dry_run if hasattr(args, 'dry_run') else False,
            trace_callback=save_trace if args.log_traces else None,
            yaml_loader=yaml_loader,
            observer=observer,
            template_version_override=starting_versions.get("deckbuilding_theory"),
        ).generate()

    if args.commander_building > 0:
        GenerateCommanderBuilding(
            data_access=data_access,
            models=models,
            validation_pct=args.validation_pct,
            target_count=args.commander_building,
            save_item=save_item,
            metrics=make_metrics("GenerateCommanderBuilding"),
            dry_run=args.dry_run if hasattr(args, 'dry_run') else False,
            trace_callback=save_trace if args.log_traces else None,
            yaml_loader=yaml_loader,
            observer=observer,
            template_version_override=starting_versions.get("commander_building"),
        ).generate()

    if args.rules_scenarios > 0:
        GenerateRulesScenarios(
            models=models,
            validation_pct=args.validation_pct,
            target_count=args.rules_scenarios,
            save_item=save_item,
            metrics=make_metrics("GenerateRulesScenarios"),
            dry_run=args.dry_run if hasattr(args, 'dry_run') else False,
            trace_callback=save_trace if args.log_traces else None,
            yaml_loader=yaml_loader,
            observer=observer,
            template_version_override=starting_versions.get("rules_scenario"),
        ).generate()

    if args.archetypes > 0:
        GenerateArchetypes(
            models=models,
            validation_pct=args.validation_pct,
            target_count=args.archetypes,
            save_item=save_item,
            metrics=make_metrics("GenerateArchetypes"),
            dry_run=args.dry_run if hasattr(args, 'dry_run') else False,
            trace_callback=save_trace if args.log_traces else None,
            yaml_loader=yaml_loader,
            observer=observer,
            template_version_override=starting_versions.get("archetype"),
        ).generate()

    if args.game_theory > 0:
        GenerateGameTheory(
            models=models,
            validation_pct=args.validation_pct,
            target_count=args.game_theory,
            save_item=save_item,
            metrics=make_metrics("GenerateGameTheory"),
            dry_run=args.dry_run if hasattr(args, 'dry_run') else False,
            trace_callback=save_trace if args.log_traces else None,
            yaml_loader=yaml_loader,
            observer=observer,
            template_version_override=starting_versions.get("game_theory"),
        ).generate()

    if args.meta_knowledge > 0:
        GenerateMetaKnowledge(
            models=models,
            validation_pct=args.validation_pct,
            target_count=args.meta_knowledge,
            save_item=save_item,
            metrics=make_metrics("GenerateMetaKnowledge"),
            dry_run=args.dry_run if hasattr(args, 'dry_run') else False,
            trace_callback=save_trace if args.log_traces else None,
            yaml_loader=yaml_loader,
            observer=observer,
            template_version_override=starting_versions.get("meta_knowledge"),
        ).generate()

    # Phase 3: Rules-grounded formats (BaseGenerator + MTGDataAccess pattern)
    if args.rule_explanations > 0:
        GenerateRuleExplanations(
            data_access=data_access,
            models=models,
            validation_pct=args.validation_pct,
            target_count=args.rule_explanations,
            save_item=save_item,
            metrics=make_metrics("GenerateRuleExplanations"),
            dry_run=args.dry_run if hasattr(args, 'dry_run') else False,
            trace_callback=save_trace if args.log_traces else None,
            yaml_loader=yaml_loader,
            observer=observer,
            template_version_override=starting_versions.get("rule_explanation"),
        ).generate()

    if args.rule_interactions > 0:
        GenerateRuleInteractions(
            data_access=data_access,
            models=models,
            validation_pct=args.validation_pct,
            target_count=args.rule_interactions,
            save_item=save_item,
            metrics=make_metrics("GenerateRuleInteractions"),
            dry_run=args.dry_run if hasattr(args, 'dry_run') else False,
            trace_callback=save_trace if args.log_traces else None,
            yaml_loader=yaml_loader,
            observer=observer,
            template_version_override=starting_versions.get("rule_interaction"),
        ).generate()

    if args.glossary_examples > 0:
        GenerateGlossaryWithExamples(
            data_access=data_access,
            models=models,
            validation_pct=args.validation_pct,
            target_count=args.glossary_examples,
            save_item=save_item,
            metrics=make_metrics("GenerateGlossaryWithExamples"),
            dry_run=args.dry_run if hasattr(args, 'dry_run') else False,
            trace_callback=save_trace if args.log_traces else None,
            yaml_loader=yaml_loader,
            observer=observer,
            template_version_override=starting_versions.get("glossary_with_examples"),
        ).generate()

    if args.rule_edge_cases > 0:
        GenerateRuleEdgeCases(
            data_access=data_access,
            models=models,
            validation_pct=args.validation_pct,
            target_count=args.rule_edge_cases,
            save_item=save_item,
            metrics=make_metrics("GenerateRuleEdgeCases"),
            dry_run=args.dry_run if hasattr(args, 'dry_run') else False,
            trace_callback=save_trace if args.log_traces else None,
            yaml_loader=yaml_loader,
            observer=observer,
            template_version_override=starting_versions.get("rule_edge_case"),
        ).generate()

    if args.rule_why > 0:
        GenerateRuleWhyQuestions(
            data_access=data_access,
            models=models,
            validation_pct=args.validation_pct,
            target_count=args.rule_why,
            save_item=save_item,
            metrics=make_metrics("GenerateRuleWhyQuestions"),
            dry_run=args.dry_run if hasattr(args, 'dry_run') else False,
            trace_callback=save_trace if args.log_traces else None,
            yaml_loader=yaml_loader,
            observer=observer,
            template_version_override=starting_versions.get("rule_why"),
        ).generate()

    # Phase 4: EDHREC-grounded formats
    if args.article_qa > 0:
        GenerateArticleQa(
            data_access=data_access,
            models=models,
            validation_pct=args.validation_pct,
            target_count=args.article_qa,
            save_item=save_item,
            metrics=make_metrics("GenerateArticleQa"),
            trace_callback=save_trace if args.log_traces else None,
            yaml_loader=yaml_loader,
            observer=observer,
            template_version_override=starting_versions.get("article_qa"),
        ).generate()

    if args.guide_qa > 0:
        GenerateGuideQa(
            data_access=data_access,
            models=models,
            validation_pct=args.validation_pct,
            target_count=args.guide_qa,
            save_item=save_item,
            metrics=make_metrics("GenerateGuideQa"),
            dry_run=args.dry_run if hasattr(args, 'dry_run') else False,
            trace_callback=save_trace if args.log_traces else None,
            yaml_loader=yaml_loader,
            observer=observer,
            template_version_override=starting_versions.get("guide_qa"),
        ).generate()

    if args.staple_analysis > 0:
        GenerateStapleAnalysis(
            data_access=data_access,
            models=models,
            validation_pct=args.validation_pct,
            target_count=args.staple_analysis,
            save_item=save_item,
            metrics=make_metrics("GenerateStapleAnalysis"),
            dry_run=args.dry_run if hasattr(args, 'dry_run') else False,
            trace_callback=save_trace if args.log_traces else None,
            yaml_loader=yaml_loader,
            observer=observer,
            template_version_override=starting_versions.get("staple_analysis"),
        ).generate()

    if args.color_staples > 0:
        GenerateColorStaples(
            data_access=data_access,
            models=models,
            validation_pct=args.validation_pct,
            target_count=args.color_staples,
            save_item=save_item,
            metrics=make_metrics("GenerateColorStaples"),
            dry_run=args.dry_run if hasattr(args, 'dry_run') else False,
            trace_callback=save_trace if args.log_traces else None,
            yaml_loader=yaml_loader,
            observer=observer,
            template_version_override=starting_versions.get("color_staples"),
        ).generate()

    if args.salt_questions > 0:
        GenerateSaltQuestions(
            data_access=data_access,
            models=models,
            validation_pct=args.validation_pct,
            target_count=args.salt_questions,
            save_item=save_item,
            metrics=make_metrics("GenerateSaltQuestions"),
            dry_run=args.dry_run if hasattr(args, 'dry_run') else False,
            trace_callback=save_trace if args.log_traces else None,
            yaml_loader=yaml_loader,
            observer=observer,
            template_version_override=starting_versions.get("salt_analysis"),
        ).generate()
    
    # Flush observer for any remaining buffered traces
    if observer:
        observer.flush()

    # Summary
    print("\n" + "="*80)
    print(f"RUN ID: {run_id}")
    print("="*80)
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

    # Write final validation metrics to MongoDB
    used_metrics = [m for m in active_metrics if m.total_candidates > 0]
    if used_metrics:
        print(f"\n📊 Validation metrics written to MongoDB (synthetic_metrics.generator_runs, run_id={run_id})")
        for m in used_metrics:
            m.flush()
            print(f"  → {m.generator_name}: doc_id={m._id}")

        print(f"\n{'='*80}")
        print("VALIDATION METRICS SUMMARY")
        print(f"{'='*80}")
        print(f"  Run ID: {run_id}")
        print(f"  Generation model: {models[ModelType.GENERATION].name}")
        print(f"  Validation model: {models[ModelType.VALIDATION].name}")
        if shadow_validation_model:
            print(f"  Shadow validation model: {shadow_validation_model.name} (trace-only)")
        for m in used_metrics:
            summary = m.summary()
            print(f"\n  Generator: {m.generator_name} (doc_id={m._id})")
            print(f"    Total candidates:      {summary['total_candidates']:,}")
            print(f"    Validated:             {summary['total_validated']:,}")
            print(f"    Skipped (no validate): {summary['total_skipped']:,}")
            print(f"    Passed:                {summary['total_passed']:,}")
            print(f"      - First attempt:     {summary['total_first_attempt_passes']:,}")
            print(f"      - After fix:         {summary['total_pass_after_fix']:,}")
            print(f"    Failed:                {summary['total_failed']:,}")
            print(f"      - First attempt:     {summary['total_failed_first_attempt']:,}")
            print(f"      - After fix(es):     {summary['total_failed_after_fixes']:,}")
            print(f"    Fix attempts:          {summary['total_fix_attempts']:,}")
            print(f"    Overall pass rate:       {summary['overall_pass_rate']:.1f}%")
            print(f"    First-attempt pass rate: {summary['first_attempt_pass_rate']:.1f}%")
            if summary['fix_recovery_rate'] is not None:
                print(f"    Fix recovery rate:       {summary['fix_recovery_rate']:.1f}%")
            print(f"    Fix involvement rate:    {summary['fix_involvement_rate']:.1f}%")
            if summary.get('by_category'):
                print(f"\n    Breakdown by category:")
                for cat, stats in sorted(summary['by_category'].items()):
                    print(f"      {cat:22s}: {stats['passed']:>4} passed / {stats['failed']:>4} failed / {stats['validated']:>4} validated (pass rate: {stats['pass_rate']:.1f}%)  [first_pass: {stats['first_attempt_passes']}, after_fix: {stats['pass_after_fix']}, failed_first: {stats['failed_first_attempt']}, failed_after_fix: {stats['failed_after_fixes']}]")

    print(f"\n✅ Ready to extract!")
    print("="*80)

    # Flush remaining traces
    if args.log_traces:
        flush_traces()
        print(f"\n📝 Generation traces saved to synthetic_metrics.generation_traces")
        print(f"   Generation errors saved to synthetic_metrics.generation_errors")

    # Clean up
    data_access.close()


if __name__ == "__main__":
    main()