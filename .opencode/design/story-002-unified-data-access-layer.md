# Design: Unified Data Access Layer (Story 002)

## Overview
Create a single `MTGDataAccess` class in `training_data/generate_synthetic_data/data_access.py` that provides typed, high-level access to all MongoDB collections with pre-built joins. This eliminates raw pymongo queries from all 23 generators and ensures consistent, enriched data access across the pipeline.

## User Story Reference
`.opencode/discovery/story-002-unified-data-access-layer.md`

---

## Architecture Decisions

### 1. Single Class with Typed Methods (Facade Pattern)
**Decision**: One `MTGDataAccess` class with explicit typed methods for each data need.
**Why**: 
- Generators currently write raw pymongo queries with inconsistent field mappings
- Single class = single source of truth, easy to maintain, easy to test
- Typed returns (Pydantic models from Story 3) enable IDE autocomplete and runtime validation
**Trade-offs**:
- ✅ Centralized query logic, consistent field mapping, type safety
- ✅ Easy to add caching, connection pooling, retries in one place
- ⚠️ Large class (~30 methods) - mitigate with clear section organization

### 2. MongoDB Aggregation Pipelines for Joins
**Decision**: Use aggregation pipelines (`$lookup`, `$unwind`, `$project`) for all multi-collection joins.
**Why**: 
- Current generators do manual joins in Python (N+1 queries, slow, inconsistent)
- Aggregation runs on server, returns enriched documents in single round-trip
- MongoDB optimizes pipeline execution
**Trade-offs**:
- ✅ Performance (single query), consistency, server-side filtering
- ⚠️ Pipeline complexity - mitigate with helper methods and comments

### 3. Connection Pooling with Context Manager
**Decision**: Internal `MongoClient` with `maxPoolSize=50`, context manager support (`with MTGDataAccess() as db:`).
**Why**: 
- Generators run concurrently in same process; pooling prevents connection exhaustion
- Context manager ensures clean shutdown
**Trade-offs**:
- ✅ Resource management, concurrent safety
- ⚠️ Long-lived client - ensure proper cleanup on process exit

### 4. Graceful Degradation for Missing Collections
**Decision**: Methods return empty list/log warning if collection missing, never raise.
**Why**: 
- Some environments may not have all collections (dev, CI, partial restores)
- Generators should degrade gracefully, not crash
**Trade-offs**:
- ✅ Resilient, works in partial environments
- ⚠️ Silent failures - mitigate with structured logging (warning level)

### 5. Index Verification on Startup
**Decision**: `verify_indexes()` method called on first use; creates missing indexes.
**Why**: 
- Aggregation performance depends on proper indexes
- Ensures consistent performance across environments
**Trade-offs**:
- ✅ Self-healing, no manual index management
- ⚠️ Requires write permissions - handle gracefully if read-only

---

## Files to Create/Modify

### New Files
| File | Purpose | Key Responsibilities |
|------|---------|---------------------|
| `training_data/generate_synthetic_data/data_access.py` | Unified data access layer | All MongoDB queries, aggregation pipelines, connection management, caching |

### Modified Files
| File | Changes | Reason |
|------|---------|--------|
| `training_data/generate_synthetic_data/domain_models.py` | (Story 3) Pydantic models returned by data access | Data access layer returns typed models |
| `training_data/generate_synthetic_data/base_generator.py` | (Story 1) Inject `MTGDataAccess` instance | Generators use data access instead of raw collections |
| `training_data/generate_synthetic_data/main.py` | Create `MTGDataAccess` instance, pass to generators | Single initialization point |

---

## Task Breakdown (Ordered by Dependency)

### Task 1: Create `MTGDataAccess` Class with Connection Management
- **Files**: `data_access.py` (new)
- **Description**: Core class with MongoDB client, connection pooling, context manager, index verification
- **Acceptance Criteria**:
  - `__init__(uri, username, password, db_name="mtg_json")` with connection pooling (maxPoolSize=50)
  - Context manager support (`__enter__`, `__exit__`)
  - `verify_indexes()` creates missing indexes on startup
  - `close()` method for explicit cleanup
  - Handles auth, timeout (30s default), retry logic

