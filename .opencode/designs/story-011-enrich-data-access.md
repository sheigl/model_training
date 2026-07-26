# Design: Enrich TrainForge MTGDataAccess with Typed Joins

## Overview
Port the 1253-line enriched MTG data access layer from the old CLI (`training_data/generate_synthetic_data/data_access.py`) into TrainForge's `MTGDataAccess` (`trainforge/domains/mtg/data_source.py`), adding aggregation pipelines, typed Pydantic return models, caching, retry logic, and analytics methods.

## User Story Reference
`.opencode/discovery/story-011-tf-enrich-data-access.md`

## Architecture Decisions

**Decision 1: Add `aggregate()` to `MongoDataSource` base class**
The current `MongoDataSource` only exposes `get_records()` (simple `find()`) — no aggregation pipeline support. Every enriched method in the old CLI uses `collection.aggregate(pipeline, allowDiskUse=True)`. Adding a single `aggregate()` method to the base keeps the pattern clean and enables all future enrichment work.

- **Alternative rejected**: Keeping pipelines private to MTGDataAccess and accessing pymongo's `aggregate` via `_get_collection().aggregate()`. This would duplicate the collection-name-parsing logic and couple MTGDataAccess to pymongo internals.
- **API**: `def aggregate(self, collection: str, pipeline: list[dict], allow_disk_use: bool = True) -> list[dict]`

**Decision 2: Dual collection namespace strategy**
Existing simple methods keep their `synthetic_queries.*` namespace (`synthetic_queries.mtg_cards`, `synthetic_queries.mtg_articles`). Enriched methods reference actual MongoDB databases directly (`mtg_json.cards`, `commander_spellbook.variants`, `edhrec.commanders`).

- **Why**: The `synthetic_queries` database contains rearranged/renamed collections. The enriched pipelines were built against the original database schema (`mtg_json`, `commander_spellbook`, `edhrec`). Migrating data is out of scope — the enriched pipelines must run against the original schema.
- **How**: `MongoDataSource.get_records()` and `aggregate()` already support `"db.collection"` syntax. Simple methods pass `f"{self.db_name}.mtg_cards"` (db = `synthetic_queries`). Enriched methods pass `"mtg_json.cards"` directly.
- **Trade-off**: Slightly confusing dual namespace. Mitigated by clear docstrings on each method and the collection-name-mapping table in the architecture doc.

**Decision 3: Port all domain models into TrainForge (merge Story 12 into this story)**
Story 12 (port domain models) is a prerequisite but not yet done. Rather than block this story, include the model port as a task here.

- **Why**: All enriched methods need `CardWithMetadata`, `ComboWithCards`, `CommanderWithTags` etc. as return types. Tests can't be written without models. The old CLI's `domain_models.py` (605 lines) is stable and well-tested — it needs a clean copy with import paths adjusted.
- **Location**: `trainforge/domains/mtg/models.py`
- **Changes from original**: Import paths, add module-level `__all__`, add `model_rebuild()` calls.

**Decision 4: Keep aggregation pipelines as private `_build_*` methods**
The old CLI has cleanly separated pipeline builders (`_build_card_enrichment_pipeline`, `_build_combo_pipeline`, `_build_commander_pipeline`). Keep this pattern. The public methods call the private builder, run the aggregation, and convert results to typed models.

- **Why**: Pipeline builders are testable in isolation. Unit tests can verify stage order, field mappings, filter translation without mocking MongoDB.

**Decision 5: Port `_translate_card_filters()` verbatim**
This method handles the tricky JSON-stringified array fields (`colorIdentity` stored as `'["W","U"]'`, `keywords` stored as `'["Flying","Trample"]'`). The old implementation is battle-tested — don't re-invent.

## Collection Name Mapping

When the implementer writes enriched methods, these are the collection references to use:

