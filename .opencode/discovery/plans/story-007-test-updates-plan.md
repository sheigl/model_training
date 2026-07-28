# Technical Plan: Test Suite Updates for YAML Template System

## Overview
Update the test suite to work with the new YAML-based template system. Remove obsolete MongoDB-specific tests, add YAML loader tests, and ensure zero new failures.

## Architecture Decisions

### Decision 1: Keep `to_template_config()` tests
`TemplateStore.to_template_config()` is a pure static method reused by the YAML loader. It should remain tested even after MongoDB removal since it's part of the public API surface.

### Decision 2: Mock filesystem for YAML loader tests
Use `pytest`'s `tmp_path` fixture and `monkeypatch` to create temporary YAML files, avoiding dependency on actual filesystem state during tests.

### Decision 3: Preserve fallback chain coverage
The critical behavior to test is the fallback chain: YAML present → YAML absent → class constants. Tests must verify all three paths.

## Files to Modify

### Removed files
- `tests/test_template_store.py` — remove (MongoDB CRUD tests are obsolete; keep only `to_template_config` as a standalone test if desired)
- `tests/test_cli_version_flags.py` — remove (flags no longer exist)
- `tests/test_seed_templates.py` — replace with new version for YAML generation

### Modified files
- `tests/test_template_loading.py` — replace MongoDB mock tests with YAML loader tests
- `tests/test_base_generator.py` — update constructor calls to pass `yaml_loader=` instead of `template_store=`
- New: `tests/test_yaml_loader.py` — dedicated tests for the new loader module

### New files
- `tests/test_cli_templates_dir.py` — test the new `--templates-dir` flag
- `tests/test_seed_templates_yaml.py` — test YAML generation from Python constants

## Task Breakdown

### Task 1: Assess existing test failures
Before making changes, run the current suite to establish baseline:
```bash
pytest training_data/generate_synthetic_data/ -v --tb=no -q
```
Document which 20 tests are pre-existing failures (must not increase this count).

### Task 2: Create `test_yaml_loader.py`
Test the new `YamlTemplateLoader` class:
- `test_load_generator_templates()` — loads templates for a known generator slug
- `test_load_shared_scaffolding()` — loads scaffolding from shared.yaml
- `test_load_validator()` — loads qa_validation and card_comparison validators
- `test_missing_template_id_returns_none()` — non-existent key returns None (not error)
- `test_templates_dir_not_found_raises_descriptive_error()` — missing directory raises clear exception
- `test_malformed_yaml_raises_descriptive_error()` — bad YAML raises with file path in message
- `test_to_template_config_reused()` — verify the static method produces correct TemplateConfig

### Task 3: Update `test_template_loading.py`
Replace MongoDB-mock tests:
- Old: mock `TemplateStore.get_template()` → return dict
- New: use `YamlTemplateLoader` with tmp_path fixtures containing YAML files

Preserve:
- Fallback-to-class-constants test (still valid — when no YAML and no loader)
- Test that unknown template_id falls back gracefully

### Task 4: Update `test_base_generator.py`
Check for any constructor calls passing `template_store=`. Replace with `yaml_loader=`. Verify the generator still selects templates correctly via `_load_templates_from_store()` (now reads from YAML).

### Task 5: Create `test_cli_templates_dir.py`
Test the new CLI flag:
- `test_templates_dir_flag_sets_path()` — verify argparse handles `--templates-dir /some/path`
- `test_default_templates_dir_resolves_to_package_path()` — verify default behavior
- `test_version_flags_removed()` — verify old flags are not recognized

### Task 6: Update `test_seed_templates.py` → `test_seed_templates_yaml.py`
Test the repurposed script:
- `test_extract_shared_blocks_still_works()` — existing extraction logic unchanged
- `test_generate_yaml_files_creates_expected_files()` — new YAML generation
- `test_yaml_content_matches_manual_extraction()` — round-trip verification

### Task 7: Run full suite and verify
```bash
pytest training_data/generate_synthetic_data/ -v
```
Verify: same 20 pre-existing failures, zero new failures.

## Testing Strategy
- Use `tmp_path` fixture for all filesystem-dependent tests
- Use `monkeypatch.syspath_prepend` if needed to control import paths
- Mock `TemplateStore.to_template_config()` calls in YAML loader tests to verify it's being called correctly
- Integration test: construct a real generator with a real YAML loader and tmp_path templates, verify template selection works

## Risk Assessment
- **Medium risk**: Test file restructuring is straightforward but numerous. The key risk is accidentally breaking a test that was passing (reducing from 341+ passing). Careful baseline measurement before changes is essential.
- **Low risk**: New tests for YAML loader are isolated and use mocks/tmp_path, so they won't interfere with existing tests.
