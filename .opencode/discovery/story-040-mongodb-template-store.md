# Story: MongoDB Versioned Template Store

## User Story
As a pipeline maintainer, I want a MongoDB-backed versioned template store with a `TemplateStore` class (CRUD + version resolution + latest lookup), so that both the legacy CLI and TrainForge can load generation/validator templates from a single shared, version-controlled source instead of hardcoded Python constants and YAML files.

## Context
Today, templates live in two parallel places:
- **Legacy CLI** (`training_data/generate_synthetic_data/`): `constants.py` holds shared scaffolding blocks (`SYSTEM_MESSAGE`, `MTG_NOTATION_LEGEND`, `REQUIREMENTS_BASE`, `OUTPUT_FORMAT`, `CARD_COMPARISON_INSTRUCTIONS`, `VALIDATION_CHECKLIST`, `VALIDATION_SCORING_GUIDE`, `RULE_*_VALIDATION`); `common.py` defines `TemplateConfig` + ~20 `build_*_prompt()` functions; each generator file (e.g. `generate_combo_queries.py`) defines a class-level `TEMPLATES: ClassVar[list[TemplateConfig]]` with `template_id`, `task_instruction`, `weight`, `validation_rules`. The shared validator prompt is built by `query_model.py` `__build_qa_validation_prompt()`.
- **TrainForge** (`trainforge/src/trainforge/`): `domains/mtg/templates.yaml` holds `system_message`, `notation_legend`, and 27 categories each with templates (`instruction`, `weight`, `validation_rules`). `DomainPlugin.get_templates_for_category()` parses this YAML into `TemplateConfig` objects.

This story creates the **foundation**: a single MongoDB collection holding one document per `(generator, template_id, template_type, version)` with `is_latest` flagging, plus a `TemplateStore` Python class providing CRUD, version resolution, latest lookup, and a seed/import entry point. No existing code is modified yet — this is purely additive infrastructure.

## MongoDB Document Shape
```
{
  generator: "combo_query",        # generator/category identifier
  template_id: "how_does_it_work", # template identifier
  template_type: "generation",     # "generation" | "validator"
  version: 1,                      # integer version number
  yaml_content: "...",             # the YAML template body (instruction + weight + validation_rules + scaffolding)
  created_at: "ISO timestamp",
  is_latest: true                  # boolean — exactly one doc per (generator, template_id, template_type) has this=true
}
```

## Acceptance Criteria
- [ ] A new MongoDB collection (e.g. `synthetic_metrics.templates` or `synthetic_queries.templates`) is designated for template storage, shared by both codebases.
- [ ] A `TemplateStore` class exists in a shared location importable by both the legacy CLI and TrainForge (e.g. `training_data/generate_synthetic_data/template_store.py` with TrainForge re-exporting, OR a new shared module). Decision deferred to the technical plan.
- [ ] `TemplateStore` provides: `get_latest(generator, template_id, template_type)`, `get_version(generator, template_id, template_type, version)`, `list_versions(generator, template_id, template_type)`, `upsert(generator, template_id, template_type, yaml_content)` (auto-increments version + flips `is_latest`), `delete_version(...)`, and `seed(templates_dict)` (idempotent bulk import).
- [ ] `upsert` enforces the invariant: exactly one doc per `(generator, template_id, template_type)` has `is_latest=true`. Bumping a version creates a new doc and flips the previous latest to `is_latest=false` atomically (or via a small transaction / findAndModify sequence).
- [ ] Compound unique index on `(generator, template_id, template_type, version)` is created idempotently.
- [ ] Index on `(generator, template_id, template_type, is_latest)` for fast latest-lookup.
- [ ] `TemplateStore` is constructed from a MongoDB collection (pymongo) — no hard dependency on `MTGDataAccess` or `DomainPlugin` so it is reusable.
- [ ] `TemplateStore` exposes a `to_template_config(doc) -> TemplateConfig` helper that parses `yaml_content` into the legacy `common.TemplateConfig` shape (and/or the TrainForge `domain.TemplateConfig` shape — see plan for unification).
- [ ] Unit tests cover: upsert new, upsert bump version (old flips to latest=false), get_latest, get_version, list_versions, idempotent seed, index creation, and the `is_latest` invariant under repeated upserts.
- [ ] No existing production code is modified — this story is purely additive.

## Technical Plan
**Plan file**: `plans/story-040-mongodb-template-store-plan.md` ✅ Created

The technical design, architecture decisions, and task breakdown for this story
are in the companion plan file linked above.

## Dependencies
- None (foundation story)

## Priority: High

## Notes
- **Shared collection**: Both codebases must read the SAME collection so templates are portable. The plan should decide the exact db.collection name and whether `TemplateStore` lives in a shared package or is duplicated with a shared interface.
- **TemplateConfig unification**: The legacy `common.TemplateConfig` (frozen dataclass) and TrainForge `domain.TemplateConfig` (plain class) have identical fields. The plan should decide whether to introduce one canonical `TemplateConfig` or keep both and have `TemplateStore` return a neutral dict.
- **yaml_content field**: Stores the template body as YAML text (instruction, weight, validation_rules, min/max answer length). For shared scaffolding blocks (SYSTEM_MESSAGE, MTG_NOTATION_LEGEND, REQUIREMENTS_BASE), a special `generator="__shared__"` namespace with `template_id` per block is recommended — see plan.
- **Validator templates**: `template_type="validator"` docs hold the shared validator prompt body (currently built by `query_model.py __build_qa_validation_prompt`). Per-generator validator overrides use the generator's own `generator` field.
- **Idempotency**: `seed()` must be re-runnable without duplicating docs (match on `(generator, template_id, template_type, version)` and skip if exists).