| Purpose | Old CLI Reference | TrainForge Enriched Reference |
|---------|------------------|-------------------------------|
| Cards | `mtg_json.cards` | `mtg_json.cards` |
| Card prices | `mtg_json.cardPrices` | `mtg_json.cardPrices` |
| Card legalities | `mtg_json.cardLegalities` | `mtg_json.cardLegalities` |
| Card rulings | `mtg_json.cardRulings` | `mtg_json.cardRulings` |
| Keywords | `mtg_json.keywords` | `mtg_json.keywords` |
| Commander Spellbook combos | `commander_spellbook.variants` | `commander_spellbook.variants` |
| EDHREC commanders | `edhrec.commanders` | `edhrec.commanders` |
| EDHREC articles | `edhrec.articles` | `edhrec.articles` |
| EDHREC guides | `edhrec.guides` | `edhrec.guides` |
| EDHREC game-changers | `edhrec.game-changers` | `edhrec.game-changers` |
| MTG rules | `mtg_rules.rules` | `mtg_rules.rules` |
| MTG glossary | `mtg_rules.glossary` | `mtg_rules.glossary` |
| Archetypes | `mtg_archetypes.archetypes` | `mtg_archetypes.archetypes` |
| Scryfall oracle | `scryfall.oracle_cards` | `scryfall.oracle_cards` |
| Training games | `mtg_training.games` | `mtg_training.games` |

Simple (existing) methods keep using `synthetic_queries.mtg_cards`, `synthetic_queries.mtg_articles`, etc.

## Files to Create/Modify

### New Files

| File | Purpose | Key Responsibilities |
|------|---------|---------------------|
| `trainforge/domains/mtg/models.py` | Pydantic v2 domain models | Card, CardWithMetadata, PriceData, Ruling, CardLegalities, Combo, ComboWithCards, Commander, CommanderWithTags, Article, Guide, Archetype, Rule, GlossaryTerm, Keyword, etc. |
| `trainforge/tests/domains/mtg/test_data_source.py` | Unit tests for enriched MTGDataAccess | 40+ tests covering cache, retry, pipelines, lookups, analytics, filter translation |
| `trainforge/tests/domains/mtg/__init__.py` | Package init | Empty init |

### Modified Files

| File | Changes | Reason |
|------|---------|--------|
| `trainforge/src/trainforge/data_source.py` | Add `aggregate()` method to `DataSource` ABC and `MongoDataSource` | Enrichment pipelines need aggregation support |
| `trainforge/domains/mtg/data_source.py` | Complete rewrite — add 25+ new methods, caching, retry, index verification, pipeline builders | Core of the story — port from old CLI |

## Task Breakdown (Ordered by Dependency)

### Task 1: Add `aggregate()` to MongoDataSource base class

**Files**: `trainforge/src/trainforge/data_source.py`

**Description**: Add `aggregate()` to both `DataSource` (ABC) and `MongoDataSource` (impl):

```python
# In DataSource (ABC):
@abstractmethod
def aggregate(
    self, collection: str, pipeline: list[dict], allow_disk_use: bool = True
) -> list[dict]:
    """Run an aggregation pipeline on a collection.
    
    Args:
        collection: Collection name (supports 'db.coll' or just 'coll')
        pipeline: List of aggregation stages
        allow_disk_use: Allow $sort/$group stages to use disk
    
    Returns:
        List of result documents
    """
    ...

# In MongoDataSource:
def aggregate(
    self, collection: str, pipeline: list[dict], allow_disk_use: bool = True
) -> list[dict]:
    """Run aggregation pipeline. Collection supports 'db.coll' syntax."""
    parts = collection.split(".", 1)
    if len(parts) == 2:
        db_name, coll_name = parts
    else:
        db_name = self.DEFAULT_DATABASE
        coll_name = collection
    coll = self._get_collection(db_name, coll_name)
    return list(coll.aggregate(pipeline, allowDiskUse=allow_disk_use))
```

**Acceptance Criteria**:
- [ ] `DataSource.aggregate()` declared as abstractmethod
- [ ] `MongoDataSource.aggregate()` parses `db.coll` syntax (same pattern as `get_records`)
- [ ] Returns `list[dict]` from aggregation cursor
- [ ] Handles missing collection gracefully (returns empty list)
- [ ] Default `allowDiskUse=True`
- [ ] Existing tests pass

---

### Task 2: Create LRUCacheWithTTL and retry decorator utilities

**Files**: `trainforge/domains/mtg/data_source.py` (as module-level definitions, before the class)

**Description**: Port `LRUCacheWithTTL` class and `retry_on_transient_error` decorator from old CLI. Identical implementation.

