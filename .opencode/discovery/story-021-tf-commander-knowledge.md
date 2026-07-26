# Story: Port GenerateCommanderKnowledge to TrainForge

## User Story
As a **TrainForge user**, I want **the Commander knowledge generator available in the TrainForge UI**, so that **I can generate Commander rules Q&A data through the web interface**.

## Context
The `GenerateCommanderKnowledge` generator is implemented in the old CLI (157 lines) with 2 templates and 8 Commander sub-topics. It generates Q&A about Commander format rules (deck construction, commander tax, commander damage, command zone, color identity, multiplayer, partner/background, companion/wish effects). This generator does NOT use `MTGDataAccess` — it uses hardcoded topic/context pairs.

## Acceptance Criteria
- [ ] Create `trainforge/domains/mtg/generators/commander_knowledge.py`
- [ ] Generator class extends `BaseGenerator[str]` (TrainForge version)
- [ ] All 2 templates ported: general_advice, example_driven
- [ ] All 8 Commander sub-topics ported (deck construction, commander tax, commander damage, command zone, color identity, multiplayer, partner/background, companion/wish)
- [ ] Both validation rule sets ported (COMMANDER_KNOWLEDGE_GENERAL_VALIDATION, COMMANDER_KNOWLEDGE_EXAMPLE_VALIDATION)
- [ ] `build_prompt()` uses topic + context formatting from COMMANDER_SUBTOPICS
- [ ] `build_context()` ported for validation context
- [ ] Templates defined in `templates.yaml` under `commander_rules` category
- [ ] Generator registered in `MTGDomain.get_generators()`
- [ ] Generator appears in TrainForge UI generation page
- [ ] Tests written for the generator

## Dependencies
- Story 012: Port MTG domain models to TrainForge domain plugin

## Priority: High

## Notes
- This generator does NOT need data access (Story 11) since all topics are hardcoded
- The old CLI yields sub-topics in a `while True` infinite loop — TrainForge should use a bounded loop or generator pattern
- Order and content of sub-topics must be preserved exactly
