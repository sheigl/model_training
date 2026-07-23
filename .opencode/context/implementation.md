# Implementation Summary

# Implementation Summary: Fix Code Review Issues in Generation Trace Logging (Jul 21, 2026)

## Changes Made

### 1. `common.py` — Trace data loss + final_outcome fix
- **Fix 1 (Critical)**: When `new_answer is None` (regeneration fails), `round_data` was NOT being appended to `trace.validation_rounds` before the `break`. Now appends round_data (containing both failed validation and failed regeneration data) before breaking.
- **Fix 6 (Minor)**: `final_outcome` was misleading for skipped validation — when `should_validate` is False, it now reports "skipped" instead of being computed from `is_valid` which is stale from a previous loop or uninitialized.

### 2. `base_generator.py` — Double-parse + callback + imports
- **Fix 2 (Critical)**: Eliminated redundant double-parse of generation response. `_parse_generation_response()` was called once purely for the `trace.generation_parsed_ok` flag (result discarded), then called again for the actual parse. Now parses once, captures the result, and derives the trace flag from it.
- **Fix 3 (Major)**: Trace callback was firing for every successful Q&A pair in the qa_pairs loop. If a template generates 3 Q&A pairs, the callback fired 3 times with the same mutable trace object that had accumulating `validation_rounds`. Now fires once and sets `trace = None` to prevent repeated firing.
- **Fix 4 (Major)**: `from datetime import datetime` and `import uuid` were imported inside the for loop body. Moved to module-level imports alongside existing imports.

### 3. `query_model.py` — Stale elapsed time on failure
- **Fix 5 (Minor)**: `self._last_elapsed_ms` was not updated when `query()` raised an exception. Added `self._last_elapsed_ms = int((end - start) * 1000)` to the except block before re-raising.

## Testing
- 201 tests pass, 18 pre-existing failures (MockQueryModel missing `purpose` kwarg, stale pipeline assertions, missing MongoDB)
- Zero regressions introduced by these fixes

---

# Implementation Summary: Model Output Trace Logging (Jul 21, 2026)

## Changes Made

### 1. `models.py` — Added `GenerationTrace` dataclass
- New dataclass capturing full LLM interaction traces per Q&A item
- Fields: item_id (UUID), run_id, category, source_template, generator_name, models, timestamps
- Generation section: prompt, response, parsed_ok, latency_ms
- Validation rounds: list of dicts with round#, prompt, response, score, errors, verification_checklist, regeneration details
- Final outcome: pending / accepted_first_attempt / accepted_after_fix / rejected
- Added to `__all__` in both try/except branches

### 2. `query_model.py` — Added trace instrumentation
- `__init__()`: Added `self._last_elapsed_ms = 0` for timing capture
- `query()`: After `end = time.time()`, stores `self._last_elapsed_ms = int((end - start) * 1000)`
- `validate_qa()`: New optional `trace_round: dict | None = None` parameter; populates dict with prompt, response, score, errors, latency on success/failure
- `regenerate_answer()`: New optional `trace_regeneration: dict | None = None` parameter; populates dict with prompt, response, parsed_ok, new_answer, latency on success/failure

### 3. `common.py` — Trace accumulation in validation loop
- Added `from __future__ import annotations` at top
- `validate_and_loop_with_suggested_fix()`: New optional `trace: GenerationTrace | None = None` parameter
- Initializes `round_num = 0` before loop, creates `round_data = {"round": round_num}` per iteration
- Passes `trace_round=round_data` to `validate_qa()` and `trace_regeneration=regen_data` to `regenerate_answer()`
- Appends `round_data` to `trace.validation_rounds` before continue/break
- After loop: computes `trace.total_rounds`, `trace.final_score`, `trace.final_outcome`

### 4. `base_generator.py` — Trace creation and callback wiring
- Added `trace_callback: Callable[[GenerationTrace], None] | None = None` parameter to `__init__()`
- `_process_item()`: Creates `GenerationTrace` per template iteration (when callback exists), populates generation_prompt/response/latency/parsed_ok after query, passes `trace=trace` to `validate_answer()`, fires callback after successful save
- `validate_answer()`: New optional `trace` parameter, passes through to `validate_and_loop_with_suggested_fix()`

