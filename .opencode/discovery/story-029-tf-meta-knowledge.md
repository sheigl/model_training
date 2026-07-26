# Story: Port GenerateMetaKnowledge to TrainForge

## User Story
As a **TrainForge user**, I want **the meta knowledge generator available in the TrainForge UI**, so that **I can generate meta and power level Q&A data through the web interface**.

## Context
The `GenerateMetaKnowledge` generator is implemented in the old CLI (160 lines) with 2 templates and 9 topics covering cEDH viability, power level scale (1-10), pod communication, fast mana, tutors, cEDH win conditions, commander evaluation, meta reads, and banned list philosophy. This generator does NOT use `MTGDataAccess`.

## Acceptance Criteria
- [ ] Create `trainforge/domains/mtg/generators/meta_knowledge.py`
- [ ] Generator class extends `BaseGenerator[str]` (TrainForge version)
- [ ] All 2 templates ported: general_advice, meta_deep_dive
- [ ] All 9 topics ported with context (cEDH, power level scale, pod communication, fast mana, tutors, cEDH win cons, commander evaluation, meta reads, banned list)
- [ ] Both validation rule sets ported (META_KNOWLEDGE_GENERAL_VALIDATION, META_KNOWLEDGE_DEEP_DIVE_VALIDATION)
- [ ] `build_prompt()` uses topic + context formatting
- [ ] `build_context()` ported for validation context
- [ ] Templates defined in `templates.yaml` under `meta_knowledge` category
- [ ] Generator registered in `MTGDomain.get_generators()`
- [ ] Generator appears in TrainForge UI generation page
- [ ] Tests written for the generator

## Dependencies
- Story 012: Port MTG domain models to TrainForge domain plugin

## Priority: High

## Notes
- This generator does NOT need data access (Story 11) since all topics are hardcoded
- Part of Phase 2 in the old CLI (1,000 examples in phase2 mode)
- Second template is called "meta_deep_dive" (unique name among generators)
