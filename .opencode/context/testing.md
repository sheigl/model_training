# Testing Guide for Story 11 — Enriched MTGDataAccess Tests

## Test File
`trainforge/tests/domains/mtg/test_data_source.py`

## Test Framework
- `pytest` with `unittest.mock`
- No real MongoDB required — all operations mocked
- Patch `pymongo.MongoClient` to avoid real connections

## Fixture Patterns

### Basic Fixture (for most tests)
```python
@pytest.fixture
def data_access():
    """Create MTGDataAccess with mocked client and collections."""
    with patch("trainforge.domains.mtg.data_source.MongoClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.admin.command.return_value = {"ok": 1}

        da = MTGDataAccess()
        da._client = mock_client

        # Set up mock databases and collections
        mock_db = MagicMock()
        mock_db.list_collection_names.return_value = [
            "cards", "cardPrices", "cardLegalities", "cardRulings"
        ]
        mock_cards_coll = MagicMock()
        mock_db.__getitem__.return_value = mock_cards_coll
        mock_client.__getitem__.return_value = mock_db
        da._databases["mtg_json"] = mock_db
        da._collections["mtg_json.cards"] = mock_cards_coll

        yield da, mock_cards_coll
```

### Lookup Methods Fixture (multiple databases)
```python
@pytest.fixture
def multi_db_data_access():
    """Create MTGDataAccess with multiple mocked databases."""
    with patch("trainforge.domains.mtg.data_source.MongoClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.admin.command.return_value = {"ok": 1}

        da = MTGDataAccess()
        da._client = mock_client

        for db_name in ["mtg_json", "commander_spellbook", "edhrec", "mtg_rules"]:
            mock_db = MagicMock()
            mock_db.list_collection_names.return_value = []
            mock_client.__getitem__.return_value = mock_db
            da._databases[db_name] = mock_db

        yield da
```

## Test Class Organization

### 1. TestLRUCacheWithTTL
```python
class TestLRUCacheWithTTL:
    def test_basic_set_get(self):
        cache = LRUCacheWithTTL(maxsize=10, ttl=60)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_miss_returns_none(self):
        cache = LRUCacheWithTTL(maxsize=10, ttl=60)
        assert cache.get("nonexistent") is None

    def test_ttl_expiration(self):
        cache = LRUCacheWithTTL(maxsize=10, ttl=0)
        cache.set("key1", "value1")
        import time; time.sleep(0.01)
        assert cache.get("key1") is None

    def test_lru_eviction(self):
        cache = LRUCacheWithTTL(maxsize=2, ttl=60)
        cache.set("key1", "v1"); cache.set("key2", "v2"); cache.set("key3", "v3")
        assert cache.get("key1") is None  # Evicted
        assert cache.get("key2") == "v2"
        assert cache.get("key3") == "v3"

    def test_cache_stats(self):
        cache = LRUCacheWithTTL()
        cache.set("k1", "v1"); cache.get("k1")  # hit
        cache.get("k2")  # miss
        stats = cache.stats()
        assert stats["hits"] == 1 and stats["misses"] == 1 and stats["size"] == 1

    def test_clear(self):
        cache = LRUCacheWithTTL()
        cache.set("k1", "v1"); cache.clear()
        assert cache.get("k1") is None
```

### 2. TestRetryDecorator
```python
class TestRetryDecorator:
    def test_success_on_first_try(self):
        mock_func = Mock(return_value="success")
        decorated = retry_on_transient_error(max_retries=3)(mock_func)
        assert decorated() == "success"
        assert mock_func.call_count == 1

    def test_retry_on_connection_failure(self):
        from pymongo.errors import ConnectionFailure
        mock_func = Mock(side_effect=[ConnectionFailure("timeout"), "success"])
        mock_func.__name__ = "test_func"
        decorated = retry_on_transient_error(max_retries=3, base_delay=0.01)(mock_func)
        assert decorated() == "success"
        assert mock_func.call_count == 2

    def test_exhausts_retries(self):
        from pymongo.errors import ConnectionFailure
        mock_func = Mock(side_effect=ConnectionFailure("persistent"))
        mock_func.__name__ = "test_func"
        decorated = retry_on_transient_error(max_retries=3, base_delay=0.01)(mock_func)
        with pytest.raises(ConnectionFailure):
            decorated()
        assert mock_func.call_count == 3
```

