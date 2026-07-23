# Changelog

### Feature: Generation Trace Logging for Synthetic Data — 2026-07-21

Added comprehensive LLM interaction tracing to capture the full lifecycle of every generated Q&A item. This enables debugging, analysis, and optimization of the generation/validation pipeline.

**Core Architecture:**
- **`GenerationTrace` dataclass** (`models.py`): Captures complete LLM interaction traces per Q&A item — generation prompt/response/latency, validation rounds with scores/reasons/prompts, regeneration attempts, and final outcome
- **`trace_round` / `trace_regeneration` params** (`query_model.py`): Optional dicts populated with full interaction data during validation and regeneration
- **`trace` param** on `validate_and_loop_with_suggested_fix()` (`common.py`): Accumulates `round_data` across validation iterations
- **`trace_callback` param** on `BaseGenerator.__init__()` (`base_generator.py`): Creates `GenerationTrace` per template iteration, fires callback on first successful save

**CLI & Storage:**
- `--log-traces` (default: on) / `--no-log-traces` CLI flags in `main.py`
- Traces batch-flushed to `synthetic_metrics.generation_traces` collection (batch size: 50)
- MongoDB compound index: `(run_id, category, final_outcome)` + single index on `item_id`
- `final_outcome` values: `"accepted_first_attempt"`, `"accepted_after_fix"`, `"rejected"`, `"skipped"`

**Files Modified:**
- `models.py` — Added `GenerationTrace` dataclass
- `query_model.py` — Added `_last_elapsed_ms` tracking, `trace_round`/`trace_regeneration` params
- `common.py` — Added `trace` param, round accumulation logic
- `base_generator.py` — Added `trace_callback`, trace creation and callback wiring
- `main.py` — Added CLI flags, `generation_traces` collection, `save_trace()`/`flush_traces()`, wired all 27 generators

### Fix: Code review issues in generation trace logging — 2026-07-21

- **common.py**: Fixed trace data loss when regeneration fails — `round_data` is now appended to `trace.validation_rounds` before the `break` on regeneration failure; fixed `final_outcome` to report "skipped" when validation was not performed
- **base_generator.py**: Eliminated redundant double-parse of generation response (was parsing JSON twice per call); fixed trace callback firing for every Q&A pair in a template (now fires once per template, preventing accumulating trace corruption); moved `datetime` and `uuid` imports to module level
- **query_model.py**: Fixed stale `_last_elapsed_ms` on query failure — the except block now updates `_last_elapsed_ms` before re-raising

### Model Output Trace Logging for Synthetic Data Generation — 2026-07-21

- **models.py**: Added `GenerationTrace` dataclass capturing full LLM interaction traces per Q&A item — includes generation prompt/response, latency, validation rounds with scores/prompts/responses, and final outcome (accepted_first_attempt/accepted_after_fix/rejected)
- **query_model.py**: Added `_last_elapsed_ms` timing to `QueryModel`, plus optional `trace_round` parameter on `validate_qa()` and `trace_regeneration` parameter on `regenerate_answer()` that populate trace dicts on success and failure
- **common.py**: `validate_and_loop_with_suggested_fix()` now accepts optional `trace: GenerationTrace` parameter that accumulates validation round details and computes final outcome
- **base_generator.py**: Added `trace_callback` parameter to `BaseGenerator.__init__()`, creates `GenerationTrace` per template iteration, populates generation details, passes trace through validation, fires callback after save
- **main.py**: Added `--log-traces`/`--no-log-traces` CLI flags (default: on), MongoDB `generation_traces` collection with indexes, batched trace flushing (50 per batch), trace callback wired to all 27 generator instantiations
- **test_base_generator.py**: Updated `MockQueryModel` signatures to accept new optional `trace_round` and `trace_regeneration` parameters

### Feature: Convert 5 EDHREC-grounded generators to BaseGenerator + MTGDataAccess pattern (Phase 4 complete) — 2026-07-21