```python
class LRUCacheWithTTL:
    """Thread-safe LRU cache with TTL support."""
    
    def __init__(self, maxsize: int = 1000, ttl: int = 300):
        self.maxsize = maxsize
        self.ttl = ttl
        self._cache: dict[str, tuple[Any, float]] = {}
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str) -> Any | None:
        with self._lock:
            if key in self._cache:
                value, timestamp = self._cache[key]
                if time.time() - timestamp < self.ttl:
                    self._hits += 1
                    return value
                del self._cache[key]
            self._misses += 1
            return None
    
    def set(self, key: str, value: Any) -> None:
        with self._lock:
            if len(self._cache) >= self.maxsize:
                oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
                del self._cache[oldest_key]
            self._cache[key] = (value, time.time())
    
    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
    
    def stats(self) -> dict[str, int]:
        with self._lock:
            return {"hits": self._hits, "misses": self._misses, "size": len(self._cache)}
```

```python
def retry_on_transient_error(max_retries: int = 3, base_delay: float = 0.5):
    """Retry on ConnectionFailure, ServerSelectionTimeoutError, OperationFailure."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (ConnectionFailure, ServerSelectionTimeoutError, OperationFailure) as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(f"Transient error (attempt {attempt+1}/{max_retries}): {e}. Retrying in {delay:.1f}s...")
                        time.sleep(delay)
                    else:
                        logger.error(f"All retries exhausted: {e}")
            raise last_exception
        return wrapper
    return decorator
```

**Acceptance Criteria**:
- [ ] Thread-safe set/get/clear/stats
- [ ] TTL expiration (test with ttl=0)
- [ ] LRU eviction (test with maxsize=2)
- [ ] Retry on transient errors, pass-through on success, raise on exhaustion

---

### Task 3: Port domain models to TrainForge

**Files**: Create `trainforge/domains/mtg/models.py`

**Description**: Port all 22 model classes from `training_data/generate_synthetic_data/domain_models.py` (605 lines). Keep every field, alias, validator, computed property, and factory method. Changes:

1. Remove the leading `from .domain_models import ...` comment pattern — no relative import into `domain_models`
2. Keep `from __future__ import annotations`
3. Keep all classes: `MongoModel`, `CardFace`, `Card`, `CardWithMetadata`, `PriceData`, `Ruling`, `Legality`, `CardLegalities`, `ComboCard`, `ComboProduces`, `Combo`, `ComboWithCards`, `Commander`, `CommanderWithTags`, `Archetype`, `Article`, `GuideChapter`, `Guide`, `GameState`, `Rule`, `GlossaryTerm`, `Keyword`
4. Add `__all__` export list
5. Keep `model_rebuild()` calls at module end: `Card.model_rebuild()`, `Combo.model_rebuild()`, `Rule.model_rebuild()`
6. Update imports: `from pydantic import BaseModel, ConfigDict, Field, field_validator`

**Acceptance Criteria**:
- [ ] All 22 model classes exist with correct fields and aliases
- [ ] `CardWithMetadata` inherits from `Card`
- [ ] `ComboWithCards(Combo)` has `cards: list[CardWithMetadata]`
- [ ] `CommanderWithTags(Commander)` has `card_details: CardWithMetadata | None`
- [ ] All computed properties work (`cmc`, `is_commander_legal`, `best_price`, etc.)
- [ ] `Card.from_dict()` factory method works with MongoDB docs
- [ ] `Card.to_prompt_detail()` formats correctly
- [ ] `from trainforge.domains.mtg.models import CardWithMetadata, ComboWithCards` works

---

### Task 4: Enrich MTGDataAccess with all methods

**Files**: `trainforge/domains/mtg/data_source.py`

**Description**: This is the largest task. Add the following to the existing `MTGDataAccess` class, which inherits from `MongoDataSource`.

#### 4a: Updated __init__

```python
def __init__(self, uri: str = "mongodb://localhost:27017", **kwargs):
    super().__init__(uri=uri, **kwargs)
    self.db_name = "synthetic_queries"  # For backward compat with simple methods
    self._cache = LRUCacheWithTTL(maxsize=kwargs.pop("cache_maxsize", 1000), ttl=kwargs.pop("cache_ttl", 300))
    self._indexes_verified = False
```

#### 4b: Class-level constants (port from old CLI)

