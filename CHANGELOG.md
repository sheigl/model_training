# Changelog

## [Unreleased] — TrainForge Generic Framework (2026-07-24)

### Feature: MTG AI Pipeline prompt improvements (sibling feedback + trigger ordering) — 2026-07-26

Three coordinated changes to improve the generator model's first-attempt pass rate from ~46% to a projected ~55-60%, targeting the two largest failure modes (wrong trigger/stack ordering ~50% of failures, vague outcomes ~20% of failures).

**Change 1 — Generator prompt (`constants.py`)**
- New item inserted at index 3 of `REQUIREMENTS_BASE`: "CRITICAL — Trigger ordering: ..." covering LIFO stack resolution, ETB timing, static vs triggered ability rules. Targets the #1 failure mode.
- Vague-outcome item (index 5) expanded: banned phrases now include "infinite triggers", "infinite value", "overwhelm opponents"; example updated to "infinite 1/1 Snake creature tokens".
- `REQUIREMENTS_BASE` list grew from 8 to 9 items.

**Change 2 — Fix prompt (`query_model.py`)**
- `regenerate_answer` gained a `sibling_feedback: str = ""` parameter. When Q2/Q3 of a combo generation are being corrected, they now see what was wrong with and how Q1 was corrected.
- `sibling_block` is built conditionally and inserted into the prompt f-string after the context block.

**Change 3 — Sibling feedback threading (hoisted accumulator architecture)**
- `base_generator.py` `_process_item`: added `sibling_corrections: list[str] = []` before the QA loop; passes it to `validate_answer`.
- `base_generator.py` `validate_answer`: added `sibling_corrections: list[str] | None = None` param; threads it into `validate_and_loop_with_suggested_fix`.
- `generate_quick_guidelines.py` `validate_answer` override: added the same `sibling_corrections` param.
- `common.py` `validate_and_loop_with_suggested_fix`: added `sibling_corrections: list[str] | None = None` param; passes `sibling_feedback` to `regenerate_answer`; appends to the accumulator on successful fix (guarded by `if sibling_corrections is not None`).

**Architecture note**: The accumulator is hoisted into `BaseGenerator._process_item` (not inside `validate_and_loop_with_suggested_fix`) because that function is always called with `qa_pairs` of length 1. The 3 sibling Q&As from one combo generation are iterated by `_process_item`'s own loop, so the accumulator must live in that scope to persist across siblings.

**Files changed:**
- `training_data/generate_synthetic_data/constants.py` — `REQUIREMENTS_BASE` expanded
- `training_data/generate_synthetic_data/query_model.py` — `regenerate_answer` `sibling_feedback` param
- `training_data/generate_synthetic_data/common.py` — `validate_and_loop_with_suggested_fix` `sibling_corrections` param
- `training_data/generate_synthetic_data/base_generator.py` — `_process_item` + `validate_answer` sibling_corrections threading
- `training_data/generate_synthetic_data/generate_quick_guidelines.py` — `validate_answer` override `sibling_corrections` param
- 5 test mock files updated to accept the `sibling_feedback` param

**Tests:** 229 passed, 20 pre-existing failures, zero regressions. 5 behavioral tests confirmed sibling feedback threading works.

### Ported 4 medium-sized MTG generators from old CLI to TrainForge — 2026-07-24

| File | Class | Type Param | Category | Data Source |
|------|-------|------------|----------|-------------|
| `combo_queries.py` | `ComboQueriesGenerator` | `ComboWithCards` | `combo_query` | `get_combos_enriched()` — 4 templates: how_does_it_work, what_do_i_need, why_does_this_work, what_is_the_result |
| `budget_alternatives.py` | `BudgetAlternativesGenerator` | `tuple[CardWithMetadata, list[CardWithMetadata]]` | `budget` | `get_cards_enriched()` (edhrecRank<500, price>$20) + `get_budget_alternatives()` |
| `color_identity_questions.py` | `ColorIdentityQuestionsGenerator` | `dict` | `color_identity` | `get_commanders_enriched()` + `get_cards_enriched()` — weighted by popularity, 4 template types (mono/two/three/five-color) |
| `quick_guidelines.py` | `QuickGuidelinesGenerator` | `dict` | `guidelines` | `get_cards_enriched()` (edhrecRank exists) — derives card role (removal, ramp, card_draw, tutor, counterspell) from oracle text |