### Task 2: Implement Core Card Enrichment Methods
- **Files**: `data_access.py`
- **Description**: Methods returning `CardWithMetadata` with all joins (EDHREC, prices, legalities, rulings, keywords)
- **Acceptance Criteria**:
  - `get_cards_enriched(filters, limit)` → `list[CardWithMetadata]`
  - `get_card_by_name(name)` → `CardWithMetadata | None`
  - `get_cards_by_keyword_mechanic(keyword, limit)` → `list[CardWithMetadata]`
  - `get_cards_by_archetype(archetype, limit)` → `list[CardWithMetadata]`
  - Aggregation pipeline joins: cards ← cardPrices ← cardLegalities ← cardRulings ← keywords
  - Filters support: color_identity, type, rarity, cmc range, edhrec_rank range

### Task 3: Implement Combo & Commander Enrichment Methods
- **Files**: `data_access.py`
- **Description**: Methods for combo and commander data with full card details
- **Acceptance Criteria**:
  - `get_combos_enriched(filters, limit)` → `list[ComboWithCards]`
  - `get_commanders_enriched(filters, limit)` → `list[CommanderWithTags]`
  - Combo pipeline: variants → unwind uses → lookup cards → enrich each card
  - Commander pipeline: edhrec.commanders → enrich with card details from mtg_json.cards

### Task 4: Implement Lookup & Analytics Methods
- **Files**: `data_access.py`
- **Description**: Specialized query methods for generators needing specific data patterns
- **Acceptance Criteria**:
  - `get_rulings_for_cards(card_names)` → `list[Ruling]`
  - `get_prices_for_cards(card_names)` → `dict[str, PriceData]`
  - `get_legalities_for_cards(card_names)` → `dict[str, Legalities]`
  - `get_keyword_taxonomy()` → `dict[str, list[str]]` (keyword → [descriptions])
  - `get_archetype_data()` → `list[Archetype]`
  - `get_training_game_data()` → `list[GameState]`
  - `get_top_cards_by_edhrec_rank(color_identity, limit)` → `list[CardWithMetadata]`
  - `get_budget_alternatives(expensive_card, max_price, limit)` → `list[CardWithMetadata]`
  - `get_synergy_partners(card_name, limit)` → `list[CardWithMetadata]`
  - `get_commander_staples(color_identity, min_decks, limit)` → `list[CardWithMetadata]`
  - `get_format_legalities(format_name, limit)` → `list[CardWithMetadata]`
  - `calculate_color_identity(mana_cost, text, color_indicator)` → `list[str]`
  - `search_cards_text(regex, filters, limit)` → `list[CardWithMetadata]`

### Task 5: Implement Caching Layer
- **Files**: `data_access.py`
- **Description**: In-memory caching for frequently accessed reference data
- **Acceptance Criteria**:
  - Cache commanders, keywords, archetypes on first access
  - TTL-based invalidation (configurable, default 1 hour)
  - Cache stats logging (hits/misses)
  - Thread-safe (use `threading.RLock`)

### Task 6: Integrate with Generators
- **Files**: `main.py`, `base_generator.py`, all generator files
- **Description**: Replace raw pymongo collections with `MTGDataAccess` methods
- **Acceptance Criteria**:
  - `main.py` creates single `MTGDataAccess` instance, passes to generators
  - `BaseGenerator` accepts `data_access: MTGDataAccess` parameter
  - All 23 generators use `data_access.get_cards_enriched()` etc. instead of raw queries
  - Zero direct `pymongo` imports in generator files

---

## Data Models / Interfaces

