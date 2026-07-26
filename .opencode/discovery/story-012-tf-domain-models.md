# Story: Port MTG domain models to TrainForge domain plugin

## User Story
As a **TrainForge MTG domain developer**, I want **comprehensive Pydantic v2 domain models for all MTG entities ported to the TrainForge domain plugin**, so that **generators and data access methods return typed, validated objects with IDE autocomplete**.

## Context
The old CLI (`training_data/generate_synthetic_data/domain_models.py`) has 605 lines of Pydantic v2 models covering 10 model categories. TrainForge's `models.py` has only generic models (Model, QuestionAnswer, etc.) — MTG-specific models belong in the MTG domain plugin.

### Models to Port
1. **Card** — CardFace, Card, CardWithMetadata (with computed properties, to_prompt_detail(), from_dict())
2. **PriceData** — usd, eur, best_price, is_budget()
3. **Ruling** — uuid, date, text, source
4. **Legality** — Legality, CardLegalities (with is_legal_in())
5. **Combo** — ComboCard, ComboProduces, Combo, ComboWithCards
6. **Commander** — Commander, CommanderWithTags (with salt_level, is_popular())
7. **Archetype** — Archetype (key_cards, win_conditions, etc.)
8. **Article/Guide** — Article, GuideChapter, Guide
9. **Rule/Glossary** — Rule, GlossaryTerm (with subrules)
10. **Keyword** — Keyword (is_evergreen, is_deciduous)

## Acceptance Criteria
- [ ] Create `trainforge/domains/mtg/domain_models.py` with all 10 model categories
- [ ] All models use `MongoModel` base with `ConfigDict(populate_by_name=True, extra="ignore")`
- [ ] Field aliases match MongoDB field names (camelCase)
- [ ] Computed properties preserved: `cmc`, `is_commander_legal`, `is_creature`, `primary_face`, `best_price`, `salt_level`, etc.
- [ ] `to_prompt_detail()` method on Card for LLM context
- [ ] `from_dict()` factory method handling JSON-stringified arrays
- [ ] Model forward references resolved (Card ↔ ComboWithCards references)
- [ ] Models importable via `trainforge.domains.mtg.domain_models`
- [ ] Re-exported from `trainforge.domains.mtg.__init__`
- [ ] All models compatible with TrainForge's Python version and dependency versions
- [ ] Tests for all core models

## Dependencies
- Story 003: Extended Data Models (old CLI reference implementation)
- Story 011: Enrich TrainForge MTGDataAccess (these models are return types for data access)

## Priority: High

## Notes
- **Reference implementation**: `training_data/generate_synthetic_data/domain_models.py` (605 lines)
- **Key difference**: Old CLI's `MongoModel` has `to_dict()` method and `model_config` with `populate_by_name=True, extra="ignore", arbitrary_types_allowed=True, use_enum_values=True`
- TrainForge's `models.py` does NOT have a `MongoModel` base — one should be added to `domains/mtg/domain_models.py`
- The `Card.from_dict()` method handles JSON-stringified arrays (subtypes, colors stored as `'["W","U"]'` strings in MongoDB) — this is critical for backward compatibility
- `Card.to_prompt_detail()` is used by ALL generators for LLM context — must be preserved exactly
- Model rebuild calls at bottom of file (`Card.model_rebuild()`, `Combo.model_rebuild()`, `Rule.model_rebuild()`) must be replicated
