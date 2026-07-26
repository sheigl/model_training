# Story: Port GenerateTerminologyQuestions to TrainForge

## User Story
As a **TrainForge user**, I want **the terminology generator available in the TrainForge UI**, so that **I can generate MTG terminology Q&A data through the web interface**.

## Context
The `GenerateTerminologyQuestions` generator is implemented in the old CLI (204 lines) with 2 templates and 20 MTG terms (CEDH, pillow fort, MLD, staple, salt, aristocrats, voltron, group hug, stax, GY, ETB, LTB, ramp, tutor, wheel, pod, blink, flicker, bounce, hatedraft). It generates Q&A explaining MTG slang, jargon, and format-specific terms. This generator does NOT use `MTGDataAccess`.

## Acceptance Criteria
- [ ] Create `trainforge/domains/mtg/generators/terminology.py`
- [ ] Generator class extends `BaseGenerator[str]` (TrainForge version)
- [ ] All 2 templates ported: definition_focused, practical_application
- [ ] All 20 MTG terms ported with their definitions (order and content must not change)
- [ ] Both validation rule sets ported (TERMINOLOGY_DEFINITION_VALIDATION, TERMINOLOGY_PRACTICAL_VALIDATION)
- [ ] `build_prompt()` uses term + definition formatting from TERMINOLOGY list
- [ ] `build_context()` ported for validation context
- [ ] Templates defined in `templates.yaml` under `terminology` category
- [ ] Generator registered in `MTGDomain.get_generators()`
- [ ] Generator appears in TrainForge UI generation page
- [ ] Tests written for the generator

## Dependencies
- Story 012: Port MTG domain models to TrainForge domain plugin

## Priority: High

## Notes
- This generator does NOT need data access (Story 11) since all terms are hardcoded
- The old CLI yields terms in a `while True` infinite loop — TrainForge should use a bounded loop
- Terms are Phase 1 in the old CLI (1,000 examples in phase1 mode)
