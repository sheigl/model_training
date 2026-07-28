# Story: Validator Template Migration to YAML

## User Story
As a validation pipeline maintainer, I want validator prompts (the QA validation prompt and card comparison validation prompt) stored as YAML files instead of being built inline or seeded into MongoDB, so that validator logic is as editable and version-tracked as generation templates.

## Context
Currently there are two validator prompt paths:
1. **Shared Q&A validator** (`qa_validation`): Built dynamically in `query_model.py.__build_qa_validation_prompt()`. When a store doc exists, it uses the stored template with `{question}`, `{answer}`, `{context}`, `{category}` placeholders via `str.replace()`. The public helper `build_qa_validation_prompt_template()` produces the template string for seeding.
2. **Card comparison validator** (`card_validation`): Built dynamically in `query_model.py.__build_card_validation_prompt()`. Same pattern — store doc takes precedence over inline construction.

Both live in MongoDB under generator-specific or shared namespaces. The seed script extracts them from the public helper functions. After migration, both should be stored as YAML files.

## Acceptance Criteria
- [ ] `templates/shared.yaml` contains a `validators:` section with `qa_validation` key holding the full Q&A validator prompt template (with `{question}`, `{answer}`, `{context}`, `{category}` placeholders)
- [ ] `templates/comparison_validator.yaml` contains the card comparison validator prompt template (with `{card1_name}`, `{card1_type}`, etc. placeholders)
- [ ] `QueryModel._resolve_validator_template()` reads from the YAML loader instead of MongoDB when a loader is provided
- [ ] The `str.replace()` substitution logic for MTG-brace-safe placeholder replacement is preserved exactly
- [ ] When no loader is provided, `_resolve_validator_template()` returns `None` and the inline prompt construction is used (byte-identical to current fallback behavior)
- [ ] The public helper functions `build_qa_validation_prompt_template()` and `build_card_validation_prompt_template()` are kept as reference implementations but are no longer called by the production path
- [ ] Tests verify: store path uses YAML template, inline fallback works when no loader, MTG braces in templates are preserved

## Technical Plan
**Plan file**: `plans/story-004-validator-yaml-migration-plan.md`

The technical design, architecture decisions, and task breakdown for this story
are in the companion plan file linked above.

## Dependencies
- Story 001 (YAML loader module must exist)
- Story 003 (scaffolding blocks in shared.yaml — qa_validation lives there)

## Priority: High

## Notes
- The two public helper functions (`build_qa_validation_prompt_template`, `build_card_validation_prompt_template`) were created specifically for the seed script. After this migration they become documentation/reference only and can be kept or moved to a `_templates_reference.py` module.
- The `validation_checklist` and `validation_scoring_guide` scaffolding blocks in `shared.yaml` are separate from the validator prompt templates — they're referenced by the inline fallback path, not by the stored template path.
