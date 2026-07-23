# Architecture Overview

## Project Structure

```
training_data/generate_synthetic_data/
├── base_generator.py          # Abstract base class using Template Method pattern
├── data_access.py             # MTGDataAccess - unified MongoDB facade
├── domain_models.py           # Pydantic v2 models (CardWithMetadata, etc.)
├── models.py                  # Legacy models + ValidationMetrics, ModelType, Model
├── common.py                  # Shared prompt builders, validation, utilities
├── constants.py               # System messages, templates, validation rules
├── query_model.py             # LLM query/validation interface
├── logger.py                  # Logging utilities
├── main.py                    # CLI entry point
├── generate_card_search_queries.py   # Card search query generator (BaseGenerator[CardWithMetadata])
├── generate_combo_queries.py         # Combo query generator (BaseGenerator[ComboWithCards])
├── generate_article_qa.py            # Article Q&A generator (BaseGenerator[Article])
├── generate_quick_guidelines.py      # Quick guidelines generator (BaseGenerator[dict])
├── generate_color_identity_questions.py  # Color identity generator (BaseGenerator[ColorIdentityContext])
├── generate_comparison_questions.py  # Card comparison generator (BaseGenerator[tuple])
├── generate_deckbuilding_theory.py   # Deckbuilding theory (BaseGenerator[str])
├── generate_game_theory.py           # Game theory (BaseGenerator[str])
├── generate_commander_building.py    # Commander building (BaseGenerator[str])
├── generate_rules_scenarios.py       # Rules scenarios (BaseGenerator[str])
├── generate_meta_knowledge.py        # Meta knowledge (BaseGenerator[str]) — 9 topics, 2 templates
├── generate_commander_knowledge.py   # Commander knowledge (BaseGenerator[str]) — 8 sub-topics, 2 templates
├── generate_terminology_questions.py # Terminology (BaseGenerator[str]) — 20 terms, 2 templates
├── generate_archetypes.py            # Archetypes (BaseGenerator[str]) — 10 archetypes, 2 templates
└── ... (other generators)
```

## Key Architectural Patterns

### 1. BaseGenerator (Template Method Pattern)
- **Abstract methods**: `get_data_batches()`, `build_prompt()`, `get_source_category()`
- **Concrete methods**: `generate()`, `select_templates()`, `validate_answer()`, `_process_item()`
- **Hooks**: `build_context()`, `get_source_data()`, `select_templates()`
- **Configuration**: `TEMPLATES` class variable with `TemplateConfig` dataclasses

### 2. MTGDataAccess (Facade Pattern)
- Single entry point for all MongoDB operations
- Aggregation pipelines for enriched data (cards with prices, legalities, rulings, keywords)
- Caching with LRU + TTL
- Retry logic for transient errors
- Connection pooling
- Key methods: `get_cards_enriched()`, `get_combos_enriched()`, `get_commanders_enriched()`, `get_articles()`, `get_guides()`, `get_rules()`, `get_glossary()`, `get_game_changers()`, `get_salty_cards()`, `get_top_cards_by_color()`

### 3. Domain Models (Pydantic v2)
- `CardWithMetadata` - enriched card with prices, legalities, rulings, keywords, EDHREC data
- `ComboWithCards` - combos with fully enriched card data
- `CommanderWithTags` - commanders with EDHREC tags and card details
- Computed properties: `cmc`, `is_commander_legal`, `best_price`, etc.
- Serialization: `to_prompt_detail()` for consistent LLM context

### 4. Validation Pipeline
- `validate_and_loop_with_suggested_fix()` - orchestrates validation with regeneration
- `QueryModel.validate_qa()` - LLM-based validation with scoring
- `QueryModel.regenerate_answer()` - LLM-based answer correction
- Metrics tracking via `ValidationMetrics`

### 5. Trace Logging (Generation Traces)
- **Data model**: `GenerationTrace` dataclass in models.py — captures full LLM interaction per Q&A item
- **Storage**: MongoDB collection `synthetic_metrics.generation_traces` (separate from Q&A docs)
- **Flow**: BaseGenerator creates trace → populates generation details → passes to validate_and_loop → accumulates validation rounds → fires trace_callback → batched flush to MongoDB
- **CLI control**: `--log-traces` (default on) / `--no-log-traces` to disable
- **Indexes**: Compound (run_id, category, final_outcome) + item_id for querying
- **Batch size**: 50 traces per MongoDB insert for performance

## Generator Categories

### Category A: Data-Driven Generators (use MTGDataAccess)
These generators fetch data from MongoDB and generate Q&A from it:
- `GenerateCardSearchQueries` → `BaseGenerator[CardWithMetadata]`
- `GenerateComboQueries` → `BaseGenerator[ComboWithCards]`
- `GenerateArticleQa` → `BaseGenerator[Article]`
- `GenerateQuickGuidelines` → `BaseGenerator[dict]`
- `GenerateColorIdentityQuestions` → `BaseGenerator[ColorIdentityContext]`
- `GenerateComparisonQuestions` → `BaseGenerator[tuple[CardWithMetadata, CardWithMetadata]]`
- `GenerateRuleExplanations` → `BaseGenerator[Rule]` — rules from MTGDataAccess.get_rules(), 3 templates, 2 per item
- `GenerateRuleInteractions` → `BaseGenerator[ProjectedRulePair]` — rule pairs from interacting sections, 3 templates, 2 per item
- `GenerateGlossaryWithExamples` → `BaseGenerator[GlossaryTerm]` — glossary terms from MTGDataAccess.get_glossary(), single template
- `GenerateRuleEdgeCases` → `BaseGenerator[Rule]` — complex section rules, single template
- `GenerateRuleWhyQuestions` → `BaseGenerator[Rule]` — principle section rules, single template
- `GenerateGuideQa` → `BaseGenerator[Guide]` — guides from MTGDataAccess.get_guides(), single template
- `GenerateStapleAnalysis` → `BaseGenerator[dict]` — game changers from MTGDataAccess.get_game_changers(), single template
- `GenerateColorStaples` → `BaseGenerator[tuple[str, list[dict]]]` — top cards per color from MTGDataAccess.get_top_cards_by_color(), single template
- `GenerateSaltQuestions` → `BaseGenerator[list[dict]]` — salty cards from MTGDataAccess.get_salty_cards(), batch_size=8, single template
- `GenerateMultiCardUsage` → `BaseGenerator[ComboWithCards]` — combos from MTGDataAccess.get_combos_enriched(), single template

