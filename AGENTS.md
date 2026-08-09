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

### Validation Token Budget Raised (Story 047) — 2026-08-06

The validation path (`validate_qa` / `validate_with_model`) no longer inherits the 8192 `max_tokens` default from `QueryModel.query()`. Reasoning-model validators (e.g. `deepseek-v4-flash`) emit `reasoning_content` thinking tokens that count against the SAME budget on the serving backend, so the final JSON answer was truncated mid-generation → "Validation parse failed: Expecting value..." rejections (run `7c58c422` — the same failure mode Story 046 hardened against). Validation now passes `max_tokens=VALIDATION_MAX_TOKENS` (16384) — twice the old cap.

- **`query_model.py`** — New module constant `VALIDATION_MAX_TOKENS = 16384` with explanatory comment; `validate_qa()` and `validate_with_model()` now pass `max_tokens=VALIDATION_MAX_TOKENS` to `query()`
- **`test_generation_trace.py`** — 2 new regression tests (`test_validate_qa_passes_validation_max_tokens`, `test_validate_with_model_passes_validation_max_tokens`) asserting the validation path passes `VALIDATION_MAX_TOKENS`
- **Deliberately unchanged** — `QueryModel.query()` default (8192), generation path (`base_generator.py` 8192), observer (`observer.py` 2048), all `run_*.sh`, YAML templates

**New files:** None
**Modified files:** `query_model.py`, `test_generation_trace.py`
**Breaking changes:** None — no CLI flags, generator endpoints, or config changes.

### Validation Transport-Failure Hardening (Story 046) — 2026-08-06

Validator transport failures (unparseable/truncated/errored responses, e.g. "Validation parse failed: Expecting value...") are no longer treated as answer-quality rejections. They re-validate the SAME answer (bounded to 2 retries) without regenerating, counting a fix attempt, or appending sibling feedback — then reject without regeneration if the validator stays unparseable. Prevents mechanically-fine answers from being permanently rejected at score 0 (the observed `deepseek-v4-flash` failure mode in run `7c58c422`).

- **`run_*.sh` (all 27)** — `VALIDATION_MODEL` default reconciled from `deepseek-v4-flash` → `glm-5.2` (matching `generator-dashboard/config.py`); stale `glm-5.1` comment in `run_combos.sh` updated
- **`query_model.py`** — New `is_transport_failure_reason()` predicate matching the `"Validation parse failed"` / `"Validation error"` reason prefixes returned by `validate_qa` / `validate_with_model`
- **`common.py`** — `validate_and_loop_with_suggested_fix`: transport-failure retry path (same answer, ≤2 retries, no regen/metrics/sibling feedback), `_upsert_sibling_correction()` per-QA dedupe helper, trace `round_num` advances on retries and `final_outcome` uses the `iteration == 0` discriminator
- **Single-QA note** — Production callers (`base_generator.validate_answer`, `generate_quick_guidelines.validate_answer`) always pass ONE QA per call, so `enumerated_i` is always 0 and the sibling-corrections accumulator holds at most one entry (the most recent correction). Threading the batch QA index for true per-QA dedupe is a tracked follow-up.
- **`observer.py`** — Transport-failure reasons excluded from the top-rejection stats fed to the observer LLM
- **`batch_validate.py`** — Fixed crash from unpacking `validate_qa`'s 3-tuple as 4 values
- **Tests**: 6 new tests (5 in `test_generation_trace.py`, 1 in `test_observer.py`)

**New files:** None
**Modified files:** 27 `run_*.sh` scripts, `query_model.py`, `common.py`, `observer.py`, `batch_validate.py`, `test_generation_trace.py`, `test_observer.py`
**Breaking changes:** None — CLI flags, generator endpoints, and dashboard UI unchanged.

### Scraper Dashboard (generator-dashboard) — 2026-08-02

Added management of the `training_data/scrape_*.py` scripts to the generator dashboard, separated from the 27 generation scripts behind a top-level **Generators | Scrapers** toggle. Scrapers get the same Start/Stop + live-log controls but a simplified panel (no validation metrics).

- **New registry**: `ScraperSpec` dataclass + 9 scraper items (`edhrec_guides`, `edhrec_articles`, `edhrec_commanders`, `edhrec_game_changers`, `edhrec_top_color`, `edhrec_top_type`, `funtrivia`, `commander_spellbook`, `mtg_archetypes`) in `generator-dashboard/config.py`
- **New wrapper scripts**: `training_data/run_<slug>.sh` (9) invoke the python scraper with `"$@"` so the dashboard can pass an editable "Extra args" field
- **`process_manager.py`** — Added `scan_scrapers()` (matches `run_<slug>.sh` in `ps` so shared scripts stay unambiguous), `start_scraper()` (default + extra args), `stop_scraper()`; shared `_spawn`/`_stop` helpers
- **`app.py`** — Snapshot now includes `scrapers`; new endpoints `/api/scrapers`, `/api/scrapers/{slug}/start|stop`, `/api/scraper-logs/{slug}` (SSE)
- **Frontend** — `static/index.html` + `app.js` + `style.css`: mode toggle, scraper tabs/panel with "Extra args" field and log viewer
- **Tests**: 23 new tests across `test_scraper_registry.py`, `test_scraper_process_manager.py`, `test_scraper_api.py` (56 dashboard tests passing)

**Scraper deps:** the EDHREC scrapers need the local `pyedhrec` fork (`uv pip install -e /home/sheigl/code/pyedhrec`; already in `requirements.txt`); `mtg_archetypes` additionally needs `beautifulsoup4` + `selenium` (not installed).

**New files:** 9 `run_*.sh` wrappers, 3 test files
**Modified files:** `config.py`, `process_manager.py`, `app.py`, `static/index.html`, `static/app.js`, `static/style.css`
**Breaking changes:** None — generator endpoints/UI unchanged.

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

Current: 394 tests passing (8 pre-existing failures unchanged).