- **data_access.py**: Added 3 new methods for Phase 4 data access:
  - `get_game_changers(limit)`: Queries edhrec.game-changers where game_changer=True, sorted by num_decks → list[dict]
  - `get_salty_cards(min_salt=1.2, limit)`: Queries edhrec.game-changers where salt >= min_salt, sorted by salt score → list[dict]
  - `get_top_cards_by_color(color, limit)`: Queries edhrec.top-{color} collections for each of the 6 colors → list[dict]

- **generate_guide_qa.py**: Converted to extend `BaseGenerator[Guide]`
  - Uses `MTGDataAccess.get_guides()` instead of raw pymongo collection
  - Preserves content length >300 filter and random shuffle behavior
  - Source category: "guide_qa"

- **generate_staple_analysis.py**: Converted to extend `BaseGenerator[dict]`
  - Uses `MTGDataAccess.get_game_changers()` instead of raw pymongo collection
  - Preserves game_changer=True filter and num_decks sorting
  - Source category: "staple_analysis"

- **generate_color_staples.py**: Converted to extend `BaseGenerator[tuple[str, list[dict]]]`
  - Uses `MTGDataAccess.get_top_cards_by_color()` for all 6 colors instead of raw collections dict
  - Preserves per-color subset logic (10/20/30 card groups)
  - Source category: "color_staples"

- **generate_salt_questions.py**: Converted to extend `BaseGenerator[list[dict]]`
  - Uses `MTGDataAccess.get_salty_cards(min_salt=1.2)` instead of raw pymongo collection
  - Preserves BATCH_SIZE=8 grouping and salt >= 1.2 threshold
  - Source category: "salt_analysis"

- **generate_multi_card_usage.py**: Converted to extend `BaseGenerator[ComboWithCards]`
  - Uses existing `MTGDataAccess.get_combos_enriched()` instead of raw pymongo collection
  - Preserves card_names < 2 filter and description check
  - Source category: "multi_card_usage"

- **main.py**: Updated all 5 Phase 4 instantiation blocks to use new BaseGenerator constructor signature (`data_access=`, `models=`, `validation_pct=`, `target_count=`, `save_item=`, `metrics=`, `dry_run=`) and call `.generate()` instead of generator-specific methods

- **Tests**: Zero regressions across entire test suite after Phase 4 conversions

### Feature: Convert 5 rules-grounded generators to BaseGenerator + MTGDataAccess pattern (Phase 3 complete) — 2026-07-21

- **generate_rule_explanations.py**: Converted `GenerateRuleExplanations` to extend `BaseGenerator[Rule]`
  - Uses `MTGDataAccess.get_rules()` with SKIP_SECTIONS filter, templates_per_item=2
  - Preserves text length >50 filter and 2 templates per rule behavior
  - Defines TEMPLATES from RULE_EXPLANATION_TEMPLATES with validation rules from RULE_EXPLANATION_VALIDATION
  - Uses `build_rule_explanation_prompt()` common builder
  - Source category: "rule_explanation"

- **generate_rule_interactions.py**: Converted `GenerateRuleInteractions` to extend `BaseGenerator[ProjectedRulePair]`
  - `ProjectedRulePair` is now a dataclass (was plain class) with same fields
  - Uses `MTGDataAccess.get_rules()`, builds ProjectedRulePair instances from rules data
  - Preserves all 37 INTERACTION_PAIRS, section grouping logic, and deduplication via seen_names
  - Custom inline prompt builder preserved in `build_prompt()` method
  - Source category: "rule_interaction"

- **generate_glossary_with_examples.py**: Converted `GenerateGlossaryWithExamples` to extend `BaseGenerator[GlossaryTerm]`
  - Uses `MTGDataAccess.get_glossary()` instead of raw pymongo collection
  - Preserves definition length >30 filter and single template behavior
  - Uses `build_glossary_with_examples_prompt()` common builder
  - Source category: "glossary_with_examples"

- **generate_rule_edge_cases.py**: Converted `GenerateRuleEdgeCases` to extend `BaseGenerator[Rule]`
  - Uses `MTGDataAccess.get_rules()` with COMPLEX_RULE_SECTIONS filter from constants
  - Preserves text length >=80 filter
  - Section name lookup moved into `build_prompt()` (was stored on rule dict in old pattern)
  - Source category: "rule_edge_case"