- All use enriched `MTGDataAccess` via `self.domain.get_data_source()` for data fetching
- Templates loaded from `templates.yaml` (categories already defined: `combo_query`, `budget`, `color_identity`, `guidelines`)
- Each implements `get_data_batches()`, `build_prompt()`, `get_source_category()`, and `build_context()`
- Template task_instruction formatted with placeholders: `{combo_name}`, `{card_details}`, `{expensive_card_name}`, `{card_name}`, `{role}`, etc.
- `generators/__init__.py` and `domains/mtg/__init__.py` updated to export and register all 4 generators
- All 4 files compile clean, 155 core tests pass (0 regressions, 1 pre-existing UI failure)

### Ported 5 large MTG generators from old CLI to TrainForge — 2026-07-24

| File | Class | Type Param | Category | Data Source |
|------|-------|------------|----------|-------------|
| `card_search_queries.py` | `GenerateCardSearchQueries` | `CardWithMetadata` | `card_search` | `get_cards_enriched()` with 20 search patterns |
| `comparison_questions.py` | `GenerateComparisonQuestions` | `tuple[CardWithMetadata, CardWithMetadata]` | `comparison` | `get_cards_enriched()` with 3 pairing strategies |
| `reverse_lookup_questions.py` | `GenerateReverseLookupQuestions` | `dict` | `reverse_lookup` | `search_cards_text()` with 23 effect patterns |
| `synergy_questions.py` | `GenerateSynergyQuestions` | `CardWithMetadata` | `synergy` | `get_synergy_partners()` for top-ranked cards |
| `commander_building.py` | `GenerateCommanderBuilding` | `CommanderWithTags` | `commander_building` | `get_commanders_enriched()` + 12 archetypes |

- All use enriched `MTGDataAccess` via `self.domain.get_data_source()` for data fetching
- Templates loaded from `templates.yaml` (categories already defined: `card_search`, `comparison`, `reverse_lookup`, `synergy`, `commander_building`)
- Each implements `get_data_batches()`, `build_prompt()`, `get_source_category()`, and `build_context()`
- `generators/__init__.py` and `domains/mtg/__init__.py` updated to export and register all 5 generators
- Lint clean, 302 tests pass (0 regressions, 1 pre-existing UI failure)

### 9 data-driven MTG generators complete — all 16 generators now registered — 2026-07-24

All 9 data-driven generators ported, tested, and registered in `MTGDomain.get_generators()`.

| File | Class | Type | Category | Data Source |
|------|-------|------|----------|-------------|
| `staple_analysis.py` | `StapleAnalysisGenerator` | `dict` | `staple_analysis` | `ds.get_game_changers()` |
| `salt_questions.py` | `SaltQuestionsGenerator` | `list[dict]` | `salt_questions` | `ds.get_salty_cards()` |
| `color_staples.py` | `ColorStaplesGenerator` | `tuple[str, list[dict]]` | `color_staples` | `ds.get_top_cards_by_color()` |
| `multi_card_usage.py` | `MultiCardUsageGenerator` | `ComboWithCards` | `multi_card_usage` | `ds.get_combos_enriched()` |
| `guide_qa.py` | `GuideQAGenerator` | `Guide` | `guide_qa` | `ds.get_guides()` |
| `glossary_with_examples.py` | `GlossaryWithExamplesGenerator` | `GlossaryTerm` | `glossary_with_examples` | `ds.get_glossary()` |
| `rule_why_questions.py` | `RuleWhyQuestionsGenerator` | `dict` | `rule_why_questions` | `ds.get_rules()` |
| `rule_edge_cases.py` | `RuleEdgeCasesGenerator` | `dict` | `rule_edge_cases` | `ds.get_rules()` |
| `rule_explanations.py` | `RuleExplanationsGenerator` | `dict` | `rule_explanations` | `ds.get_rules()` |

