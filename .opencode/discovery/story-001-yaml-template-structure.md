# Story: YAML Template File Structure, Directory Layout, and Loader Module

## User Story
As a developer maintaining the legacy CLI, I want generation and validator templates stored as local YAML files instead of MongoDB documents, so that template editing is straightforward (git-tracked, diffable) with no database dependency.

## Context
The current system stores all 27 generator templates + shared scaffolding blocks + validator prompts in a MongoDB `templates` collection. The collection is currently empty — nothing has ever been seeded. Every read path goes through `TemplateStore.get_latest()` which does a MongoDB query, then parses the YAML string via `yaml.safe_load(doc["yaml_content"])`.

The migration goal is to replace that indirection with direct YAML file reads from a local directory, while keeping class-level `TEMPLATES` constants as fallback for backward compatibility.

## Acceptance Criteria
- [ ] A new `templates/` directory exists at `training_data/generate_synthetic_data/templates/`
- [ ] One YAML file per generator category (e.g. `combo_query.yaml`, `card_search.yaml`) containing all generation templates for that category
- [ ] A single `shared.yaml` file containing scaffolding blocks (`system_message`, `notation_legend`, `requirements_base`, `output_format`, `card_comparison_instructions`) and shared validator prompts (`qa_validation`)
- [ ] A per-generator validator override file pattern (e.g. `comparison_validator.yaml`) for generator-specific validators like card comparison
- [ ] Each YAML entry uses the schema: `template_id`, `instruction` (or `task_instruction` alias), `weight`, `validation_rules`, `min_answer_length`, `max_answer_length`
- [ ] A new module `yaml_template_loader.py` provides a `YamlTemplateLoader` class with methods mirroring the read surface of `TemplateStore`: `get_latest(generator, template_id, template_type) -> dict | None` and `list_versions(...)` returning empty
- [ ] The loader resolves file paths relative to the package root (`training_data/generate_synthetic_data/templates/`)
- [ ] All 27 generator categories have a corresponding YAML file with content extracted from their current class-level `TEMPLATES` constants
- [ ] `shared.yaml` contains all 5 generation scaffolding blocks and 3 validator scaffolding entries (qa_validation, validation_checklist, validation_scoring_guide)
- [ ] The loader module has unit tests covering: load existing files, missing file returns None, malformed YAML raises descriptive error, schema field aliases work

## Technical Plan
**Plan file**: `plans/story-001-yaml-template-structure-plan.md`

The technical design, architecture decisions, and task breakdown for this story
are in the companion plan file linked above.

## Dependencies
- None — this is the foundational story that all others depend on

## Priority: High

## Notes
- The YAML schema intentionally mirrors the MongoDB `yaml_content` body shape so the existing `TemplateStore.to_template_config()` static method can be reused with minimal changes (it just needs to accept a dict instead of a MongoDB doc).
- Version tracking (`template_version` field on `GenerationTrace`) will record `"1"` or the git SHA — no multi-version support needed since YAML is the single source of truth.
- TrainForge's `templates.yaml` is a separate system and must not be conflated with this one.