### Pydantic Models (from Story 3 - `domain_models.py`)
```python
# These are defined in Story 3; data_access.py imports and returns them
from domain_models import (
    CardWithMetadata, ComboWithCards, CommanderWithTags,
    Ruling, PriceData, Legalities, Archetype, GameState,
    Keyword, Article, Guide
)
```

### Method Signatures (Core)

```python
class MTGDataAccess:
    def __init__(
        self,
        uri: str = "mongodb://localhost:27017",
        username: str = "root",
        password: str = "whatever",
        database: str = "mtg_json",
        max_pool_size: int = 50,
        server_selection_timeout_ms: int = 30000,
    ): ...
    
    def __enter__(self) -> "MTGDataAccess": ...
    def __exit__(self, *args) -> None: ...
    def close(self) -> None: ...
    def verify_indexes(self) -> None: ...
    
    # === Core Enrichment Methods ===
    def get_cards_enriched(
        self,
        filters: dict | None = None,
        limit: int = 100,
        skip: int = 0,
    ) -> list[CardWithMetadata]: ...
    
    def get_card_by_name(self, name: str) -> CardWithMetadata | None: ...
    
    def get_cards_by_keyword_mechanic(
        self, keyword: str, limit: int = 100
    ) -> list[CardWithMetadata]: ...
    
    def get_cards_by_archetype(
        self, archetype: str, limit: int = 100
    ) -> list[CardWithMetadata]: ...
    
    # === Combo & Commander Methods ===
    def get_combos_enriched(
        self,
        filters: dict | None = None,
        limit: int = 100,
    ) -> list[ComboWithCards]: ...
    
    def get_commanders_enriched(
        self,
        filters: dict | None = None,
        limit: int = 100,
    ) -> list[CommanderWithTags]: ...
    
    # === Lookup Methods ===
    def get_rulings_for_cards(self, card_names: list[str]) -> list[Ruling]: ...
    def get_prices_for_cards(self, card_names: list[str]) -> dict[str, PriceData]: ...
    def get_legalities_for_cards(self, card_names: list[str]) -> dict[str, Legalities]: ...
    def get_keyword_taxonomy(self) -> dict[str, list[str]]: ...
    def get_archetype_data(self) -> list[Archetype]: ...
    def get_training_game_data(self) -> list[GameState]: ...
    
    # === Analytics Methods ===
    def get_top_cards_by_edhrec_rank(
        self, color_identity: list[str], limit: int = 50
    ) -> list[CardWithMetadata]: ...
    
    def get_budget_alternatives(
        self, expensive_card: str, max_price: float, limit: int = 10
    ) -> list[CardWithMetadata]: ...
    
    def get_synergy_partners(
        self, card_name: str, limit: int = 20
    ) -> list[CardWithMetadata]: ...
    
    def get_commander_staples(
        self, color_identity: list[str], min_decks: int, limit: int = 50
    ) -> list[CardWithMetadata]: ...
    
    def get_format_legalities(
        self, format_name: str, limit: int = 100
    ) -> list[CardWithMetadata]: ...
    
    # === Utility Methods ===
    def calculate_color_identity(
        self, mana_cost: str | None, text: str | None, color_indicator: list[str] | None
    ) -> list[str]: ...
    
    def search_cards_text(
        self, regex: str, filters: dict | None = None, limit: int = 100
    ) -> list[CardWithMetadata]: ...
```

---

## MongoDB Aggregation Pipeline Examples