- **generate_rule_why_questions.py**: Converted `GenerateRuleWhyQuestions` to extend `BaseGenerator[Rule]`
  - Uses `MTGDataAccess.get_rules()` with PRINCIPLE_SECTIONS filter (14 section prefixes)
  - Preserves text length >=100 filter
  - Uses `build_rule_why_prompt()` common builder
  - Source category: "rule_why"

- **main.py**: Updated Phase 3 instantiation blocks for all 5 generators to use new BaseGenerator constructor signature (`data_access=`, `models=`, `validation_pct=`, `target_count=`, `save_item=`, `metrics=`, `dry_run=`) and call `.generate()` instead of generator-specific methods. Added missing import for `GenerateRuleWhyQuestions`.

- **Tests**: 219 tests pass (177 existing + 42 new), zero regressions across entire test suite

### Feature: Convert final 4 topic-based generators to BaseGenerator[str] — 2026-07-20

- **generate_meta_knowledge.py**: Converted `GenerateMetaKnowledge` to extend `BaseGenerator[str]`
  - Preserves all 9 topics (cEDH viability, power level scale, fast mana, tutors, etc.) as class-level `TOPICS` list
  - Defines 2 templates: `general_advice` and `meta_deep_dive` with distinct validation criteria
  - Implements `get_data_batches()`, `build_prompt()`, `get_source_category()` → "meta_knowledge", `build_context()`

- **generate_commander_knowledge.py**: Converted `GenerateCommanderKnowledge` to extend `BaseGenerator[str]`
  - Breaks monolithic Commander rules topic into 8 sub-topics (deck construction, commander tax, damage, command zone, color identity, multiplayer, partner/background, companion/wish)
  - Defines 2 templates: `general_advice` and `example_driven` with distinct validation criteria
  - New inline prompt replaces old `build_commander_prompt()` that generated 20 Q&A in a single call
  - Implements `get_data_batches()`, `build_prompt()`, `get_source_category()` → "commander_rules", `build_context()`

- **generate_terminology_questions.py**: Converted `GenerateTerminologyQuestions` to extend `BaseGenerator[str]`
  - Preserves all 20 terminology terms (CEDH, pillow fort, MLD, staple, salt, etc.) as class-level `TERMINOLOGY` list
  - **Behavior change**: Old pattern created Q&A directly (question = "What is X?", answer = definition) with no LLM generation. New pattern uses LLM generation for varied questions and richer answers with examples.
  - Defines 2 templates: `definition_focused` and `practical_application` with distinct validation criteria
  - Implements `get_data_batches()`, `build_prompt()`, `get_source_category()` → "terminology", `build_context()`

- **generate_archetypes.py**: Converted `GenerateArchetypes` to extend `BaseGenerator[str]`
  - Preserves all 10 archetypes (Aggro, Control, Combo, Midrange, Stax, Voltron, Tokens, Reanimator, Storm, Pillow Fort) as class-level `ARCHETYPES` list
  - **Removed pymongo/ScryfallMongo dependencies** — no longer takes `card_collection`, `archetype_collection`, or `scryfall_client` in constructor
  - Defines 2 templates: `general_advice` and `example_driven` with distinct validation criteria
  - Implements `get_data_batches()`, `build_prompt()`, `get_source_category()` → "archetype", `build_context()`

- **main.py**: Updated instantiation for all 4 generators to use new BaseGenerator constructor signature (`models=`, `validation_pct=`, `target_count=`, `save_item=`, `metrics=`, `dry_run=`) and call `.generate()` instead of generator-specific methods

### Feature: Convert 4 topic-based generators to BaseGenerator[str] — 2026-07-20

- **generate_deckbuilding_theory.py**: Converted `GenerateDeckbuildingTheory` to extend `BaseGenerator[str]`
  - Preserves all 12 topics (card evaluation, mana curve, synergy vs goodstuff, etc.) as class-level `TOPICS` list
  - Defines 2 templates: `general_advice` and `example_driven` with distinct validation criteria
  - Implements `get_data_batches()`, `build_prompt()`, `get_source_category()` → "deckbuilding_theory", `build_context()`

