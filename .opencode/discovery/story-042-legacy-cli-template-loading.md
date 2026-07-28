# Story: Legacy CLI Template Loading Integration

## User Story
As a pipeline maintainer, I want the legacy CLI's `BaseGenerator`, `common.py` build functions, and `query_model.py` validator to load templates from the MongoDB `TemplateStore` instead of hardcoded Python constants, so that template changes can be made by bumping a version in MongoDB without redeploying code — while falling back to the current hardcoded behavior if the store is empty or unavailable.

## Context
The legacy CLI (`training_data/generate_synthetic_data/`) is the ACTIVE system. Today:
- `BaseGenerator.select_templates()` reads `self.TEMPLATES` (class-level `ClassVar[list[TemplateConfig]]`).
- Each generator's `build_prompt()` calls `common.build_*_prompt()` functions which embed scaffolding from `constants.py` (`SYSTEM_MESSAGE`, `MTG_NOTATION_LEGEND`, `REQUIREMENTS_BASE`, `OUTPUT_FORMAT`, etc.) plus the template's `task_instruction`.
- `query_model.py __build_qa_validation_prompt()` builds the shared validator prompt from `constants.SYSTEM_MESSAGE`, `MTG_NOTATION_LEGEND`, and inline verification blocks.

After Stories 040 + 041, the MongoDB store holds versioned docs for every template and scaffolding block. This story wires the legacy CLI to READ from the store at generator-construction time, with a hard fallback to the existing hardcoded constants if the store is unavailable/empty (backward compatibility).

## Acceptance Criteria
- [ ] `BaseGenerator.__init__` accepts an optional `template_store: TemplateStore | None` and an optional `template_version_override: int | None` per-generator.
- [ ] When a `template_store` is provided AND a doc exists for `(generator=get_source_category(), template_id, template_type="generation")`, `select_templates()` returns `TemplateConfig` objects built from the store docs (using `store.to_template_config()`). When the store is None or returns no docs, it falls back to the class-level `TEMPLATES` constant (current behavior).
- [ ] When `template_version_override` is set for a generator, `select_templates()` calls `store.get_version(generator, template_id, "generation", version=override)` instead of `get_latest`. If that version doesn't exist, fall back to latest, then to the class constant, logging a warning.
- [ ] `common.py` `build_*_prompt()` functions accept an optional `scaffolding: dict | None` parameter (or read from a module-level store handle) so shared blocks (`SYSTEM_MESSAGE`, `MTG_NOTATION_LEGEND`, `REQUIREMENTS_BASE`, `OUTPUT_FORMAT`) come from the store when available, falling back to `constants.py` imports.
- [ ] `query_model.py __build_qa_validation_prompt()` reads the shared validator template from the store (`generator="__shared__"`, `template_id="qa_validation"`, `template_type="validator"`) when a store handle is provided, falling back to the current inline construction.
- [ ] `query_model.py __build_card_validation_prompt()` similarly reads `generator="comparison"`, `template_id="card_validation"` from the store when available.
- [ ] A generator may override its validator template by providing a `(generator=<its category>, template_id="validator", template_type="validator")` doc in the store; when present, the generator uses it instead of the shared validator. (Hybrid granularity per requirement #4.)
- [ ] Backward compatibility: with `template_store=None` (the default), every generator behaves exactly as it does today — no MongoDB dependency, no behavior change. All existing unit tests pass unchanged.
- [ ] `main.py` constructs a single `TemplateStore` instance (when MongoDB is available) and passes it to every generator constructor.
- [ ] Unit tests cover: store-present path (templates loaded from store), store-absent fallback path (class constant used), version-override path, validator-override path, and the shared-scaffolding fallback.

## Technical Plan
**Plan file**: `plans/story-042-legacy-cli-template-loading-plan.md` ✅ Created

The technical design, architecture decisions, and task breakdown for this story
are in the companion plan file linked above.

## Dependencies
- Story 040 (Template Store)
- Story 041 (Seed Script — so the store is populated when integration runs)

## Priority: High

## Notes
- **Backward compat is critical**: The default `template_store=None` path must be byte-identical to current behavior. This is the safety net for the cutover.
- **`build_*_prompt` signature change**: Adding an optional `scaffolding` param to ~20 functions is invasive. The plan should consider a module-level `_SCAFFOLDING_CACHE` populated from the store at startup, so individual build functions read `SYSTEM_MESSAGE = _SCAFFOLDING_CACHE.get("system_message") or constants.SYSTEM_MESSAGE` without changing their signatures. This keeps the diff small.
- **Validator hybrid**: The shared validator is the default; a generator-specific validator doc overrides it. The plan should define the lookup order: (1) generator-specific validator doc, (2) shared validator doc, (3) inline `__build_qa_validation_prompt` fallback.
- **`TemplateConfig` frozen dataclass**: The legacy `common.TemplateConfig` is `@dataclass(frozen=True)`. `store.to_template_config()` must return instances of this exact class so `select_templates()` and `build_prompt(template, ...)` work unchanged.
- **No schema migration**: Existing `QuestionAnswerEnhanced` docs in MongoDB are untouched. Only template loading changes.