### 5. `main.py` — CLI flags and MongoDB writer
- Added `--log-traces` / `--no-log-traces` CLI flags (default: enabled)
- Added `generation_traces` collection from `synthetic_metrics` DB
- Added MongoDB indexes: compound (run_id, category, final_outcome) and item_id
- Added `save_trace()` / `flush_traces()` with 50-doc batch buffer
- Wired `trace_callback=save_trace if args.log_traces else None` to all 27 generator instantiations
- Flush remaining traces before `data_access.close()`

### 6. `test_base_generator.py` — Mock signature updates
- Updated `MockQueryModel.validate_qa()` to accept `trace_round: dict | None = None`
- Updated `MockQueryModel.regenerate_answer()` to accept `trace_regeneration: dict | None = None`
- Prevents TypeError when `validate_and_loop_with_suggested_fix` passes new keyword args

## Key Design Decisions
- **Optional by default**: All new parameters default to `None`, so existing code works unchanged
- **Separate MongoDB collection**: Traces stored in `synthetic_metrics.generation_traces`, not embedded in Q&A docs
- **CLI flag**: `--log-traces` enabled by default, `--no-log-traces` to disable
- **Batch flushing**: 50 traces per batch to MongoDB for performance

## Testing
- All syntax checks pass for all 6 modified files
- Integration tests verify: GenerationTrace dataclass, _last_elapsed_ms timing, trace_callback wiring, trace accumulation in validation loop (accepted_first_attempt, accepted_after_fix, rejected), backward compatibility (no trace_callback)
- No regressions in existing test infrastructure (conftest mock pattern unchanged)

---

# Implementation Summary: Convert 5 Rules-Grounded Generators to BaseGenerator + MTGDataAccess (Jul 20, 2026)

## Changes Made

### 1. `generate_rule_explanations.py` — Converted to BaseGenerator[Rule]
- Uses `MTGDataAccess.get_rules()` instead of raw pymongo collection
- Preserves SKIP_SECTIONS filter ({000-005, 900}), text length >50 filter, and templates_per_item=2
- Defines TEMPLATES from RULE_EXPLANATION_TEMPLATES with validation rules from RULE_EXPLANATION_VALIDATION
- Uses `build_rule_explanation_prompt()` common builder

### 2. `generate_rule_interactions.py` — Converted to BaseGenerator[ProjectedRulePair]
- `ProjectedRulePair` is now a dataclass (was plain class) with same fields: name, rule1_number/text, rule2_number/text, sections
- Preserves all 37 INTERACTION_PAIRS, section grouping logic, deduplication via seen_names
- Custom inline prompt builder preserved in `build_prompt()` method
- Uses `MTGDataAccess.get_rules()` instead of raw pymongo collection

### 3. `generate_glossary_with_examples.py` — Converted to BaseGenerator[GlossaryTerm]
- Uses `MTGDataAccess.get_glossary()` instead of raw pymongo collection
- Preserves definition length >30 filter and single template behavior
- Uses `build_glossary_with_examples_prompt()` common builder

### 4. `generate_rule_edge_cases.py` — Converted to BaseGenerator[Rule]
- Uses `MTGDataAccess.get_rules()` instead of raw pymongo collection
- Preserves COMPLEX_RULE_SECTIONS filter and text length >=80 filter
- Section name lookup moved into `build_prompt()` (was stored on rule dict in old pattern)

### 5. `generate_rule_why_questions.py` — Converted to BaseGenerator[Rule]
- Uses `MTGDataAccess.get_rules()` instead of raw pymongo collection
- Preserves PRINCIPLE_SECTIONS filter and text length >=100 filter
- Uses `build_rule_why_prompt()` common builder

### 6. `main.py` — Updated Phase 3 instantiation blocks
- All 5 generators now use new BaseGenerator constructor signature with keyword args
- Calls `.generate()` instead of generator-specific methods (`.generate_rule_explanations()`, etc.)
- Supports `dry_run` parameter for all 5 generators