- **generate_game_theory.py**: Converted `GenerateGameTheory` to extend `BaseGenerator[str]`
  - Preserves all 10 situations (threat assessment, opening hand evaluation, multiplayer politics, etc.) as class-level `SITUATIONS` list
  - Defines 2 templates: `general_advice` and `scenario_walkthrough` with distinct validation criteria
  - Implements `get_data_batches()`, `build_prompt()`, `get_source_category()` → "game_theory", `build_context()`

- **generate_commander_building.py**: Converted `GenerateCommanderBuilding` to extend `BaseGenerator[str]`
  - Preserves all 12 archetypes (sacrifice/aristocrats, spellslinger/magecraft, token swarm, reanimator, etc.) as class-level `ARCHETYPES` list
  - Defines 2 templates: `general_advice` and `example_driven` with distinct validation criteria
  - Implements `get_data_batches()`, `build_prompt()`, `get_source_category()` → "commander_building", `build_context()`

- **generate_rules_scenarios.py**: Converted `GenerateRulesScenarios` to extend `BaseGenerator[str]`
  - Preserves all 15 scenarios (stack resolution, combat damage, triggered abilities, SBAs, etc.) as class-level `SCENARIOS` list
  - Defines 2 templates: `general_advice` and `example_driven` with distinct validation criteria
  - Implements `get_data_batches()`, `build_prompt()`, `get_source_category()` → "rules_scenario", `build_context()`

- **main.py**: Updated instantiation for all 4 generators to use new BaseGenerator constructor signature (`models=`, `validation_pct=`, `target_count=`, `save_item=`, `metrics=`, `dry_run=`) and call `.generate()` instead of generator-specific methods

### Fix: 13 failing unit tests in generate_synthetic_data — 2026-07-20

- **test_generate_color_identity_questions.py**: Added `lite` parameter to `MockDataAccess.get_cards_enriched()` to match production signature, fixing 11 TypeError failures
- **test_data_access.py**: Updated pipeline builder tests (`test_build_combo_pipeline`, `test_build_commander_pipeline`) to assert on actual MongoDB stage structures after pipeline refactoring, fixing 2 assertion failures

### Feature: GenerateColorIdentityQuestions with BaseGenerator + MTGDataAccess — 2026-07-19

- **generate_color_identity_questions.py**: Implemented new `GenerateColorIdentityQuestions` inheriting from `BaseGenerator[ColorIdentityContext]`
  - Uses `MTGDataAccess.get_commanders_enriched()` + `get_cards_enriched()` + `get_legalities_for_cards()` for data
  - Fetches EDHREC commanders weighted by `num_decks` (popularity) with distribution: mono (10), two-color (15), three-color (10), five-color (5)
  - Calculates color identity legality: `card.colors ⊆ commander.color_identity` per Commander rule 903.4
  - Defines 4 templates via `TemplateConfig` with distinct intents:
    - `mono_color`: "Can I play [card] in my mono-[color] [commander] deck?" — explains rule 903.4, checks mana symbols + color indicator, gives yes/no with reasoning
    - `two_color`: "Is [card] legal in my [color pair] commander deck?" — explains both colors, hybrid mana counts as both, distinguishes color vs color identity
    - `three_color`: "What's the color identity of [card]? Can it go in [3-color commander]?" — handles wedge/shard, off-color fetch lands, checks all mana symbols
    - `five_color`: "Are there any color identity restrictions in 5-color commanders?" — explains no restrictions, mentions The World Tree, Domain, Converge, Sunburst, Bring to Light, notable 5-color commanders
  - Implements `get_data_batches()`, `build_prompt()`, `get_source_category()` → "color_identity", `get_source_data()`, `build_context()` with rich validation context (card details, commander details, legality, rule 903.4 text, color identity explanation)
  - Template-specific validation criteria with HARD REJECT rules per template type
  - Replaces legacy `GenerateColorIdentityQuestions` that used raw pymongo collections

- **main.py**: Updated to use new generator architecture
  - Passes `data_access` to `GenerateColorIdentityQuestions` constructor
  - Calls `.generate()` instead of `.generate_color_identity_questions()`

### Feature: GenerateQuickGuidelines with BaseGenerator + MTGDataAccess — 2026-07-19

