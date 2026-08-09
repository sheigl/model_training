# Architecture

## Overview

The MTG Expert Model Training project generates synthetic Q&A training data using LLM generation + validation, then extracts it into JSONL format for fine-tuning smaller models.

## Core Architecture

### BaseGenerator Pattern

All synthetic data generators extend `BaseGenerator[T]` (in `base_generator.py`), which provides:

- **Invariant generation loop**: Iterates through data batches, selects templates, builds prompts, validates output
- **Template Method pattern**: Subclasses implement abstract hooks; base class orchestrates the flow
- **Validation pipeline**: Uses a separate validation model to score and optionally fix generated Q&A
- **Metrics tracking**: Records pass rates, fix attempts, and per-category statistics to MongoDB

**Subclass contract** (what each generator must implement):

```python
class MyGenerator(BaseGenerator[str]):
    TEMPLATES: ClassVar[list[TemplateConfig]] = [...]

    def get_data_batches(self) -> Iterator[list[str]]:
        """Yield data items (topics, cards, combos, etc.)"""

    def build_prompt(self, template: TemplateConfig, data_batch: str) -> str:
        """Build the LLM prompt for a specific template + data item"""

    def get_source_category(self) -> str:
        """Return category string (e.g., 'meta_knowledge', 'card_search')"""

    def build_context(self, template: TemplateConfig, data_batch: str) -> dict:
        """Return validation context dict"""

    def get_source_data(self, data_batch: str) -> list[str]:
        """Return source data for tracking (optional)"""
```

**Constructor signature** (common to all generators):

```python
Generator(
    data_access: MTGDataAccess | None,     # Data access layer (None for topic-based generators)
    models: dict[ModelType, Model],        # Generation + validation models
    validation_pct: float,                 # % of items to validate (0.0-1.0)
    target_count: int,                     # Target number of items to generate
    save_item: Callable[[QuestionAnswerEnhanced], None],  # Save callback
    metrics: ValidationMetrics | None,     # Optional metrics tracker
    dry_run: bool = False,                 # Skip saving if True
)
```

**main.py orchestration**: Creates a single `MTGDataAccess` instance at startup, passes it to each generator's constructor, calls `.generate()` on all 27 generators sequentially, then closes the data access layer.

### Generator Types

All 27 generators now use the `BaseGenerator[T]` + `MTGDataAccess` pattern. They are organized by their data source:

#### Rules-Grounded Generators (data from rules/glossary collections)

These generators fetch official Magic rules and glossary terms via `MTGDataAccess`:

- `GenerateRuleExplanations(BaseGenerator[Rule])` — Uses `get_rules()` with SKIP_SECTIONS filter, 2 templates per rule. Source: "rule_explanation"
- `GenerateRuleInteractions(BaseGenerator[ProjectedRulePair])` — Uses `get_rules()`, builds 37 interaction pairs as dataclass instances. Source: "rule_interaction"
- `GenerateGlossaryWithExamples(BaseGenerator[GlossaryTerm])` — Uses `get_glossary()`. Source: "glossary_with_examples"
- `GenerateRuleEdgeCases(BaseGenerator[Rule])` — Uses `get_rules()` with COMPLEX_RULE_SECTIONS filter. Source: "rule_edge_case"
- `GenerateRuleWhyQuestions(BaseGenerator[Rule])` — Uses `get_rules()` with PRINCIPLE_SECTIONS filter (14 section prefixes). Source: "rule_why"

#### EDHREC-Grounded Generators (data from edhrec collections)

These generators fetch deck-building data, card rankings, and guides via `MTGDataAccess`:

- `GenerateGuideQa(BaseGenerator[Guide])` — Uses `get_guides()` with content length >300 filter. Source: "guide_qa"
- `GenerateStapleAnalysis(BaseGenerator[dict])` — Uses `get_game_changers()`. Source: "staple_analysis"
- `GenerateColorStaples(BaseGenerator[tuple[str, list[dict]]])` — Uses `get_top_cards_by_color()` for all 6 colors. Source: "color_staples"
- `GenerateSaltQuestions(BaseGenerator[list[dict]])` — Uses `get_salty_cards(min_salt=1.2)`, BATCH_SIZE=8. Source: "salt_analysis"
- `GenerateMultiCardUsage(BaseGenerator[ComboWithCards])` — Uses `get_combos_enriched()`. Source: "multi_card_usage"