### 1. Cards Enriched with Prices, Legalities, Rulings, Keywords
```python
def get_cards_enriched(self, filters: dict | None = None, limit: int = 100) -> list[CardWithMetadata]:
    pipeline = [
        {"$match": filters or {}},
        # Join prices (cardPrices collection, by uuid)
        {"$lookup": {
            "from": "cardPrices",
            "localField": "uuid",
            "foreignField": "uuid",
            "as": "price_docs"
        }},
        {"$addFields": {
            "prices": {"$arrayElemAt": ["$price_docs", 0]}
        }},
        # Join legalities (cardLegalities collection, by uuid)
        {"$lookup": {
            "from": "cardLegalities",
            "localField": "uuid",
            "foreignField": "uuid",
            "as": "legality_docs"
        }},
        # Join rulings (cardRulings collection, by uuid)
        {"$lookup": {
            "from": "cardRulings",
            "localField": "uuid",
            "foreignField": "uuid",
            "as": "ruling_docs"
        }},
        # Join keywords (keywords collection, by keyword name)
        {"$lookup": {
            "from": "keywords",
            "localField": "keywords",
            "foreignField": "keyword",
            "as": "keyword_docs"
        }},
        # Project to clean shape
        {"$project": {
            "name": 1, "uuid": 1, "scryfallId": 1,
            "manaCost": 1, "type": 1, "text": 1, "oracleText": 1,
            "power": 1, "toughness": 1, "loyalty": 1,
            "colors": 1, "colorIdentity": 1,
            "subtypes": 1, "supertypes": 1, "keywords": 1,
            "edhrecRank": 1, "edhrecSalt": 1, "edhrecTags": 1,
            "legalities": 1,
            "prices": {
                "usd": "$prices.usd", "usd_foil": "$prices.usd_foil",
                "eur": "$prices.eur", "eur_foil": "$prices.eur_foil",
                "tix": "$prices.tix", "lastUpdated": "$prices.lastUpdated"
            },
            "rulings": {
                "$map": {
                    "input": "$ruling_docs",
                    "as": "r",
                    "in": {
                        "uuid": "$$r.uuid", "date": "$$r.date",
                        "text": "$$r.text", "source": "$$r.source"
                    }
                }
            },
            "keyword_details": "$keyword_docs"
        }},
        {"$limit": limit}
    ]
    return [CardWithMetadata(**doc) for doc in self.cards.aggregate(pipeline)]
```

### 2. Combos with Full Card Details
```python
def get_combos_enriched(self, filters: dict | None = None, limit: int = 100) -> list[ComboWithCards]:
    pipeline = [
        {"$match": {"status": "OK", **(filters or {})}},
        {"$unwind": "$uses"},
        {"$lookup": {
            "from": "cards",  # mtg_json.cards
            "localField": "uses.card.name",
            "foreignField": "name",
            "as": "card_details"
        }},
        {"$addFields": {
            "uses.card_details": {"$arrayElemAt": ["$card_details", 0]}
        }},
        {"$group": {
            "_id": "$_id",
            "name": {"$first": "$name"},
            "description": {"$first": "$description"},
            "produces": {"$first": "$produces"},
            "notes": {"$first": "$notes"},
            "requires": {"$first": "$requires"},
            "tags": {"$first": "$tags"},
            "commanders": {"$first": "$commanders"},
            "uses": {"$push": "$uses"}
        }},
        {"$limit": limit}
    ]
    return [ComboWithCards(**doc) for doc in self.combos.aggregate(pipeline)]
```

### 3. Commanders with EDHREC Tags + Card Details
```python
def get_commanders_enriched(self, filters: dict | None = None, limit: int = 100) -> list[CommanderWithTags]:
    pipeline = [
        {"$match": filters or {}},
        {"$lookup": {
            "from": "cards",  # mtg_json.cards
            "localField": "cardUuid",
            "foreignField": "uuid",
            "as": "card_details"
        }},
        {"$addFields": {
            "card_details": {"$arrayElemAt": ["$card_details", 0]}
        }},
        {"$limit": limit}
    ]
    return [CommanderWithTags(**doc) for doc in self.commanders.aggregate(pipeline)]
```

