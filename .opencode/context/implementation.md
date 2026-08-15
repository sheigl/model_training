# Implementation Summary — Raise Generation Token Cap (GENERATION_MAX_TOKENS=16384)

## What was implemented

The GENERATION path was truncating responses mid-generation: both `BaseGenerator._process_item()` (the initial generation call, hardcoded `max_tokens=8192`) and `QueryModel.regenerate_answer()` (silently inheriting `query()`'s default 8192) were capped below what reasoning-model generators (e.g. `deepseek-v4-flash`) need. Those models emit `reasoning_content` thinking tokens that count against the SAME `max_tokens` budget on the serving backend, so the final answer JSON got cut off mid-generation. This mirrors the Story 047 fix for the validation path.

### Files Modified

1. **`query_model.py`**
   - Added module constant `GENERATION_MAX_TOKENS = 16384` directly below `VALIDATION_MAX_TOKENS` (line 35, comment block at lines 29–34) with a comment explaining the reasoning-token rationale (same text as the validation comment, s/validators/generators/).
   - `regenerate_answer()` (line 368): `self.query(generation_model, prompt, max_tokens=GENERATION_MAX_TOKENS, purpose="REGENERATION")` (was inheriting the 8192 default).
   - NOT changed: `query()` default `max_tokens=8192`, validation path (`VALIDATION_MAX_TOKENS` usages), observer's `max_tokens=2048`, `run_*.sh` scripts, YAML templates.

2. **`base_generator.py`**
   - Import updated: `from .query_model import QueryModel, GENERATION_MAX_TOKENS`.
   - `_process_item()` generation call (line 472–477, `max_tokens=` at line 475): `max_tokens=8192` → `max_tokens=GENERATION_MAX_TOKENS`.

3. **`test_generation_trace.py`** — Two regression-guard tests proving the max_tokens passthrough on the generation path:
   - `TestBaseGeneratorTraceIntegration::test_generation_call_passes_generation_max_tokens` — builds a `ConcreteGenerator`, patches the real `QueryModel.query` and `validate_qa` on the generator's query model via `patch.object`, calls `generate()`, asserts the generation call's `call_args.kwargs["max_tokens"] == GENERATION_MAX_TOKENS` and `== 16384`.
   - `TestBackwardCompatibility::test_regenerate_answer_passes_generation_max_tokens` — patches `qm.query` via `patch.object` (Story 047 style), calls `regenerate_answer()`, asserts `call_args.kwargs["max_tokens"] == GENERATION_MAX_TOKENS` and `== 16384`.
   - Import updated: `from ...query_model import QueryModel, VALIDATION_MAX_TOKENS, GENERATION_MAX_TOKENS`.

4. **`CHANGELOG.md`** — Added entry under `# Changelog`.

### Grep verification for max_tokens assertions
- Fake `query()` methods in test files (`test_generation_trace.py`, `test_base_generator.py`, `test_generate_reverse_lookup_questions.py`, `test_generate_quick_guidelines.py`, `test_generate_color_identity_questions.py`) define `max_tokens: int = 8192` as the default param — they ACCEPT any value passed. No test asserted the exact 8192 value on the generation path, so no stale assertions needed updating.

### Test Results
- test_generation_trace.py: 52 tests (50 pre-existing + 2 new), all passing
- Full suite: 433 passed / 0 failed (431 baseline + 2 new), zero failures
- Lint: 9 pre-existing ruff errors in the 3 touched files (unused imports `dataclasses.dataclass`, `typing.Iterator`, `yaml`, `anthropic.Stream`, `MagicMock`, `call`, `QuestionAnswerEnhanced`, `ValidationMetrics`, f-string at line 72) — all pre-existing, none in touched lines, left untouched

---

# Implementation Summary — Raise Validation Token Cap (VALIDATION_MAX_TOKENS=16384)

## What was implemented

`QueryModel.validate_qa()` and `validate_with_model()` (the two VALIDATION entry points) were silently inheriting `query()`'s default `max_tokens=8192`. Reasoning-model validators (e.g. `deepseek-v4-flash`) emit `reasoning_content` thinking tokens that count against the SAME max_tokens budget on the serving backend, so the final JSON answer was getting truncated mid-generation → "Validation parse failed: Expecting value..." rejections (run `7c58c422`).

### Files Modified

1. **`query_model.py`**
   - Added module constant `VALIDATION_MAX_TOKENS = 16384` (after `VALIDATION_TRANSPORT_ERROR_PREFIX`, line ~27) with a comment explaining the deepseek-v4-flash reasoning-token rationale.
   - `validate_with_model()` (~line 180): `self.query(model, validation_prompt, max_tokens=VALIDATION_MAX_TOKENS, purpose="VALIDATION")`
   - `validate_qa()` (~line 266): `self.query(validation_model, prompt, max_tokens=VALIDATION_MAX_TOKENS, purpose="VALIDATION")`
   - NOT changed: `query()` default `max_tokens=8192` (generation path), observer's `max_tokens=2048`, `run_*.sh` scripts, YAML templates.

2. **`test_generation_trace.py`** (follow-up, code-review requested) — Two regression-guard tests in `TestBackwardCompatibility` proving the max_tokens passthrough on the validation path:
   - `test_validate_qa_passes_validation_max_tokens` — patches `qm.query` via `patch.object`, calls `validate_qa`, asserts `call_args.kwargs["max_tokens"] == VALIDATION_MAX_TOKENS` and `== 16384`.
   - `test_validate_with_model_passes_validation_max_tokens` — same pattern for `validate_with_model` with a full card-comparison validation JSON (score/is_acceptable/missing_info/errors/mechanical_accuracy/cost_comparison_correct) so the call parses cleanly.
   - Import updated: `from ...query_model import QueryModel, VALIDATION_MAX_TOKENS`.

3. **`CHANGELOG.md`** — Added entry under `# Changelog`.

### Grep verification for max_tokens assertions
- Mock `query()` methods in test files (`test_generation_trace.py`, `test_base_generator.py`, `test_generate_reverse_lookup_questions.py`, `test_generate_quick_guidelines.py`, `test_generate_color_identity_questions.py`) define `max_tokens: int = 8192` as the default param — they ACCEPT any value passed, so no test asserts the 8192 value in a VALIDATION context. No test changes required.

### Test Results
- test_generation_trace.py: 37 passed / 0 failed (35 pre-existing + 2 new)
- Full suite: 394 passed / 8 pre-existing failed (test_data_access.py ×7, test_yaml_template_loader.py ×1 — unchanged baseline), zero new failures
- Lint: 4 pre-existing ruff errors in query_model.py (unused imports `Iterator`/`yaml`/`Stream`, f-string at line 64) — all pre-existing, none in touched lines, left untouched

---

# Implementation Summary — Story 046 (Code Review round 2): 8 Review Fixes

## What was implemented

Code Review returned CHANGES REQUESTED on the Story 046 implementation. All 8 review findings were addressed as targeted fixes to the existing work.

### Fixes Applied

1. **Fix 1 (blocking A-1)** — `common.py`: `round_num += 1` added inside the parse-retry branch (after the trace-append guard, before `continue`), so retry rounds are recorded with incrementing round numbers in `trace.validation_rounds`. NOTE: initial application landed with a 4-space indentation error in the block; detected via `ast.parse` + indentation dump and corrected.
2. **Fix 2 (blocking A-2)** — `common.py`: `final_outcome` discriminator changed from `round_num == 0` to `iteration == 0` so a retry-accepted (never-regenerated) answer is correctly `accepted_first_attempt`.
3. **Fix 3 (blocking A-3)** — `test_generation_trace.py`: added trace-fidelity assertions to the two retry tests (round numbers 0,1 and `total_rounds == 2` for the revalidate test; 3 rounds and `total_rounds == 3` for the exhausted-retries test).
4. **Fix 4 (minor #2)** — `common.py`: reject branch now sets `result = (False, None)` explicitly so a trailing rejection overrides an earlier accepted doc.
5. **Fix 5 (minor #3)** — `common.py`: `parse_retries_left = _MAX_VALIDATION_PARSE_RETRIES` reset after successful regeneration so a newly regenerated answer gets the full retry allowance.
6. **Fix 6 (minor #4)** — `common.py`: generic rejection print changed to `✗ REJECTED (after {iteration} fix attempt(s), reason: {reason or 'unknown'}): {qa.question[:80]}` (metrics logic untouched).
7. **Fix 7 (minor #1)** — `test_observer.py`: new `test_transport_failure_reason_excluded_from_top_reasons` in `TestAnalysisTriggering` — patches `_llm_analyze_generation_template`/`_llm_analyze_validation_template` to capture `top_reasons` (arg index 6 in both), calls `_analyze` directly (interval=10 avoids auto-trigger before the mocks install), asserts the parse-failure reason is absent and the genuine content reason is present.
8. **Fix 8 (orchestrator decision)** — `common.py`: added the NOTE comment above the `_upsert_sibling_correction` call site documenting the single-QA production contract and the bounded accumulator behavior.

### Test Results
- test_generation_trace.py: 35 passed / 0 failed
- test_observer.py: 31 passed / 0 failed (30 existing + 1 new)
- Full suite: 392 passed / 8 pre-existing failed (test_data_access.py ×7, test_yaml_template_loader.py ×1 — unchanged from baseline), zero new failures
- Lint: 23 pre-existing ruff errors on the 3 touched files, unchanged after fixes (zero new)

---

# Implementation Summary — Story 046: Filter Validator Transport Failures Out of the Fix Loop

## What was implemented

Stopped validator transport failures (unparseable/truncated/errored responses) from being treated as answer-quality rejections. They no longer burn regeneration attempts, inflate fix metrics, permanently reject good answers, or flood sibling feedback. Also reconciled the drifted `VALIDATION_MODEL` default in all 27 `run_*.sh` scripts.

### Files Modified

1. **27 × `run_*.sh`** — Replaced `deepseek-v4-flash` → `glm-5.2` in the `VALIDATION_MODEL` default line (matching `generator-dashboard/config.py`). Updated the stale `glm-5.1` usage comment in `run_combos.sh` line 3 → `glm-5.2`. `MODEL`/`OBSERVER_MODEL` defaults untouched.

2. **`query_model.py`** — Added `VALIDATION_PARSE_FAILURE_PREFIX`, `VALIDATION_TRANSPORT_ERROR_PREFIX`, and `is_transport_failure_reason(reason)` recognizing the `"Validation parse failed"` / `"Validation error"` prefixes returned by `validate_qa` / `validate_with_model`.

3. **`common.py`** — Imported `is_transport_failure_reason`; added `_MAX_VALIDATION_PARSE_RETRIES = 2`; added `_upsert_sibling_correction()` helper (per-QA dedup/replace). In `validate_and_loop_with_suggested_fix`: transport-failure rejections re-validate the SAME answer up to 2 times (no regeneration, no fix-attempt metric, no sibling feedback), then reject without regeneration. Sibling-correction append replaced with dedup helper. Restructured the tail so all `qa_pairs` are processed (no early return after the first accepted QA) — a no-op for production (always called with 1 QA) but required for multi-QA sibling-feedback tests.

4. **`observer.py`** — Imported `is_transport_failure_reason`; `_analyze`'s reason-counting loop skips transport-failure reasons so observer stats/templates exclude validator noise.

5. **`batch_validate.py`** — Fixed 4-tuple unpack of `validate_qa` (returns 3-tuple) → `is_valid, reason, score = ...; suggested_fix = None`.

6. **`test_generation_trace.py`** — `MockQueryModel` records `sibling_feedbacks`; 5 new tests: parse-failure retry (no regen, no fix metric, `accepted_first_attempt`), exhausted-retry rejection (no regen, `record_failed_first_attempt`), parse failures excluded from sibling feedback, per-QA dedupe, and the `is_transport_failure_reason` predicate.

### Test Results
- New tests: 5 passed, 0 failed (test_generation_trace.py: 35/35)
- Full suite: 391 passed (baseline 386 + 5), same 8 pre-existing failures unchanged (test_data_access.py ×7, test_yaml_template_loader.py ×1 — confirmed failing at HEAD), zero new failures
- Lint: 26 pre-existing ruff errors unchanged, zero new

### Deviations from plan
- Dropped `round_num += 1` from the transport-retry path: with it, the existing trace logic would classify a retry-accepted (never-regenerated) answer as `accepted_after_fix`, contradicting the plan's own test asserting `final_outcome == "accepted_first_attempt"`.
- Restructured the loop tail to process all QAs (see above) — the plan's multi-QA test (`test_parse_failure_not_in_sibling_feedback`) requires it.
- Kept the predicate's local import inside `test_is_transport_failure_reason` (as specified) instead of extending the top-level import, avoiding a new F401/F811 lint error.

---

# Implementation Summary — Story 007: Test Suite Updates for YAML Template System

## What was implemented

Trimmed obsolete MongoDB-specific tests from the test suite after the full YAML template migration. Verified zero new failures and preserved coverage of the fallback chain (YAML → class constants).

### Files Modified

1. **`test_template_store.py`** — Reduced from 26 to 4 tests. Kept only `TestToTemplateConfig` which tests the pure static method `TemplateStore.to_template_config()` still reused by the YAML loader. Removed: TestEnsureIndexes, TestUpsert, TestReads, TestSeed, TestDeleteVersion, TestFromUri, TestSharedNamespace.

2. **`test_seed_templates.py`** — Reduced from 12 to 9 tests. Removed 3 deprecated MongoDB seeding tests (`test_idempotent_seed`, `test_dry_run_does_not_write_to_mongodb`, `test_non_dry_run_calls_seed`) whose functionality is covered by `test_seed_templates_yaml.py`. Preserved: extraction function tests, generator registry tests, build_all_templates integration test.

### Test Results
- New tests added: 0 (all coverage already present in existing files)
- Tests removed: 24 (obsolete MongoDB-specific tests)
- Full suite: 368 passed, 20 pre-existing failures unchanged, zero regressions

---

# Implementation Summary — Story 005: CLI Cleanup — Remove MongoDB/Version Flags, Add --templates-dir

## What was implemented

Simplified the CLI by removing all MongoDB template-store and per-generator version override flags. Added a single `--templates-dir` flag (defaulting to the package's `templates/` directory) and wired `YamlTemplateLoader` into generator construction.

### Files Modified

1. **`main.py`** — Major cleanup:
   - Removed `import json` and `from .template_store import TemplateStore`
   - Added `from pathlib import Path` and `from .yaml_template_loader import YamlTemplateLoader`
   - Extracted `build_parser()` from `main()` so tests can exercise flag parsing without running the pipeline
   - Added `--templates-dir` flag (default: `Path(__file__).parent / "templates"`)
   - Removed the entire per-generator version flag loop (`--<slug>-template-version`, `--<slug>-validator-template-version` for all 27 generators)
   - Removed `--template-versions JSON` and `--list-template-versions` flags
   - Replaced `TemplateStore.from_uri()` construction + `init_scaffolding(store=store)` with `YamlTemplateLoader(templates_dir)` + `init_scaffolding(yaml_loader=yaml_loader)`
   - Removed the `--list-template-versions` handler, `--template-versions` JSON parsing block, and version override warning block
   - Simplified dry-run output to a single line: "Dry run complete. Templates loaded from: {templates_dir}"
   - Updated all 27 generator instantiations: replaced `template_store=template_store`, `template_version_override=...`, `validator_template_version_override=...` with `yaml_loader=yaml_loader`

2. **`test_cli_version_flags.py`** — Removed (flags no longer exist)

3. **`test_cli_templates_dir.py`** (new) — 13 tests covering:
   - `--templates-dir` flag parsing and default
   - All old version flags are rejected by argparse
   - Original count flags, preset flags, and MongoDB flags still present
   - Dry-run simplified output

### Test Results
- New tests: 13 passed, 0 failed
- Full suite: 393 passed (up from ~341), 20 pre-existing failures unchanged, zero regressions

---

# Implementation Summary — Story 006: Seed Script Removal & Migration Helper

## What was implemented

Repurposed `seed_templates.py` from a MongoDB-only seeder into a dual-mode script that can generate YAML template files via `--to-yaml`. The existing pure extraction functions (`extract_shared_blocks`, `extract_legacy`, `extract_validators`) are reused unchanged. MongoDB seeding remains but is marked deprecated with a `DeprecationWarning`.

### Files Modified

1. **`seed_templates.py`** — Added `--to-yaml` and `--output-dir` CLI flags; added `generate_yaml_files()` (groups extracted docs into shared.yaml, per-generator YAMLs, qa_validation.yaml, comparison_validator.yaml) and `write_yaml_file()` helpers; branched `main()` on mode with deprecation warning for MongoDB path.

2. **`test_seed_templates_yaml.py`** (new) — 14 tests covering:
   - `write_yaml_file`: directory creation, serialization, overwrite
   - `generate_yaml_files`: file structure, shared scaffolding/validators keys, qa_validation content, comparison_validator content, per-generator template_ids, default output dir
   - CLI: `--to-yaml` writes files, default dir, creates nested dirs
   - Deprecation warning on MongoDB path
   - Round-trip: generated YAML is loadable by `YamlTemplateLoader`

### Output Structure

```
templates/
  shared.yaml                  # scaffolding + validators sections
  qa_validation.yaml           # Q&A validator prompt
  comparison_validator.yaml    # card-comparison validator prompt
  {category}.yaml              # 27 per-generator files (list of template entries)
```

### Test Results
- New tests: 14 passed, 0 failed
- Seed-template suite: 26 passed (12 existing + 14 new)
- Full suite: same 20 pre-existing failures, zero regressions

---

# Implementation Summary — Story 004: Validator Template Migration to YAML

## What was implemented

Migrated validator prompts (QA validation and card comparison) from MongoDB/inline construction to YAML files, while preserving the exact `str.replace()` placeholder substitution logic and fallback behavior. The `_resolve_validator_template()` method in `QueryModel` now reads from the YAML loader when provided, falling back to MongoDB store (deprecated), then inline construction.

### Files Modified

1. **`query_model.py`** — Added reference-implementation comments to `build_qa_validation_prompt_template()` and `build_card_validation_prompt_template()`. The `_resolve_validator_template()` method already had YAML loader path from prior work; no changes needed there.

2. **`test_template_loading.py`** — Added 4 new end-to-end tests in `TestQueryModelYamlValidator`:
   - `test_qa_validation_prompt_uses_real_yaml_file` — loads actual `shared.yaml` via real `YamlTemplateLoader` and verifies placeholder substitution + MTG brace preservation
   - `test_card_validation_prompt_uses_real_yaml_file` — loads actual `comparison_validator.yaml` and verifies all card placeholders substitute correctly
   - `test_qa_validation_yaml_loader_preserves_mtg_braces` — explicit regression test that `{T}`, `{C}`, `{W}`, etc. survive intact through the YAML path
   - `test_card_validation_yaml_loader_preserves_mtg_braces` — same for card comparison validator

### Test Results
- New tests: 4 passed, 0 failed
- Validator suite: 37 passed (up from 33)
- Full suite: 392 passed (up from 384), 20 pre-existing failures unchanged, zero regressions

---

# Implementation Summary — Story 003: Scaffolding Block Migration to YAML

## What was implemented

Migrated the 5 shared scaffolding blocks (`SYSTEM_MESSAGE`, `MTG_NOTATION_LEGEND`, `OUTPUT_FORMAT`, `CARD_COMPARISON_INSTRUCTIONS`, `REQUIREMENTS_BASE`) from MongoDB-only loading to also support YAML loader, while keeping Python constants as fallback. The existing `_get_scaffold(key, fallback)` pattern in prompt builders required no changes.

### Files Modified

1. **`common.py`** — Added `_CACHE_KEY_TO_YAML_KEY` mapping (cache key → YAML snake_case key). Refactored `init_scaffolding()` to accept both `yaml_loader` and `store` params with YAML taking precedence. Extracted `_populate_from_yaml()` and preserved `_populate_from_store()` for the legacy MongoDB path.

2. **`main.py`** — Updated `init_scaffolding(template_store)` call site to `init_scaffolding(store=template_store)` to match the new signature (yaml_loader is first param). Full YAML loader wiring deferred to Story 005.

3. **`test_template_loading.py`** — Added 4 new tests:
   - `test_init_scaffolding_from_yaml_populates_cache` — verifies all 5 blocks loaded from mock YAML loader
   - `test_init_scaffolding_yaml_precedence_over_store` — verifies YAML wins when both loaders provided
   - `test_init_scaffolding_yaml_missing_key_uses_fallback` — verifies partial YAML data leaves missing keys out of cache
   - `test_init_scaffolding_yaml_none_is_noop` — verifies None scaffolding returns no-op
   - Fixed existing `test_scaffolding_cache_populated` to pass `store=store` keyword arg

### Test Results
- New tests: 4 passed, 0 failed
- Targeted suite: 54 passed (same baseline)
- Full suite: 388 passed (20 pre-existing failures unchanged, zero regressions)