#### Card-Focused Generators (data from card/commander collections)

These generators fetch enriched card data, commanders, and legalities via `MTGDataAccess`:

- `GenerateCardSearchQueries(BaseGenerator[CardWithMetadata])` — Uses `get_cards_enriched()` with 20 search patterns. Source: "card_search"
- `GenerateComboQueries(BaseGenerator[ComboWithCards])` — Uses `get_combos_enriched()`. Source: "combo_query"
- `GenerateColorIdentityQuestions(BaseGenerator[ColorIdentityContext])` — Uses `get_commanders_enriched()` + `get_cards_enriched()` + `get_legalities_for_cards()`. Source: "color_identity"
- `GenerateComparisonQuestions(BaseGenerator[tuple[CardWithMetadata, CardWithMetadata]])` — Uses `get_cards_enriched()` for 10 effect categories. Source: "comparison"
- `GenerateQuickGuidelines(BaseGenerator[dict])` — Uses `get_archetype_data()`, `get_commanders_enriched()`, etc. for 19 archetypes. Source: "quick_guideline"
- `GenerateReverseLookupQuestions` — Feature-to-card lookup via card collections
- `GenerateSynergyQuestions` — Card synergy discovery via card collections
- `GenerateBudgetAlternatives` — Budget card alternatives via card collections
- `GenerateArticleQa(BaseGenerator[Article])` — Uses `get_articles()`. Source: "article_qa"

#### Ported Generators (Topic-Based — hardcoded lists, data type = str)

These generators iterate over hardcoded class-level constant lists (tuples of `(name, description)`). They extend `BaseGenerator[str]` and do not require `MTGDataAccess`. Templates are loaded from `templates.yaml` automatically via the domain plugin — no hardcoded template strings in the generator classes.

| File | Class | Topics | Category |
|------|-------|--------|----------|
| `commander_knowledge.py` | `GenerateCommanderKnowledge` | 8 Commander sub-topics | `commander_knowledge` |
| `terminology_questions.py` | `GenerateTerminologyQuestions` | 20 MTG terminology terms | `terminology` |
| `deckbuilding_theory.py` | `GenerateDeckbuildingTheory` | 12 deckbuilding topics | `deckbuilding_theory` |
| `rules_scenarios.py` | `RulesScenariosGenerator` | 15 rules scenarios | `rules_scenarios` |
| `archetypes.py` | `ArchetypesGenerator` | 10 deck archetypes | `archetypes` |
| `game_theory.py` | `GameTheoryGenerator` | 10 game theory situations | `game_theory` |
| `meta_knowledge.py` | `MetaKnowledgeGenerator` | 9 meta knowledge topics | `meta_knowledge` |

Each generator implements the standard `BaseGenerator[str]` contract:
- `get_data_batches()` — yields topic names from the class-level constant
- `build_prompt()` — fills template instruction with topic name and context description, wraps with MTG notation legend and `<task>` tags
- `get_source_category()` — returns the category string matching `templates.yaml`
- `build_context()` — returns context string with category, topic, and description for validation

All 7 are exported from `generators/__init__.py` and returned by `MTGDomain.get_generators()`.

**Note**: `GenerateCommanderBuilding` (12 archetypes, source: `commander_building`) is a standalone generator that hasn't been consolidated into the main generator registry.

### Template System

Each generator defines `TEMPLATES: ClassVar[list[TemplateConfig]]` with:

- **template_id**: Unique identifier (e.g., `"general_advice"`, `"meta_deep_dive"`)
- **task_instruction**: The prompt instruction for this template
- **weight**: Selection weight for weighted random sampling
- **validation_rules**: Template-specific HARD REJECT rules
- **version**: Optional `int | None` — the template version loaded from the store (Story 045)

