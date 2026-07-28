# AGENTS.md

## Project Overview

**MTG Expert Model Training** — Generates synthetic Q&A training data using LLM generation + validation, then extracts it into JSONL format for fine-tuning smaller models. 27 MTG-specific generators using `BaseGenerator[T]` + `MTGDataAccess`.

## Quick Start

```bash
# Generate synthetic data (dry run)
python -m training_data.generate_synthetic_data.main --dry-run

# Regenerate YAML templates from Python constants
python -m training_data.generate_synthetic_data.seed_templates --to-yaml
```

**Prerequisites:** Python 3.10+, MongoDB, Ollama or API keys for Anthropic/OpenAI.

## Recent Changes

### YAML Template Migration (Stories 001–007) — 2026-07-27

Replaced the MongoDB-based template store with local YAML files. All 27 generator templates, shared scaffolding blocks, and validator prompts now live as `.yaml` files in `training_data/generate_synthetic_data/templates/`. A new `YamlTemplateLoader` class mirrors the read surface of the old `TemplateStore`, so downstream code swaps in with minimal changes.

- **New directory**: `templates/` — 27 category YAML files + `shared.yaml` (5 scaffolding blocks + validators) + `comparison_validator.yaml`
- **New module**: `yaml_template_loader.py` — `YamlTemplateLoader` class with `get_latest()`, `list_versions()`, `get_scaffolding()`, `get_validator()`
- **`main.py`** — Removed 54 per-generator version flags; added `--templates-dir` flag (defaults to package `templates/`); wired `YamlTemplateLoader` instead of `TemplateStore`
- **`base_generator.py`** — Added `yaml_loader` param; renamed `_load_templates_from_store()` → `_load_templates_from_source()`; fallback chain: YAML loader → MongoDB store (deprecated) → class constants
- **`query_model.py`** — Added `yaml_loader` support in `_resolve_validator_template()`
- **`common.py`** — Extracted `_dict_to_template_config()`; updated `init_scaffolding()` for YAML path
- **`seed_templates.py`** — Added `--to-yaml` mode to regenerate YAML files from Python constants; MongoDB seeding kept as deprecated path with `DeprecationWarning`
- **Tests**: 55 new tests across `test_yaml_template_loader.py` (28), `test_cli_templates_dir.py` (13), `test_seed_templates_yaml.py` (14); trimmed obsolete MongoDB-specific tests in `test_template_store.py` and `test_seed_templates.py`

**New files:** `yaml_template_loader.py`, `templates/__init__.py`, 3 test files
**Modified files:** `base_generator.py`, `query_model.py`, `common.py`, `template_store.py`, `main.py`, `seed_templates.py`
**Removed files:** `test_cli_version_flags.py`
**Breaking changes:** None — class-level `TEMPLATES` constants retained as ultimate fallback.

### Data-Driven Versioned Templates (Stories 040–045) — 2026-07-26

All hardcoded templates now live in a version-controlled MongoDB collection (`synthetic_metrics.templates`). Key additions:

- **`TemplateStore`** — CRUD access to versioned templates
- **`seed_templates.py`** — Imports all 27 generator templates + shared scaffolding from constants.py and templates.yaml
- **CLI version flags** — `--<slug>-template-version N`, `--template-versions '{"category": N}'`, `--list-template-versions`
- **Version tracking** — `GenerationTrace.template_version` + `ValidationMetrics.record_template_version()` enable version-to-version performance comparison
- **Fallback chain** — Version override → latest → class-level constant → store unavailable = hardcoded fallback
- **Bugfix** — Validator store path used `.format()` which broke on MTG braces; replaced with `str.replace()`

**New files:** `template_store.py`, `seed_templates.py`, 10 test files (167 new tests)
**Modified files:** `base_generator.py`, `common.py`, `query_model.py`, `main.py`, `models.py`
**Breaking changes:** None

### MTG AI Pipeline Prompt Improvements — 2026-07-26

Three coordinated changes targeting the two largest failure modes (wrong trigger/stack ordering, vague outcomes):

- **`REQUIREMENTS_BASE`** expanded from 8 to 9 items (new: trigger ordering, LIFO stack, ETB timing)
- **Sibling feedback threading** — corrections from Q1 are threaded to Q2/Q3 regeneration prompts
- **`common.py`** — `validate_and_loop_with_suggested_fix` accepts `sibling_corrections` accumulator

### TrainForge Generic Framework — 2026-07-24

Extracted the `BaseGenerator` pattern into a reusable framework:

- **Plugin architecture** — domains implement `DomainPlugin` ABC + `config.yaml` + `templates.yaml`
- **16 generators** — 7 topic-based + 9 data-driven, all registered in `MTGDomain`
- **Multi-provider LLM** — Ollama, Anthropic, OpenAI via config
- **Streamlit UI** — Generation, browsing, validation review, and export

### Enriched MTGDataAccess (Story 11) — 2026-07-23

25+ typed methods with aggregation pipelines, LRU caching, and retry:

- Card enrichment (`get_cards_enriched()`), combo enrichment (`get_combos_enriched()`)
- Commander enrichment (`get_commanders_enriched()`)
- Cached lookups (rulings, prices, legalities, keywords, archetypes)
- Analytics (top cards, budget alternatives, synergy partners, color identity)

## Key Files

| File | Purpose |
|------|---------|
| `training_data/generate_synthetic_data/base_generator.py` | Abstract base for all legacy generators |
| `training_data/generate_synthetic_data/main.py` | CLI entry point, 27 generator instantiations |
| `training_data/generate_synthetic_data/yaml_template_loader.py` | YAML-based template loader (replaces MongoDB TemplateStore) |
| `training_data/generate_synthetic_data/templates/` | Local YAML templates — 27 categories + shared scaffolding + validators |
| `training_data/generate_synthetic_data/common.py` | Prompt builders, validation pipeline, scaffolding cache |
| `training_data/generate_synthetic_data/query_model.py` | Multi-provider LLM client |

TrainForge files live in the separate `../trainforge/` repository — see `../trainforge/AGENTS.md` for its key files.

## Test Commands

```bash
# All tests
pytest training_data/generate_synthetic_data/ -v
```

Current: 368 tests passing (20 pre-existing failures unchanged).