### 7. Unit tests — 35 new tests in `test_generate_rules_generators.py`
- Tests cover: templates defined, skip sections, source category, data batch filtering, build_prompt behavior, BaseGenerator inheritance, ProjectedRulePair structure

## Architecture Pattern

All 5 generators follow the same pattern:
- **Data type**: `Rule`, `ProjectedRulePair`, or `GlossaryTerm` (typed domain models)
- **get_data_batches()**: Fetches from MTGDataAccess, filters in Python, yields `[item]` per batch
- **build_prompt()**: Delegates to common.py builder functions with data_batch fields
- **get_source_category()**: Returns category string for metrics

## Testing

- All 60 tests pass (25 original + 35 new)
- All new files pass ruff linting

---

# Implementation Summary: Convert Final 4 Topic-Based Generators to BaseGenerator[str] (Jul 20, 2026)

## Changes Made

### 1. `generate_meta_knowledge.py` — Converted to BaseGenerator[str]
- Preserves all 9 topics as class-level `TOPICS` list with descriptions
- Defines 2 templates: `general_advice` and `meta_deep_dive`
- Implements `get_data_batches()`, `build_prompt()`, `get_source_category()` → "meta_knowledge", `build_context()`

### 2. `generate_commander_knowledge.py` — Converted to BaseGenerator[str]
- Breaks monolithic Commander rules topic into 8 sub-topics as class-level `COMMANDER_SUBTOPICS` list
- Covers: deck construction, commander tax, commander damage, command zone, color identity, multiplayer, partner/background, companion/wish
- Defines 2 templates: `general_advice` and `example_driven`
- New inline prompt replaces old `build_commander_prompt()` (was monolithic 20 Q&A generator)
- Implements `get_data_batches()`, `build_prompt()`, `get_source_category()` → "commander_rules", `build_context()`

### 3. `generate_terminology_questions.py` — Converted to BaseGenerator[str]
- Preserves all 20 terminology terms as class-level `TERMINOLOGY` list with definitions
- **Behavior change**: Old pattern created Q&A directly (no LLM). New pattern uses LLM generation for varied, richer output.
- Defines 2 templates: `definition_focused` and `practical_application`
- Implements `get_data_batches()`, `build_prompt()`, `get_source_category()` → "terminology", `build_context()`

### 4. `generate_archetypes.py` — Converted to BaseGenerator[str]
- Preserves all 10 archetypes as class-level `ARCHETYPES` list with descriptions
- **Removed pymongo/ScryfallMongo dependencies** — no longer needs card/archetype collections
- Defines 2 templates: `general_advice` and `example_driven`
- Implements `get_data_batches()`, `build_prompt()`, `get_source_category()` → "archetype", `build_context()`

### 5. `main.py` — Updated instantiation for all 4 generators
- Uses new BaseGenerator constructor signature with keyword args
- Calls `.generate()` instead of generator-specific methods
- Supports `dry_run` parameter for all 4 generators

### 6. Unit tests — 4 new test files, 62 tests total
- `tests/test_generate_meta_knowledge.py`: 13 tests (templates, data batches, source category, build prompt, build context, dry run)
- `tests/test_generate_commander_knowledge.py`: 14 tests (includes 8 subtopic check)
- `tests/test_generate_terminology_questions.py`: 14 tests (includes 20 terms check)
- `tests/test_generate_archetypes.py`: 14 tests (includes no pymongo import check)

## Architecture Pattern

All 4 generators follow the same pattern:
- **Data type**: `str` (topic/sub-topic/term/archetype name)
- **get_data_batches()**: Cycles through hardcoded list, yielding `[name]` per batch
- **build_prompt()**: Looks up description by name, formats template instruction with domain-specific context + output_format
- **build_context()**: Returns category, template_id, and domain-specific label for validation

## Testing

- All 145 tests pass (83 original + 62 new)
- All new files pass ruff linting
- All new files pass ruff format check

---

# Implementation Summary: Convert 4 Topic-Based Generators to BaseGenerator[str] (Jul 20, 2026)

## Changes Made

