# Story: Port GenerateArchetypes to TrainForge

## User Story
As a **TrainForge user**, I want **the archetypes generator available in the TrainForge UI**, so that **I can generate deck archetype strategy Q&A data through the web interface**.

## Context
The `GenerateArchetypes` generator is implemented in the old CLI (155 lines) with 2 templates and 10 archetypes (Aggro, Control, Combo, Midrange, Stax, Voltron, Tokens, Reanimator, Storm, Pillow Fort). It generates Q&A about deck archetype strategies. This generator does NOT use `MTGDataAccess`.

## Acceptance Criteria
- [ ] Create `trainforge/domains/mtg/generators/archetypes.py`
- [ ] Generator class extends `BaseGenerator[str]` (TrainForge version)
- [ ] All 2 templates ported: general_advice, example_driven
- [ ] All 10 archetypes ported with context (Aggro, Control, Combo, Midrange, Stax, Voltron, Tokens, Reanimator, Storm, Pillow Fort)
- [ ] Both validation rule sets ported (ARCHETYPE_GENERAL_VALIDATION, ARCHETYPE_EXAMPLE_VALIDATION)
- [ ] `build_prompt()` uses archetype + context formatting
- [ ] `build_context()` ported for validation context
- [ ] Templates defined in `templates.yaml` under `archetype` category
- [ ] Generator registered in `MTGDomain.get_generators()`
- [ ] Generator appears in TrainForge UI generation page
- [ ] Tests written for the generator

## Dependencies
- Story 012: Port MTG domain models to TrainForge domain plugin

## Priority: High

## Notes
- This generator does NOT need data access (Story 11) since all archetypes are hardcoded
- Part of Phase 2 in the old CLI (1,500 examples in phase2 mode)
- Category is "archetype" (singular, not "archetypes")
