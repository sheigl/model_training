# Story: Port GenerateRuleWhyQuestions to TrainForge

## User Story
As a **TrainForge user**, I want **the rule why-questions generator available in the TrainForge UI**, so that **I can generate backward-reasoning Q&A data through the web interface**.

## Context
The `GenerateRuleWhyQuestions` generator is implemented in the old CLI (82 lines) with 1 template. It generates "why does this work" Q&A from principle rule sections fetched via `MTGDataAccess.get_rules()`. It focuses on backward-reasoning: starting from a known outcome and asking why the rules produce that outcome.

## Acceptance Criteria
- [ ] Create `trainforge/domains/mtg/generators/rule_why_questions.py`
- [ ] Generator class extends `BaseGenerator[Rule]` (TrainForge version)
- [ ] Template ported: why (1 template)
- [ ] Uses `MTGDataAccess.get_rules()` with text-exists filter
- [ ] Filters for rules with text > 100 characters
- [ ] Filters by principle section list (116, 117, 118, 120, 601, 602, 603, 604, 608, 700, 701, 702, 704, 706)
- [ ] `build_prompt()` delegates to `build_rule_why_prompt()` from common.py
- [ ] Templates defined in `templates.yaml` under `rule_why` category
- [ ] Generator registered in `MTGDomain.get_generators()`
- [ ] Generator appears in TrainForge UI generation page
- [ ] Tests written for the generator

## Dependencies
- Story 011: Enrich TrainForge MTGDataAccess with typed joins
- Story 012: Port MTG domain models to TrainForge domain plugin

## Priority: High

## Notes
- Part of Phase 3 in the old CLI (1,000 examples in phase3 mode)
- The `build_rule_why_prompt()` helper in common.py also needs porting
- Category is "rule_why"
- PRINCIPLE_SECTIONS list identifies sections relevant for "why" reasoning (core gameplay mechanics)
