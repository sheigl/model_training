# TrainForge Architecture

## Project Structure

```
trainforge/
├── src/
│   └── trainforge/
│       ├── __init__.py
│       ├── config.py          — YAML config loader with ${ENV_VAR} interpolation
│       ├── data_source.py     — DataSource ABC + MongoDataSource
│       ├── domain.py          — DomainPlugin ABC, TemplateConfig, DomainRegistry
│       ├── generator.py       — Generic BaseGenerator[T] (template method pattern)
│       ├── models.py          — Pydantic v2 models (Model, QA, Trace, Metrics)
│       ├── query_model.py     — Multi-provider LLM client (Ollama/Anthropic/OpenAI)
│       ├── training.py        — JSONL exporter
│       ├── validator.py       — Validation + regeneration loop
│       ├── ui/                — Streamlit web interface
│       └── domains/
│           └── mtg/
│               ├── __init__.py         — MTGDomain plugin (auto-registered)
│               ├── config.yaml         — MongoDB collections config
│               ├── templates.yaml      — All 27 template categories
│               ├── data_source.py      — MTGDataAccess (enriched methods)
│               ├── models.py           — 22 Pydantic v2 domain models
│               └── generators/
│                   ├── __init__.py     — Exports all 25 generator classes
│                   ├── archetypes.py              — topic-based
│                   ├── budget_alternatives.py      — data-driven (NEW)
│                   ├── card_search_queries.py      — data-driven
│                   ├── color_identity_questions.py — data-driven (NEW)
│                   ├── color_staples.py            — data-driven
│                   ├── combo_queries.py            — data-driven (NEW)
│                   ├── commander_building.py       — data-driven
│                   ├── commander_knowledge.py      — topic-based
│                   ├── comparison_questions.py     — data-driven
│                   ├── deckbuilding_theory.py      — topic-based
│                   ├── game_theory.py              — topic-based
│                   ├── glossary_with_examples.py   — data-driven
│                   ├── guide_qa.py                 — data-driven
│                   ├── meta_knowledge.py           — topic-based
│                   ├── multi_card_usage.py         — data-driven
│                   ├── quick_guidelines.py         — data-driven (NEW)
│                   ├── reverse_lookup_questions.py — data-driven
│                   ├── rule_edge_cases.py          — data-driven
│                   ├── rule_explanations.py        — data-driven
│                   ├── rule_why_questions.py       — data-driven
│                   ├── rules_scenarios.py          — topic-based
│                   ├── salt_questions.py           — data-driven
│                   ├── staple_analysis.py          — data-driven
│                   ├── synergy_questions.py        — data-driven
│                   └── terminology_questions.py    — topic-based
└── tests/
    ├── core/        — Core framework tests (models, config, domain, generator, etc.)
    ├── domains/     — Domain-specific tests (mtg/data_source)
    └── ui/          — Streamlit UI tests
```

## Key Patterns

1. **BaseGenerator[T]** — abstract template-method pattern. Subclasses implement:
   - `get_data_batches() -> list[T]` — data fetching
   - `build_prompt(template, data_batch) -> str` — prompt construction
   - `get_source_category() -> str` — category identifier matching templates.yaml
   - `build_context(data_batch) -> str | None` — optional metadata for validation

2. **MTGDataAccess** — enriched data access layer. Generators use `self.domain.get_data_source()` to get it. Key methods:
   - `get_cards_enriched(filters, limit)` — cards with prices/rulings/keywords
   - `get_combos_enriched(filters, limit)` — combo data with card details
   - `get_commanders_enriched(filters, limit)` — EDHREC commander data
   - `search_cards_text(regex, filters, limit)` — oracle text search
   - `get_synergy_partners(card_name, limit)` — combo-based partner cards
   - `get_commander_staples(color_identity, min_decks, limit)` — staple cards

3. **Generator → Category → Template** mapping:
   - `get_source_category()` returns a string like `"card_search"`
   - This matches a key in `templates.yaml` under `categories`
   - `self.get_templates()` loads the templates for that category

4. **21 generators total**: 7 topic-based (str type), 14 data-driven (various types)
   - Topic-based: data is class-level constants, no DB needed
   - Data-driven: data fetched from MongoDB via MTGDataAccess

## Domain Registration

MTGDomain auto-registers via DomainRegistry at import time (`trainforge.domains.mtg.__init__`). The domain provides system_message, notation_legend, template loading, and data source creation.
