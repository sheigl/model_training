# Story: Seed/Import Script for MongoDB Template Store

## User Story
As a pipeline maintainer, I want a one-time idempotent seed script that populates the MongoDB template store from all existing hardcoded template sources (legacy `constants.py`, `common.py` build functions, per-generator `TEMPLATES` class vars, and TrainForge `templates.yaml`), so that the versioned store starts populated with version 1 of every template and the existing pipelines can switch to reading from the store without losing any current template content.

## Context
Story 040 creates the `TemplateStore` with a `seed()` entry point. This story is the **operational script** that actually extracts every template from the current hardcoded sources and writes them into the store as version 1 docs. Without this, the store is empty and the integration stories (042, 043) cannot fall back gracefully — they would have nothing to load.

Sources to extract:
1. **Legacy `constants.py`** — shared scaffolding blocks: `SYSTEM_MESSAGE`, `OUTPUT_FORMAT`, `REQUIREMENTS_BASE` (list → joined), `MTG_NOTATION_LEGEND`, `CARD_COMPARISON_INSTRUCTIONS`, `VALIDATION_CHECKLIST`, `VALIDATION_SCORING_GUIDE`, `RULE_INTERACTION_VALIDATION`, `RULE_EXPLANATION_VALIDATION`, `COMBO_QUESTION_TEMPLATES`, `RULE_INTERACTION_TEMPLATES`, `RULE_EXPLANATION_TEMPLATES`.
2. **Legacy `common.py`** — the ~20 `build_*_prompt()` functions each embed a prompt scaffold. These become `template_type="generation"` docs keyed by generator category (e.g. `build_commander_prompt` → `generator="commander_knowledge"`).
3. **Legacy per-generator files** — each generator's `TEMPLATES: ClassVar[list[TemplateConfig]]` (e.g. `generate_combo_queries.py` has 4 templates: `how_does_it_work`, `what_do_i_need`, `why_does_this_work`, `what_is_the_result`). These become `template_type="generation"` docs.
4. **Legacy `query_model.py`** — `__build_qa_validation_prompt()` body becomes the shared validator template: `generator="__shared__"`, `template_id="qa_validation"`, `template_type="validator"`. `__build_card_validation_prompt()` becomes `generator="comparison"`, `template_id="card_validation"`, `template_type="validator"`.
5. **TrainForge `templates.yaml`** — `system_message`, `notation_legend`, and all 27 categories with their templates. These should map to the SAME `(generator, template_id)` keys as the legacy sources so the store is unified (not duplicated). Where TrainForge and legacy differ, the legacy version wins (legacy is the active system per CHANGELOG).

## Acceptance Criteria
- [ ] A script exists (e.g. `training_data/generate_synthetic_data/seed_templates.py`) runnable as `python -m training_data.generate_synthetic_data.seed_templates` that connects to MongoDB and populates the template store.
- [ ] The script extracts all shared scaffolding blocks from `constants.py` and writes them as `generator="__shared__"` docs with appropriate `template_id` (e.g. `system_message`, `notation_legend`, `requirements_base`, `output_format`, `card_comparison_instructions`, `validation_checklist`, `validation_scoring_guide`).
- [ ] The script extracts every per-generator `TEMPLATES` class var across all 27 generator files and writes one `template_type="generation"` doc per `(generator, template_id)` with `version=1`, `is_latest=true`.
- [ ] The script extracts the shared validator prompt body from `query_model.py __build_qa_validation_prompt` and writes it as `generator="__shared__"`, `template_id="qa_validation"`, `template_type="validator"`.
- [ ] The script extracts the card-comparison validator prompt from `query_model.py __build_card_validation_prompt` and writes it as `generator="comparison"`, `template_id="card_validation"`, `template_type="validator"`.
- [ ] The script reconciles TrainForge `templates.yaml` content against the legacy sources: where `(generator, template_id)` already exists from legacy extraction, the legacy content is kept (no overwrite); where TrainForge has a template the legacy lacks, it is added.
- [ ] The script is **idempotent**: re-running it does not create duplicate docs and does not flip `is_latest`. It checks for existing `(generator, template_id, template_type, version=1)` docs and skips them.
- [ ] The script prints a summary: how many docs inserted, how many skipped (already existed), grouped by `template_type`.
- [ ] The script accepts `--dry-run` to print what would be inserted without writing.
- [ ] The script accepts `--mongo-uri`, `--mongo-user`, `--mongo-pass` flags consistent with `main.py`.
- [ ] Unit tests verify the extraction logic produces the expected set of `(generator, template_id, template_type)` keys (no duplicates, all 27 generators covered, shared blocks present).

## Technical Plan
**Plan file**: `plans/story-041-seed-import-script-plan.md` ✅ Created

The technical design, architecture decisions, and task breakdown for this story
are in the companion plan file linked above.

## Dependencies
- Story 040 (MongoDB Template Store — needs `TemplateStore.seed()`)

## Priority: High

## Notes
- **Extraction approach**: The plan should decide whether to (a) import the generator modules and introspect their `TEMPLATES` class var, or (b) parse the source files. Introspection (a) is preferred — it reuses the live `TemplateConfig` objects and avoids drift.
- **`build_*_prompt` functions**: These embed scaffolding inline (e.g. `build_commander_prompt` hardcodes the Commander rules context). The plan should decide whether to store the full prompt scaffold or just the variable parts. Recommendation: store the full scaffold as `yaml_content` so the integration story can swap the whole prompt body.
- **`REQUIREMENTS_BASE` is a list**: Store as a YAML list inside `yaml_content` so the integration can re-join with `\n`.
- **Validation rules**: Legacy stores these as multi-line strings (e.g. `COMBO_HOW_VALIDATION`) split by `\n` into `validation_rules`. TrainForge stores them as YAML lists. The seed should normalize to YAML lists in `yaml_content`.
- **Reconciliation conflict policy**: Legacy wins because it is the active system. The script should log any conflicts where TrainForge and legacy differ so a human can review later.