```python
REQUIRED_COLLECTIONS = {
    "mtg_json": ["cards", "cardPrices", "cardLegalities", "cardRulings", "keywords"],
    "commander_spellbook": ["variants"],
    "edhrec": ["commanders", "articles", "guides", "game-changers"],
    "mtg_archetypes": ["archetypes"],
    "mtg_rules": ["rules", "glossary"],
    "scryfall": ["oracle_cards"],
}

REQUIRED_INDEXES = {
    "mtg_json.cards": [[("uuid", 1)], [("name", 1)], [("colorIdentity", 1)], [("keywords", 1)], [("edhrecRank", 1)]],
    "mtg_json.cardPrices": [[("uuid", 1)]],
    "mtg_json.cardLegalities": [[("uuid", 1)]],
    "mtg_json.cardRulings": [[("uuid", 1)]],
    "commander_spellbook.variants": [[("status", 1)], [("uses.card.name", 1)]],
    "edhrec.commanders": [[("cardUuid", 1)], [("numDecks", -1)], [("colorIdentity", 1)]],
    "mtg_rules.rules": [[("ruleNumber", 1)]],
    "mtg_rules.glossary": [[("term", 1)]],
}
```

#### 4c: Card enrichment pipeline

```python
@retry_on_transient_error()
def get_cards_enriched(self, filters=None, limit=100, skip=0, lite=False) -> list[CardWithMetadata]:
    """Get cards enriched with prices, legalities, rulings, keywords."""
    pipeline = self._build_card_enrichment_pipeline(filters or {}, limit, skip, lite=lite)
    try:
        docs = self.aggregate("mtg_json.cards", pipeline)
        return [self._convert_doc_to_model(d, CardWithMetadata) for d in docs]
    except Exception as e:
        logger.error("Error in get_cards_enriched: %s", e)
        return []

def _build_card_enrichment_pipeline(self, filters, limit, skip, lite=False) -> list[dict]:
    """Build aggregation pipeline for enriched card queries.
    
    Stages:
    1. $match (translated filters)
    2. If not lite: $lookup cardPrices, cardLegalities, cardRulings
    3. $addFields for projections
    4. $project to shape output
    5. $skip (if skip > 0)
    6. $sample {size: limit}
    7. $limit
    """
    processed_filters = self._translate_card_filters(filters or {})
    pipeline = [{"$match": processed_filters}] if processed_filters else [{"$match": {}}]
    
    # ... see old CLI lines 492-567 for exact pipeline stages
    # Key: lookup cardPrices by uuid, sort by date desc, pick latest
    # lookup cardLegalities by uuid, reshape to per-format dict
    # lookup cardRulings by uuid, sort by date desc, slice 5
    
    if skip > 0:
        pipeline.append({"$skip": skip})
    pipeline.append({"$sample": {"size": limit}})
    pipeline.append({"$limit": limit})
    return pipeline
```

#### 4d: Card filter translation

```python
def _translate_card_filters(self, filters: dict) -> dict:
    """Translate custom filter keys to MongoDB queries.
    
    Handles JSON-stringified arrays: colorIdentity, keywords stored as 
    '["W","U"]' strings instead of array.
    """
    # Port exactly from old CLI lines 392-468
    # - name: direct passthrough
    # - colorIdentity/colors: {"$regex": '"W"'} per color
    # - text/oracleText/text_regex: {"$regex": ..., "$options": "i"}
    # - keywords/keywords_regex: {"$regex": ..., "$options": "i"}
    # - rarity: {"$in": [...]} or direct
    # - Combine all with $and if multiple
```

#### 4e: Model conversion helper

```python
def _convert_doc_to_model(self, doc: dict, model_class: type[T]) -> T | None:
    """Convert MongoDB doc to Pydantic model, returning None on failure."""
    try:
        return model_class(**doc)
    except Exception as e:
        logger.warning("Failed to convert doc to %s: %s", model_class.__name__, e)
        return None
```

#### 4f: Single card lookup

```python
@retry_on_transient_error()
def get_card_by_name(self, name: str) -> CardWithMetadata | None:
    cards = self.get_cards_enriched(filters={"name": name}, limit=1)
    return cards[0] if cards else None
```

#### 4g: Keyword mechanic lookup

```python
@retry_on_transient_error()
def get_cards_by_keyword_mechanic(self, keyword: str, limit: int = 100) -> list[CardWithMetadata]:
    return self.get_cards_enriched(filters={"keywords": keyword}, limit=limit)
```

#### 4h: Combo enrichment pipeline