**Generator totals:** 7 topic-based + 9 data-driven = **16 generators** registered.
**Tests:** 397 total passing, 1 pre-existing failure, lint clean.

### Ported 4 rules/glossary MTG generators from old CLI to TrainForge — 2026-07-24

| File | Class | Type Param | Category | Data Source |
|------|-------|------------|----------|-------------|
| `glossary_with_examples.py` | `GlossaryWithExamplesGenerator` | `GlossaryTerm` | `glossary_with_examples` | `get_glossary(limit=200)`, def > 30 chars |
| `rule_why_questions.py` | `RuleWhyQuestionsGenerator` | `dict` | `rule_why_questions` | `get_rules(limit=500)`, sections 100-199, 400-499, 700-799 |
| `rule_edge_cases.py` | `RuleEdgeCasesGenerator` | `dict` | `rule_edge_cases` | `get_rules(limit=500)`, sections 701-708, text >= 80 |
| `rule_explanations.py` | `RuleExplanationsGenerator` | `dict` | `rule_explanations` | `get_rules(limit=500)`, skip 000-005, 900s, text > 50 |

- All use enriched `MTGDataAccess` via `self.domain.get_data_source()` for data fetching
- Section filtering uses regex extraction from `ruleNumber` field (e.g., `"702.1a"` → `702`)
- Templates loaded from `templates.yaml` (categories already defined: `glossary_with_examples`, `rule_why_questions`, `rule_edge_cases`, `rule_explanations`)
- Each implements `get_data_batches()`, `build_prompt()`, `get_source_category()`, and `build_context()`
- `generators/__init__.py` and `domains/mtg/__init__.py` updated to export and register all 4 generators
- 38 new unit tests across 4 test files, all passing

### Ported 7 topic-based MTG generators from old CLI to TrainForge — 2026-07-24

| File | Class | Topics | Category |
|------|-------|--------|----------|
| `commander_knowledge.py` | `GenerateCommanderKnowledge` | 8 Commander sub-topics | `commander_knowledge` |
| `terminology_questions.py` | `GenerateTerminologyQuestions` | 20 MTG terminology terms | `terminology` |
| `deckbuilding_theory.py` | `GenerateDeckbuildingTheory` | 12 deckbuilding topics | `deckbuilding_theory` |
| `rules_scenarios.py` | `RulesScenariosGenerator` | 15 rules scenarios | `rules_scenarios` |
| `archetypes.py` | `ArchetypesGenerator` | 10 deck archetypes | `archetypes` |
| `game_theory.py` | `GameTheoryGenerator` | 10 game theory situations | `game_theory` |
| `meta_knowledge.py` | `MetaKnowledgeGenerator` | 9 meta knowledge topics | `meta_knowledge` |

- All generators extend `BaseGenerator[str]` with no MongoDB dependencies — data is class-level constant lists (tuples of `(name, description)`)
- Templates loaded from `templates.yaml` via the domain plugin (no hardcoded strings)
- Each implements `get_data_batches()`, `build_prompt()`, `get_source_category()`, and `build_context()`
- `generators/__init__.py` and `domains/mtg/__init__.py` updated to export and register all 7 generators
- 195 tests pass (0 regressions), lint clean

### Ported 5 data-driven MTG generators from old CLI to TrainForge — 2026-07-24