- **generate_quick_guidelines.py**: Implemented new `GenerateQuickGuidelines` inheriting from `BaseGenerator[dict]`
  - Uses `MTGDataAccess.get_archetype_data()`, `get_commanders_enriched()`, `get_game_states()`, `get_top_cards_by_edhrec_rank()` for data-driven guidelines
  - Defines 19 archetypes from EDHREC tags + mtg_archetypes: aristocrats, spellslinger, token_swarm, reanimator, combo, control, voltron, stax, landfall, graveyard_value, turbo_draw, midrange, enchantress, artifact, planeswalker, tribal_elves, tribal_goblins, tribal_zombies, tribal_dragons
  - Defines 5 templates via `TemplateConfig` with distinct intents:
    - `land_count`: "How many lands should my [archetype] deck run?" — specific range (36-38), explains based on curve/ramp, cites 2+ commanders, mentions ramp effect
    - `ramp_package`: "How much ramp does [archetype] need?" — count range (8-12), breaks down by type (land/artifact/ritual), explains based on commander CMC, lists 3+ specific cards, mentions color constraints
    - `removal_suite`: "What removal should I run in [archetype]?" — count range (8-12), targeted vs board wipes breakdown, explains based on archetype role, lists 3+ specific cards matching colors, mentions versatile vs narrow
    - `card_advantage`: "How do I get card advantage in [archetype]?" — 3+ specific engines (draw/selection/recursion), explains synergy with archetype, distinguishes burst vs steady, cites 1+ commander enabling CA
    - `win_con_density`: "How many win conditions does [archetype] need?" — specific count/range (2-4), explains compact vs redundant, lists 2+ example win cons, explains strategy impact, mentions tutor density relationship
  - Implements `get_data_batches()`, `build_prompt()`, `get_source_category()` → "quick_guideline", `get_source_data()`, `build_context()` with rich validation context (strategy, commanders, key cards, avg CMC, color identity, deck stats)
  - Template-specific validation criteria with HARD REJECT rules per template type
  - Replaces legacy `GenerateQuickGuidelines` that used hardcoded guidelines without archetype-specific data

- **main.py**: Updated to use new generator architecture
  - Passes `data_access` to `GenerateQuickGuidelines` constructor
  - Calls `.generate()` instead of `.generate_quick_guidelines()`

- **test_generate_quick_guidelines.py**: Added comprehensive unit tests
  - Tests all 5 templates defined with validation rules
  - Tests data batch generation for all 19 archetypes
  - Tests archetype context contains required fields (strategy, commanders, key cards, avg CMC, color identity, deck stats)
  - Tests prompt building includes archetype context and MTG notation
  - Tests source category, source data extraction, and validation context
  - Tests dry-run generation works correctly

### Feature: GenerateComparisonQuestions with BaseGenerator + MTGDataAccess — 2026-07-19

- **generate_comparison_questions.py**: Implemented new `GenerateComparisonQuestions` inheriting from `BaseGenerator[tuple[CardWithMetadata, CardWithMetadata]]`
  - Uses `MTGDataAccess.get_cards_enriched()` to fetch pairs of similar cards across 10 effect categories (Fast Mana, Green Ramp, Removal, Card Draw, Counterspells, Board Wipes, Tutors, Reanimation, Protection, Token Generation)
  - Creates card pairs using 3 strategies: adjacent EDHREC rank, same CMC different colors, same effect different colors
  - Defines 4 templates via `TemplateConfig` with distinct intents:
    - `power_level`: "Which is stronger: [card1] or [card2] for [archetype]?" — compares EDHREC rank, inclusion %, salt score, cites oracle text
    - `mana_efficiency`: "Which gives better mana value: [card1] or [card2]?" — calculates CMC, net mana advantage, tempo, colored vs colorless
    - `commander_suitability`: "Should I run [card1] or [card2] in my [commander] deck?" — checks color identity legality, commander synergy
    - `synergy_potential`: "Which has better synergy with [theme]: [card1] or [card2]?" — identifies shared keywords/mechanics, explains interaction
  - 10 example commanders and 15 synergy themes for context variation
  - Implements `get_data_batches()`, `build_prompt()`, `get_source_category()` → "comparison", `get_source_data()`, `build_context()` with rich validation context (full card details, EDHREC stats, prices, legalities, keywords, rulings)
  - Template-specific validation criteria with HARD REJECT rules per template type
  - Replaces legacy `GenerateComparisonQuestions` that used raw pymongo collections