### 1. `generate_deckbuilding_theory.py` — Converted to BaseGenerator[str]
- Preserves all 12 topics as class-level `TOPICS` list with descriptions
- Defines 2 templates: `general_advice` and `example_driven`
- Implements `get_data_batches()`, `build_prompt()`, `get_source_category()` → "deckbuilding_theory", `build_context()`

### 2. `generate_game_theory.py` — Converted to BaseGenerator[str]
- Preserves all 10 situations as class-level `SITUATIONS` list with descriptions
- Defines 2 templates: `general_advice` and `scenario_walkthrough`
- Implements `get_data_batches()`, `build_prompt()`, `get_source_category()` → "game_theory", `build_context()`

### 3. `generate_commander_building.py` — Converted to BaseGenerator[str]
- Preserves all 12 archetypes as class-level `ARCHETYPES` list with descriptions
- Defines 2 templates: `general_advice` and `example_driven`
- Implements `get_data_batches()`, `build_prompt()`, `get_source_category()` → "commander_building", `build_context()`

### 4. `generate_rules_scenarios.py` — Converted to BaseGenerator[str]
- Preserves all 15 scenarios as class-level `SCENARIOS` list with descriptions
- Defines 2 templates: `general_advice` and `example_driven`
- Implements `get_data_batches()`, `build_prompt()`, `get_source_category()` → "rules_scenario", `build_context()`

### 5. `main.py` — Updated instantiation for all 4 generators
- Uses new BaseGenerator constructor signature with keyword args
- Calls `.generate()` instead of generator-specific methods

## Architecture Pattern

All 4 generators follow the same pattern:
- **Data type**: `str` (topic/situation/archetype/scenario name)
- **get_data_batches()**: Cycles through hardcoded list, yielding `[name]` per batch
- **build_prompt()**: Looks up description by name, formats template instruction with topic + context + output_format
- **build_context()**: Returns category, template_id, and domain-specific label for validation

## Testing

- All existing tests pass (25 tests in test_base_generator.py)
- Code passes ruff linting (all 4 new files clean)

---

# Implementation Summary: GenerateCardSearchQueries

## Changes Made

### 1. New File: `training_data/generate_synthetic_data/generate_card_search_queries.py`
- Implements `GenerateCardSearchQueries` class inheriting from `BaseGenerator[CardWithMetadata]`
- Uses `MTGDataAccess.get_cards_enriched()` with filters for search patterns
- Defines 5 templates with distinct intents:
  - **competitive**: EDHREC rank, inclusion %, top-tier cards (rank < 500)
  - **budget**: Actual USD prices, cards under $5, budget alternatives
  - **commander_specific**: Color identity legality, commander synergy
  - **thematic**: Mechanic synergy, keyword interactions
  - **beginner**: Simple terms, no jargon, concrete examples
- 20 search patterns covering major Commander archetypes/effects
- Template-specific validation criteria with HARD REJECT rules
- Rich validation context including prices, EDHREC ranks, keywords, legalities, oracle text snippets

### 2. Modified: `training_data/generate_synthetic_data/main.py`
- Updated import: `from generate_card_search_queries import GenerateCardSearchQueries`
- Updated usage to pass `data_access` and call `.generate()` instead of `.generate_card_search_queries()`

### 3. Updated: `CHANGELOG.md`
- Added entry for the new implementation

## Architecture

The new generator follows the BaseGenerator pattern:
- `get_data_batches()`: Yields card batches for each search pattern × template combination
- `build_prompt()`: Builds LLM prompt with card details and template-specific instructions
- `get_source_category()`: Returns "card_search"
- `get_source_data()`: Returns card dicts for source tracking
- `build_context()`: Provides rich validation context with prices, ranks, keywords, legalities

## Testing

- All existing tests pass (25 tests in test_base_generator.py)
- Code passes ruff linting
- Syntax check passes for both new and modified files

---

# Implementation Summary: Fix 13 Failing Unit Tests (Jul 20, 2026)

## Changes Made

### 1. `test_generate_color_identity_questions.py` — MockDataAccess missing `lite` parameter
- Added `lite: bool = False` parameter to `MockDataAccess.get_cards_enriched()` method signature
- This matches the production `MTGDataAccess.get_cards_enriched()` which added a `lite` parameter for skipping expensive joins
- Fixed 11 test failures that were all caused by `TypeError: got an unexpected keyword argument 'lite'`

