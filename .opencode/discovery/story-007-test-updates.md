# Story: Test Suite Updates for YAML Template System

## User Story
As a developer, I want all tests updated to work with the new YAML-based template system instead of MongoDB mocks, so that the test suite accurately verifies the production code path and no dead test coverage remains.

## Context
The following test files reference `TemplateStore`, MongoDB mocks, or seed script behavior that will change:
- `test_template_store.py` — tests MongoDB store CRUD; most become obsolete
- `test_cli_version_flags.py` — tests version override flags that are being removed
- `test_seed_templates.py` — tests seed-to-MongoDB behavior
- `test_template_loading.py` — tests store-present and store-absent paths; needs YAML-loader equivalents
- `test_base_generator.py` — may reference template_store in generator construction

The migration must ensure 0 new test failures and preserve coverage of the fallback chain (YAML present → YAML absent → class constants).

## Acceptance Criteria
- [ ] `test_template_store.py` is removed or reduced to only test the `to_template_config()` static method (which is reused by the YAML loader)
- [ ] `test_cli_version_flags.py` is replaced with tests for the new `--templates-dir` flag and removal of version flags
- [ ] `test_seed_templates.py` is updated to test the `--to-yaml` path (if repurposed) or removed
- [ ] `test_template_loading.py` is updated: MongoDB-mock tests replaced with YAML-loader mock tests; fallback-to-class-constants tests preserved
- [ ] `test_base_generator.py` is checked and updated if it passes `template_store=` to constructors
- [ ] All existing tests pass after the migration (`pytest training_data/generate_synthetic_data/ -v`)
- [ ] New tests cover: YAML loader loads correct files, missing template_id falls back to class constant, malformed YAML raises descriptive error, scaffolding cache populated from YAML

## Technical Plan
**Plan file**: `plans/story-007-test-updates-plan.md`

The technical design, architecture decisions, and task breakdown for this story
are in the companion plan file linked above.

## Dependencies
- Story 001 (YAML loader module)
- Story 002 (YAML template loading path)
- Story 005 (CLI cleanup — affects which flags are tested)

## Priority: High

## Notes
- The existing test suite has 341+ tests with 20 pre-existing failures. This story must not increase the failure count.
- Tests that verify MongoDB-specific behavior (indexes, upsert idempotency, delete_version promotion) can be deleted — they're no longer relevant.
- The `TemplateStore.to_template_config()` method is a pure function that parses a dict into `TemplateConfig`; it should still be tested even after MongoDB removal since the YAML loader reuses it.
