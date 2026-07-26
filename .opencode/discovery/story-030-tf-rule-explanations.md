# Story: Port GenerateRuleExplanations to TrainForge

## User Story
As a **TrainForge user**, I want **the rule explanations generator available in the TrainForge UI**, so that **I can generate rules-grounded Q&A data through the web interface**.

## Context
The `GenerateRuleExplanations` generator is implemented in the old CLI (85 lines) with templates loaded from `RULE_EXPLANATION_TEMPLATES` in constants.py (3 templates: plain_english, in_game_scenario, edge_case). It generates natural Q&A from specific rule text fetched via `MTGDataAccess.get_rules()`.

## Acceptance Criteria
- [ ] Create `trainforge/domains/mtg/generators/rule_explanations.py`
- [ ] Generator class extends `BaseGenerator[Rule]` (TrainForge version)
- [ ] All 3 templates ported: plain_english, in_game_scenario, edge_case
- [ ] Load templates from `RULE_EXPLANATION_TEMPLATES` (or port to `templates.yaml`)
- [ ] Validation rules loaded from `RULE_EXPLANATION_VALIDATION`
- [ ] `SKIP_SECTIONS` set ported (000, 001, 002, 003, 004, 005, 900)
- [ ] Uses `MTGDataAccess.get_rules()` with text-exists filter
- [ ] Filters for rules with text > 50 characters
- [ ] `build_prompt()` delegates to `build_rule_explanation_prompt()` from common.py
- [ ] Templates defined in `templates.yaml` under `rule_explanation` category
- [ ] Generator registered in `MTGDomain.get_generators()`
- [ ] Generator appears in TrainForge UI generation page
- [ ] Tests written for the generator

## Dependencies
- Story 011: Enrich TrainForge MTGDataAccess with typed joins
- Story 012: Port MTG domain models to TrainForge domain plugin

## Priority: High

## Notes
- Relies on `RULE_EXPLANATION_TEMPLATES` and `RULE_EXPLANATION_VALIDATION` from constants.py
- Part of Phase 3 in the old CLI (2,000 examples in phase3 mode)
- The `build_rule_explanation_prompt()` helper in common.py also needs porting to TrainForge's common utilities