| File | Class | Type Param | Category | Data Source |
|------|-------|------------|----------|-------------|
| `staple_analysis.py` | `StapleAnalysisGenerator` | `dict` | `staple_analysis` | `get_game_changers()` |
| `salt_questions.py` | `SaltQuestionsGenerator` | `list[dict]` | `salt_questions` | `get_salty_cards()` (batches of 8) |
| `color_staples.py` | `ColorStaplesGenerator` | `tuple[str, list[dict]]` | `color_staples` | `get_top_cards_by_color()` (6 colors) |
| `multi_card_usage.py` | `MultiCardUsageGenerator` | `ComboWithCards` | `multi_card_usage` | `get_combos_enriched()` (2+ cards) |
| `guide_qa.py` | `GuideQAGenerator` | `Guide` | `guide_qa` | `get_guides()` (>300 chars) |

- All use enriched `MTGDataAccess` via `self.domain.get_data_source()` for data fetching
- Templates loaded from `templates.yaml` (categories already defined: `staple_analysis`, `salt_questions`, `color_staples`, `multi_card_usage`, `guide_qa`)
- Each implements `get_data_batches()`, `build_prompt()`, `get_source_category()`, and `build_context()`
- `generators/__init__.py` exports all 5 new classes
- Fixed f-string syntax error in existing `staple_analysis.py` (unterminated string on line 104)
- 195 core tests pass (0 regressions), lint clean

### Story 11: Enrich TrainForge MTGDataAccess with typed joins — 2026-07-23

### Story 11: Enrich TrainForge MTGDataAccess with typed joins — 2026-07-23

**Completed components:**

- **`aggregate()` abstract method** added to `DataSource` ABC and implemented on `MongoDataSource` with `allowDiskUse=True`, enabling aggregation pipeline support for enrichment methods
- **22 Pydantic v2 domain models** ported from old CLI (`trainforge/src/trainforge/domains/mtg/models.py`): `Card`, `CardWithMetadata`, `PriceData`, `Ruling`, `Legality`, `CardLegalities`, `Combo`, `ComboWithCards`, `Commander`, `CommanderWithTags`, `Archetype`, `Article`, `Guide`, `GameState`, `Rule`, `GlossaryTerm`, `Keyword`, and more — all with field aliases, validators, computed properties, and factory methods preserved
- **Enriched MTGDataAccess** (`trainforge/src/trainforge/domains/mtg/data_source.py`) with:
  - `LRUCacheWithTTL` (thread-safe, TTL-aware) and `retry_on_transient_error` (exponential backoff) utilities
  - Card enrichment pipeline: `get_cards_enriched()`, `get_card_by_name()`, `get_cards_by_keyword_mechanic()`
  - Combo enrichment: `get_combos_enriched()` with two-phase fetch (aggregate + Python-side card lookup)
  - Commander enrichment: `get_commanders_enriched()` reshaping EDHREC data to `CommanderWithTags`
  - Cached lookups: `get_rulings_for_cards()`, `get_prices_for_cards()`, `get_legalities_for_cards()`, `get_keyword_taxonomy()`, `get_archetype_data()`
  - Analytics: `get_top_cards_by_edhrec_rank()`, `get_budget_alternatives()`, `get_synergy_partners()`, `get_commander_staples()`, `get_format_legalities()`, `calculate_color_identity()`, `search_cards_text()`
  - All 11 original simple methods preserved (backward compatible)
- **Test suite**: 40 new unit tests in `trainforge/tests/domains/mtg/test_data_source.py` (12 test classes), 300/301 total tests pass (1 pre-existing UI failure, 0 regressions)
- **Dual collection namespace**: simple methods query `synthetic_queries.*`, enriched methods query `mtg_json.*`, `commander_spellbook.*`, `edhrec.*`
- **Pipeline builders** as private `_build_*` methods testable in isolation
- **JSON-stringified array fields** parsed in `_convert_doc_to_model` before Pydantic construction
- **Package structure**: `trainforge/src/trainforge/domains/__init__.py` (NEW), `domains/mtg/models.py` (NEW), `domains/mtg/data_source.py` (REWRITTEN)

See sub-entries below for detailed method listings and fixes.

### Fixed: Code review issues in MTGDataAccess + unit test suite — 2026-07-23