Template selection is weighted random, allowing generators to balance between different output styles (e.g., definition-focused vs. practical-application for terminology).

### YAML Template System (Stories 001–007)

The legacy CLI loads generation and validator templates from local YAML files instead of hardcoded Python constants or a MongoDB store. Templates live in `training_data/generate_synthetic_data/templates/` alongside the package code, making them easy to inspect, edit, and version-control with git.

#### Directory Layout

```
templates/
    shared.yaml                    # scaffolding blocks + shared validators
    comparison_validator.yaml      # card comparison validator override
    combo_query.yaml               # generation templates for combo queries
    card_search.yaml               # ...etc (one file per generator category)
    commander_rules.yaml
    terminology.yaml
    ...                            # 27 total category files
```

- **`shared.yaml`** — Cross-generator scaffolding blocks (`system_message`, `notation_legend`, `requirements_base`, `output_format`, `card_comparison_instructions`) and shared validator prompts (`qa_validation`, `validator`).
- **`comparison_validator.yaml`** — Per-generator validator override for the comparison category.
- **Category files** — One YAML file per generator (e.g., `combo_query.yaml`, `meta_knowledge.yaml`), each containing a list of template definitions with `template_id`, `instruction`, `weight`, and optional `validation_rules`.

#### File Schema

Each category YAML file has the shape:

```yaml
templates:
  - template_id: how_does_it_work
    instruction: "Generate exactly 3 Q&A pairs explaining this combo..."
    weight: 1
    validation_rules:
      - "Must mention both cards by name"
      - "Each answer must be at least 2 sentences"
```

Shared scaffolding blocks in `shared.yaml` use top-level keys matching the scaffold cache keys:

```yaml
system_message: |
  You are a Magic: The Gathering expert...
notation_legend: |
  {T} = tap, {C} = card cost, ...
requirements_base: |
  - CRITICAL — Trigger ordering...
output_format: |
  <qa>...</qa>
```

#### Template Loading

`YamlTemplateLoader` (in `yaml_template_loader.py`) reads templates at construction time from the configured directory. Its public API mirrors the old `TemplateStore` surface:

- `get_latest(generator, template_id, template_type)` — returns a dict compatible with `TemplateConfig`
- `list_versions(generator, template_id, template_type)` — returns `[]` (no versioning in YAML)
- `get_scaffolding(key)` — returns shared block text by key
- `get_validator(category)` — returns validator prompt for the given category

The loader is wired into `BaseGenerator` via the `yaml_loader` parameter. The fallback chain for template resolution is:

1. **YAML loader** (primary) — loads from local YAML files
2. **MongoDB store** (deprecated, kept as fallback) — reads from `synthetic_metrics.templates` if available
3. **Class-level constant** (`TEMPLATES`) — hardcoded fallback

If the YAML directory is missing, construction raises a `ValueError`. If the MongoDB store is also unavailable, generators fall back to their class-level `TEMPLATES` constants.

#### Scaffolding Cache

Shared blocks are loaded once at startup into a module-level `_SCAFFOLDING_CACHE` in `common.py` via `init_scaffolding(yaml_loader)`. All ~20 `build_*_prompt` functions read shared blocks via `_get_scaffold(key, fallback)`, falling back to `constants.py` imports when the cache is empty. `reset_scaffolding_cache()` is provided for tests.

#### CLI Flag

