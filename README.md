# MTG Expert Model Training

Fine-tune LLMs to be Magic: The Gathering experts — covering all 108K+ cards, 76K+ combos, comprehensive rules (292 pages), strategic advice, and competitive meta knowledge.

This repository contains two projects:

- **`training_data/`** — Legacy MTG-specific synthetic data generation system (CLI-based, 27 generators)
- **`trainforge/`** — Generic synthetic data generation framework with Streamlit web UI and pluggable domain architecture (includes MTG as first domain plugin)

## Prerequisites

- **Python 3.10+** (see `.python-version`)
- **MongoDB** running on `localhost:27017` (user: `root`, password: `whatever`)
- **Ollama** with models pulled (default: `qwen2.5:14b`)
- **uv** package manager (recommended) or pip
- **Populated MongoDB databases**: `mtg_json`, `edhrec`, `commander_spellbook`, `mtg_rules`, `mtg_archetypes`

## Setup

```bash
# Install dependencies
uv sync

# Or with pip
pip install -r requirements.txt

# Pull the LLM model for generation
ollama pull qwen2.5:14b
```

## Running

### Synthetic Data Generation

Generate training Q&A pairs using LLM generation + validation:

```bash
# Generate all formats (~57K examples)
python -m training_data.generate_synthetic_data.main --all

# Phase presets
python -m training_data.generate_synthetic_data.main --phase1   # 15K card-focused
python -m training_data.generate_synthetic_data.main --phase2   # 13K strategy/theory
python -m training_data.generate_synthetic_data.main --phase3   # 8K rules-grounded
python -m training_data.generate_synthetic_data.main --phase4   # 9K EDHREC-grounded

# Individual formats
python -m training_data.generate_synthetic_data.main --combo-queries 500
python -m training_data.generate_synthetic_data.main --meta-knowledge 200
python -m training_data.generate_synthetic_data.main --terminology 200

# Dry run (no MongoDB writes)
python -m training_data.generate_synthetic_data.main --archetypes 100 --dry-run

# Disable generation trace logging (traces are on by default)
python -m training_data.generate_synthetic_data.main --all --no-log-traces
```

### Data Extraction

Extract training data from all MongoDB sources:

```bash
python training_data/extract_training_data.py
```

### Model Training

```bash
python training.py
```

### TrainForge Web Interface (Generic Framework)

TrainForge is a generic synthetic data generation framework with a Streamlit web UI. The MTG domain plugin provides the same 27 categories as the legacy system, but through a pluggable architecture.

```bash
cd trainforge

# Install dependencies
uv sync

# Start the web interface
streamlit run src/trainforge/ui/app.py

# Or use the entry point (after installing with uv/pip)
trainforge
```

The UI provides generation control, data browsing, metrics dashboards, and JSONL export — all through a browser. Configure MongoDB connection, LLM provider (Ollama/Anthropic/OpenAI), and domain settings in the Settings page.

See `docs/ARCHITECTURE.md` for TrainForge architecture details and how to add new domains.

## Running Tests

```bash
# All tests
pytest tests/ training_data/generate_synthetic_data/test_*.py

# Specific test file
pytest tests/test_generate_meta_knowledge.py -v
```

## Generation Trace Logging

Generation traces capture the full LLM interaction lifecycle for debugging and analysis. Traces are stored in `synthetic_metrics.generation_traces` with full prompt/response text, validation scores, and final outcomes.

```bash
# Traces are enabled by default
python -m training_data.generate_synthetic_data.main --all

# Disable trace logging if not needed
python -m training_data.generate_synthetic_data.main --all --no-log-traces
```

See `docs/ARCHITECTURE.md` for the trace schema and design details.

## Project Structure

```
model_training/
├── training_data/
│   ├── generate_synthetic_data/    # Legacy MTG-specific synthetic Q&A generation (CLI)
│   │   ├── base_generator.py       # BaseGenerator[T] abstract class
│   │   ├── main.py                 # CLI entry point for all generators
│   │   ├── data_access.py          # MTGDataAccess - MongoDB abstraction
│   │   ├── models.py               # Data models (Card, QuestionAnswer, etc.)
│   │   ├── common.py               # TemplateConfig, prompt building, validation
│   │   ├── constants.py            # MTG notation legend, constants
│   │   ├── generate_*.py           # Individual generator implementations
│   │   └── test_*.py               # Generator unit tests
│   └── *.py                        # Data scraping, extraction, and conversion
├── trainforge/                     # Generic synthetic data generation framework
│   ├── src/trainforge/             # Core framework modules (9 files)
│   │   ├── models.py               # Pydantic v2 models (Model, Q&A, Trace, Metrics)
│   │   ├── config.py               # YAML loader with env var interpolation
│   │   ├── data_source.py          # DataSource ABC + MongoDataSource
│   │   ├── domain.py               # DomainPlugin ABC, TemplateConfig, DomainRegistry
│   │   ├── generator.py            # BaseGenerator[T] template method pattern
│   │   ├── query_model.py          # Multi-provider LLM client (Ollama/Anthropic/OpenAI)
│   │   ├── training.py             # JSONL exporter with ratio controls
│   │   ├── validator.py            # Domain-agnostic validation + regeneration loop
│   │   └── ui/                     # Streamlit web interface (7 files)
│   ├── domains/mtg/                # MTG domain plugin (first domain implementation)
│   │   ├── models.py               # 22 Pydantic v2 domain models (Card, Combo, Commander, etc.)
│   │   ├── data_source.py          # Enriched MTGDataAccess with typed joins, cache, retry
│   │   ├── __init__.py             # MTGDomain plugin (auto-registers)
│   │   ├── config.yaml             # Domain metadata, MongoDB collection config
│   │   └── templates.yaml          # 27 category templates with validation rules
│   ├── tests/                      # 301 tests (core + UI + MTG domain)
│   └── pyproject.toml              # Dependencies and entry point
├── tests/                          # Top-level unit tests (legacy)
├── qwen_training/                  # Qwen model training scripts
├── CHANGELOG.md
└── docs/
    └── ARCHITECTURE.md             # Architecture for both legacy + TrainForge
```

## Generator Categories

All generators extend `BaseGenerator[T]` and use LLM generation + validation:

| Category | Generators | Source |
|----------|-----------|--------|
| Card Search | `generate_card_search_queries` | MTG card data |
| Combo Queries | `generate_combo_queries` | Commander Spellbook |
| Color Identity | `generate_color_identity_questions` | MTG card data |
| Comparisons | `generate_comparison_questions` | MTG card data |
| Quick Guidelines | `generate_quick_guidelines` | EDHREC archetype data |
| Deckbuilding Theory | `generate_deckbuilding_theory` | Hardcoded topics |
| Commander Building | `generate_commander_building` | Hardcoded archetypes |
| Game Theory | `generate_game_theory` | Hardcoded situations |
| Rules Scenarios | `generate_rules_scenarios` | Hardcoded scenarios |
| Archetypes | `generate_archetypes` | Hardcoded archetypes |
| Meta Knowledge | `generate_meta_knowledge` | Hardcoded topics |
| Commander Knowledge | `generate_commander_knowledge` | Hardcoded sub-topics |
| Terminology | `generate_terminology_questions` | Hardcoded terms |
| Budget Alternatives | `generate_budget_alternatives` | MTG card data |
| Reverse Lookup | `generate_reverse_lookup_questions` | MTG card data |
| Synergy | `generate_synergy_questions` | MTG card data |