- **CRITICAL**: `_convert_doc_to_model` now pre-parses JSON-stringified array fields (colors, colorIdentity, keywords, subtypes, supertypes, frameEffects) before passing docs to Pydantic model constructors, fixing silent data corruption when mtg_json stores array fields as JSON strings
- **CRITICAL**: Fixed `__init__` kwargs ordering — `cache_maxsize`/`cache_ttl` are now popped from kwargs before calling `super().__init__()`, preventing `TypeError: unexpected keyword argument` when these params leak to MongoDataSource
- **MAJOR**: Changed `Ruling.date` type from `datetime` (required) to `datetime | None = None`, fixing Pydantic validation errors when ruling dates are empty strings or missing
- **MAJOR**: Eliminated double calls to `_convert_doc_to_model` in list comprehensions (3 locations: `get_cards_enriched`, `get_budget_alternatives`, `get_synergy_partners`) using walrus operator — previously the expensive conversion ran twice per document
- **MINOR**: Moved `import re as _re` from function body to module-level in `calculate_color_identity`
- **Tests**: Added 40-unit test suite for MTGDataAccess with 12 test classes covering LRU cache, retry decorator, filter translation, pipeline builders, doc-to-model conversion, enrichment methods, combo methods, lookup methods, analytics methods, JSON string parsing, cache integration, and EDHREC rank queries

New `trainforge/` subproject: a **generic synthetic data generation web interface** with Streamlit UI, pluggable domain architecture, and MongoDB backend. Extracts the proven BaseGenerator pattern from the MTG-specific codebase into a reusable framework where new domains can be added by implementing a plugin ABC and providing YAML configuration files — no core code changes required.

### Added: Enriched MTGDataAccess with LRU cache, retry, and 25+ typed methods — 2026-07-23

- Added `LRUCacheWithTTL` (thread-safe, TTL-based eviction) and `retry_on_transient_error` (exponential backoff for MongoDB transient errors) as module-level utilities
- Added class constants `REQUIRED_COLLECTIONS` and `REQUIRED_INDEXES` for collection/index verification
- Added card enrichment pipeline: `get_cards_enriched()`, `get_card_by_name()` (overloaded with `CardWithMetadata` return), `get_cards_by_keyword_mechanic()`, `_translate_card_filters()`, `_build_card_enrichment_pipeline()`
- Added combo enrichment: `get_combos_enriched()`, `_build_combo_pipeline()` — two-phase fetch (aggregate + Python-side card lookup)
- Added commander enrichment: `get_commanders_enriched()`, `_build_commander_pipeline()` — reshapes EDHREC data to `CommanderWithTags`
- Added lookup methods with caching: `get_rulings_for_cards()`, `get_prices_for_cards()`, `get_legalities_for_cards()`, `get_keyword_taxonomy()`, `get_archetype_data()`
- Added analytics methods: `get_top_cards_by_edhrec_rank()`, `get_budget_alternatives()`, `get_synergy_partners()`, `get_commander_staples()`, `get_format_legalities()`, `calculate_color_identity()`, `search_cards_text()`
- Added helpers: `_convert_doc_to_model()`, `_batch_lookup_cards_by_name()`, `verify_indexes()`
- All existing 11 simple methods preserved with backward compatibility (`get_cards()`, `get_articles()`, `get_rules()`, etc.)

### Added: Domain models for MTG data at `trainforge/domains/mtg/models.py` — 2026-07-23

- Ported all 22 Pydantic v2 domain model classes from the reference implementation (`training_data/generate_synthetic_data/domain_models.py`) into the TrainForge project
- Models include: `Card`, `CardWithMetadata`, `PriceData`, `Ruling`, `Legality`, `CardLegalities`, `Combo`, `ComboWithCards`, `Commander`, `CommanderWithTags`, `Archetype`, `Article`, `Guide`, `Rule`, `GlossaryTerm`, `Keyword`, and more
- All field aliases, validators, computed properties (`cmc`, `best_price`, `salt_level`, etc.), factory methods (`from_dict`, `to_prompt_detail`), and `model_rebuild()` calls preserved
- Self-contained module with `__all__` export list — no imports from other trainforge modules