- **main.py**: Updated to use new generator architecture
  - Passes `data_access` to `GenerateComparisonQuestions` constructor
  - Calls `.generate()` instead of `.generate_comparison_questions()`

### Feature: GenerateCardSearchQueries with BaseGenerator + MTGDataAccess — 2026-07-19

- **generate_card_search_queries.py**: Implemented new `GenerateCardSearchQueries` inheriting from `BaseGenerator[CardWithMetadata]`
  - Uses `MTGDataAccess.get_cards_enriched()` with filters for search patterns (text regex, colors, Commander legality)
  - Defines 5 templates via `TemplateConfig` with distinct intents:
    - `competitive`: "What are the best cards for [effect] in competitive Commander?" — cites EDHREC rank, inclusion %, top-tier cards
    - `budget`: "What are good budget options for [effect] under $5?" — cites actual USD prices, budget alternatives
    - `commander_specific`: "What [effect] cards work well in [commander] deck?" — checks color identity legality, commander synergy
    - `thematic`: "What cards support [theme/mechanic] strategy?" — explains mechanic synergy, cites keyword interactions
    - `beginner`: "I'm new to Commander, what [effect] cards should I consider?" — simple terms, no jargon, concrete examples
  - 20 search patterns covering: Green Ramp, Zombie Tokens, Treasure Tokens, White Removal, Blue Card Draw, ETB Effects, Black Removal, Red Burn, Counterspells, Board Wipes, Tutors, Reanimation, Protection, Sacrifice Outlets, Artifact Ramp, Graveyard Hate, Politics/Group Hug, Landfall, Proliferate, Blink/Flicker
  - Implements `get_data_batches()`, `build_prompt()`, `get_source_category()` → "card_search", `get_source_data()`, `build_context()` with rich validation context (prices, EDHREC ranks, keywords, legalities, oracle text snippets)
  - Template-specific validation criteria with HARD REJECT rules per template type
  - Replaces legacy `GenerateCardSearchQueries` that used raw pymongo collections

- **main.py**: Updated to use new generator architecture
  - Passes `data_access` to `GenerateCardSearchQueries` constructor
  - Calls `.generate()` instead of `.generate_card_search_queries()`

### Refactor: Pilot Generators to BaseGenerator + MTGDataAccess — 2026-07-19

- **generate_combo_queries.py**: Refactored `GenerateComboQueries` to inherit from `BaseGenerator[ComboWithCards]`
  - Removed manual MongoDB connection handling (combos_collection, card_collection, scryfall_client)
  - Uses `MTGDataAccess.get_combos_enriched()` in `get_data_batches()`
  - Defines 4 templates via `TemplateConfig`: `how_does_it_work`, `what_do_i_need`, `why_does_this_work`, `what_is_the_result`
  - Implements `build_prompt()`, `get_source_category()` → "combo_query", `get_source_data()`, `build_context()`
  - Validation criteria with HARD REJECT rules for each template type
  - Removed `__extract_combo_data()`, `__map_combo_cards()`, `__map_using_card()` — replaced by data_access

- **generate_article_qa.py**: Refactored `GenerateArticleQa` to inherit from `BaseGenerator[Article]`
  - Removed manual MongoDB connection handling (articles_collection)
  - Uses `MTGDataAccess.get_articles()` in `get_data_batches()`
  - Defines 1 template via `TemplateConfig`: `article_qa`
  - Implements `build_prompt()`, `get_source_category()` → "article_qa", `get_source_data()`, `build_context()`
  - Validation criteria with HARD REJECT rules

- **main.py**: Updated to use new architecture
  - Creates single `MTGDataAccess` instance at startup
  - Passes `data_access` to refactored generators via new constructor signatures
  - Calls `.generate()` (base class method) instead of generator-specific methods
  - Closes `data_access` at end of run
  - Other generators unchanged (still use old collection-passing pattern)