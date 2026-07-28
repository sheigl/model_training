# TrainForge Architecture

> **Note:** As of 2026-07-26 (Story 046), TrainForge lives in a separate repository at `/home/sheigl/code/trainforge/` (sibling to this repo). The structure below describes the TrainForge codebase as it exists in that repository.

## Project Structure

```
trainforge/   # Separate repo: /home/sheigl/code/trainforge/
├── src/
│   └── trainforge/
│       ├── __init__.py
│       ├── config.py          — YAML config loader with ${ENV_VAR} interpolation
│       ├── data_source.py     — DataSource ABC + MongoDataSource
│       ├── domain.py          — DomainPlugin ABC, TemplateConfig, DomainRegistry
│       ├── generator.py       — Generic BaseGenerator[T] (template method pattern)
│       ├── models.py          — Pydantic v2 models (Model, QA, Trace, Metrics)
│       ├── query_model.py     — Multi-provider LLM client (Ollama/Anthropic/OpenAI)
│       ├── template_store.py  — Read-only TemplateStoreClient (MongoDB, Story 043)
│       ├── training.py        — JSONL exporter
│       ├── validator.py       — Validation + regeneration loop (store-aware, Story 043)
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

## Shared Template Store (Story 040)

A MongoDB-backed versioned template store is shared by both the legacy CLI and TrainForge so generation/validator templates can be loaded from a single version-controlled source instead of hardcoded Python constants and YAML files.

- **Canonical implementation**: `training_data/generate_synthetic_data/template_store.py` — `TemplateStore` class (lives in the legacy CLI; TrainForge gets a thin read-only client in Story 043).
- **Collection**: `synthetic_metrics.templates` (same database as `generator_runs` / `generation_traces`).
- **Document shape**: one doc per `(generator, template_id, template_type, version)`; exactly one doc per `(generator, template_id, template_type)` has `is_latest=True`.
- **Construction**: `TemplateStore(collection: pymongo.collection.Collection)` — no hard dependency on `MTGDataAccess` or `DomainPlugin`, so it is reusable from either codebase. `from_uri(...)` convenience constructor also available.
- **Indexes** (created idempotently in the constructor):
  - Compound unique on `(generator, template_id, template_type, version)` — guards against race-condition duplicate inserts.
  - Lookup index on `(generator, template_id, template_type, is_latest)` — fast latest-lookup.
- **API**: `get_latest`, `get_version`, `list_versions`, `upsert` (auto-increments version + flips previous latest to `is_latest=False`; idempotent on identical `yaml_content`), `delete_version` (promotes next-highest to latest; refuses to delete the only version), `seed` (idempotent bulk import at version=1), `to_template_config` (YAML → legacy `common.TemplateConfig`).
- **Shared scaffolding namespace**: `generator="__shared__"` is reserved for cross-generator blocks (`system_message`, `notation_legend`, `requirements_base`, `output_format`, `card_comparison_instructions`, `validation_checklist`, `validation_scoring_guide`, `qa_validation`). Seeded in Story 041.
- **Backward-compat**: purely additive — no existing production files modified. Default generator behavior unchanged; `TemplateStore` is only used when explicitly constructed and passed.

## Legacy CLI Template Loading (Story 042)

The legacy CLI (`training_data/generate_synthetic_data/`) now loads generation/validator templates from the MongoDB `TemplateStore` when a store handle is provided, with full backward compatibility — `template_store=None` (the default) preserves byte-identical current behavior.

- **`BaseGenerator.__init__`** accepts optional `template_store`, `template_version_override`, `validator_template_version_override`. `select_templates()` calls `_load_templates_from_store()` which iterates the class `TEMPLATES` list as the key set, looking up each `template_id` in the store (version override → latest → class constant fallback). The store handle is wired into `self._query_model.template_store` so validator prompts are also store-driven.
- **`common.py` scaffolding cache**: module-level `_SCAFFOLDING_CACHE` populated once at startup by `init_scaffolding(yaml_loader, store)`. YAML path takes precedence — calls `loader.get_scaffolding()` and maps keys via `_CACHE_KEY_TO_YAML_KEY`. Legacy MongoDB path preserved in `_populate_from_store()`. Each `build_*_prompt` function reads shared blocks (`MTG_NOTATION_LEGEND`, `SYSTEM_MESSAGE`, `OUTPUT_FORMAT`, `CARD_COMPARISON_INSTRUCTIONS`) via `_get_scaffold(key, fallback)`, falling back to `constants.py` imports when the cache is empty. No function signatures changed in prompt builders.
- **`QueryModel` validator lookup**: `_resolve_validator_template(category)` implements hybrid granularity — a generator-specific `(category, "validator", "validator")` doc overrides the shared `(__shared__, "qa_validation", "validator")` doc. `__build_qa_validation_prompt` / `__build_card_validation_prompt` use `str.replace()` placeholder substitution when a stored template exists, falling back to the unchanged inline construction. `str.replace()` (not `.format()`) is required because the stored templates embed `MTG_NOTATION_LEGEND` whose mana-symbol braces (`{T}`, `{C}`, `{W}`, ...) would be misinterpreted as format placeholders by `.format()`.
- **`main.py`**: constructs a single `TemplateStore` (try/except guarded), calls `init_scaffolding()`, passes `template_store` to all 27 generator instantiations. `template_version_override` left as None (Story 044 wires CLI flags).

## TrainForge Template Loading (Story 043)

TrainForge's `MTGDomain` plugin now loads templates from the shared MongoDB `TemplateStore` when a `TemplateStoreClient` is injected, with full backward compatibility — `template_store=None` (the default) preserves byte-identical YAML-only behavior.

- **`template_store.py` (NEW)**: thin read-only `TemplateStoreClient` reading the same `synthetic_metrics.templates` collection as the legacy CLI's `TemplateStore`, but does NOT import the legacy package. Read paths: `get_latest`, `get_version`, `list_versions`, `list_all`. Conversion helpers: `to_template_config` (YAML → TrainForge `TemplateConfig`), `to_text` (single text field for shared scaffolding). `from_config` convenience constructor. `SHARED_NAMESPACE = "__shared__"`.
- **`DomainPlugin` base**: gains `_template_store: Any = None` (set in new `__init__`) and `set_template_store(store)` for lazy post-registration injection (domains are auto-instantiated at import time, before MongoDB config is loaded). Base `get_templates_for_category` keeps YAML-parsing default (unchanged fallback).
- **`MTGDomain`**: `get_templates_for_category` is store-first — iterates YAML-declared template_ids, prefers the store's latest `generation` doc per id (via `TemplateStoreClient.to_template_config`), falls back to the YAML `TemplateConfig` for any id the store is missing. `system_message`/`notation_legend` properties check the store's `__shared__` namespace first, fall back to YAML-loaded values.
- **`validator.py`**: `_resolve_validator_template(template_store, category, template_id)` implements hybrid lookup (generator-specific `(category, "validator", "validator")` override → shared `(__shared__, "qa_validation", "validator")` → None). `validate_and_loop_with_suggested_fix` and `_validate_qa` accept optional `template_store`/`category` params. Stored template substitution uses `str.replace()` (NOT `.format()`) so MTG braces pass through verbatim. Inline construction is the unchanged fallback.
- **`generator.py`**: `BaseGenerator.generate()` threads `template_store=getattr(self.domain, "_template_store", None)` and `category` into the validator call. `get_templates()` unchanged.
- **`ui/app.py`**: `_connect_mongodb()` constructs `TemplateStoreClient.from_config(...)` and injects into the registered MTG domain via `set_template_store()` when MongoDB is available. Wrapped in try/except (non-fatal; YAML fallback on failure).
- **Fallback chain**: `template_store=None` → YAML parsing (current behavior). Store present, no doc for `(category, tid, "generation")` → YAML `TemplateConfig` for that id. Store present, doc exists → `TemplateStoreClient.to_template_config(doc)`. `system_message`/`notation_legend`: store doc → store content; no store doc → YAML value. Validator: generator-specific doc → shared doc → inline construction.
- **Backward compat**: 469 passed (426 existing + 43 new), 1 pre-existing failure unchanged. With `template_store=None` (default) TrainForge behaves byte-identically to pre-Story-043.