### Added: `aggregate()` method to DataSource ABC and MongoDataSource — 2026-07-23

- Added `aggregate()` as an abstract method on the `DataSource` ABC with signature `(collection, pipeline, allow_disk_use=True) -> list[dict]`
- Implemented `aggregate()` on `MongoDataSource` with `db.coll` name parsing, graceful `None` collection handling, and default `allowDiskUse=True`
- Enables aggregation pipeline support for future enrichment methods (card joins, combo pipelines, commander analytics)

### Added

- **Core framework** (`src/trainforge/`): 9 modules
  - `models.py` — Pydantic v2 models: `Model` (LLM config), `QuestionAnswerEnhanced` (Q&A with metadata), `GenerationTrace` (full LLM interaction trace), `ValidationMetrics` (per-category/per-template stats)
  - `config.py` — YAML loader with `${ENV_VAR}` interpolation, `AppConfig` singleton via `get_config()`
  - `data_source.py` — `DataSource` ABC + `MongoDataSource` implementation with `DEFAULT_DATABASE` constant
  - `domain.py` — `DomainPlugin` ABC, `TemplateConfig`, `DomainRegistry` with auto-discovery from `config/domains.yaml`
  - `generator.py` — Generic `BaseGenerator[T]` using template method pattern; `create_generator()` factory function
  - `query_model.py` — Multi-provider LLM client (Ollama/Anthropic/OpenAI) with streaming to stderr; accepts `Model` object or string params
  - `training.py` — JSONL exporter with per-domain export (category ratio control) and cross-domain mixing
  - `validator.py` — Domain-agnostic validation + regeneration loop (up to 3 fix attempts)

- **Streamlit UI** (`src/trainforge/ui/`): 7 files
  - `app.py` — Main entry point with sidebar navigation, welcome dashboard, connection status
  - `pages/01_Dashboard.py` — Generation metrics with Plotly charts, per-category/per-generator breakdowns
  - `pages/02_Generate.py` — Generation control: domain/generator/model selection, real-time progress, live output
  - `pages/03_Browse_Data.py` — Data browser: search, filter by domain/category/score, pagination, export selected
  - `pages/04_Export_Training.py` — Per-domain and cross-domain JSONL export with ratio controls
  - `pages/05_Settings.py` — MongoDB config, model settings, API keys, domain management, danger zone
  - `components/sidebar.py` — Shared sidebar: navigation menu, connection status, quick stats

- **MTG domain plugin** (`domains/mtg/`): first domain implementation with 27 categories
  - `__init__.py` — `MTGDomain(DomainPlugin)` with auto-registration, loads `templates.yaml` on init
  - `config.yaml` — Domain metadata, MongoDB collections config
  - `templates.yaml` — All 27 categories with templates migrated from old `constants.py` (system_message, notation_legend, per-category templates with validation_rules)
  - `data_source.py` — `MTGDataAccess` extending `MongoDataSource` with typed methods (`get_cards`, `get_articles`, `get_rules`, `get_glossary`, `get_edhrec_data`, etc.)

- **Test suite** (`tests/`): 261 tests total (9 core module tests + 7 UI page tests)
  - Core: models, config, domain, generator, training, data_source, integration, config validation
  - UI: app, dashboard, generate, browse_data, export_training, settings, sidebar

### Changed

- Domain templates migrated from monolithic `constants.py` to per-domain `templates.yaml`, enabling multi-domain support without code changes

### Design Highlights

- **Plugin architecture**: New domains added by implementing `DomainPlugin` ABC + providing `config.yaml` + `templates.yaml` — zero core framework modifications needed
- **Multi-provider LLM support**: Same generator works with Ollama, Anthropic, or OpenAI via config-driven model selection
- **Web-first workflow**: Generation, browsing, validation review, and export all available through the Streamlit UI (CLI still supported)

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