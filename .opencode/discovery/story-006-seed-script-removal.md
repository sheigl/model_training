# Story: Seed Script Removal and Migration Helper

## User Story
As a project maintainer, I want the MongoDB seed script (`seed_templates.py`) removed or repurposed into a one-time migration helper that extracts current templates into YAML files, so that new contributors don't accidentally try to seed an empty MongoDB collection.

## Context
`seed_templates.py` currently:
1. Imports all 27 generator classes and reads their `TEMPLATES` constants
2. Extracts shared scaffolding blocks from `constants.py`
3. Builds validator templates from public helper functions in `query_model.py`
4. Calls `TemplateStore.seed()` to insert everything into MongoDB

Since the MongoDB collection is empty and we're moving to YAML files, this script's purpose is now reversed: instead of seeding MongoDB, it should seed YAML files. The script can either be removed entirely (since the YAML files will be committed directly) or repurposed as a one-time migration tool that generates the initial YAML files from the current Python constants.

## Acceptance Criteria
- [ ] Option A chosen and implemented: either the script is removed AND YAML files are committed directly, OR the script is repurposed to generate YAML files from Python constants
- [ ] If repurposed: `python -m training_data.generate_synthetic_data.seed_templates --to-yaml` generates all YAML files in `templates/`
- [ ] The generated YAML files match exactly what would be produced by manual extraction (same content, same structure)
- [ ] `test_seed_templates.py` is updated or replaced with tests for the new behavior
- [ ] No references to `TemplateStore.seed()` remain in the production codebase
- [ ] If script is removed: a comment in `constants.py` or a README notes that templates are now YAML files

## Technical Plan
**Plan file**: `plans/story-006-seed-script-removal-plan.md`

The technical design, architecture decisions, and task breakdown for this story
are in the companion plan file linked above.

## Dependencies
- Story 001 (YAML structure must be designed before migration helper can generate files)

## Priority: Medium

## Notes
- Recommendation: repurpose the script rather than delete it. The existing extraction logic (`extract_shared_blocks`, `extract_legacy`, `extract_validators`) is valuable and tests cover it well. A `--to-yaml` flag lets contributors regenerate YAML if they modify Python constants.
- The `GENERATOR_REGISTRY` in `seed_templates.py` should be kept in sync with `main.py`'s `GENERATOR_FLAGS`.
