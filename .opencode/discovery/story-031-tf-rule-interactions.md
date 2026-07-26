# Story: Port GenerateRuleInteractions to TrainForge

## User Story
As a **TrainForge user**, I want **the rule interactions generator available in the TrainForge UI**, so that **I can generate rule interaction Q&A data through the web interface**.

## Context
The `GenerateRuleInteractions` generator is implemented in the old CLI (198 lines) with templates loaded from `RULE_INTERACTION_TEMPLATES` (3 templates: plain_english, in_game_scenario, edge_case) and 35+ interaction pairs between rule sections. It generates Q&A where two rules interact. It uses `MTGDataAccess.get_rules()` to fetch rule data and pairs rules from interacting sections.

## Acceptance Criteria
- [ ] Create `trainforge/domains/mtg/generators/rule_interactions.py`
- [ ] Generator class extends `BaseGenerator[ProjectedRulePair]` (TrainForge version)
- [ ] Port `ProjectedRulePair` dataclass (name, rule1_number, rule1_text, rule2_number, rule2_text, sections)
- [ ] All 3 templates ported: plain_english, in_game_scenario, edge_case
- [ ] Load templates from `RULE_INTERACTION_TEMPLATES` (or port to `templates.yaml`)
- [ ] Validation rules loaded from `RULE_INTERACTION_VALIDATION`
- [ ] All 35+ interaction pairs ported (e.g., "601"+"116" for Casting+Priority, "603"+"704" for Triggers+SBAs, etc.)
- [ ] Uses `MTGDataAccess.get_rules()` with text-exists filter
- [ ] Filters for rules with text > 60 characters
- [ ] Deduplication logic by pair name preserved
- [ ] `build_prompt()` includes system message, notation legend, both rule texts, task instruction, and requirements
- [ ] Templates defined in `templates.yaml` under `rule_interaction` category
- [ ] Generator registered in `MTGDomain.get_generators()`
- [ ] Generator appears in TrainForge UI generation page
- [ ] Tests written for the generator

## Dependencies
- Story 011: Enrich TrainForge MTGDataAccess with typed joins
- Story 012: Port MTG domain models to TrainForge domain plugin

## Priority: High

## Notes
- Relies on `RULE_INTERACTION_TEMPLATES` and `RULE_INTERACTION_VALIDATION` from constants.py
- Part of Phase 3 in the old CLI (2,000 examples in phase3 mode)
- Interaction pairs cover: Casting, Priority, Triggered abilities, SBAs, Keywords, Damage, Copying, Costs, Multiplayer, Commander, Zone changes, Replacement effects, Layers, Combat, Counters, Mana
