# Story: Port GenerateGameTheory to TrainForge

## User Story
As a **TrainForge user**, I want **the game theory generator available in the TrainForge UI**, so that **I can generate in-game decision-making Q&A data through the web interface**.

## Context
The `GenerateGameTheory` generator is implemented in the old CLI (165 lines) with 2 templates and 10 situations covering threat assessment, mulligan decisions, spell sequencing, mana efficiency, multiplayer politics, threat perception, conservative vs aggressive play, card advantage, combat math, and timing win attempts. This generator does NOT use `MTGDataAccess`.

## Acceptance Criteria
- [ ] Create `trainforge/domains/mtg/generators/game_theory.py`
- [ ] Generator class extends `BaseGenerator[str]` (TrainForge version)
- [ ] All 2 templates ported: general_advice, scenario_walkthrough
- [ ] All 10 situations ported with context (threat assessment, mulliganing, sequencing, mana efficiency, politics, threat perception, conservative play, card advantage, combat math, timing win attempts)
- [ ] Both validation rule sets ported (GAME_THEORY_GENERAL_VALIDATION, GAME_THEORY_SCENARIO_VALIDATION)
- [ ] `build_prompt()` uses situation + context formatting
- [ ] `build_context()` ported for validation context
- [ ] Templates defined in `templates.yaml` under `game_theory` category
- [ ] Generator registered in `MTGDomain.get_generators()`
- [ ] Generator appears in TrainForge UI generation page
- [ ] Tests written for the generator

## Dependencies
- Story 012: Port MTG domain models to TrainForge domain plugin

## Priority: High

## Notes
- This generator does NOT need data access (Story 11) since all situations are hardcoded
- Part of Phase 2 in the old CLI (1,500 examples in phase2 mode)
- Second template is called "scenario_walkthrough" (not "example_driven" like most others)
