# Story: CLI Cleanup — Remove MongoDB/Version Flags, Add YAML Path Flag

## User Story
As a CLI user, I want a simpler command-line interface that removes all MongoDB template store flags and version override flags (since YAML has no versioning), so that the CLI is easier to use and doesn't require an unavailable MongoDB connection just for templates.

## Context
The current CLI (`main.py`) has these template-related flags:
- `--mongo-uri`, `--mongo-user`, `--mongo-pass` — still needed for source data and output, but NOT for templates
- `--combo-queries-template-version N` through all 27 generators (54 flags total)
- `--template-versions JSON` — bulk version override
- `--list-template-versions` — print store contents
- `--dry-run` prints resolved template versions

After migration, templates come from local YAML files. The only new flag needed is `--templates-dir` (defaulting to the package's `templates/` directory). All version-related flags become irrelevant.

## Acceptance Criteria
- [ ] A new `--templates-dir` flag is added to the parser, defaulting to the package-relative path `training_data/generate_synthetic_data/templates/`
- [ ] All 27 per-generator `--<slug>-template-version` flags are removed from the parser
- [ ] All 27 per-generator `--<slug>-validator-template-version` flags are removed from the parser
- [ ] The `--template-versions` JSON flag is removed
- [ ] The `--list-template-versions` flag is removed
- [ ] `TemplateStore` construction and `init_scaffolding(store)` call are removed from `main.py`
- [ ] A `YamlTemplateLoader` instance is created in `main.py` and passed to each generator constructor as `yaml_loader=`
- [ ] Generator instantiations no longer pass `template_store=`, `template_version_override=`, or `validator_template_version_override=`
- [ ] The dry-run mode still works but no longer prints version resolution info (or prints a simplified message)
- [ ] All 27 generator classes accept `yaml_loader` in their `**kwargs` (they already pass unknown kwargs to `super().__init__`)
- [ ] Tests for CLI flag parsing (`test_cli_version_flags.py`) are removed or replaced with tests for the new `--templates-dir` flag

## Technical Plan
**Plan file**: `plans/story-005-cli-cleanup-plan.md`

The technical design, architecture decisions, and task breakdown for this story
are in the companion plan file linked above.

## Dependencies
- Story 002 (YAML template loading path must work before CLI can use it)
- Story 003 (scaffolding loaded from YAML)
- Story 004 (validators loaded from YAML)

## Priority: High

## Notes
- `--mongo-uri`, `--mongo-user`, `--mongo-pass` are **kept** — they're still needed for source data (cards, combos, etc.) and output collection. Only the template-store-specific MongoDB connection is removed.
- The `GENERATOR_FLAGS` list in `main.py` can be simplified to remove the `dest` field used for version flag generation, or kept for other purposes.
- If any external scripts or CI pipelines reference the removed flags, they should be updated separately.
