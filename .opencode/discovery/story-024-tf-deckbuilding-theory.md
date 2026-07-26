# Story: Port GenerateDeckbuildingTheory to TrainForge

## User Story
As a **TrainForge user**, I want **the deckbuilding theory generator available in the TrainForge UI**, so that **I can generate deckbuilding theory Q&A data through the web interface**.

## Context
The `GenerateDeckbuildingTheory` generator is implemented in the old CLI (173 lines) with 2 templates and 12 topics. It generates Q&A about deckbuilding theory, card evaluation, mana curves, synergy vs goodstuff, and construction principles. This generator does NOT use `MTGDataAccess`.

## Acceptance Criteria
- [ ] Create `trainforge/domains/mtg/generators/deckbuilding_theory.py`
- [ ] Generator class extends `BaseGenerator[str]` (TrainForge version)
- [ ] All 2 templates ported: general_advice, example_driven
- [ ] All 12 topics ported with context (card evaluation, card advantage vs selection, mana curve, redundancy, synergy vs goodstuff, win conditions, deck tuning, threat density, mana base, protection, interaction philosophy, tribal construction)
- [ ] Both validation rule sets ported (DECKBUILDING_GENERAL_VALIDATION, DECKBUILDING_EXAMPLE_VALIDATION)
- [ ] `build_prompt()` uses topic + context formatting
- [ ] `build_context()` ported for validation context
- [ ] Templates defined in `templates.yaml` under `deckbuilding_theory` category
- [ ] Generator registered in `MTGDomain.get_generators()`
- [ ] Generator appears in TrainForge UI generation page
- [ ] Tests written for the generator

## Dependencies
- Story 012: Port MTG domain models to TrainForge domain plugin

## Priority: High

## Notes
- This generator does NOT need data access (Story 11) since all topics are hardcoded
- Part of Phase 2 in the old CLI (2,000 examples in phase2 mode)
- Topics are deckbuilding fundamentals, not specific card data