### 2. `test_data_access.py` — Pipeline builder tests assert old MongoDB stages
- **`test_build_combo_pipeline`**: Updated assertions to match refactored pipeline structure (`$match → $limit → $addFields ×2 → $project`). Removed stale assertions for `$unwind`, `$lookup`, `$group` which no longer exist. Added behavioral checks for filter merging and limit value.
- **`test_build_commander_pipeline`**: Updated assertions to match refactored pipeline structure (`$match → $project → $limit`). Removed stale assertions for `$lookup`, `$addFields`. Added behavioral checks for filter passthrough, limit value, and field mapping in project stage.

## Result
All 142 tests pass (was 13 failed, 129 passed). No production code was modified.

---

# Implementation Summary: Convert 5 EDHREC-Grounded Generators to BaseGenerator + MTGDataAccess (Jul 20, 2026)

## Changes Made

### 1. `data_access.py` — Added 3 new methods
- **`get_game_changers(limit)`**: Fetches game-changer cards from edhrec.game-changers sorted by num_decks descending
- **`get_salty_cards(min_salt, limit)`**: Fetches high-salt cards (salt >= threshold) from edhrec.game-changers sorted by salt descending
- **`get_top_cards_by_color(color, limit)`**: Fetches top cards from dynamic edhrec.top-{color} collections sorted by num_decks

### 2. `generate_guide_qa.py` — Converted to BaseGenerator[Guide]
- Uses `MTGDataAccess.get_guides()` instead of raw pymongo collection
- Preserves content length >300 filter and random shuffle behavior
- Defines 1 template: `guide_qa`
- Source category: "guide_qa"

### 3. `generate_staple_analysis.py` — Converted to BaseGenerator[dict]
- Uses `MTGDataAccess.get_game_changers()` instead of raw pymongo collection
- Preserves game_changer=True filter and num_decks sorting
- Defines 1 template: `staple_analysis`
- Source category: "staple_analysis"

### 4. `generate_color_staples.py` — Converted to BaseGenerator[tuple[str, list[dict]]]
- Uses `MTGDataAccess.get_top_cards_by_color()` for all 6 colors instead of raw collections dict
- Preserves per-color subset logic (10/20/30 card groups)
- Defines 1 template: `color_staples`
- Source category: "color_staples"

### 5. `generate_salt_questions.py` — Converted to BaseGenerator[list[dict]]
- Uses `MTGDataAccess.get_salty_cards()` instead of raw pymongo collection
- Preserves batch_size=8 grouping and salt >= 1.2 threshold
- Defines 1 template: `salt_analysis`
- Source category: "salt_analysis"

### 6. `generate_multi_card_usage.py` — Converted to BaseGenerator[ComboWithCards]
- Uses `MTGDataAccess.get_combos_enriched()` instead of raw pymongo collection
- Preserves card_names < 2 filter and description check
- Defines 1 template: `multi_card`
- Source category: "multi_card_usage"

### 7. `main.py` — Updated all 5 instantiation blocks
- All 5 generators now use new BaseGenerator constructor signature with keyword args (`data_access=`, `models=`, etc.)
- Calls `.generate()` instead of generator-specific methods (`.generate_guide_qa()`, `.generate_staple_analysis()`, `.generate_color_staples()`, `.generate_salt_questions()`, `.generate_multi_card_usage()`)
- Supports `dry_run` parameter for all 5 generators

## Architecture Pattern

All 5 generators follow the same BaseGenerator pattern:
- **Data type**: Domain-specific (`Guide`, `dict`, `tuple[str, list[dict]]`, `list[dict]`, `ComboWithCards`)
- **get_data_batches()**: Fetches from MTGDataAccess, filters in Python, yields `[item]` per batch
- **build_prompt()**: Delegates to common.py builder functions with data_batch fields
- **get_source_category()**: Returns category string for metrics

## Testing

- All 145 tests pass (no regressions)
- All new/modified files pass ruff linting (0 errors in changed code)