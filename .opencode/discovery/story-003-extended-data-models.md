# Story: Extended Data Models (Pydantic)

## User Story
As a **developer building the synthetic data generators**, I want **comprehensive Pydantic models for all MTG domain objects** with proper typing, validation, and serialization, so that **the Unified Data Access Layer returns rich, typed objects and generators have full IDE autocomplete and runtime validation**.

## Context
This story was originally scoped to BUILD the Pydantic domain models. **It has been implemented in the old CLI, but needs to be ported to the TrainForge domain plugin.**

### Old CLI Implementation (`training_data/generate_synthetic_data/domain_models.py`) ✅ COMPLETE
- 605 lines, all 10 model categories implemented:
  1. Card, CardFace, CardWithMetadata
  2. PriceData
  3. Ruling
  4. Legality, CardLegalities
  5. ComboCard, ComboProduces, Combo, ComboWithCards
  6. Commander, CommanderWithTags
  7. Archetype
  8. Article, GuideChapter, Guide
  9. GameState
  10. Rule, GlossaryTerm, Keyword
- Pydantic v2 (`BaseModel`, `Field`, `ConfigDict`)
- MongoDB field aliases for seamless deserialization
- Computed properties (cmc, is_commander_legal, etc.)
- `to_prompt_detail()` for LLM context building
- `models.py` re-exports for backward compatibility

### TrainForge Implementation (`trainforge/src/trainforge/models.py`) ⚠️ PARTIAL
- Has generic models only: `Model`, `QuestionAnswer`, `QuestionAnswerEnhanced`, `GenerationTrace`, `ValidationMetrics`
- **By design**, MTG-specific domain models are NOT in the generic framework
- MTG domain models should live in `trainforge/domains/mtg/domain_models.py`

## Acceptance Criteria

### Old CLI Status (already verified)
- [x] File: `training_data/generate_synthetic_data/domain_models.py` — EXISTS
- [x] All models use Pydantic v2 (`BaseModel`, `Field`, `ConfigDict`) — EXISTS
- [x] Models include MongoDB field aliases for seamless deserialization — EXISTS
- [x] Computed properties for derived data (color identity, CMC, etc.) — EXISTS
- [x] Serialization helpers for LLM prompt building — EXISTS
- [x] All 10 model categories implemented — EXISTS

### TrainForge Porting Needed (new story — see Story 12)
- [ ] Port MTG domain models to `trainforge/domains/mtg/domain_models.py`
- [ ] Ensure Pydantic v2 compatibility with TrainForge's `models.py`
- [ ] Reconcile field name differences (old CLI uses `mtg_json.*` camelCase; TrainForge config uses different collection names)
- [ ] Add/re-export in MTG domain `__init__.py`

## Dependencies
- None (foundation story)

## Priority: High

## Notes
- The old CLI `domain_models.py` is the REFERENCE IMPLEMENTATION
- TrainForge's `models.py` only needs generic, domain-agnostic types — MTG domain models belong in the domain plugin
- Key difference: old CLI models handle `mtg_json.cards` schemas (JSON-stringified arrays for subtypes, colors, keywords); TrainForge may use different collection formats
- The old CLI's `Card.from_dict()` handles JSON-stringified arrays — this logic must be preserved