```python
@retry_on_transient_error()
def get_combos_enriched(self, filters=None, limit=100) -> list[ComboWithCards]:
    """Get combos with enriched card details.
    
    Two-phase:
    1. Aggregate on commander_spellbook.variants to get combo data
    2. Python-side lookup of card details from mtg_json.cards by name
    """
    pipeline = self._build_combo_pipeline(filters or {}, limit)
    try:
        raw_combos = self.aggregate("commander_spellbook.variants", pipeline)
    except Exception as e:
        logger.error("Error in get_combos_enriched: %s", e)
        return []
    
    # Phase 2: Look up cards by name (cross-database)
    all_card_names = set()
    for combo in raw_combos:
        for use in combo.get("uses", []):
            if use.get("name"):
                all_card_names.add(use["name"])
    
    card_lookup = self._batch_lookup_cards_by_name(list(all_card_names))
    
    # Build ComboWithCards objects
    results = []
    for combo_doc in raw_combos:
        combo = self._convert_doc_to_model(combo_doc, ComboWithCards)
        if combo is None:
            continue
        combo.cards = [card_lookup.get(use.name) for use in (combo.uses or []) if use.name in card_lookup]
        results.append(combo)
    return results

def _build_combo_pipeline(self, filters, limit) -> list[dict]:
    """Build aggregation pipeline for combos.
    
    Match default: {"status": "OK"}
    Transform uses array from CSB shape to ComboCard shape
    Transform produces array to ComboProduces with regex classification
    """
    # Port from old CLI lines 681-756
```

#### 4i: Commander enrichment pipeline

```python
@retry_on_transient_error()
def get_commanders_enriched(self, filters=None, limit=100) -> list[CommanderWithTags]:
    pipeline = self._build_commander_pipeline(filters or {}, limit)
    try:
        docs = self.aggregate("edhrec.commanders", pipeline)
        return [CommanderWithTags(**doc) for doc in docs]
    except Exception as e:
        logger.error("Error in get_commanders_enriched: %s", e)
        return []

def _build_commander_pipeline(self, filters, limit) -> list[dict]:
    """Project edhrec.commanders fields to CommanderWithTags shape."""
    # Port from old CLI lines 758-791
```

#### 4j: Lookup methods

```python
@retry_on_transient_error()
def get_rulings_for_cards(self, card_names: list[str]) -> list[Ruling]:
    if not card_names:
        return []
    cache_key = f"rulings:{','.join(sorted(card_names))}"
    cached = self._cache.get(cache_key)
    if cached is not None:
        return cached
    # Get UUIDs from cards collection, then rulings
    # Port from old CLI lines 797-843

@retry_on_transient_error()
def get_prices_for_cards(self, card_names: list[str]) -> dict[str, PriceData]:
    if not card_names:
        return {}
    cache_key = f"prices:{','.join(sorted(card_names))}"
    # Port from old CLI lines 845-885

@retry_on_transient_error()
def get_legalities_for_cards(self, card_names: list[str]) -> dict[str, CardLegalities]:
    # Port from old CLI lines 887-921

@retry_on_transient_error()
def get_keyword_taxonomy(self) -> dict[str, list[str]]:
    # Port from old CLI lines 923-943

@retry_on_transient_error()
def get_archetype_data(self) -> list[Archetype]:
    # Port from old CLI lines 945-959
```

#### 4k: Analytics methods

```python
@retry_on_transient_error()
def get_top_cards_by_edhrec_rank(self, color_identity: list[str], limit: int = 50) -> list[CardWithMetadata]:
    return self.get_cards_enriched(
        filters={"colorIdentity": {"$all": color_identity}, "edhrecRank": {"$ne": None}},
        limit=limit
    )

@retry_on_transient_error()
def get_budget_alternatives(self, expensive_card: str, max_price: float, limit: int = 10) -> list[CardWithMetadata]:
    # Port from old CLI lines 1066-1108
    # Uses aggregation with $lookup to cardPrices, $match on min_price <= max_price

@retry_on_transient_error()
def get_synergy_partners(self, card_name: str, limit: int = 20) -> list[CardWithMetadata]:
    # Port from old CLI lines 1110-1145
    # Uses aggregation on commander_spellbook.variants with $unwind, $group, $lookup

@retry_on_transient_error()
def get_commander_staples(self, color_identity: list[str], min_decks: int, limit: int = 50) -> list[CardWithMetadata]:
    # Port from old CLI lines 1147-1170

@retry_on_transient_error()
def get_format_legalities(self, format_name: str, limit: int = 100) -> list[CardWithMetadata]:
    return self.get_cards_enriched(
        filters={f"legalities.{format_name.lower()}": "legal"},
        limit=limit
    )

def calculate_color_identity(self, mana_cost: str | None, text: str | None, color_indicator: list[str] | None) -> list[str]:
    # Pure Python — port from old CLI lines 1178-1210
    pass

@retry_on_transient_error()
def search_cards_text(self, regex: str, filters: dict | None = None, limit: int = 100) -> list[CardWithMetadata]:
    return self.get_cards_enriched(
        filters={"oracleText": {"$regex": regex, "$options": "i"}, **(filters or {})},
        limit=limit
    )
```

