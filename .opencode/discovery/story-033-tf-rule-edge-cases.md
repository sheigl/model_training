# Story: Port GenerateRuleEdgeCases to TrainForge

## User Story
As a **TrainForge user**, I want **the rule edge cases generator available in the TrainForge UI**, so that **I can generate tricky edge case Q&A data through the web interface**.

## Context
The `GenerateRuleEdgeCases` generator is implemented in the old CLI (85 lines) with 1 template. It generates tricky edge case Q&A from complex rule sections fetched via `MTGDataAccess.get_rules()`, using `COMPLEX_RULE_SECTIONS` from constants.py to identify the most complex rule sections.

## Acceptance Criteria
- [ ] Create `trainforge/domains/mtg/generators/rule_edge_cases.py`
- [ ] Generator class extends `BaseGenerator[Rule]` (TrainForge version)
- [ ] Template ported: edge_case (1 template)
- [ ] Uses `MTGDataAccess.get_rules()` with text-exists filter
- [ ] Filters for rules with text > 80 characters
- [ ] Filters by complex section prefixes from `COMPLEX_RULE_SECTIONS` in constants.py
- [ ] `build_prompt()` delegates to `build_rule_edge_case_prompt()` with rule number, text, and section name
- [ ] Templates defined in `templates.yaml` under `rule_edge_case` category
- [ ] Generator registered in `MTGDomain.get_generators()`
- [ ] Generator appears in TrainForge UI generation page
- [ ] Tests written for the generator

## Dependencies
- Story 011: Enrich TrainForge MTGDataAccess with typed joins
- Story 012: Port MTG domain models to TrainForge domain plugin

## Priority: High

## Notes
- Part of Phase 3 in the old CLI (1,500 examples in phase3 mode)
- Relies on `COMPLEX_RULE_SECTIONS` from constants.py — these must be ported
- The `build_rule_edge_case_prompt()` helper in common.py also needs porting
