"""Unit tests for MTGDataAccess, LRUCacheWithTTL, retry_on_transient_error.

All tests mock MongoDB — no real connection required.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from trainforge.domains.mtg.data_source import (
    LRUCacheWithTTL,
    MTGDataAccess,
    retry_on_transient_error,
)
from trainforge.domains.mtg.models import (
    CardWithMetadata,
    ComboWithCards,
    Ruling,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mtg_da():
    """Create MTGDataAccess with mocked MongoClient so no real connection is made."""
    da = MTGDataAccess()
    # Set _client to a MagicMock so _ensure_connected doesn't actually connect to MongoDB
    da._client = MagicMock()
    yield da


# =============================================================================
# 1. LRUCacheWithTTL
# =============================================================================


class TestLRUCacheWithTTL:
    """Unit tests for the LRU cache with TTL support."""

    def test_set_get(self):
        """Set a value and retrieve it."""
        cache = LRUCacheWithTTL(maxsize=100, ttl=300)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_miss(self):
        """Get a non-existent key returns None."""
        cache = LRUCacheWithTTL(maxsize=100, ttl=300)
        assert cache.get("nonexistent") is None

    def test_ttl_expiry(self):
        """Set with zero TTL so the entry expires immediately."""
        cache = LRUCacheWithTTL(maxsize=100, ttl=0)
        cache.set("key1", "value1")
        time.sleep(0.001)
        assert cache.get("key1") is None

    def test_eviction(self):
        """Maxsize=2; inserting 3 keys causes oldest to be evicted."""
        cache = LRUCacheWithTTL(maxsize=2, ttl=300)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)  # should evict 'a'
        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert cache.get("c") == 3

    def test_stats(self):
        """hits, misses, size after a series of operations."""
        cache = LRUCacheWithTTL(maxsize=100, ttl=300)
        cache.set("k1", "v1")
        cache.get("k1")  # hit
        cache.get("k1")  # hit
        cache.get("missing")  # miss
        stats = cache.stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["size"] == 1

    def test_clear(self):
        """Clear resets everything; subsequent get counts as a miss."""
        cache = LRUCacheWithTTL(maxsize=100, ttl=300)
        cache.set("k1", "v1")
        cache.get("k1")  # hit — increments hits to 1
        cache.clear()  # resets hits=0, misses=0, cache empty
        # Calling get on a cleared cache is a miss
        assert cache.get("k1") is None
        stats = cache.stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 1  # the get() after clear is a miss
        assert stats["size"] == 0


# =============================================================================
# 2. RetryDecorator
# =============================================================================


class TestRetryDecorator:
    """Unit tests for the retry_on_transient_error decorator."""

    def test_first_try_succeeds(self):
        """Function that succeeds on first call — no retry needed."""

        @retry_on_transient_error(max_retries=3, base_delay=0.1)
        def ok():
            return "success"

        with patch("time.sleep") as mock_sleep:
            result = ok()
            assert result == "success"
            mock_sleep.assert_not_called()

    def test_retry_then_succeeds(self):
        """Function fails twice then succeeds on third attempt."""

        call_count = 0

        @retry_on_transient_error(max_retries=3, base_delay=0.1)
        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionFailure("transient")
            return "ok"

        with patch("time.sleep") as mock_sleep:
            result = flaky()
            assert result == "ok"
            assert call_count == 3
            assert mock_sleep.call_count == 2

    def test_all_retries_exhausted(self):
        """Function always fails — raises last exception."""

        call_count = 0

        @retry_on_transient_error(max_retries=3, base_delay=0.1)
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise ServerSelectionTimeoutError("down")

        with patch("time.sleep") as mock_sleep:
            with pytest.raises(ServerSelectionTimeoutError):
                always_fails()
            assert call_count == 3
            assert mock_sleep.call_count == 2


# =============================================================================
# 3. TranslateCardFilters
# =============================================================================


class TestTranslateCardFilters:
    """Unit tests for _translate_card_filters."""

    def test_name_filter(self):
        """Name filter passes through directly."""
        da = MTGDataAccess()
        result = da._translate_card_filters({"name": "Opt"})
        assert result == {"name": "Opt"}

    def test_color_identity_regex(self):
        """Color identity filter generates proper $regex pattern."""
        da = MTGDataAccess()
        result = da._translate_card_filters({"colorIdentity": ["W", "U"]})
        assert "$and" in result
        for part in result["$and"]:
            assert "colorIdentity" in part
            assert "$regex" in part["colorIdentity"]

    def test_empty_filters(self):
        """Empty filters return empty dict."""
        da = MTGDataAccess()
        assert da._translate_card_filters({}) == {}

    def test_text_regex(self):
        """oracleText filter is translated to $regex with $options."""
        da = MTGDataAccess()
        result = da._translate_card_filters({"oracleText": "draw"})
        assert "text" in result
        assert result["text"]["$regex"] == "draw"
        assert result["text"]["$options"] == "i"

    def test_combination(self):
        """Multiple filters combined with $and."""
        da = MTGDataAccess()
        result = da._translate_card_filters({
            "name": "Opt",
            "colorIdentity": ["U"],
        })
        assert "$and" in result
        assert len(result["$and"]) == 2  # name + color


# =============================================================================
# 4. PipelineBuilders
# =============================================================================


class TestPipelineBuilders:
    """Unit tests for aggregation pipeline builders."""

    def test_card_enrichment_pipeline(self):
        """Full pipeline includes $lookup stages."""
        da = MTGDataAccess()
        pipeline = da._build_card_enrichment_pipeline({}, 10, skip=0, lite=False)
        assert pipeline[0]["$match"] == {}
        stages = [list(s.keys())[0] for s in pipeline]
        assert "$lookup" in stages
        assert "$sample" in stages
        assert "$skip" not in stages

    def test_card_enrichment_lite(self):
        """Lite pipeline has NO $lookup stages."""
        da = MTGDataAccess()
        pipeline = da._build_card_enrichment_pipeline({}, 10, skip=0, lite=True)
        stages = [list(s.keys())[0] for s in pipeline]
        assert "$lookup" not in stages

    def test_combo_pipeline(self):
        """Combo pipeline includes status filter."""
        da = MTGDataAccess()
        pipeline = da._build_combo_pipeline(None, 10)
        assert pipeline[0]["$match"]["status"] == "OK"

    def test_commander_pipeline(self):
        """Commander pipeline has correct field projections and limit."""
        da = MTGDataAccess()
        pipeline = da._build_commander_pipeline({}, 20)
        assert pipeline[0]["$match"] == {}
        assert pipeline[1]["$sample"]["size"] == 20
        project = pipeline[2]["$project"]
        assert "name" in project
        assert "colorIdentity" in project
        assert "tags" in project
        assert "numDecks" in project
        assert "card_details" in project

    def test_skip_param(self):
        """$skip is present when skip > 0, before $sample."""
        da = MTGDataAccess()
        pipeline = da._build_card_enrichment_pipeline({}, 10, skip=50, lite=True)
        stages = [list(s.keys())[0] for s in pipeline]
        assert "$skip" in stages
        skip_idx = stages.index("$skip")
        sample_idx = stages.index("$sample")
        assert skip_idx < sample_idx, "$skip should appear before $sample"


# =============================================================================
# 5. ConvertDocToModel
# =============================================================================


class TestConvertDocToModel:
    """Unit tests for _convert_doc_to_model."""

    def test_valid_doc(self):
        """A well-formed doc returns a model instance."""
        da = MTGDataAccess()
        doc = {"name": "Opt", "type": "Instant", "text": "Scry 1. Draw a card."}
        model = da._convert_doc_to_model(doc, CardWithMetadata)
        assert model is not None
        assert model.name == "Opt"
        assert model.type == "Instant"

    def test_invalid_doc(self):
        """A malformed doc returns None (warning logged)."""
        da = MTGDataAccess()
        doc = {"uuid": "abc"}  # missing required 'name'
        with patch("trainforge.domains.mtg.data_source.logger") as mock_logger:
            result = da._convert_doc_to_model(doc, CardWithMetadata)
            assert result is None
            mock_logger.warning.assert_called_once()

    def test_json_string_array_parsing(self):
        """JSON-stringified array fields are parsed into lists."""
        da = MTGDataAccess()
        doc = {
            "name": "Raugrin Triome",
            "type": "Land",
            "text": "T: Add W, U, or R.",
            "colors": '["W","U","R"]',
            "colorIdentity": '["W","U","R"]',
        }
        model = da._convert_doc_to_model(doc, CardWithMetadata)
        assert model is not None
        assert isinstance(model.colors, list)
        assert model.colors == ["W", "U", "R"]
        # colorIdentity alias -> color_identity attribute
        assert isinstance(model.color_identity, list)
        assert model.color_identity == ["W", "U", "R"]

    def test_invalid_json_array_string_returns_empty(self):
        """Invalid JSON string for an array field is handled gracefully."""
        da = MTGDataAccess()
        doc = {
            "name": "Junk Card",
            "type": "Creature",
            "text": "",
            "colors": "[not valid json",
        }
        model = da._convert_doc_to_model(doc, CardWithMetadata)
        assert model is not None
        assert model.colors == []

    def test_json_parsing_skipped_for_non_card_model(self):
        """JSON string parsing only applies to Card/Commander model classes."""
        da = MTGDataAccess()
        doc = {
            "uuid": "abc-123",
            "date": "2024-01-15T00:00:00Z",
            "text": "A ruling",
            "source": "official",
        }
        # Ruling model is not in the Card/Commander list, so JSON parsing is skipped
        model = da._convert_doc_to_model(doc, Ruling)
        assert model is not None
        assert model.uuid == "abc-123"


# =============================================================================
# 6. EnrichmentMethods
# =============================================================================


class TestEnrichmentMethods:
    """Tests for card enrichment methods (get_cards_enriched et al.)."""

    def test_get_cards_enriched(self, mtg_da):
        """Mocks aggregate, verifies returned list of CardWithMetadata."""
        fake_doc = {
            "name": "Test Card",
            "type": "Instant",
            "text": "Test text.",
            "colors": ["W"],
            "colorIdentity": ["W"],
        }
        mtg_da.aggregate = MagicMock(return_value=[fake_doc])  # type: ignore[method-assign]

        results = mtg_da.get_cards_enriched(limit=1)
        assert len(results) == 1
        assert isinstance(results[0], CardWithMetadata)
        assert results[0].name == "Test Card"

    def test_get_card_by_name_found(self, mtg_da):
        """get_card_by_name returns a list with one CardWithMetadata when found."""
        fake_doc = {
            "name": "Sol Ring",
            "type": "Artifact",
            "text": "{T}: Add {C}{C}.",
            "colors": [],
            "colorIdentity": [],
        }
        mtg_da.aggregate = MagicMock(return_value=[fake_doc])  # type: ignore[method-assign]

        results = mtg_da.get_card_by_name("Sol Ring")
        assert len(results) == 1
        assert results[0].name == "Sol Ring"

    def test_get_card_by_name_not_found(self, mtg_da):
        """get_card_by_name returns empty list when not found."""
        mtg_da.aggregate = MagicMock(return_value=[])  # type: ignore[method-assign]

        results = mtg_da.get_card_by_name("NonExistentCard")
        assert results == []

    def test_get_cards_by_keyword_mechanic(self, mtg_da):
        """Keyword mechanic filter applied to get_cards_enriched."""
        fake_doc = {
            "name": "Vigilant Card",
            "type": "Creature",
            "text": "Has vigilance.",
            "keywords": ["Vigilance"],
            "colors": [],
            "colorIdentity": ["W"],
        }
        mtg_da.aggregate = MagicMock(return_value=[fake_doc])  # type: ignore[method-assign]

        results = mtg_da.get_cards_by_keyword_mechanic("Vigilance", limit=1)
        assert len(results) == 1
        assert results[0].name == "Vigilant Card"


# =============================================================================
# 7. ComboMethods
# =============================================================================


class TestComboMethods:
    """Tests for combo enrichment methods."""

    def test_get_combos_enriched(self, mtg_da):
        """Mocks aggregate, returns typed list of ComboWithCards."""
        fake_combo = {
            "id": "123",
            "name": "Test Combo",
            "status": "OK",
            "uses": [],
            "produces": [],
            "description": "A test combo.",
        }
        mtg_da.aggregate = MagicMock(return_value=[fake_combo])  # type: ignore[method-assign]

        results = mtg_da.get_combos_enriched(limit=1)
        assert len(results) == 1
        assert isinstance(results[0], ComboWithCards)

    def test_get_combos_empty_collection(self, mtg_da):
        """When aggregate returns empty, get_combos_enriched returns []."""
        mtg_da.aggregate = MagicMock(return_value=[])  # type: ignore[method-assign]

        results = mtg_da.get_combos_enriched(limit=10)
        assert results == []


# =============================================================================
# 8. LookupMethods
# =============================================================================


class TestLookupMethods:
    """Tests for lookup methods (rulings, prices, legalities, keywords)."""

    def test_get_rulings_empty_input(self, mtg_da):
        """Empty card_names list returns [] without any DB calls."""
        result = mtg_da.get_rulings_for_cards([])
        assert result == []

    def test_get_prices_for_cards(self, mtg_da):
        """Mocks cards + prices lookups, returns populated dict."""
        fake_card_doc = {"uuid": "abc-123", "name": "Opt"}
        fake_price_doc = {"uuid": "abc-123", "usd": 0.25}

        def mock_find(filter_spec, *args, **kwargs):
            if filter_spec.get("name"):
                return [fake_card_doc]
            if filter_spec.get("uuid"):
                return [fake_price_doc]
            return []

        mock_coll = MagicMock()
        mock_coll.find = mock_find
        mtg_da._get_collection = MagicMock(return_value=mock_coll)

        result = mtg_da.get_prices_for_cards(["Opt"])
        assert isinstance(result, dict)
        assert "Opt" in result

    def test_get_legalities_for_cards(self, mtg_da):
        """Mocks legalities lookup, returns populated dict."""
        fake_card_doc = {"uuid": "abc-123", "name": "Sol Ring"}
        fake_legality_doc = {
            "uuid": "abc-123",
            "legalities": {"commander": "legal", "modern": "legal"},
        }

        def mock_find(filter_spec, *args, **kwargs):
            if filter_spec.get("name"):
                return [fake_card_doc]
            if filter_spec.get("uuid"):
                return [fake_legality_doc]
            return []

        mock_coll = MagicMock()
        mock_coll.find = mock_find
        mtg_da._get_collection = MagicMock(return_value=mock_coll)

        result = mtg_da.get_legalities_for_cards(["Sol Ring"])
        assert isinstance(result, dict)
        assert "Sol Ring" in result

    def test_get_keyword_taxonomy(self, mtg_da):
        """Mocks keywords collection, returns dict."""
        fake_keywords = [
            {"keyword": "Flying", "description": "Can only be blocked by creatures with flying."},
            {"keyword": "Haste", "description": "Can attack the turn it enters the battlefield."},
        ]

        mock_coll = MagicMock()
        mock_coll.find.return_value = fake_keywords
        mtg_da._get_collection = MagicMock(return_value=mock_coll)

        result = mtg_da.get_keyword_taxonomy()
        assert isinstance(result, dict)
        assert "Flying" in result
        assert "Haste" in result


# =============================================================================
# 9. AnalyticsMethods
# =============================================================================


class TestAnalyticsMethods:
    """Tests for analytics / utility methods."""

    def test_calculate_color_identity(self):
        """Pure function: no mock needed."""
        da = MTGDataAccess()
        # From mana cost
        assert da.calculate_color_identity("{W}{U}", None, None) == ["U", "W"]
        # From color indicator
        assert da.calculate_color_identity(None, None, ["B", "R"]) == ["B", "R"]
        # From rules text
        assert da.calculate_color_identity(None, "{T}: Add {G}", None) == ["G"]
        # Empty
        assert da.calculate_color_identity(None, None, None) == []

    def test_get_format_legalities(self, mtg_da):
        """Format filter applied correctly — delegates to get_cards_enriched."""
        fake_doc = {
            "name": "Opt",
            "type": "Instant",
            "text": "Draw.",
            "colors": [],
            "colorIdentity": ["U"],
        }
        mtg_da.aggregate = MagicMock(return_value=[fake_doc])  # type: ignore[method-assign]

        results = mtg_da.get_format_legalities("commander", limit=1)
        assert len(results) == 1

    def test_search_cards_text(self, mtg_da):
        """Regex filter applied via get_cards_enriched."""
        fake_doc = {
            "name": "Counterspell",
            "type": "Instant",
            "text": "Counter target spell.",
            "colors": ["U"],
            "colorIdentity": ["U"],
        }
        mtg_da.aggregate = MagicMock(return_value=[fake_doc])  # type: ignore[method-assign]

        results = mtg_da.search_cards_text("counter", limit=1)
        assert len(results) == 1
        assert results[0].name == "Counterspell"


# =============================================================================
# 10. Integration of JSON string fix
# =============================================================================


class TestJsonStringParsing:
    """Verify JSON string array fields are handled correctly in enrichment."""

    def test_json_string_colors_in_pipeline(self, mtg_da):
        """When the pipeline returns JSON strings, _convert_doc_to_model parses them."""
        doc_with_json = {
            "name": "Chromanticore",
            "type": "Enchantment Creature",
            "text": "Bestow...",
            "colors": '["W","U","B","R","G"]',
            "colorIdentity": '["W","U","B","R","G"]',
        }
        mtg_da.aggregate = MagicMock(return_value=[doc_with_json])  # type: ignore[method-assign]

        results = mtg_da.get_cards_enriched(limit=1)
        assert len(results) == 1
        assert results[0].colors == ["W", "U", "B", "R", "G"]


# =============================================================================
# 11. Cache integration
# =============================================================================


class TestCacheIntegration:
    """Verify caching works for the lookup methods."""

    def test_cache_hits_for_prices(self, mtg_da):
        """After first call, second call hits cache and avoids DB."""
        fake_card_doc = {"uuid": "abc-123", "name": "Opt"}
        fake_price_doc = {"uuid": "abc-123", "usd": 0.25}

        mock_coll = MagicMock()
        mock_coll.find.side_effect = [
            [fake_card_doc],  # first call: card lookup
            [fake_price_doc],  # first call: price lookup
        ]
        mtg_da._get_collection = MagicMock(return_value=mock_coll)

        # First call — populates cache
        result1 = mtg_da.get_prices_for_cards(["Opt"])
        assert "Opt" in result1

        # Second call — should come from cache
        mock_coll.find.reset_mock()
        result2 = mtg_da.get_prices_for_cards(["Opt"])
        assert "Opt" in result2
        # If cache worked, find was not called again
        mock_coll.find.assert_not_called()


# =============================================================================
# 12. TopCardsByEdhrecRank
# =============================================================================


class TestTopCardsByEdhrecRank:
    """Tests for get_top_cards_by_edhrec_rank."""

    def test_rank_filter_applied(self, mtg_da):
        """Filter includes colorIdentity and edhrecRank."""
        fake_doc = {
            "name": "Test",
            "type": "Creature",
            "text": "Test.",
            "colors": ["W"],
            "colorIdentity": ["W"],
        }
        mtg_da.aggregate = MagicMock(return_value=[fake_doc])  # type: ignore[method-assign]

        results = mtg_da.get_top_cards_by_edhrec_rank(["W"], limit=1)
        assert len(results) == 1