### 4. Budget Alternatives (Cards with Similar Effects, Lower Price)
```python
def get_budget_alternatives(self, expensive_card: str, max_price: float, limit: int = 10) -> list[CardWithMetadata]:
    # First get the expensive card's oracle text and color identity
    card = self.cards.find_one({"name": expensive_card})
    if not card:
        return []
    
    # Search for cards with similar keywords/effects, lower price
    pipeline = [
        {"$match": {
            "keywords": {"$in": card.get("keywords", [])},
            "colorIdentity": {"$in": card.get("colorIdentity", [])},
        }},
        {"$lookup": {
            "from": "cardPrices",
            "localField": "uuid",
            "foreignField": "uuid",
            "as": "price_docs"
        }},
        {"$addFields": {
            "min_price": {"$min": "$price_docs.usd"}
        }},
        {"$match": {"min_price": {"$lte": max_price, "$ne": None}}},
        {"$sort": {"min_price": 1, "edhrecRank": 1}},
        {"$limit": limit}
    ]
    return [CardWithMetadata(**doc) for doc in self.cards.aggregate(pipeline)]
```

### 5. Synergy Partners (Cards Appearing in Same Combos)
```python
def get_synergy_partners(self, card_name: str, limit: int = 20) -> list[CardWithMetadata]:
    pipeline = [
        {"$match": {"status": "OK"}},
        {"$unwind": "$uses"},
        {"$match": {"uses.card.name": card_name}},
        {"$unwind": "$uses"},
        {"$match": {"uses.card.name": {"$ne": card_name}}},
        {"$group": {
            "_id": "$uses.card.name",
            "count": {"$sum": 1},
            "card_data": {"$first": "$uses.card"}
        }},
        {"$sort": {"count": -1}},
        {"$limit": limit},
        {"$lookup": {
            "from": "cards",
            "localField": "_id",
            "foreignField": "name",
            "as": "card_details"
        }},
        {"$addFields": {"card_details": {"$arrayElemAt": ["$card_details", 0]}}},
        {"$replaceRoot": {"newRoot": "$card_details"}}
    ]
    return [CardWithMetadata(**doc) for doc in self.combos.aggregate(pipeline)]
```

---

## Integration Points with Existing Code

### 1. `main.py` - Single Initialization Point
```python
# Before: Multiple raw collections passed to each generator
# After: Single MTGDataAccess instance
from data_access import MTGDataAccess

def main():
    # ... existing arg parsing ...
    
    with MTGDataAccess(args.mongo_uri, args.mongo_user, args.mongo_pass) as data_access:
        data_access.verify_indexes()
        
        # Pass data_access to all generators
        if args.combo_queries > 0:
            GenerateComboQueries(
                data_access=data_access,  # NEW
                save_item=save_item,
                models=models,
                validation_pct=args.validation_pct,
                target_count=args.combo_queries,
                metrics=make_metrics("GenerateComboQueries")
            ).generate()
```

### 2. `base_generator.py` - Dependency Injection
```python
class BaseGenerator(ABC, Generic[T]):
    def __init__(
        self,
        data_access: MTGDataAccess,  # NEW - injected
        models: dict[ModelType, Model],
        validation_pct: float,
        target_count: int,
        save_item: Callable[[QuestionAnswerEnhanced], None],
        # ... other params
    ):
        self.data_access = data_access
        # ...
```

### 3. Generator Refactoring Example: `generate_combo_queries.py`
```python
# BEFORE: Raw pymongo collections passed in __init__
class GenerateComboQueries:
    def __init__(self, combos_collection, card_collection, scryfall_client, ...):
        self.combos_collection = combos_collection
        self.card_collection = card_collection
        # ...

# AFTER: Use data_access
class GenerateComboQueries(BaseGenerator[ComboWithCards]):
    def __init__(self, data_access: MTGDataAccess, ...):
        super().__init__(data_access=data_access, ...)
    
    def get_data_batches(self) -> list[ComboWithCards]:
        return self.data_access.get_combos_enriched(limit=self.target_count * 2)
    
    def build_prompt(self, template: TemplateConfig, combo: ComboWithCards) -> str:
        # combo.cards already enriched with full CardWithMetadata
        return self._build_combo_prompt(combo.cards, combo.description, ...)
```

