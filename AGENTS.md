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

### Generation Token Budget Raised (Story 051) — 2026-08-14

The generation path (`BaseGenerator._process_item()` initial generation and `regenerate_answer()`) no longer inherits the 8192 `max_tokens` default from `QueryModel.query()`. Reasoning-model generators (e.g. `deepseek-v4-flash`) emit `reasoning_content` thinking tokens that count against the SAME budget on the serving backend, so the final answer JSON was truncated mid-generation. Generation now passes `max_tokens=GENERATION_MAX_TOKENS` (16384) — twice the old cap, mirroring the Story 047 validation raise.

- **`query_model.py`** — New module constant `GENERATION_MAX_TOKENS = 16384` with explanatory comment (directly below `VALIDATION_MAX_TOKENS`); `regenerate_answer()` now passes `max_tokens=GENERATION_MAX_TOKENS` to `query()`
- **`base_generator.py`** — Import updated; the `_process_item()` generation call switches from the hardcoded `max_tokens=8192` to `max_tokens=GENERATION_MAX_TOKENS`
- **`test_generation_trace.py`** — 2 new regression tests (`test_generation_call_passes_generation_max_tokens`, `test_regenerate_answer_passes_generation_max_tokens`) asserting the generation path passes `GENERATION_MAX_TOKENS`. Total 433 passing.
- **Deliberately unchanged** — `QueryModel.query()` default (8192), validation path (`VALIDATION_MAX_TOKENS` 16384), observer (`observer.py` 2048), all `run_*.sh`, YAML templates

**New files:** None
**Modified files:** `query_model.py`, `base_generator.py`, `test_generation_trace.py`
**Breaking changes:** None — additive constant + call-site changes; no CLI flags, generator endpoints, or config changes.

### Validator Context Parity + Shadow Disagreement Metric + Mana-Cost Hardening (Story 050) — 2026-08-13

Run analysis of `muse:30b`-as-generator showed an information-asymmetry bug: the generation prompt included `Color Identity`, `Mana Cost`, and `Type` for every card, but the **validation context stripped those fields down to oracle text only**. The grounding rules then marked correct claims ("Guttersnipe is legal in Ashling's red deck") as `UNSUPPORTED` → auto-reject → regeneration produced evasive hedging answers. Also observed: `muse` hallucinating a card's color as judge (rejecting mono-black Viscera Seer as "white") and fabricating mana costs as generator.

