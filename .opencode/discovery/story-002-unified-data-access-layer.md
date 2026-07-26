# Story: Unified Data Access Layer

## User Story
As a **synthetic data generator developer**, I want a **single unified data access class** that provides typed access to all MongoDB collections with pre-built joins, so that **generators don't write raw MongoDB queries and can access rich, joined data through clean Python methods**.

## Context
This story was originally scoped to BUILD the data access layer. **It has been implemented in the old CLI, but the TrainForge equivalent is partial.**

### Old CLI Implementation (`training_data/generate_synthetic_data/data_access.py`) ✅ COMPLETE
- 1253+ line `MTGDataAccess` class with all methods
- Uses MongoDB aggregation pipelines for efficient joins
- Has `LRUCacheWithTTL`, retry decorators, index verification
- Returns typed `CardWithMetadata`, `ComboWithCards`, `CommanderWithTags`, etc.

### TrainForge Implementation (`trainforge/src/trainforge/data_source.py` + `domains/mtg/data_source.py`) ⚠️ PARTIAL
- Generic `DataSource` ABC and `MongoDataSource` base — COMPLETE
- MTG-specific `MTGDataAccess` extending `MongoDataSource` — **NEEDS ENRICHMENT**
  - Has basic methods: `get_cards()`, `get_articles()`, `get_rules()`, `get_glossary()`, `get_edhrec_data()`, `get_game_changers()`, `get_salty_cards()`, `get_top_cards_by_color()`
  - All return `list[dict]` instead of typed Pydantic models
  - Missing: enriched joins (prices, legalities, rulings, keywords), analytics methods, typed return types
- Collection names differ from old CLI's `mtg_json.*` — using `synthetic_queries.mtg_cards` etc.

## Acceptance Criteria

### Old CLI Status (already verified)
- [x] Class `MTGDataAccess` in `training_data/generate_synthetic_data/data_access.py` — EXISTS
- [x] Single MongoDB client connection managed internally (connection pooling) — EXISTS
- [x] Typed dataclasses/Pydantic models for all returned data — EXISTS
- [x] Pre-built join methods: `get_cards_enriched`, `get_combos_enriched`, `get_commanders_enriched` — EXISTS
- [x] Analytics methods: `get_top_cards_by_edhrec_rank`, `get_budget_alternatives`, `get_synergy_partners`, etc. — EXISTS
- [x] Utility methods: `calculate_color_identity`, `get_card_by_name`, `search_cards_text` — EXISTS

### TrainForge Porting Needed (new story — see Story 11)
- [ ] Port enriched join methods to `trainforge/domains/mtg/data_source.py`
- [ ] Add typed Pydantic return types (domain models)
- [ ] Port analytics methods (get_budget_alternatives, get_synergy_partners, etc.)
- [ ] Reconcile collection names between old CLI and TrainForge config

## Dependencies
- Story 3 (Extended Data Models) — provides the Pydantic models returned by this layer

## Priority: High

## Notes
- The old CLI `data_access.py` is the REFERENCE IMPLEMENTATION for what needs to be ported
- TrainForge's generic `MongoDataSource` is fine; the MTG-specific subclass needs enrichment
- Key porting challenge: old CLI uses `mtg_json.cards` collection with camelCase fields; TrainForge config uses `synthetic_queries.mtg_cards`
- The aggregation pipelines in old CLI directly reference MongoDB field names — these need to be preserved during porting
