# Story: Port GenerateRulesScenarios to TrainForge

## User Story
As a **TrainForge user**, I want **the rules scenarios generator available in the TrainForge UI**, so that **I can generate rules scenario Q&A data through the web interface**.

## Context
The `GenerateRulesScenarios` generator is implemented in the old CLI (185 lines) with 2 templates and 15 scenarios covering stack, combat damage, triggered abilities, state-based actions, activated abilities, replacement effects, keyword interactions, Commander-specific rules, planeswalker rules, token/copy rules, priority, ETB/LTB triggers, targeting, mana/casting, and graveyard/exile interactions. This generator does NOT use `MTGDataAccess`.

## Acceptance Criteria
- [ ] Create `trainforge/domains/mtg/generators/rules_scenarios.py`
- [ ] Generator class extends `BaseGenerator[str]` (TrainForge version)
- [ ] All 2 templates ported: general_advice, example_driven
- [ ] All 15 scenarios ported with context (spell resolution, combat damage, triggered abilities, state-based actions, activated abilities, replacement effects, keyword interactions, Commander rules, planeswalker rules, token/copy rules, priority, ETB/LTB, targeting, mana/casting, graveyard/exile)
- [ ] Both validation rule sets ported (RULES_GENERAL_VALIDATION, RULES_EXAMPLE_VALIDATION)
- [ ] `build_prompt()` uses scenario + context formatting
- [ ] `build_context()` ported for validation context
- [ ] Templates defined in `templates.yaml` under `rules_scenario` category
- [ ] Generator registered in `MTGDomain.get_generators()`
- [ ] Generator appears in TrainForge UI generation page
- [ ] Tests written for the generator

## Dependencies
- Story 012: Port MTG domain models to TrainForge domain plugin

## Priority: High

## Notes
- This generator does NOT need data access (Story 11) since all scenarios are hardcoded
- Part of Phase 2 in the old CLI (3,000 examples in phase2 mode)
- Category string is "rules_scenario" in the old CLI