A single `--templates-dir` flag (defaulting to the package's `templates/` directory) lets operators point at a custom templates root:

```bash
python -m training_data.generate_synthetic_data.main --all --templates-dir /path/to/templates
```

#### Seed Script (`--to-yaml`)

`seed_templates.py` supports a `--to-yaml` mode that regenerates all YAML template files from Python constants. This is the canonical way to bootstrap or update the YAML templates after code changes:

```bash
python -m training_data.generate_synthetic_data.seed_templates --to-yaml
```

The existing MongoDB seeding path remains available but emits a `DeprecationWarning`.

#### Backward Compatibility

All class-level `TEMPLATES` constants are retained as the ultimate fallback. The old `TemplateStore` class and its MongoDB-dependent tests have been trimmed to only keep the pure dict-to-`TemplateConfig` conversion test (`TestToTemplateConfig`). Per-generator version override flags were removed; operators who need version pinning should edit the YAML files directly or use `--templates-dir` with a different directory.

### Validation Pipeline

1. **Generate**: LLM produces Q&A pair from prompt
2. **Validate**: Separate validation model scores output against rules
3. **Fix**: If score is low, regeneration prompt includes feedback
4. **Hard Reject**: Universal rules (no markdown, no rule numbers, minimum length) plus template-specific rules
5. **Retry**: Up to `max_regeneration_attempts` (default 3) before accepting or rejecting
6. **Transport-failure re-validation**: validator parse/transport errors (empty, truncated, or unparseable responses) are not answer-quality rejections — they re-validate the same answer up to 2 times without burning a regeneration or recording a fix attempt, then reject if the validator stays unparseable (see Sibling Feedback Threading)

### Sibling Feedback Threading

When a single template iteration produces multiple Q&A pairs (e.g., the 3 sibling Q&As from one combo generation), corrections from earlier siblings are threaded forward to later siblings' regeneration prompts. This lets Q2/Q3 see what was wrong with and how Q1 was corrected, improving fix-attempt quality.

**Threading path:**
1. `BaseGenerator._process_item` declares `sibling_corrections: list[str] = []` **before** the QA loop and passes it to `validate_answer`
2. `BaseGenerator.validate_answer` (and the `generate_quick_guidelines.py` override) accept `sibling_corrections: list[str] | None = None` and forward it to `validate_and_loop_with_suggested_fix`
3. `common.py` `validate_and_loop_with_suggested_fix` accepts `sibling_corrections`, passes `sibling_feedback` (joined corrections) to `regenerate_answer`, and records corrections via `_upsert_sibling_correction()` — a **per-QA dedupe** that replaces (rather than appends) the entry for the same QA index, so the accumulated list never grows unbounded (guarded by `if sibling_corrections is not None`)
4. `query_model.py` `regenerate_answer` accepts `sibling_feedback: str = ""` and conditionally inserts a `sibling_block` into the prompt f-string after the context block

**Why the accumulator is hoisted into `_process_item`:** `validate_and_loop_with_suggested_fix` is always called with `qa_pairs` of length 1. The 3 sibling Q&As from one combo generation are iterated by `_process_item`'s own loop, so the accumulator must live in that scope to persist across siblings. Placing it inside `validate_and_loop_with_suggested_fix` would reset it on every call.

**Validator transport failures are not sibling feedback:** unparseable/truncated validator responses (e.g. "Validation parse failed...") are detected by `query_model.is_transport_failure_reason()` and never enter the accumulator. They re-validate the SAME answer up to `_MAX_VALIDATION_PARSE_RETRIES` (2) times — no regeneration, no fix-attempt accounting, no sibling feedback — then reject without regeneration if the validator stays unparseable.

**Single-QA contract (bounded accumulator):** production callers (`base_generator.validate_answer`, `generate_quick_guidelines.validate_answer`) always pass a single QA per call, so `enumerated_i` is always 0 and the accumulator holds at most one entry — the most recent correction. Threading the batch QA index through for true per-QA dedupe across siblings is a tracked follow-up.

### Generator Prompt Requirements (`REQUIREMENTS_BASE`)

`constants.py` defines `REQUIREMENTS_BASE`, a list of mandatory rules prepended to every generator prompt. As of 2026-07-26 it contains 9 items, including:

- **Index 3 — "CRITICAL — Trigger ordering"**: LIFO stack resolution, ETB timing, static vs triggered ability rules. Targets the #1 failure mode (~50% of failures were wrong trigger/stack ordering).
- **Index 5 — Vague-outcome ban list**: Expanded banned phrases ("infinite triggers", "infinite value", "overwhelm opponents") with a concrete example ("infinite 1/1 Snake creature tokens"). Targets ~20% of failures.

### Data Flow

```
MongoDB (source data)
  → MTGDataAccess (unified access layer)
    → BaseGenerator.get_data_batches()
      → build_prompt() with TemplateConfig
        → LLM generation (Ollama)
          → Validation pipeline
            → save_item() callback
              → MongoDB (synthetic_queries.queries)
                → extract_training_data.py
                  → JSONL file
                    → training.py (LoRA fine-tuning)
```

### MTGDataAccess — Domain Models

`training_data/generate_synthetic_data/domain_models.py` contains 22 Pydantic v2 domain models. All models are self-contained with `__all__` export:

| Model | Description |
|-------|-------------|
| `MongoModel` | Base model with `id`→`_id` alias and `model_config` |
| `CardFace` | Single face of a multi-faced card |
| `Card` | Full card data with oracle text, type line, colors, etc. |
| `CardWithMetadata` | Card + EDHREC rank, price, keywords, rulings, legalities |
| `PriceData` | Card prices (USD, EUR, TIX) with computed `best_price` |
| `Ruling` | Card ruling with date, text, source |
| `Legality` | Format legality (format name + legality string) |
| `CardLegalities` | Set of `Legality` for a card |
| `ComboCard` | Card reference within a combo |
| `ComboProduces` | Result of a combo |
| `Combo` | Raw Commander Spellbook combo |
| `ComboWithCards` | Combo with resolved card data |
| `Commander` | Commander with EDHREC metrics |
| `CommanderWithTags` | Commander + archetype tags |
| `Archetype` | Deck archetype strategy data |
| `Article` | EDHREC article |
| `GuideChapter` | Chapter within an EDHREC guide |
| `Guide` | EDHREC guide with chapters |
| `GameState` | Board state descriptions |
| `Rule` | MTG comprehensive rule entry |
| `GlossaryTerm` | MTG glossary term with examples |
| `Keyword` | Keyword ability definition |

Key features: field aliases for MongoDB `_id`→`id` mapping, JSON-stringified array parsing (`colors`, `colorIdentity`, `keywords`, `subtypes`, etc.), computed properties (`cmc`, `best_price`, `salt_level`), factory methods (`from_dict`, `to_prompt_detail`), and `model_rebuild()` calls for forward references.

### MTGDataAccess Methods

`MTGDataAccess` provides typed access to all MongoDB collections used by generators. It lives in `training_data/generate_synthetic_data/data_access.py`.

**Dual collection namespace** design:
- **Simple methods** (preserved from original): query `synthetic_queries.*` collections (e.g., `get_cards()`, `get_articles()`, `get_rules()`, `get_glossary()`, `get_edhrec_data()`)
- **Enriched methods** (Story 11): query `mtg_json.*`, `commander_spellbook.*`, `edhrec.*` collections with aggregation pipeline joins, caching, and typed model conversion

---

#### Simple Methods (backward compatible, all 11 preserved)

- `get_cards()` → list[dict] — Raw cards from `synthetic_queries.test_cards`
- `get_articles()` → list[dict] — Raw EDHREC articles
- `get_rules()` → list[dict] — Raw MTG rules
- `get_glossary()` → list[dict] — Raw glossary terms
- `get_edhrec_data()` → list[dict] — Raw EDHREC data
- `get_guides()` → list[dict] — Raw EDHREC guides
- `get_game_changers(limit)` → list[dict] — Game-changer cards (game_changer=True), sorted by num_decks
- `get_salty_cards(min_salt, limit)` → list[dict] — High-salt cards sorted by salt score
- `get_top_cards_by_color(color, limit)` → list[dict] — Top cards from `edhrec.top-{color}`
- `get_combos()` → list[dict] — Raw Commander Spellbook combos
- `get_commanders()` → list[dict] — Raw commander data

---

#### Enrichment Methods (Story 11)

**Card Enrichment Pipelines:**
- `get_cards_enriched(filters=None, lite=False)` → list[`CardWithMetadata`] — Full card data with EDHREC stats (rank, inclusion %), prices (USD/EUR), keywords, rulings, and format legalities via a multi-stage `$lookup` aggregation pipeline across `mtg_json.clean_cards`, `edhrec.top_cards`, `edhrec.card_prices`, `mtg_json.keywords`, `mtg_json.rulings`, and `mtg_json.card_legalities`
- `get_card_by_name(name)` → `CardWithMetadata | None` — Single card lookup by name (case-insensitive) with full enrichment
- `get_cards_by_keyword_mechanic(keyword)` → list[`CardWithMetadata`] — Cards matching a specific keyword/mechanic (e.g., "Flying", "Vigilance") via `mtg_json.keywords` join
- `_translate_card_filters(filters)` → dict — Converts common filter names (`colors`, `cmc`, `type`, `format`) to MongoDB query predicates
- `_build_card_enrichment_pipeline(match_stage)` → list[dict] — The 8-stage aggregation pipeline as a private, testable method

**Combo Enrichment:**
- `get_combos_enriched()` → list[`ComboWithCards`] — Two-phase fetch: (1) aggregate combos from `commander_spellbook.combos` with `$lookup` on `commander_spellbook.combo_cards` and `commander_spellbook.combo_card_sources`, (2) Python-side batch lookup to resolve card names to `CardWithMetadata` objects via `_batch_lookup_cards_by_name()`
- `_build_combo_pipeline()` → list[dict] — Pipeline stages as a private method

**Commander Enrichment:**
- `get_commanders_enriched()` → list[`CommanderWithTags`] — EDHREC commander data reshaped from `edhrec.commanders` with `$lookup` on `edhrec.commander_tags` and `edhrec.top-*` color collections
- `_build_commander_pipeline()` → list[dict] — Pipeline stages as a private method

---

#### Cached Lookup Methods (Story 11)

Uses `LRUCacheWithTTL` (thread-safe, TTL-aware) for high-traffic lookups:

- `get_rulings_for_cards(card_ids)` → dict[`ObjectId`, list[`Ruling`]] — Batch rulings lookup from `mtg_json.rulings` grouped by card
- `get_prices_for_cards(card_ids)` → dict[`ObjectId`, `PriceData`] — Current prices from `edhrec.card_prices`
- `get_legalities_for_cards(card_ids)` → dict[`ObjectId`, `CardLegalities`] — Format legalities from `mtg_json.card_legalities`
- `get_keyword_taxonomy()` → list[`Keyword`] — Full keyword/ability taxonomy from `mtg_json.keywords` (cached 1 hour)
- `get_archetype_data()` -> dict — Archetype strategy data from EDHREC tags + `mtg_archetypes` (cached 1 hour)

---

#### Analytics Methods (Story 11)

- `get_top_cards_by_edhrec_rank(limit=100, min_rank=1)` → list[`CardWithMetadata`] — Highest-ranked cards from `edhrec.top_cards` sorted by EDHREC rank
- `get_budget_alternatives(card_names, max_price=5.0)` → list[`CardWithMetadata`] — Cards under `max_price` from the same color identity and type, ranked by EDHREC rank
- `get_synergy_partners(card_name, limit=10)` → list[`CardWithMetadata`] — Cards sharing keywords/keyword mechanics with the given card
- `get_commander_staples(color_identity, limit=20)` → list[`CardWithMetadata`] — Top cards legal in a given color identity from `edhrec.top-*`
- `get_format_legalities()` → list[str] — Distinct format names from `mtg_json.card_legalities`
- `calculate_color_identity(color_str)` → frozenset — Normalizes color strings/abbreviations into a canonical color identity set
- `search_cards_text(pattern)` → list[`CardWithMetadata`] — Full-text search on card oracle text via regex

---

#### Utilities & Helpers (Story 11)

- `_convert_doc_to_model(doc)` → `CardWithMetadata` — Converts a MongoDB document to a Pydantic model, pre-parsing JSON-stringified array fields (`colors`, `colorIdentity`, `keywords`, `subtypes`, `supertypes`, `frameEffects`) before construction
- `_batch_lookup_cards_by_name(names)` → dict[str, `CardWithMetadata`] — Batch card name lookup (case-insensitive) with results cached in `_card_name_cache`
- `verify_indexes()` → dict[str, list[str]] — Verifies that `REQUIRED_COLLECTIONS` exist and `REQUIRED_INDEXES` are in place, returning missing items per collection
- `LRUCacheWithTTL` — Thread-safe LRU cache with TTL-based eviction, hit/miss stats, and `maxsize`/`ttl` configurable per instance
- `retry_on_transient_error` — Decorator with exponential backoff (initial delay 1s, max 5 attempts) for MongoDB `AutoReconnect` and `ServerSelectionTimeoutError`

### Metrics

`ValidationMetrics` tracks per-generator:
- Total candidates generated
- Pass/fail rates (first attempt, after fix)
- Fix recovery rate
- Per-category breakdowns
- **Template version tracking** (Story 045): `template_versions` and `validator_template_versions` dicts recording which template version was used for each generation. With the YAML template system (Stories 001–007), these fields are always `None` since YAML templates have no versions, but the infrastructure is retained for backward compatibility with MongoDB-trace data.

Metrics are stored in `synthetic_metrics.generator_runs` with a shared `run_id` per process.

### Generation Trace Logging

Every Q&A item generated can have a full LLM interaction trace stored in `synthetic_metrics.generation_traces`. This captures the complete lifecycle — from prompt construction through validation rounds to final outcome — enabling debugging, analysis, and optimization of the generation pipeline.

**Trace per template iteration**: One `GenerationTrace` document is created per template iteration (not per Q&A pair). A single template call may produce multiple Q&A items, all sharing the same trace. Each trace records which template version was used for generation and validation (Story 045), enabling version-to-version performance comparison.

**Trace lifecycle:**
1. `BaseGenerator.generate()` creates a `GenerationTrace` at the start of each template iteration
2. Generation prompt/response and latency are populated after LLM call
3. `validate_and_loop_with_suggested_fix()` accumulates validation rounds via the `trace` parameter
4. Each validation round appends a `round_data` dict with score, prompt, response, errors, etc.
5. If regeneration occurs, the `regeneration` sub-dict captures the regeneration prompt/response
6. On first successful save, `trace_callback` fires with the completed trace
7. Traces are batch-flushed to MongoDB (50 per batch)

**CLI flags:**
- `--log-traces` (default: enabled) — Enable trace logging
- `--no-log-traces` — Disable trace logging entirely

**MongoDB schema** (`synthetic_metrics.generation_traces`):
```json
{
  "_id": "uuid",
  "run_id": "uuid",
  "item_id": "uuid",
  "category": "combo_query",
  "source_template": "how_does_it_work",
  "template_version": null,        // always null with YAML templates; recorded for MongoDB-trace backward compat
  "validator_template_version": null, // always null with YAML templates; recorded for MongoDB-trace backward compat
  "generator_name": "GenerateComboQueries",
  "generation_model": "qwen3.6:27b",
  "validation_model": "qwen3.6:27b",
  "created_at": "ISO timestamp",
  "generation": {
    "prompt": "full prompt text...",
    "response": "raw model response...",
    "parsed_ok": true,
    "latency_ms": 4200
  },
  "validation_rounds": [
    {
      "round": 0,
      "prompt": "validation prompt...",
      "response": "raw validation JSON...",
      "parsed_ok": true,
      "score": 6.5,
      "is_acceptable": false,
      "errors": "...",
      "missing_info": "...",
      "reason": "...",
      "verification_checklist": [...],
      "latency_ms": 2100,
      "regeneration": null
    }
  ],
  "final_outcome": "accepted_after_fix",
  "total_rounds": 2,
  "final_score": 8.0
}
```

**Final outcome values:**
- `"accepted_first_attempt"` — Q&A passed validation on first try
- `"accepted_after_fix"` — Q&A required regeneration but eventually passed
- `"rejected"` — Q&A failed after all regeneration attempts
- `"skipped"` — Validation was not performed (validation_pct=0)

**Indexes:**
- Compound: `(run_id, category, final_outcome)` — For filtering traces by run, category, and outcome
- Single: `item_id` — For looking up traces by Q&A item
- Compound: `(category, template_version)` — For version-based analytics on traces (Story 045; deprecated with YAML templates since versions are always `null`)
- Compound: `(run_id, template_version)` — For version-based analytics per run (Story 045; deprecated with YAML templates since versions are always `null`)

### Domain Models (`training_data/generate_synthetic_data/domain_models.py`)

The MTG domain models are defined in the legacy CLI. Key design choices:

- **Self-contained module**: All 22 models in a single file with `__all__` export, enabling standalone use
- **JSON-stringified array parsing**: `_convert_doc_to_model` pre-parses array fields (`colors`, `colorIdentity`, `keywords`, `subtypes`, `supertypes`, `frameEffects`) before Pydantic construction, fixing silent data corruption when `mtg_json` stores arrays as JSON strings
- **Field aliases**: MongoDB `_id` mapped to Pydantic `id` via `Field(validation_alias="_id")`
- **Computed properties**: `cmc` (from mana cost), `best_price` (min of USD/EUR/TIX), `salt_level` (from EDHREC salt score)
- **Factory methods**: `from_dict()` for alternative construction, `to_prompt_detail()` for LLM prompt formatting

### Enriched MTGDataAccess (`domains/mtg/data_source.py`)

The enriched data access layer (Story 11) adds aggregation pipelines on top of the original simple methods. Key design decisions:

- **Dual collection namespace**: Simple methods continue to query `synthetic_queries.*` collections for backward compatibility; enriched methods query `mtg_json.*`, `commander_spellbook.*`, `edhrec.*` collections with proper joins
- **Pipeline builders as private methods**: `_build_card_enrichment_pipeline()`, `_build_combo_pipeline()`, `_build_commander_pipeline()` are each independently testable methods returning raw pipeline stages
- **Two-phase combo enrichment**: Combos use an aggregate `$lookup` for the combo structure, then Python-side batch card resolution via `_batch_lookup_cards_by_name()` — this avoids MongoDB `$lookup` limitations with large card datasets
- **Thread-safe caching**: `LRUCacheWithTTL` uses a `Lock`-protected OrderedDict with TTL-based eviction and stats tracking (hits/misses/current size)
- **Exponential backoff retry**: `retry_on_transient_error` decorator handles MongoDB transient failures with configurable initial delay, max attempts, and optional re-raise after exhaustion
- **Backward compatibility**: All 11 original simple methods are preserved unchanged — existing generators continue to work

## Key Design Decisions

1. **Unified BaseGenerator[T] pattern**: All 27 generators extend `BaseGenerator[T]`, providing invariant generation loop, validation pipeline, and metrics tracking. Topic-based generators use `T=str`; data-backed generators use typed dataclasses or tuples.

2. **MTGDataAccess as the sole data layer**: Every generator that needs MongoDB data accesses it through `MTGDataAccess`. No raw pymongo collections are passed to any generator. This was achieved through a multi-phase migration (completed Phase 4).

3. **No raw pymongo in generators**: All generators access data through `MTGDataAccess` or class-level constants. `main.py` creates the single `MTGDataAccess` instance and passes it to each generator's constructor.

4. **Dry-run support**: All BaseGenerator subclasses support `dry_run=True` for testing without MongoDB writes.

5. **Weighted template selection**: Allows balancing output diversity without complex routing logic.

6. **Typed data batches**: Data-backed generators use typed generics (`BaseGenerator[Rule]`, `BaseGenerator[ProjectedRulePair]`, etc.) enabling type-safe prompt building and validation context construction.

7. **Generation traces stored separately**: Traces live in `synthetic_metrics.generation_traces` (not embedded in Q&A docs). Full prompt text is captured (not just hashes). Traces are batch-flushed (50 per batch) to minimize MongoDB write overhead. Traces are per template iteration, not per Q&A pair.


**Total**: 368 tests passing (20 pre-existing failures unchanged).