- **Validator context parity** — `build_context()` in `generate_commander_building.py`, `generate_commander_knowledge.py`, and `generate_synergy_questions.py` now emit the same `to_prompt_detail()` card data the generation prompt sees (Name, Mana Cost, Type, Oracle Text, Color Identity, Keywords, EDHREC data) instead of truncated oracle text. The validator can now ground legality/cost claims; `commander_building` and `commander_rules` were the two legality-sensitive categories with the full asymmetry, `synergy` was missing Mana Cost/CI on its primary card and partners.
- **Shadow disagreement counter** — `GenerationTrace` gains defaulted `shadow_disagreements: int = 0` (backward compatible, `asdict`-serialized). New `_record_shadow_disagreement()` in `common.py` runs after every shadow validation round and counts rounds where the real validator and shadow validator produced **different parseable verdicts** (a proxy for the validator's own hallucination rate); unparseable transport-failure rounds never count. Matching rounds are flagged `disagreement: bool` on the shadow round and `shadow_disagreement: bool` on the corresponding `validation_rounds` entry so both sides join by `round`. Records only — never affects acceptance/regeneration/metrics/observer.
- **Mana-cost hardening** — both `commander_building.yaml` templates gain: "Do NOT state a card's mana cost or color identity unless it appears verbatim in the provided card data."
- **Tests**: 18 new (`test_generate_commander_building.py` covers context parity across all 3 generators + template rule; `TestShadowValidation` ×5 loop-level disagreement tests + 1 unit test of `_record_shadow_disagreement`). Total 431 passing.

**New files:** `test_generate_commander_building.py`
**Modified files:** `common.py`, `models.py`, `generate_commander_building.py`, `generate_commander_knowledge.py`, `generate_synergy_questions.py`, `templates/commander_building.yaml`, `test_generation_trace.py`
**Breaking changes:** None — additive fields, context parity only enriches validator input. Note: `seed_templates.py --to-yaml` reads commander_building from YAML, so the hardened instruction survives regeneration.

## Recent Changes

### Shadow Validator — Trace-Only Second Validator (Story 049) — 2026-08-12

`main.py` accepts an optional `--shadow-validation-model`. When set, every answer passed to the real validator is ALSO validated by the shadow model using the identical validation template/context. The shadow verdict is recorded on the trace's new `shadow_validation_rounds` field (each round tagged `"shadow": True`, `"model"`, and the matching `"round"` index for joining to `validation_rounds`) plus the `shadow_validation_model` field — it NEVER affects acceptance, regeneration, metrics, or the observer. This enables trace analysis comparing real vs shadow validator verdicts (same template, different model) to tune the validation template for a future validator swap. Skipped items (`validation_pct`) and `--no-log-traces` runs produce no shadow rounds; `batch_validate.py` (no traces) is unaffected.

- **`models.py`** — `ModelType.SHADOW_VALIDATION`; `GenerationTrace` gains defaulted `shadow_validation_model: str = ""` and `shadow_validation_rounds: list` (backward compatible, `asdict`-serialized to MongoDB automatically)
- **`common.py`** — New `_run_shadow_validation()` invoked after every real `validate_qa` inside `validate_and_loop_with_suggested_fix`; reads the shadow model from the shared `models` dict (`.get(ModelType.SHADOW_VALIDATION)`), no-ops when unset or no trace; prints `👤 SHADOW VALIDATION (<model>): accepted/rejected (score x/10)`
- **`main.py`** — New `--shadow-validation-model` flag; injects the shadow `Model` into the shared `models` dict so all 27 generators pick it up with zero per-generator changes; banner + run summary print it
- **`run_common.sh` (new)** — Shared POSIX-sh named-argument parser (`--count/--model/--validation-model/--validation-pct/--dry-run/--observer-model/--shadow-validation-model`) making run-script argument order irrelevant; per-script `DEFAULT_MODEL`/`DEFAULT_VALIDATION_MODEL` are overridable variables
- **`run_*.sh` (all 27)** — Refactored off positional `$2..$6` onto `run_common.sh` + named flags; added `--shadow-validation-model $SHADOW_VALIDATION_MODEL` pass-through; legacy count shorthand (`run_combos.sh 1000`) still works
- **`generator-dashboard/process_manager.py`** — `start()` gains `shadow_validation_model`; command built from named flags instead of raw positional tokens (also fixes a latent bug where a dashboard run with an observer model silently forced `--dry-run`)
- **`generator-dashboard/config.py`** — `DEFAULT_SHADOW_VALIDATION_MODEL = ""` (opt-in); `script_model_defaults()` parses `DEFAULT_MODEL`/`DEFAULT_VALIDATION_MODEL` and returns a 4-tuple
- **`generator-dashboard/app.py`** — `StartPayload.shadow_validation_model` pass-through; snapshot exposes `default_shadow_validation_model`
- **`generator-dashboard/static/app.js`** — "Shadow validation model" field group in the generator panel (blank = disabled) + hint text
- **Tests** — 8 new: `test_generation_trace.py` (`TestShadowValidation` ×6 + dataclass/CLI assertions), `test_base_generator.py` + `test_generate_quick_guidelines.py` (end-to-end shadow-trace tests), dashboard process_manager/API shadow pass-through + registry 4-tuple

**New files:** `run_common.sh`
**Modified files:** `models.py`, `common.py`, `main.py`, 27 `run_*.sh`, `generator-dashboard/{process_manager.py,config.py,app.py,static/app.js}`, `test_generation_trace.py`, `test_base_generator.py`, `test_generate_quick_guidelines.py`, 3 dashboard test files
**Breaking changes:** None — CLI flags and dashboard UI are additive. Run-script positional args beyond the leading count move to named flags (documented in each script header); a lone leading integer still works as the legacy count shorthand.

### Per-QA Trace Emission + Generation-Error Collection Split (Story 048) — 2026-08-12

`generation_traces` used to hold ONE trace per template/data-batch: every QA in the batch mutated the same trace, so `final_outcome`/`final_score`/`total_rounds` reflected only the LAST QA while `validation_rounds` conflated all QAs' rounds (all labeled `round: 0`, no attribution). That made per-QA validator analysis (verdict stats, false-accept/false-reject, score distributions) impossible from stored data. Traces are now emitted **per QA pair**; `generation_error` traces move to a separate `generation_errors` collection so validator analysis isn't polluted by the 2,692 generation JSON-parse failures (72% of the old collection — top block 1,349 `commander_building` × `gemma4:31b-small`).

- **`models.py`** — `GenerationTrace` gains `qa_index: int = 0`, `question: str = ""`, `answer: str = ""` (final answer text as a first-class field, post-regeneration); additive defaulted fields, backward compatible
- **`base_generator.py`** — `_process_item` emits one trace per QA pair: template-level trace is now a generation scaffold, each QA deep-copies it (fresh `item_id`, sets `qa_index`/`question`, then `answer` after validation), fires `trace_callback` per QA, and the observer receives that trace's own rounds (per-QA `_rounds_start` slicing removed); `generation_error` handlers unchanged (they fire the scaffold once)
- **`generate_quick_guidelines.py`** — `validate_answer()` now passes `trace=trace` into `validate_and_loop_with_suggested_fix` (it previously dropped the trace, which would have persisted `pending` traces with zero rounds)
- **`main.py`** — New `synthetic_metrics.generation_errors` collection from `get_mongo_collections()`; `save_trace`/`flush_traces` route by `final_outcome == "generation_error"`; indexes on the new collection; summary print updated
- **Tests**: 2 new tests (`test_trace_callback_called_per_qa_with_own_rounds` asserting per-QA emission with no round bleed, `test_validate_answer_populates_trace` for quick_guidelines); existing trace tests extended for new fields

**New files:** None
**Modified files:** `models.py`, `base_generator.py`, `generate_quick_guidelines.py`, `main.py`, `test_generation_trace.py`, `test_generate_quick_guidelines.py`
**Breaking changes:** None — no CLI flags, generator endpoints, or dashboard changes. Old traces remain conflated in `generation_traces`; new runs produce clean per-QA traces (distinguishable by `question != ""`), errors go to `generation_errors`.

**Also fixed** — 8 stale tests reconciled with the newer implementations they had drifted from: `test_data_access.py` lookup tests mocked `find()` but the methods now use `aggregate()` pipelines; pipeline-builder tests asserted `$limit` but the builders use `$sample`; `test_load_all_27_category_files` didn't account for observer-generated versioned files (`{category}_vN.yaml`) and now validates them separately.

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

Current: 433 tests passing.