#### 4l: Batch card lookup helper

```python
def _batch_lookup_cards_by_name(self, names: list[str]) -> dict[str, CardWithMetadata]:
    """Batch lookup cards by name from mtg_json.cards."""
    if not names:
        return {}
    pipeline = [
        {"$match": {"name": {"$in": names}}},
        {"$group": {"_id": "$name", "doc": {"$first": "$$ROOT"}}},
    ]
    result = {}
    try:
        for group in self.aggregate("mtg_json.cards", pipeline):
            doc = group["doc"]
            doc.pop("_id", None)
            model = self._convert_doc_to_model(doc, CardWithMetadata)
            if model is not None:
                result[group["_id"]] = model
    except Exception as e:
        logger.warning("Error batch looking up cards: %s", e)
    return result
```

#### 4m: verify_indexes (port from old CLI)

```python
def verify_indexes(self) -> None:
    """Verify and create required indexes."""
    if self._indexes_verified:
        return
    with self._lock:
        if self._indexes_verified:
            return
        for coll_name, indexes in self.REQUIRED_INDEXES.items():
            try:
                parts = coll_name.split(".", 1)
                # Check collection exists
                coll = self._get_collection(parts[0], parts[1])
                if coll is None:
                    continue
                existing = {idx["name"]: idx for idx in coll.list_indexes()}
                for spec in indexes:
                    idx_name = "_".join(f"{k}_{v}" for k, v in spec)
                    if idx_name not in existing:
                        coll.create_index(spec, background=True, name=idx_name)
                        logger.info("Created index %s on %s", idx_name, coll_name)
            except Exception as e:
                logger.warning("Index error for %s: %s", coll_name, e)
        self._indexes_verified = True
```

#### 4n: Keep existing simple methods

The existing 8 methods (`get_cards`, `get_card_by_name`, `get_cards_by_type`, `get_cards_by_color`, `get_articles`, `get_rules`, `get_glossary`, `get_edhrec_data`, `get_game_changers`, `get_salty_cards`, `get_top_cards_by_color`) must be **preserved exactly as-is** for backward compatibility. The new enriched `get_card_by_name` overloads the old one (both return enriched now), which is the desired behavior.

**Acceptance Criteria** (for entire Task 4):
- [ ] `get_cards_enriched()` returns `list[CardWithMetadata]` with prices/legalities/rulings populated
- [ ] `get_cards_enriched(lite=True)` returns cards with only basic fields (no joins)
- [ ] `get_card_by_name("Sol Ring")` returns `CardWithMetadata | None`
- [ ] `get_cards_by_keyword_mechanic("Flying")` returns filtered cards
- [ ] `get_combos_enriched()` returns `list[ComboWithCards]` with card data populated
- [ ] `get_commanders_enriched()` returns `list[CommanderWithTags]` with card_details
- [ ] All lookup methods return typed models, with caching
- [ ] `get_rulings_for_cards([])` returns `[]` (empty input edge case)
- [ ] All analytics methods return typed models
- [ ] `_translate_card_filters()` handles JSON-stringified arrays
- [ ] `calculate_color_identity()` works with mana cost, text, color indicator
- [ ] `verify_indexes()` creates missing indexes, is idempotent
- [ ] All existing 8 simple methods still work and return `list[dict]`
- [ ] `_convert_doc_to_model()` returns `None` for invalid docs (graceful degradation)

---

### Task 5: Write unit tests

**Files**: Create `trainforge/tests/domains/mtg/test_data_source.py`

**Description**: Write 40+ tests covering all new functionality. Tests must not require a real MongoDB connection (patch `MongoClient`).

**Test classes and what they cover**:

