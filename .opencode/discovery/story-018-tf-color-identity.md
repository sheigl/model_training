# Story: Port GenerateColorIdentityQuestions to TrainForge

## User Story
As a **TrainForge user**, I want **the color identity legality generator available in the TrainForge UI**, so that **I can generate Commander color identity Q&A data through the web interface**.

## Context
The `GenerateColorIdentityQuestions` generator is implemented in the old CLI (686 lines) with 4 templates and full CR 903.4 support. It needs to be ported to the TrainForge generator pattern.

**CRITICAL**: The current `templates.yaml` has a `color_identity` category describing color pie philosophy questions — this is the WRONG topic and must be replaced with Commander color identity legality.

## Acceptance Criteria
- [ ] Create `trainforge/domains/mtg/generators/color_identity.py`
- [ ] Generator class extends `BaseGenerator[ColorIdentityContext]`
- [ ] All 4 templates ported: mono_color, two_color, three_color, five_color
- [ ] Commander weighting logic ported (popular commanders appear more)
- [ ] Color identity calculation ported (CR 903.4 including hybrid, phyrexian, colorless, color indicators)
- [ ] Edge case handling ported (Extort in reminder text, Devoid, DFCs)
- [ ] Templates.yaml `color_identity` category REPLACED with Commander legality templates
- [ ] Generator registered in `MTGDomain.get_generators()`
- [ ] Tests written for the generator

## Dependencies
- Story 011: Enrich TrainForge MTGDataAccess with typed joins
- Story 012: Port MTG domain models to TrainForge domain plugin

## Priority: High

## Notes
- **CRITICAL**: The `color_identity` category in templates.yaml describes color pie philosophy questions, not Commander color identity legality. This MUST be corrected during porting.
- The old CLI generator covers: hybrid mana (counts as both colors), phyrexian mana (counts as its color), colorless cards (legal in any deck), color indicators (on DFC back faces), and special cases (Extort — reminder text doesn't count)
