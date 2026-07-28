# Story: Template Loading from YAML Replacing MongoDB Path

## User Story
As a generator running in the legacy CLI, I want templates loaded directly from local YAML files instead of querying MongoDB, so that generation works without any database connection and template changes take effect immediately on restart.

## Context
Currently `BaseGenerator._load_templates_from_store()` checks `self._template_store` (a `TemplateStore` instance) first, then falls back to the class-level `TEMPLATES` constant. The store lookup does a MongoDB query per template_id and parses YAML from the doc. After this story, the same fallback chain should read from YAML files instead of MongoDB.

The key invariant: when `template_store=None` (the default), behavior must be byte-identical to today — class-level `TEMPLATES` are used. When a YAML loader is provided, it replaces the MongoDB path entirely.

## Acceptance Criteria
- [ ] `BaseGenerator.__init__` accepts an optional `yaml_loader` parameter (replacing or in addition to `template_store`)
- [ ] `_load_templates_from_store()` is renamed to `_load_templates_from_source()` and reads from the YAML loader when available
- [ ] When the YAML loader returns a template, it is converted to `TemplateConfig` using the same logic as `TemplateStore.to_template_config()` (reuse or extract that method)
- [ ] Per-template fallback still works: if the YAML file has no entry for a given `template_id`, the class constant is used
- [ ] When neither YAML loader nor class constants have templates, `ValueError` is raised (same as today)
- [ ] The `version` field on `TemplateConfig` is set to `"1"` (or a stable string) when loaded from YAML, so trace recording continues to work
- [ ] `_resolve_validator_version()` is simplified — since YAML has no versioning, it returns `None` or `"1"` consistently
- [ ] All existing tests in `test_template_loading.py` and `test_base_generator.py` pass with the new loader path (MongoDB-mock tests can be removed or converted to YAML-mock tests)

## Technical Plan
**Plan file**: `plans/story-002-yaml-template-loading-plan.md`

The technical design, architecture decisions, and task breakdown for this story
are in the companion plan file linked above.

## Dependencies
- Story 001 (YAML template file structure and loader module must exist first)

## Priority: High

## Notes
- The `template_store` parameter on `BaseGenerator.__init__` should be deprecated but kept for backward compat during a transition period — or removed entirely if no external callers pass it.
- Version override flags (`--combo-queries-template-version`) become no-ops since YAML has no versioning; they can be removed in the CLI cleanup story (005).