| Test Class | Test Count | What |
|------------|-----------|------|
| `TestLRUCacheWithTTL` | 6 | set/get, miss, TTL, eviction, stats, clear |
| `TestRetryDecorator` | 3 | first-try, retry, exhaustion |
| `TestCardEnrichmentMethods` | 4 | enriched returns typed, missing collection, single lookup, not found |
| `TestTranslateCardFilters` | 5 | name, color regex, empty, text, rarity, combination |
| `TestPipelineBuilders` | 5 | full pipeline stages, lite skip, skip param, combo status filter, commander field mapping |
| `TestComboMethods` | 2 | enriched, missing collection |
| `TestCommanderMethods` | 2 | enriched, missing collection |
| `TestLookupMethods` | 5 | empty input, rulings caching, prices, legalities, keyword taxonomy |
| `TestAnalyticsMethods` | 5 | top_by_edhrec_rank, budget_alternatives, synergy_partners, calculate_color_identity, search_text |
| `TestIndexVerification` | 2 | creates indexes, idempotent |
| `TestConvertDocToModel` | 2 | valid doc, invalid doc |

Detailed test patterns are in `.opencode/context/testing.md`.

**Acceptance Criteria**:
- [ ] All tests pass: `pytest trainforge/tests/domains/mtg/ -v`
- [ ] No real MongoDB required
- [ ] 80%+ coverage report for `trainforge/domains/mtg/data_source.py`
- [ ] All edge cases covered (empty inputs, missing collections, invalid docs)

---

## Testing Strategy

| Layer | Scope | Approach |
|-------|-------|----------|
| **Unit** | LRUCacheWithTTL, retry decorator, _translate_card_filters, _build_*_pipeline, _convert_doc_to_model, calculate_color_identity | Direct instantiation, no mocking needed |
| **Mocked** | All public methods (get_cards_enriched, get_combos_enriched, etc.) | Patch `MongoClient`, mock collection.aggregate() return values |
| **Integration** | Full pipeline with real MongoDB | Manual testing only — not automated in CI |
| **No E2E** | — | Requires real MongoDB with seeded data |

## Potential Risks

1. **Risk**: Collection name mismatch — some enriched pipelines reference collections that don't exist in the deployed MongoDB
   → **Mitigation**: Each enriched method wraps its aggregation in try/except and returns empty list with warning log. `_get_collection()` already returns `None` for missing collections.

2. **Risk**: Schema drift — the old CLI's `cardPrices` flat schema (`usd`, `usd_foil` fields) differs from what `get_budget_alternatives` expects (nested `price_docs`)
   → **Mitigation**: Port pipeline exactly as-is from old CLI, including `$sortArray` / `$arrayElemAt` for latest price. The old CLI already handles this with `$addFields` and `$cond`.

3. **Risk**: The `$sample` aggregation stage is expensive without indexes
   → **Mitigation**: `verify_indexes()` creates `edhrecRank`, `name`, `uuid`, `colorIdentity` indexes. For large datasets, generators should pre-filter with `$match` before `$sample`.

4. **Risk**: Cross-database `$lookup` fails for combo pipeline
   → **Mitigation**: Already handled in old CLI — card lookup is done in Python via `_batch_lookup_cards_by_name()`. The aggregation on `commander_spellbook.variants` only fetches combo data.

## Handoff to Implementer

**Design Document**: `.opencode/designs/story-011-enrich-data-access.md`
**User Story**: `.opencode/discovery/story-011-tf-enrich-data-access.md`
**Reference Implementation**: `training_data/generate_synthetic_data/data_access.py` (1253 lines)
**Reference Domain Models**: `training_data/generate_synthetic_data/domain_models.py` (605 lines)
**Estimated Complexity**: High (6 tasks, 25+ new methods, 2 new files, 2 modified files)
**Key Files** (in order of implementation):
1. `trainforge/src/trainforge/data_source.py` — Add `aggregate()` (Task 1)
2. `trainforge/domains/mtg/models.py` — Port domain models (Task 3)
3. `trainforge/domains/mtg/data_source.py` — Main enrichment (Task 2 + Task 4)
4. `trainforge/tests/domains/mtg/test_data_source.py` — All tests (Task 5)
**Start With**: Task 1 — add `aggregate()` to `MongoDataSource`
**Acceptance Criteria**: All 33 criteria from the user story document