### 3. TestCardEnrichmentMethods
```python
class TestCardEnrichmentMethods:
    def test_get_cards_enriched_returns_typed_models(self, data_access):
        """Enriched cards should be CardWithMetadata instances."""
        da, mock_coll = data_access
        mock_coll.aggregate.return_value = iter([
            {"name": "Test", "uuid": "abc", "type": "Creature", "manaCost": "{1}{W}"}
        ])
        result = da.get_cards_enriched(filters={"colorIdentity": ["W"]}, limit=10)
        assert len(result) == 1
        assert isinstance(result[0], CardWithMetadata)

    def test_get_cards_enriched_missing_collection_returns_empty(self, data_access):
        """Should return [] when cards collection missing."""
        da, mock_coll = data_access
        da._collections.pop("mtg_json.cards", None)
        da._databases["mtg_json"].list_collection_names.return_value = []
        assert da.get_cards_enriched() == []

    def test_get_card_by_name_found(self, data_access):
        """Should return single typed card."""
        da, mock_coll = data_access
        mock_coll.aggregate.return_value = iter([
            {"name": "Sol Ring", "uuid": "x", "type": "Artifact", "manaCost": "{1}"}
        ])
        result = da.get_card_by_name("Sol Ring")
        assert result is not None and result.name == "Sol Ring"

    def test_get_card_by_name_not_found(self, data_access):
        """Should return None when card not found."""
        da, mock_coll = data_access
        mock_coll.aggregate.return_value = iter([])
        assert da.get_card_by_name("Nonexistent") is None
```

### 4. TestTranslateCardFilters
```python
class TestTranslateCardFilters:
    def test_name_filter_passthrough(self):
        da = MTGDataAccess()
        result = da._translate_card_filters({"name": "Sol Ring"})
        assert result == {"name": "Sol Ring"}

    def test_color_identity_regex(self):
        """colorIdentity should translate to regex match for JSON strings."""
        da = MTGDataAccess()
        result = da._translate_card_filters({"colorIdentity": ["W", "U"]})
        assert "$and" in result
        # Each color becomes {"colorIdentity": {"$regex": '"W"'}}

    def test_empty_filters_returns_empty_dict(self):
        da = MTGDataAccess()
        assert da._translate_card_filters({}) == {}

    def test_text_regex_filter(self):
        da = MTGDataAccess()
        result = da._translate_card_filters({"text_regex": "flying"})
        assert "$regex" in str(result)

    def test_rarity_filter_list(self):
        da = MTGDataAccess()
        result = da._translate_card_filters({"rarity": ["rare", "mythic"]})
        assert "$in" in str(result)

    def test_multiple_filters_combine_with_and(self):
        da = MTGDataAccess()
        result = da._translate_card_filters({"name": "Sol Ring", "rarity": "rare"})
        assert "$and" in result
```

### 5. TestComboMethods
```python
class TestComboMethods:
    def test_get_combos_enriched(self, data_access):
        da, mock_coll = data_access  # needs commander_spellbook mock
        mock_coll.aggregate.return_value = iter([{
            "_id": "c1", "name": "Test Combo", "description": "A combo",
            "produces": [], "uses": [], "cards": []
        }])
        result = da.get_combos_enriched(limit=10)
        assert len(result) == 1 and isinstance(result[0], ComboWithCards)
```

### 6. TestCommanderMethods
```python
class TestCommanderMethods:
    def test_get_commanders_enriched(self, data_access):
        """Should return CommanderWithTags with correct field mapping."""
        da, mock_coll = data_access  # needs edhrec mock
        mock_coll.aggregate.return_value = iter([{
            "name": "Atraxa", "colorIdentity": ["W", "U", "B", "G"],
            "tags": ["proliferate"], "numDecks": 5000, "salt": 1.2,
            "avgDeckRank": 100.5, "cardUuid": "u123",
            "card_details": {"name": "Atraxa"}
        }])
        result = da.get_commanders_enriched(limit=10)
        assert len(result) == 1 and isinstance(result[0], CommanderWithTags)
```

### 7. TestPipelineBuilders
```python
class TestPipelineBuilders:
    def test_build_card_enrichment_pipeline_full(self):
        """Verify stage order and required fields."""
        da = MTGDataAccess()
        pipeline = da._build_card_enrichment_pipeline({"colorIdentity": ["W"]}, 10, 0)
        stages = [list(s.keys())[0] for s in pipeline]
        assert "$match" in stages and "$lookup" in stages and "$project" in stages

    def test_build_card_enrichment_pipeline_lite(self):
        """Lite mode should skip joins."""
        da = MTGDataAccess()
        pipeline = da._build_card_enrichment_pipeline({}, 10, 0, lite=True)
        stages_str = str(pipeline)
        assert "$lookup" not in stages_str  # No joins in lite mode

    def test_build_card_enrichment_pipeline_with_skip(self):
        da = MTGDataAccess()
        pipeline = da._build_card_enrichment_pipeline({}, 10, 5)
        stages = [list(s.keys())[0] for s in pipeline]
        assert "$skip" in stages

    def test_build_combo_pipeline_default_status_filter(self):
        """Default match should filter to status='OK'."""
        da = MTGDataAccess()
        pipeline = da._build_combo_pipeline(None, 20)
        match_stage = next(s for s in pipeline if "$match" in s)["$match"]
        assert match_stage["status"] == "OK"

    def test_build_commander_pipeline_field_mapping(self):
        da = MTGDataAccess()
        pipeline = da._build_commander_pipeline({}, 15)
        project_stage = next(s for s in pipeline if "$project" in s)["$project"]
        assert project_stage["colorIdentity"] == "$color_identity"
        assert project_stage["numDecks"] is not None
```

