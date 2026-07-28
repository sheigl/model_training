# Story: CLI Per-Generator Template Version Override Flags

## User Story
As a pipeline operator, I want per-generator `--<generator-slug>-template-version N` CLI flags in `main.py`, so that I can pin a specific generator to an older or newer template version for A/B testing or rollback without affecting other generators.

## Context
Requirement #3 from the user: each generator gets its own `--<generator-slug>-template-version N` flag. When provided, that generator uses version N instead of the latest. This builds on Story 042 (legacy CLI template loading), which added `template_version_override` plumbing to `BaseGenerator`. This story adds the CLI surface in `main.py` and threads the selected version through to each generator constructor.

`main.py` currently has ~27 `--<category>` count flags (e.g. `--combo-queries`, `--card-search`). Each generator is instantiated in a block that passes `models`, `validation_pct`, `target_count`, `save_item`, `metrics`, `dry_run`. This story adds a parallel set of `--<slug>-template-version` flags and passes them as `template_version_override` to each generator.

## Acceptance Criteria
- [ ] `main.py` argparse defines one `--<slug>-template-version` flag per generator, where `<slug>` matches the existing count flag slug (e.g. `--combo-queries-template-version`, `--card-search-template-version`, `--rule-explanations-template-version`). Default value: `None` (use latest).
- [ ] The flag accepts an integer. Invalid integers are rejected by argparse (`type=int`).
- [ ] Each generator instantiation block in `main.py` passes `template_version_override=args.<slug>_template_version` to the generator constructor (alongside the existing `template_store` from Story 042).
- [ ] When a version override is provided but that version does not exist in the store, the generator logs a clear warning and falls back to latest (per Story 042 fallback chain). The run does NOT crash.
- [ ] When a version override is provided but no `template_store` is configured (MongoDB unavailable), the generator logs a warning that the override is ignored and uses the class-level `TEMPLATES` constant.
- [ ] A `--list-template-versions` flag prints all available `(generator, template_id, template_type, version, is_latest)` tuples from the store and exits, for operator visibility.
- [ ] The `--help` output groups the version flags under a clear help section so operators can discover them.
- [ ] A dry-run (`--dry-run`) with a version override prints which version each generator will use without generating.
- [ ] Unit tests cover: flag parsing for a representative generator, threading of override to constructor, fallback when version missing, fallback when store absent, and `--list-template-versions` output.

## Technical Plan
**Plan file**: `plans/story-044-cli-version-override-flags-plan.md` ✅ Created

The technical design, architecture decisions, and task breakdown for this story
are in the companion plan file linked above.

## Dependencies
- Story 040 (Template Store)
- Story 042 (Legacy CLI template loading — provides the `template_version_override` constructor param)

## Priority: Medium

## Notes
- **Slug derivation**: The slug must be deterministic from the generator. Recommendation: derive from `get_source_category()` (e.g. `combo_query` → `--combo-query-template-version`) or from the existing count flag name. The plan should produce the exact mapping table for all 27 generators to avoid ambiguity.
- **Flag explosion**: 27 new flags is a lot. The plan should consider a single `--template-versions` JSON flag as an alternative (e.g. `--template-versions '{"combo_query": 2, "rule_explanation": 3}'`), OR keep the per-generator flags for discoverability. User explicitly requested per-generator flags, so keep them, but the plan may add the JSON form as a convenience alias.
- **Validator version override**: The user's requirement #4 mentions validator template overrides. This story focuses on generation template versions. A `--<slug>-validator-template-version` flag could be added here or in a follow-up. The plan should decide; recommendation: add it here for completeness since the plumbing is the same.
- **No TrainForge UI equivalent**: This story is legacy-CLI-only. TrainForge UI version controls are out of scope (noted in Story 043).