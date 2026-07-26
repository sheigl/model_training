# Story: Enrich TrainForge MTGDataAccess with typed joins

## User Story
As a **TrainForge MTG domain developer**, I want **the MTG data access layer to have typed join methods, analytics queries, and aggregated card enrichment**, so that **porting generators from the old CLI can leverage the same rich data without writing raw MongoDB pipelines**.

## Context
The old CLI (`training_data/generate_synthetic_data/data_access.py`) has a mature 1253-line `MTGDataAccess` class with advanced aggregation pipelines, typed returns, caching, and retry logic. The TrainForge equivalent (`trainforge/domains/mtg/data_source.py`) is basic — only 8 methods returning `list[dict]`. This story ports the enriched methods.

### Current TrainForge `MTGDataAccess` methods
- `get_cards()`, `get_card_by_name()`, `get_cards_by_type()`, `get_cards_by_color()` — all return `list[dict]`
- `get_articles()`, `get_rules()`, `get_glossary()` — return `list[dict]`
- `get_edhrec_data()`, `get_game_changers()`, `get_salty_cards()`, `get_top_cards_by_color()` — return `list[dict]`

### Missing (need porting from old CLI)
- Enriched card queries with prices/legalities/rulings joins
- Combo enrichment with card lookups across databases
- Analytics methods: get_budget_alternatives, get_synergy_partners, get_commander_staples
- Typed return models (CardWithMetadata, ComboWithCards, etc.)
- LRU cache with TTL
- Index verification on startup

## Acceptance Criteria
- [ ] Port `get_cards_enriched(filters, limit, lite)` — aggregation pipeline joining cardPrices, cardLegalities, cardRulings
- [ ] Port `get_combos_enriched(filters, limit)` — Commander Spellbook combos with enriched card data
- [ ] Port `get_commanders_enriched(filters, limit)` — EDHREC commanders with card details
- [ ] Port `get_card_by_name(name)` — single enriched card lookup
- [ ] Port `get_cards_by_keyword_mechanic(keyword, limit)` — keyword-filtered cards
- [ ] Port analytics: `get_top_cards_by_edhrec_rank()`, `get_budget_alternatives()`, `get_synergy_partners()`, `get_commander_staples()`, `get_format_legalities()`
- [ ] Port utility: `calculate_color_identity()`, `search_cards_text()`, `get_rulings_for_cards()`, `get_prices_for_cards()`, `get_legalities_for_cards()`
- [ ] All methods return typed Pydantic models (not `list[dict]`)
- [ ] Add `LRUCacheWithTTL` for frequently accessed data
- [ ] Add retry decorator for transient MongoDB errors
- [ ] Add index verification on startup
- [ ] All tests pass

## Dependencies
- Story 002: Unified Data Access Layer (old CLI reference implementation)
- Story 012: Port MTG domain models (provides typed return types)

## Priority: High

## Notes
- **Reference implementation**: `training_data/generate_synthetic_data/data_access.py` (1253 lines)
- **Key challenge**: The old CLI uses MongoDB aggregation pipelines that reference `mtg_json.*` collection names and camelCase field paths. The TrainForge config uses different collection names (`synthetic_queries.mtg_cards`). These must be reconciled.
- The `_translate_card_filters()` method in old CLI handles JSON-stringified array fields (subtypes, colors, keywords stored as `'["W"]'` strings) — this logic must be preserved
- Consider keeping old CLI's `MTGDataAccess` class intact and creating an adapter, or porting the aggregation pipelines to the new collection schema
- Cache TTL should match old CLI (300s default)
- Connection pooling settings should be configurable via TrainForge config
