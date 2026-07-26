# Coding Standards for TrainForge — MTG Domain Enrichment (Story 11)

## Overview
This document defines the coding standards for porting the enriched MTG data access layer from the old CLI (`training_data/generate_synthetic_data/data_access.py`) to the TrainForge framework (`trainforge/domains/mtg/data_source.py`).

---

## Python Standards

### Version & Type Hints
- **Python**: 3.11+
- **Type Hints**: Required for all public functions, methods, and class attributes
- **Pydantic**: v2 (`BaseModel`, `ConfigDict`, `Field`, `computed_field`, `field_validator`)
- **Imports**: Use `from __future__ import annotations` for forward references

### Code Style
- **Formatter**: `ruff format` (line length 100)
- **Linter**: `ruff check` with `select = ["E", "F", "I", "UP", "B", "C4", "SIM", "T20"]`
- **Naming**: 
  - Classes: `PascalCase`
  - Functions/Methods: `snake_case`
  - Constants: `UPPER_SNAKE_CASE`
  - Private: `_leading_underscore`

### Docstrings
- **Format**: Google style (Args, Returns, Raises)
- **Required**: All public methods on MTGDataAccess

---

## MongoDB Patterns

### Collection Name Strategy

Simple methods (existing) use `synthetic_queries.*` namespace:
```python
def get_cards(self, ...):
    return self.get_records(f"{self.db_name}.mtg_cards", ...)
```

Enriched methods use actual database names matching the MongoDB schema:
```python
def get_cards_enriched(self, ...):
    return self.aggregate("mtg_json.cards", pipeline, ...)
```

### Adding aggregate() to MongoDataSource

```python
def aggregate(
    self, collection: str, pipeline: list[dict], allow_disk_use: bool = True
) -> list[dict]:
    """Run an aggregation pipeline on a collection.
    
    Collection name supports 'db.coll' or just 'coll' (uses default db).
    """
    parts = collection.split(".", 1)
    if len(parts) == 2:
        db_name, coll_name = parts
    else:
        db_name = self.DEFAULT_DATABASE
        coll_name = collection

    coll = self._get_collection(db_name, coll_name)
    return list(coll.aggregate(pipeline, allowDiskUse=allow_disk_use))
```

### Aggregation Pipeline Pattern

Always use `$project` as final stage to shape output to match Pydantic models:
```python
def _build_card_enrichment_pipeline(self, filters, limit, skip, lite=False):
    pipeline = [{"$match": processed_filters}]
    if not lite:
        pipeline.extend([
            {"$lookup": {"from": "cardPrices", "localField": "uuid", "foreignField": "uuid", "as": "price_docs"}},
            {"$addFields": {...}},
            {"$lookup": {...}},
            {"$project": {**field_projections}},
        ])
    if skip > 0:
        pipeline.append({"$skip": skip})
    pipeline.append({"$sample": {"size": limit}})
    pipeline.append({"$limit": limit})
    return pipeline
```

### Card Filter Translation

The `_translate_card_filters()` method handles JSON-stringified array fields:
- `colorIdentity` in MongoDB is stored as `'["W","U"]'` (JSON string), not an array
- Use `{"$regex": '"W"'}` to match a single color
- `keywords`, `supertypes`, `subtypes` are also stored as JSON strings

### Indexes to Verify on Startup

```python
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

---

## Pydantic Model Standards (for ported domain models)

### Base Configuration
```python
from pydantic import BaseModel, ConfigDict, Field

class MongoModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,      # Allow snake_case and alias
        extra="ignore",             # Ignore unknown MongoDB fields
        arbitrary_types_allowed=True,
        use_enum_values=True,
    )
```

### Aliases (camelCase MongoDB → snake_case Python)
```python
class Card(MongoModel):
    name: str
    mana_cost: str | None = Field(default=None, alias="manaCost")
    color_identity: list[str] = Field(default_factory=list, alias="colorIdentity")
    edhrec_rank: int | None = Field(default=None, alias="edhrecRank")
