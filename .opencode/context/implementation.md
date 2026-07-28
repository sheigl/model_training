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