### 8. TestLookupMethods
```python
class TestLookupMethods:
    def test_get_rulings_for_cards_empty_input(self, multi_db_data_access):
        assert multi_db_data_access.get_rulings_for_cards([]) == []

    def test_get_prices_for_cards(self, multi_db_data_access):
        da = multi_db_data_access
        # Mock card lookup
        mock_cards = MagicMock()
        mock_cards.find.return_value = [{"uuid": "123", "name": "Test Card"}]
        da._collections["mtg_json.cards"] = mock_cards
        da._databases["mtg_json"].list_collection_names.return_value = ["cards", "cardPrices"]
        # Mock prices
        mock_prices = MagicMock()
        mock_prices.find.return_value = [{"uuid": "123", "usd": 10.50, "usd_foil": 15.00}]
        da._collections["mtg_json.cardPrices"] = mock_prices
        
        result = da.get_prices_for_cards(["Test Card"])
        assert "Test Card" in result
        assert result["Test Card"].usd == 10.50

    def test_get_legalities_for_cards(self, multi_db_data_access):
        da = multi_db_data_access
        mock_cards = MagicMock()
        mock_cards.find.return_value = [{"uuid": "123", "name": "Test"}]
        da._collections["mtg_json.cards"] = mock_cards
        da._databases["mtg_json"].list_collection_names.return_value = ["cards", "cardLegalities"]
        mock_leg = MagicMock()
        mock_leg.find.return_value = [{"uuid": "123", "legalities": {"commander": "legal"}}]
        da._collections["mtg_json.cardLegalities"] = mock_leg
        
        result = da.get_legalities_for_cards(["Test"])
        assert result["Test"].is_legal_in("commander") is True

    def test_get_keyword_taxonomy(self, multi_db_data_access):
        da = multi_db_data_access
        mock_kw = MagicMock()
        mock_kw.find.return_value = [
            {"keyword": "Flying", "description": "Can't be blocked except by creatures with flying."}
        ]
        da._collections["mtg_json.keywords"] = mock_kw
        da._databases["mtg_json"].list_collection_names.return_value = ["keywords"]
        
        result = da.get_keyword_taxonomy()
        assert "Flying" in result
```

### 9. TestAnalyticsMethods
```python
class TestAnalyticsMethods:
    def test_get_top_cards_by_edhrec_rank(self, data_access):
        da, mock_coll = data_access
        mock_coll.aggregate.return_value = iter([
            {"name": "Sol Ring", "uuid": "x", "type": "Artifact", "edhrecRank": 1}
        ])
        result = da.get_top_cards_by_edhrec_rank(["W"], limit=10)
        assert len(result) == 1 and result[0].name == "Sol Ring"

    def test_get_budget_alternatives(self, data_access):
        da, mock_coll = data_access
        da.get_card_by_name = Mock(return_value=CardWithMetadata(
            name="Expensive", uuid="x", type="Creature",
            keywords=["Flying"], colorIdentity=["W"]
        ))
        mock_coll.aggregate.return_value = iter([
            {"name": "Budget", "uuid": "y", "type": "Creature"}
        ])
        result = da.get_budget_alternatives("Expensive", max_price=5.0, limit=5)
        assert len(result) == 1 and result[0].name == "Budget"

    def test_calculate_color_identity_from_mana_cost(self):
        da = MTGDataAccess()
        result = da.calculate_color_identity("{1}{W}{U}", None, None)
        assert "W" in result and "U" in result

    def test_calculate_color_identity_from_text(self):
        da = MTGDataAccess()
        result = da.calculate_color_identity(None, "{T}: Add {G}", None)
        assert "G" in result

    def test_search_cards_text(self, data_access):
        da, mock_coll = data_access
        mock_coll.aggregate.return_value = iter([
            {"name": "Flying Card", "uuid": "x", "type": "Creature", "oracleText": "Flying"}
        ])
        result = da.search_cards_text(r"flying", limit=10)
        assert len(result) == 1
```

### 10. TestIndexVerification
```python
class TestIndexVerification:
    def test_verify_indexes(self, data_access):
        da, mock_coll = data_access
        mock_coll.list_indexes.return_value = iter([{"name": "_id_"}])
        da.verify_indexes()
        # Should have attempted index creation
        assert da._indexes_verified is True

    def test_verify_indexes_idempotent(self, data_access):
        da, mock_coll = data_access
        da._indexes_verified = True
        original_call_count = mock_coll.list_indexes.call_count
        da.verify_indexes()
        assert mock_coll.list_indexes.call_count == original_call_count  # Skipped
```