```

### Computed Properties
```python
@property
def cmc(self) -> float:
    """Converted mana cost from mana_cost string."""
    if not self.mana_cost:
        return 0.0
    ...

@property
def is_commander_legal(self) -> bool:
    return self.legalities.get("commander", "").lower() == "legal"
```

### Serialization for LLM Prompts
```python
def to_prompt_detail(self, include_prices=True, include_rulings=False) -> str:
    """Format card for LLM context - consistent across all generators."""
    lines = [
        f"Name: {self.name}",
        f"Mana Cost: {self.mana_cost or 'N/A'}",
        f"Type: {self.type or 'N/A'}",
        f"Oracle Text: {self.text or 'N/A'}",
    ]
    ...
    return "\n".join(lines)
```

### List Field Normalization
MongoDB stores lists as JSON strings. Handle in constructor or field_validator:
```python
@classmethod
def from_dict(cls, data: dict) -> "Card | None":
    def _parse_list(key: str) -> list[str]:
        raw = data.get(key, [])
        if isinstance(raw, str):
            import json; return json.loads(raw) if ... else []
        return raw if isinstance(raw, list) else []
    ...
```

---

## Caching Pattern

```python
class LRUCacheWithTTL:
    """Thread-safe LRU cache with TTL support."""
    def __init__(self, maxsize: int = 1000, ttl: int = 300): ...
    def get(self, key: str) -> Any | None: ...
    def set(self, key: str, value: Any) -> None: ...
    def clear(self) -> None: ...
    def stats(self) -> dict[str, int]: ...
```

Cache key pattern for lookup methods:
```python
cache_key = f"rulings:{','.join(sorted(card_names))}"
```

---

## Retry Decorator

```python
def retry_on_transient_error(max_retries: int = 3, base_delay: float = 0.5):
    """Decorator for retrying transient MongoDB errors with exponential backoff.
    
    Retries on: ConnectionFailure, ServerSelectionTimeoutError, OperationFailure
    """
    ...
```

Apply to all enriched data access methods:
```python
@retry_on_transient_error()
def get_cards_enriched(self, ...):
    ...
```

---

## Testing Standards

### Test Location
`trainforge/tests/domains/mtg/test_data_source.py`

### Test Framework
- `pytest` with `unittest.mock` for MongoDB mocking
- Patch `pymongo.MongoClient` before imports

### Test Organization
One class per method group:
```python
class TestCardEnrichmentMethods:
class TestComboMethods:
class TestCommanderMethods:
class TestLookupMethods:
class TestAnalyticsMethods:
class TestPipelineBuilders:
class TestTranslateCardFilters:
class TestLRUCacheWithTTL:
class TestRetryDecorator:
```

### Test Fixture Pattern

```python
@pytest.fixture
def data_access(self):
    """Create MTGDataAccess with mocked client."""
    with patch("trainforge.domains.mtg.data_source.MongoClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.admin.command.return_value = {"ok": 1}
        
        da = MTGDataAccess()
        da._client = mock_client
        
        # Mock collections as needed
        mock_cards_coll = MagicMock()
        mock_db = MagicMock()
        mock_db.list_collection_names.return_value = ["cards", "cardPrices", ...]
        mock_db.__getitem__.return_value = mock_cards_coll
        mock_client.__getitem__.return_value = mock_db
        da._databases["mtg_json"] = mock_db
        da._collections["mtg_json.cards"] = mock_cards_coll
        
        yield da
```

### Key Test Cases
- **Pipeline building**: Verify stage order, field mappings, filter translation
- **Model conversion**: Verify MongoDB doc → Pydantic model with aliases
- **Cache behavior**: Hit, miss, TTL expiration, eviction
- **Retry logic**: First-try success, retry on failure, exhaustion
- **Edge cases**: Missing collections, empty results, null fields, JSON-string arrays
- **Filter translation**: colorIdentity regex, keywords regex, text search, rarity
