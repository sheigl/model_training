# Story: Metrics + Trace Template-Version Recording

## User Story
As a pipeline analyst, I want every metrics run document and every generation trace document to record which template version (and validator template version) was used, so that I can correlate pass-rate regressions or improvements with specific template versions and roll back bad versions confidently.

## Context
Requirement #6 and #7 from the user:
- **Metrics**: `synthetic_metrics.generator_runs` should record which template version was used during the run. The `ValidationMetrics` summary should include template version info.
- **Traces**: `synthetic_metrics.generation_traces` should record the template version used. The `GenerationTrace` dataclass should carry `template_version` (and possibly `validator_template_version`).

Today:
- **Legacy `models.py`**: `ValidationMetrics.summary()` returns a dict with `generation_model`, `validation_model`, totals, `by_category`, `by_template`. `GenerationTrace` dataclass has `source_template` (the template_id) but no version. `save_to_mongo()` writes `{"_id", "run_id", "generator_name", "updated_at", "metrics": summary()}`.
- **TrainForge `models.py`**: `ValidationMetrics` (Pydantic) has the same shape. `GenerationTrace` (Pydantic) has `source_template` but no version.
- `BaseGenerator._process_item` (legacy) creates a `GenerationTrace` per template iteration with `source_template=template.template_id`. The template object is a `TemplateConfig` — after Story 042 it may carry a version (the plan should add a `version` field to `TemplateConfig`).

This story adds `template_version` and `validator_template_version` to both `GenerationTrace` and `ValidationMetrics` (in both codebases), populates them during generation, and persists them to MongoDB.

## Acceptance Criteria
- [ ] Legacy `common.TemplateConfig` gains an optional `version: int | None = None` field (default None for backward compat with hardcoded templates that have no version).
- [ ] TrainForge `domain.TemplateConfig` gains the same optional `version` field.
- [ ] `TemplateStore.to_template_config()` populates `version` from the loaded doc's `version` field; hardcoded fallback templates have `version=None`.
- [ ] Legacy `models.GenerationTrace` dataclass gains `template_version: int | None = None` and `validator_template_version: int | None = None`.
- [ ] TrainForge `models.GenerationTrace` Pydantic model gains the same two fields.
- [ ] Legacy `base_generator._process_item` populates `trace.template_version = template.version` when creating a `GenerationTrace`. The validator version is populated from the resolved validator template version (per the hybrid lookup in Story 042).
- [ ] TrainForge `generator.py generate()` populates the same fields on its `GenerationTrace`.
- [ ] Legacy `models.ValidationMetrics` gains a `template_versions: dict[str, int]` field mapping `template_id` → version used for this run, populated as templates are selected. `summary()` includes `template_versions` in the output dict.
- [ ] TrainForge `models.ValidationMetrics` gains the same field and includes it in `summary()`.
- [ ] `synthetic_metrics.generator_runs` documents now include a `template_versions` field in the `metrics` sub-document.
- [ ] `synthetic_metrics.generation_traces` documents now include `template_version` and `validator_template_version` top-level fields.
- [ ] Backward compatibility: existing trace/metrics docs in MongoDB are untouched (new fields are additive). Generators with `version=None` (hardcoded fallback) write `null` — queries filtering on version must handle null.
- [ ] Unit tests cover: trace carries correct version when loaded from store, trace carries null when using hardcoded fallback, metrics summary includes template_versions, and the MongoDB-persisted shape includes the new fields.

## Technical Plan
**Plan file**: `plans/story-045-metrics-trace-template-version-plan.md` ✅ Created

The technical design, architecture decisions, and task breakdown for this story
are in the companion plan file linked above.

## Dependencies
- Story 040 (Template Store — provides version numbers)
- Story 042 (Legacy CLI template loading — populates `TemplateConfig.version`)
- Story 043 (TrainForge template loading — populates `TemplateConfig.version` in TrainForge)

## Priority: Medium

## Notes
- **`TemplateConfig.version` is the key enabler**: Without a `version` field on `TemplateConfig`, the trace/metrics code has no way to know which version was used. This story adds it; the integration stories (042, 043) populate it. Coordinate so the field exists before the integration stories populate it (or accept `None` during the transition).
- **Per-run vs per-template version**: A run may use multiple templates per generator (e.g. combo_query has 4 template_ids, each potentially at a different version if overrides differ). `template_versions` should be a dict keyed by `template_id`, not a single int. The plan should confirm this shape.
- **Validator version**: The validator template version may differ from the generation template version (hybrid granularity). `validator_template_version` is recorded separately on the trace. For metrics, a `validator_template_versions` dict may also be needed — the plan should decide.
- **MongoDB query impact**: Analysts will want to query "show me all traces where combo_query used version 2". A compound index on `(category, template_version)` or `(run_id, template_version)` on `generation_traces` would help. The plan should specify indexes.
- **Both codebases**: This story touches legacy `models.py` AND TrainForge `models.py`. They are separate files with parallel structures. The plan should keep the field names identical across both for cross-codebase analytics.