### 4. `scryfall_mongodb.py` - Deprecate/Wrap
- `ScryfallMongo.search_scryfall()` → `data_access.search_cards_text()`
- `ScryfallMongo` methods that query `cards` collection → delegate to `data_access`
- Keep Scryfall API client methods (external API calls) if any

---

## Testing Strategy

### Unit Tests for `MTGDataAccess`
- **Connection Management**: Context manager opens/closes correctly; pool size respected
- **Index Verification**: Creates missing indexes; idempotent on re-run
- **Card Enrichment**: Returns `CardWithMetadata` with all joined fields populated
- **Combo Enrichment**: Returns `ComboWithCards` with full card details for each piece
- **Commander Enrichment**: Returns `CommanderWithTags` with card details
- **Analytics Methods**: Budget alternatives, synergy partners, staples return correct shapes
- **Caching**: Repeated calls to `get_keyword_taxonomy()` hit cache; TTL expiration works
- **Error Handling**: Missing collection returns empty list + warning log

### Integration Tests
- **Full Pipeline**: `main.py` with `--dry-run --phase1` produces same output counts as before
- **Generator Migration**: Each refactored generator produces identical Q&A format
- **Performance**: Aggregation queries complete within timeout (30s); connection pool reused

### Regression Tests
- Compare MongoDB output documents before/after migration (category counts, field presence)
- Verify `ValidationMetrics` structure unchanged

---

## Potential Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Aggregation pipelines too slow | Medium | High | Add `explain()` analysis; create compound indexes; limit pipeline stages |
| Missing collections in some environments | High | Medium | Graceful degradation (empty list + warning); document required collections |
| Pydantic model validation failures | Medium | High | Use `extra="ignore"` in ConfigDict; make all fields Optional with defaults |
| Connection pool exhaustion | Low | High | `maxPoolSize=50`; context manager ensures cleanup; monitor pool stats |
| Breaking changes to generator output | Medium | High | Pilot with 2 generators first; comprehensive integration tests |
| Cache staleness | Low | Medium | TTL-based invalidation; cache stats logging; manual `clear_cache()` method |

---

## Handoff to Implementer

**Design Document**: This file (`.opencode/design/story-002-unified-data-access-layer.md`)

**User Story**: `.opencode/discovery/story-002-unified-data-access-layer.md`

**Estimated Complexity**: High (core infrastructure, affects all generators)

**Key Files to Create/Modify**:
1. `training_data/generate_synthetic_data/data_access.py` (NEW - main deliverable)
2. `training_data/generate_synthetic_data/domain_models.py` (Story 3 dependency)
3. `training_data/generate_synthetic_data/base_generator.py` (Story 1 - add data_access param)
4. `training_data/generate_synthetic_data/main.py` (initialize and pass data_access)
5. All 23 generator files (refactor to use data_access)

**Start With**: Task 1 - Create `MTGDataAccess` class with connection management and `verify_indexes()`

**Acceptance Criteria** (from user story):
- [ ] Class `MTGDataAccess` in `data_access.py`
- [ ] Single MongoDB client connection managed internally (connection pooling, maxPoolSize=50)
- [ ] Typed dataclasses/Pydantic models for all returned data (from Story 3)
- [ ] Pre-built join methods returning enriched objects (all 18+ methods listed)
- [ ] Aggregation pipelines for joins (cards+EDHREC+prices+legalities+rulings, combos+cards+rulings, commanders+tags)
- [ ] All methods return typed Pydantic models (not raw dicts)
- [ ] Methods handle missing collections gracefully (return empty list, log warning)
- [ ] Connection pooling configured (maxPoolSize=50)
- [ ] Query timeout default 30s, configurable
- [ ] Indexes verified on startup (create if missing)
- [ ] Context manager support (`with MTGDataAccess() as db:`)
- [ ] Caching for frequently accessed data (commanders, keywords, archetypes)