### Category B: Topic-Based Generators (no MTGDataAccess)
These generators use hardcoded topic/context lists and cycle through them:
- `GenerateDeckbuildingTheory` → `BaseGenerator[str]` — 12 topics, 2 templates
- `GenerateGameTheory` → `BaseGenerator[str]` — 10 situations, 2 templates
- `GenerateCommanderBuilding` → `BaseGenerator[str]` — 12 archetypes, 2 templates
- `GenerateRulesScenarios` → `BaseGenerator[str]` — 15 scenarios, 2 templates
- `GenerateMetaKnowledge` → `BaseGenerator[str]` — 9 topics, 2 templates
- `GenerateCommanderKnowledge` → `BaseGenerator[str]` — 8 sub-topics, 2 templates
- `GenerateTerminologyQuestions` → `BaseGenerator[str]` — 20 terms, 2 templates
- `GenerateArchetypes` → `BaseGenerator[str]` — 10 archetypes, 2 templates

### Category C: Other Old-Pattern Generators (not yet converted)
- Remaining legacy generators that still use raw pymongo collections directly

## Prompt Builder Functions (in common.py)
Existing prompt builders used by generators:
- `build_meta_knowledge_prompt(topic, meta_context)` → for meta knowledge
- `build_commander_prompt()` → monolithic, generates 20 Q&A at once
- `build_archetype_prompt(archetype, archetype_context)` → for archetypes
- `build_deckbuilding_theory_prompt(topic, context)` → for deckbuilding
- `build_game_theory_prompt(situation, decision_context)` → for game theory
- `build_commander_building_prompt(archetype, strategy_context)` → for commander building
- `build_rules_scenario_prompt(scenario, relevant_rules)` → for rules scenarios
- `build_glossary_with_examples_prompt(term, definition)` → for glossary terms
- `build_rule_explanation_prompt(rule_number, rule_text, template)` → for rule explanations
- `build_rule_interaction_prompt(rule1_num, rule1_text, rule2_num, rule2_text)` → for rule interactions (common.py version)
- `build_rule_edge_case_prompt(rule_number, rule_text, section_name)` → for edge cases
- `build_rule_why_prompt(rule_number, rule_text)` → for why questions
- `build_guide_qa_prompt(title, content)` → for guide Q&A
- `build_staple_analysis_prompt(card)` → for staple card analysis
- `build_color_staples_prompt(color, cards)` → for color-specific staples
- `build_salt_prompt(cards)` → for salty/controversial card analysis
- `build_multi_card_usage_prompt(card1, card2, description)` → for multi-card interactions

Note: `GenerateRuleInteractions` uses a custom inline prompt builder in its `build_prompt()` method (not the common.py version) to preserve original behavior with detailed requirements.

## Testing
- Unit tests in `training_data/generate_synthetic_data/` and `tests/`
- `test_base_generator.py` - 25 tests covering template selection, generation loop, validation integration
- `test_generate_rules_generators.py` - 35 tests for all 5 rules-grounded generators (templates, filters, prompts, inheritance)
- `test_data_access.py` - 49 tests covering cache, retry, pipelines, all methods
- `test_generate_color_identity_questions.py` - Tests for color identity generator
- `test_generate_quick_guidelines.py` - Tests for quick guidelines generator
- `tests/test_generate_meta_knowledge.py` - 13 tests for meta knowledge generator
- `tests/test_generate_commander_knowledge.py` - 14 tests for commander knowledge generator
- `tests/test_generate_terminology_questions.py` - 14 tests for terminology generator
- `tests/test_generate_archetypes.py` - 14 tests for archetype generator (includes no pymongo check)
- `conftest.py` - Mocks `ollama`, `anthropic`, `openai`, `pymongo` before imports

## Integration Pattern (main.py)
```
data_access = MTGDataAccess(uri, user, pass)
data_access.connect()

# Trace infrastructure
traces_buffer = []
def save_trace(trace):
    traces_buffer.append(asdict(trace))
    if len(traces_buffer) >= 50:
        generation_traces.insert_many(traces_buffer, ordered=False)
        traces_buffer.clear()

# Category A generators:
GeneratorName(
    data_access=data_access,
    models=models,
    validation_pct=...,
    target_count=...,
    save_item=save_item,
    metrics=make_metrics("GeneratorName"),
    trace_callback=save_trace if args.log_traces else None,
).generate()

# Category B generators (no data_access needed):
GeneratorName(
    models=models,
    validation_pct=...,
    target_count=...,
    save_item=save_item,
    metrics=make_metrics("GeneratorName"),
    dry_run=args.dry_run,
    trace_callback=save_trace if args.log_traces else None,
).generate()

# Flush remaining traces
if args.log_traces:
    generation_traces.insert_many(traces_buffer, ordered=False)
data_access.close()
```
