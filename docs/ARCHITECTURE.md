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

#### Topic-Based Generators (hardcoded lists, data type = str)

These generators iterate over hardcoded class-level constants. They still use `BaseGenerator[str]` but do not require `MTGDataAccess`:

- `GenerateTerminologyQuestions(BaseGenerator[str])` — 20 MTG terms (cEDH, pillow fort, MLD, etc.). Source: "terminology"
- `GenerateMetaKnowledge(BaseGenerator[str])` — 9 topics (power levels, fast mana, tutors, etc.). Source: "meta_knowledge"
- `GenerateDeckbuildingTheory(BaseGenerator[str])` — 12 topics (card evaluation, mana curve, etc.). Source: "deckbuilding_theory"
- `GenerateGameTheory(BaseGenerator[str])` — 10 situations (threat assessment, politics, etc.). Source: "game_theory"
- `GenerateCommanderBuilding(BaseGenerator[str])` — 12 archetypes (aristocrats, spellslinger, etc.). Source: "commander_building"
- `GenerateRulesScenarios(BaseGenerator[str])` — 15 scenarios (stack, combat, triggered abilities, etc.). Source: "rules_scenario"
- `GenerateCommanderKnowledge(BaseGenerator[str])` — 8 sub-topics (deck construction, commander tax, etc.). Source: "commander_rules"
- `GenerateArchetypes(BaseGenerator[str])` — 10 archetypes (Aggro, Control, Combo, etc.). Source: "archetype"

### Template System

Each generator defines `TEMPLATES: ClassVar[list[TemplateConfig]]` with:

- **template_id**: Unique identifier (e.g., `"general_advice"`, `"meta_deep_dive"`)
- **task_instruction**: The prompt instruction for this template
- **weight**: Selection weight for weighted random sampling
- **validation_rules**: Template-specific HARD REJECT rules

Template selection is weighted random, allowing generators to balance between different output styles (e.g., definition-focused vs. practical-application for terminology).

### Validation Pipeline

1. **Generate**: LLM produces Q&A pair from prompt
2. **Validate**: Separate validation model scores output against rules
3. **Fix**: If score is low, regeneration prompt includes feedback
4. **Hard Reject**: Universal rules (no markdown, no rule numbers, minimum length) plus template-specific rules
5. **Retry**: Up to `max_regeneration_attempts` (default 3) before accepting or rejecting

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

### MTGDataAccess Methods

`MTGDataAccess` provides typed access to all MongoDB collections used by generators:

**Rules & Glossary:**
- `get_rules()` → list[Rule] — Fetches rules from edhrec.rules collection
- `get_glossary()` → list[GlossaryTerm] — Fetches glossary terms

**Cards & Commanders:**
- `get_cards_enriched(filters)` → list[CardWithMetadata] — Enriched card data with EDHREC stats, prices, keywords
- `get_commanders_enriched()` → list[dict] — Commander data weighted by num_decks popularity
- `get_legalities_for_cards(card_ids)` → dict — Standard/Commander legality for card sets

**EDHREC Rankings:**
- `get_game_changers(limit)` → list[dict] — Game-changer cards from edhrec.game-changers (game_changer=True), sorted by num_decks
- `get_salty_cards(min_salt, limit)` → list[dict] — High-salt cards from edhrec.game-changers (salt >= threshold), sorted by salt score
- `get_top_cards_by_color(color, limit)` → list[dict] — Top cards from edhrec.top-{color} collections for each of the 6 colors

**Combos & Articles:**
- `get_combos_enriched()` → list[ComboWithCards] — Commander Spellbook combos with enriched card data
- `get_articles()` → list[Article] — EDHREC articles

**Guides & Archetypes:**
- `get_guides()` → list[Guide] — EDHREC guides (content length >300)
- `get_archetype_data()` → dict — Archetype strategy and deck stats from EDHREC tags + mtg_archetypes

### Metrics

`ValidationMetrics` tracks per-generator:
- Total candidates generated
- Pass/fail rates (first attempt, after fix)
- Fix recovery rate
- Per-category breakdowns

Metrics are stored in `synthetic_metrics.generator_runs` with a shared `run_id` per process.

## Key Design Decisions

1. **Unified BaseGenerator[T] pattern**: All 27 generators extend `BaseGenerator[T]`, providing invariant generation loop, validation pipeline, and metrics tracking. Topic-based generators use `T=str`; data-backed generators use typed dataclasses or tuples.

2. **MTGDataAccess as the sole data layer**: Every generator that needs MongoDB data accesses it through `MTGDataAccess`. No raw pymongo collections are passed to any generator. This was achieved through a multi-phase migration (completed Phase 4).

3. **No raw pymongo in generators**: All generators access data through `MTGDataAccess` or class-level constants. `main.py` creates the single `MTGDataAccess` instance and passes it to each generator's constructor.

4. **Dry-run support**: All BaseGenerator subclasses support `dry_run=True` for testing without MongoDB writes.

5. **Weighted template selection**: Allows balancing output diversity without complex routing logic.

6. **Typed data batches**: Data-backed generators use typed generics (`BaseGenerator[Rule]`, `BaseGenerator[ProjectedRulePair]`, etc.) enabling type-safe prompt building and validation context construction.
