"""Unit tests for MTGDataAccess unified data access layer."""

import json
from unittest.mock import MagicMock, Mock, patch
from typing import Any

import pytest

from training_data.generate_synthetic_data.data_access import (
    LRUCacheWithTTL,
    MTGDataAccess,
    retry_on_transient_error,
)
from training_data.generate_synthetic_data.domain_models import (
    Archetype,
    Article,
    CardLegalities,
    CardWithMetadata,
    ComboWithCards,
    CommanderWithTags,
    GameState,
    GlossaryTerm,
    Guide,
    Keyword,
    Legality,
    PriceData,
    Ruling,
    Rule,
)


class TestLRUCacheWithTTL:
    """Tests for LRUCacheWithTTL."""

    def test_basic_set_get(self):
        cache = LRUCacheWithTTL(maxsize=10, ttl=60)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_miss_returns_none(self):
        cache = LRUCacheWithTTL(maxsize=10, ttl=60)
        assert cache.get("nonexistent") is None

    def test_ttl_expiration(self):
        cache = LRUCacheWithTTL(maxsize=10, ttl=0)  # Immediate expiration
        cache.set("key1", "value1")
        import time
        time.sleep(0.01)
        assert cache.get("key1") is None

    def test_lru_eviction(self):
        cache = LRUCacheWithTTL(maxsize=2, ttl=60)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")  # Should evict key1
        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"
        assert cache.get("key3") == "value3"

    def test_cache_stats(self):
        cache = LRUCacheWithTTL(maxsize=10, ttl=60)
        cache.set("key1", "value1")
        cache.get("key1")  # hit
        cache.get("key2")  # miss
        stats = cache.stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["size"] == 1

    def test_clear(self):
        cache = LRUCacheWithTTL(maxsize=10, ttl=60)
        cache.set("key1", "value1")
        cache.clear()
        assert cache.get("key1") is None
        assert cache.stats()["size"] == 0


class TestRetryDecorator:
    """Tests for retry_on_transient_error decorator."""

    def test_success_on_first_try(self):
        mock_func = Mock(return_value="success")
        decorated = retry_on_transient_error(max_retries=3)(mock_func)
        result = decorated()
        assert result == "success"
        assert mock_func.call_count == 1

    def test_retry_on_connection_failure(self):
        from pymongo.errors import ConnectionFailure
        mock_func = Mock(side_effect=[ConnectionFailure("timeout"), "success"])
        mock_func.__name__ = "test_func"
        decorated = retry_on_transient_error(max_retries=3, base_delay=0.01)(mock_func)
        result = decorated()
        assert result == "success"
        assert mock_func.call_count == 2

    def test_exhausts_retries(self):
        from pymongo.errors import ConnectionFailure
        mock_func = Mock(side_effect=ConnectionFailure("persistent"))
        mock_func.__name__ = "test_func"
        decorated = retry_on_transient_error(max_retries=3, base_delay=0.01)(mock_func)
        with pytest.raises(ConnectionFailure):
            decorated()
        assert mock_func.call_count == 3


class TestMTGDataAccess:
    """Tests for MTGDataAccess class."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock MongoClient."""
        with patch("training_data.generate_synthetic_data.data_access.MongoClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.admin.command.return_value = {"ok": 1}
            yield mock_client

    @pytest.fixture
    def data_access(self, mock_client):
        """Create MTGDataAccess instance with mocked client."""
        da = MTGDataAccess(
            uri="mongodb://localhost:27017",
            username="root",
            password="whatever",
            database="mtg_json",
        )
        da._client = mock_client
        return da

    def test_context_manager(self, mock_client):
        """Test context manager protocol."""
        with MTGDataAccess() as da:
            assert da._client is not None
        mock_client.close.assert_called_once()

    def test_connect_creates_client(self, mock_client):
        """Test connect() establishes connection."""
        da = MTGDataAccess()
        da.connect()
        assert da._client is not None
        mock_client.admin.command.assert_called_with("ping")

    def test_close_closes_client(self, mock_client, data_access):
        """Test close() closes connection."""
        data_access.close()
        mock_client.close.assert_called_once()
        assert data_access._client is None

    def test_health_check_success(self, mock_client, data_access):
        """Test health_check returns True on success."""
        mock_client.admin.command.return_value = {"ok": 1}
        assert data_access.health_check() is True

    def test_health_check_failure(self, mock_client, data_access):
        """Test health_check returns False on failure."""
        mock_client.admin.command.side_effect = Exception("Connection failed")
        assert data_access.health_check() is False

    def test_get_database_caches(self, mock_client, data_access):
        """Test _get_database caches database instances."""
        mock_db = MagicMock()
        mock_client.__getitem__.return_value = mock_db

        db1 = data_access._get_database("test_db")
        db2 = data_access._get_database("test_db")

        assert db1 is db2
        assert mock_client.__getitem__.call_count == 1

    def test_get_collection_returns_none_for_missing(self, mock_client, data_access):
        """Test _get_collection returns None for missing collection."""
        mock_db = MagicMock()
        mock_db.list_collection_names.return_value = ["existing"]
        mock_client.__getitem__.return_value = mock_db

        result = data_access._get_collection("test_db", "missing")
        assert result is None

    def test_get_collection_required_raises(self, mock_client, data_access):
        """Test _get_collection_required raises for missing collection."""
        mock_db = MagicMock()
        mock_db.list_collection_names.return_value = ["existing"]
        mock_client.__getitem__.return_value = mock_db

        with pytest.raises(RuntimeError, match="not available"):
            data_access._get_collection_required("test_db", "missing")

    def test_verify_indexes_creates_missing(self, mock_client, data_access):
        """Test verify_indexes creates missing indexes."""
        mock_db = MagicMock()
        mock_coll = MagicMock()
        mock_coll.list_indexes.return_value = iter([{"name": "_id_"}])
        mock_db.list_collection_names.return_value = ["cards"]
        mock_db.__getitem__.return_value = mock_coll
        mock_client.__getitem__.return_value = mock_db

        data_access.verify_indexes()
        # Should have attempted to create indexes

    def test_clear_cache(self, data_access):
        """Test clear_cache clears internal cache."""
        data_access._cache.set("key1", "value1")
        data_access.clear_cache()
        assert data_access._cache.get("key1") is None

    def test_cache_stats(self, data_access):
        """Test cache_stats returns statistics."""
        data_access._cache.set("key1", "value1")
        data_access._cache.get("key1")
        stats = data_access.cache_stats()
        assert stats["hits"] == 1
        assert stats["size"] == 1


class TestCardEnrichmentMethods:
    """Tests for card enrichment methods."""

    @pytest.fixture
    def data_access(self):
        """Create MTGDataAccess with mocked collections."""
        with patch("training_data.generate_synthetic_data.data_access.MongoClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.admin.command.return_value = {"ok": 1}

            da = MTGDataAccess()
            da._client = mock_client

            # Mock cards collection
            mock_cards_coll = MagicMock()
            mock_db = MagicMock()
            mock_db.list_collection_names.return_value = [
                "cards", "cardPrices", "cardLegalities", "cardRulings", "keywords"
            ]
            mock_db.__getitem__.return_value = mock_cards_coll
            mock_client.__getitem__.return_value = mock_db

            da._databases["mtg_json"] = mock_db
            da._collections["mtg_json.cards"] = mock_cards_coll

            yield da, mock_cards_coll

    def test_get_cards_enriched_builds_pipeline(self, data_access):
        """Test get_cards_enriched builds correct aggregation pipeline."""
        da, mock_coll = data_access
        mock_coll.aggregate.return_value = iter([
            {"name": "Test Card", "uuid": "123", "type": "Creature", "manaCost": "{1}{W}"}
        ])

        result = da.get_cards_enriched(filters={"colorIdentity": ["W"]}, limit=10)

        assert len(result) == 1
        assert isinstance(result[0], CardWithMetadata)
        assert result[0].name == "Test Card"
        mock_coll.aggregate.assert_called_once()

    def test_get_cards_enriched_missing_collection(self, data_access):
        """Test get_cards_enriched returns empty list when collection missing."""
        da, mock_coll = data_access
        da._collections.pop("mtg_json.cards", None)
        da._databases["mtg_json"].list_collection_names.return_value = []

        result = da.get_cards_enriched()
        assert result == []

    def test_get_card_by_name(self, data_access):
        """Test get_card_by_name returns single card."""
        da, mock_coll = data_access
        mock_coll.aggregate.return_value = iter([
            {"name": "Sol Ring", "uuid": "123", "type": "Artifact", "manaCost": "{1}"}
        ])

        result = da.get_card_by_name("Sol Ring")
        assert result is not None
        assert result.name == "Sol Ring"

    def test_get_card_by_name_not_found(self, data_access):
        """Test get_card_by_name returns None when not found."""
        da, mock_coll = data_access
        mock_coll.aggregate.return_value = iter([])

        result = da.get_card_by_name("Nonexistent Card")
        assert result is None


class TestComboMethods:
    """Tests for combo-related methods."""

    @pytest.fixture
    def data_access(self):
        """Create MTGDataAccess with mocked combo collection."""
        with patch("training_data.generate_synthetic_data.data_access.MongoClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.admin.command.return_value = {"ok": 1}

            da = MTGDataAccess()
            da._client = mock_client

            mock_combos_coll = MagicMock()
            mock_db = MagicMock()
            mock_db.list_collection_names.return_value = ["variants"]
            mock_db.__getitem__.return_value = mock_combos_coll
            mock_client.__getitem__.return_value = mock_db

            da._databases["commander_spellbook"] = mock_db
            da._collections["commander_spellbook.variants"] = mock_combos_coll

            yield da, mock_combos_coll

    def test_get_combos_enriched(self, data_access):
        """Test get_combos_enriched returns enriched combos."""
        da, mock_coll = data_access
        mock_coll.aggregate.return_value = iter([{
            "_id": "combo1",
            "name": "Test Combo",
            "description": "A test combo",
            "produces": [],
            "notes": "",
            "requires": [],
            "tags": [],
            "commanders": [],
            "uses": [],
            "cards": []
        }])

        result = da.get_combos_enriched(limit=10)
        assert len(result) == 1
        assert isinstance(result[0], ComboWithCards)
        assert result[0].name == "Test Combo"

    def test_get_combos_enriched_missing_collection(self, data_access):
        """Test get_combos_enriched returns empty when collection missing."""
        da, mock_coll = data_access
        da._collections.pop("commander_spellbook.variants", None)
        da._databases["commander_spellbook"].list_collection_names.return_value = []

        result = da.get_combos_enriched()
        assert result == []


class TestCommanderMethods:
    """Tests for commander-related methods."""

    @pytest.fixture
    def data_access(self):
        """Create MTGDataAccess with mocked commanders collection."""
        with patch("training_data.generate_synthetic_data.data_access.MongoClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.admin.command.return_value = {"ok": 1}

            da = MTGDataAccess()
            da._client = mock_client

            mock_cmd_coll = MagicMock()
            mock_db = MagicMock()
            mock_db.list_collection_names.return_value = ["commanders"]
            mock_db.__getitem__.return_value = mock_cmd_coll
            mock_client.__getitem__.return_value = mock_db

            da._databases["edhrec"] = mock_db
            da._collections["edhrec.commanders"] = mock_cmd_coll

            yield da, mock_cmd_coll

    def test_get_commanders_enriched(self, data_access):
        """Test get_commanders_enriched returns enriched commanders."""
        da, mock_coll = data_access
        mock_coll.aggregate.return_value = iter([{
            "name": "Atraxa",
            "colorIdentity": ["W", "U", "B", "G"],
            "tags": ["+1/+1 counters", "proliferate"],
            "numDecks": 5000,
            "salt": 1.2,
            "avgDeckRank": 100.5,
            "cardUuid": "uuid123",
            "card_details": {"name": "Atraxa", "uuid": "uuid123"}
        }])

        result = da.get_commanders_enriched(limit=10)
        assert len(result) == 1
        assert isinstance(result[0], CommanderWithTags)
        assert result[0].name == "Atraxa"


class TestLookupMethods:
    """Tests for lookup methods (rulings, prices, legalities, etc.)."""

    @pytest.fixture
    def data_access(self):
        """Create MTGDataAccess with all mocked collections."""
        with patch("training_data.generate_synthetic_data.data_access.MongoClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.admin.command.return_value = {"ok": 1}

            da = MTGDataAccess()
            da._client = mock_client

            # Mock all databases and collections
            for db_name in ["mtg_json", "scryfall", "edhrec", "mtg_archetypes", "mtg_training", "mtg_rules"]:
                mock_db = MagicMock()
                mock_db.list_collection_names.return_value = []
                mock_client.__getitem__.return_value = mock_db
                da._databases[db_name] = mock_db

            yield da

    def test_get_rulings_for_cards_empty_input(self, data_access):
        """Test get_rulings_for_cards with empty list."""
        result = data_access.get_rulings_for_cards([])
        assert result == []

    def test_get_rulings_for_cards_caching(self, data_access):
        """Test get_rulings_for_cards caches results."""
        da = data_access
        da._databases["mtg_json"].list_collection_names.return_value = ["cards", "cardRulings"]
        
        mock_cards = MagicMock()
        mock_cards.find.return_value = [{"uuid": "123", "name": "Test Card"}]
        da._collections["mtg_json.cards"] = mock_cards

        mock_rulings = MagicMock()
        mock_rulings.find.return_value = [{
            "uuid": "123",
            "rulings": [{"uuid": "123", "date": "2023-01-01", "text": "Test ruling", "source": "official"}]
        }]
        da._collections["mtg_json.cardRulings"] = mock_rulings

        # First call
        result1 = da.get_rulings_for_cards(["Test Card"])
        # Second call should use cache
        result2 = da.get_rulings_for_cards(["Test Card"])

        assert result1 == result2
        assert len(result1) == 1
        assert isinstance(result1[0], Ruling)

    def test_get_prices_for_cards(self, data_access):
        """Test get_prices_for_cards returns price data."""
        da = data_access
        da._databases["mtg_json"].list_collection_names.return_value = ["cards", "cardPrices"]
        
        mock_cards = MagicMock()
        mock_cards.find.return_value = [{"uuid": "123", "name": "Test Card"}]
        da._collections["mtg_json.cards"] = mock_cards

        mock_prices = MagicMock()
        mock_prices.find.return_value = [{
            "uuid": "123",
            "usd": 10.50,
            "usd_foil": 15.00,
            "eur": 9.00,
            "eur_foil": 13.00,
            "tix": 8.00,
            "paper": 11.00,
            "lastUpdated": "2023-01-01"
        }]
        da._collections["mtg_json.cardPrices"] = mock_prices

        result = da.get_prices_for_cards(["Test Card"])
        assert "Test Card" in result
        assert isinstance(result["Test Card"], PriceData)
        assert result["Test Card"].usd == 10.50

    def test_get_legalities_for_cards(self, data_access):
        """Test get_legalities_for_cards returns legality data."""
        da = data_access
        da._databases["mtg_json"].list_collection_names.return_value = ["cards", "cardLegalities"]
        
        mock_cards = MagicMock()
        mock_cards.find.return_value = [{"uuid": "123", "name": "Test Card"}]
        da._collections["mtg_json.cards"] = mock_cards

        mock_legalities = MagicMock()
        mock_legalities.find.return_value = [{
            "uuid": "123",
            "legalities": {"commander": "legal", "standard": "not_legal"}
        }]
        da._collections["mtg_json.cardLegalities"] = mock_legalities

        result = da.get_legalities_for_cards(["Test Card"])
        assert "Test Card" in result
        assert isinstance(result["Test Card"], CardLegalities)
        assert result["Test Card"].is_legal_in("commander") is True
        assert result["Test Card"].is_legal_in("standard") is False

    def test_get_keyword_taxonomy(self, data_access):
        """Test get_keyword_taxonomy returns keyword data."""
        da = data_access
        mock_keywords = MagicMock()
        mock_keywords.find.return_value = [
            {"keyword": "Flying", "description": "This creature can't be blocked except by creatures with flying or reach."},
            {"keyword": "Trample", "description": "This creature can deal excess damage to the player or planeswalker it's attacking."}
        ]
        da._collections["mtg_json.keywords"] = mock_keywords
        da._databases["mtg_json"].list_collection_names.return_value = ["keywords"]

        result = da.get_keyword_taxonomy()
        assert "Flying" in result
        assert "Trample" in result
        assert len(result["Flying"]) == 1

    def test_get_archetype_data(self, data_access):
        """Test get_archetype_data returns archetypes."""
        da = data_access
        mock_archetypes = MagicMock()
        mock_archetypes.find.return_value = [
            {"name": "Aggro", "description": "Fast aggressive deck", "colorIdentities": [["R"]], "keyCards": ["Goblin Guide"]},
            {"name": "Control", "description": "Control the game", "colorIdentities": [["U", "W"]], "keyCards": ["Counterspell"]}
        ]
        da._collections["mtg_archetypes.archetypes"] = mock_archetypes
        da._databases["mtg_archetypes"].list_collection_names.return_value = ["archetypes"]

        result = da.get_archetype_data()
        assert len(result) == 2
        assert all(isinstance(a, Archetype) for a in result)
        assert result[0].name == "Aggro"

    def test_get_articles(self, data_access):
        """Test get_articles returns articles."""
        da = data_access
        mock_articles = MagicMock()
        mock_articles.aggregate.return_value = iter([
            {"title": "Article 1", "content": "Content 1", "tags": ["commander"]},
            {"title": "Article 2", "content": "Content 2", "tags": ["deckbuilding"]}
        ])
        da._collections["edhrec.articles"] = mock_articles
        da._databases["edhrec"].list_collection_names.return_value = ["articles"]

        result = da.get_articles(limit=10)
        assert len(result) == 2
        assert all(isinstance(a, Article) for a in result)

    def test_get_guides(self, data_access):
        """Test get_guides returns guides."""
        da = data_access
        da._databases["edhrec"].list_collection_names.return_value = ["guides"]
        
        mock_guides = MagicMock()
        mock_guides.aggregate.return_value = iter([
            {"title": "Guide 1", "chapters": [{"title": "Ch1", "content": "Content"}], "tags": ["beginner"]}
        ])
        da._collections["edhrec.guides"] = mock_guides

        result = da.get_guides(limit=10)
        assert len(result) == 1
        assert isinstance(result[0], Guide)

    def test_get_game_states(self, data_access):
        """Test get_game_states returns game states."""
        da = data_access
        mock_games = MagicMock()
        mock_games.aggregate.return_value = iter([
            {"turn": 5, "phase": "combat", "player_state": {}, "decision_point": "attack", "optimal_action": "attack with all"}
        ])
        da._collections["mtg_training.games"] = mock_games
        da._databases["mtg_training"].list_collection_names.return_value = ["games"]

        result = da.get_game_states(limit=10)
        assert len(result) == 1
        assert isinstance(result[0], GameState)

    def test_get_rules(self, data_access):
        """Test get_rules returns rules."""
        da = data_access
        mock_rules = MagicMock()
        mock_rules.aggregate.return_value = iter([
            {"ruleNumber": "101.1", "section": "General", "text": "Magic is a game...", "category": "general"}
        ])
        da._collections["mtg_rules.rules"] = mock_rules
        da._databases["mtg_rules"].list_collection_names.return_value = ["rules"]

        result = da.get_rules()
        assert len(result) == 1
        assert isinstance(result[0], Rule)
        assert result[0].rule_number == "101.1"

    def test_get_glossary(self, data_access):
        """Test get_glossary returns glossary terms."""
        da = data_access
        mock_glossary = MagicMock()
        mock_glossary.aggregate.return_value = iter([
            {"term": "Mana", "definition": "Magical energy", "relatedTerms": ["Mana cost"]}
        ])
        da._collections["mtg_rules.glossary"] = mock_glossary
        da._databases["mtg_rules"].list_collection_names.return_value = ["glossary"]

        result = da.get_glossary()
        assert len(result) == 1
        assert isinstance(result[0], GlossaryTerm)
        assert result[0].term == "Mana"


class TestAnalyticsMethods:
    """Tests for analytics methods."""

    @pytest.fixture
    def data_access(self):
        """Create MTGDataAccess with mocked collections."""
        with patch("training_data.generate_synthetic_data.data_access.MongoClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.admin.command.return_value = {"ok": 1}

            da = MTGDataAccess()
            da._client = mock_client

            for db_name in ["mtg_json", "commander_spellbook", "edhrec"]:
                mock_db = MagicMock()
                mock_db.list_collection_names.return_value = []
                mock_client.__getitem__.return_value = mock_db
                da._databases[db_name] = mock_db

            yield da

    def test_get_top_cards_by_edhrec_rank(self, data_access):
        """Test get_top_cards_by_edhrec_rank."""
        da = data_access
        mock_cards = MagicMock()
        mock_cards.aggregate.return_value = iter([
            {"name": "Sol Ring", "uuid": "123", "type": "Artifact", "manaCost": "{1}", "edhrecRank": 1}
        ])
        da._collections["mtg_json.cards"] = mock_cards
        da._databases["mtg_json"].list_collection_names.return_value = ["cards", "cardPrices", "cardLegalities", "cardRulings", "keywords"]

        result = da.get_top_cards_by_edhrec_rank(["W", "U"], limit=10)
        assert len(result) == 1
        assert result[0].name == "Sol Ring"

    def test_get_budget_alternatives(self, data_access):
        """Test get_budget_alternatives."""
        da = data_access
        # Mock get_card_by_name
        da.get_card_by_name = Mock(return_value=CardWithMetadata(
            name="Expensive Card",
            uuid="123",
            type="Creature",
            manaCost="{3}{W}{W}",
            keywords=["Flying", "Vigilance"],
            colorIdentity=["W"]
        ))

        mock_cards = MagicMock()
        mock_cards.aggregate.return_value = iter([
            {"name": "Budget Card", "uuid": "456", "type": "Creature", "manaCost": "{2}{W}", "keywords": ["Flying"]}
        ])
        da._collections["mtg_json.cards"] = mock_cards
        da._databases["mtg_json"].list_collection_names.return_value = ["cards", "cardPrices", "cardLegalities", "cardRulings", "keywords"]

        result = da.get_budget_alternatives("Expensive Card", max_price=5.0, limit=5)
        assert len(result) == 1
        assert result[0].name == "Budget Card"

    def test_get_synergy_partners(self, data_access):
        """Test get_synergy_partners."""
        da = data_access
        mock_combos = MagicMock()
        mock_combos.aggregate.return_value = iter([
            {"name": "Partner Card", "uuid": "789", "type": "Creature", "manaCost": "{1}{G}"}
        ])
        da._collections["commander_spellbook.variants"] = mock_combos
        da._databases["commander_spellbook"].list_collection_names.return_value = ["variants"]

        result = da.get_synergy_partners("Test Card", limit=10)
        assert len(result) == 1
        assert result[0].name == "Partner Card"

    def test_calculate_color_identity(self, data_access):
        """Test calculate_color_identity."""
        da = data_access

        # Test with mana cost
        colors = da.calculate_color_identity("{1}{W}{U}", None, None)
        assert "W" in colors
        assert "U" in colors

        # Test with color indicator
        colors = da.calculate_color_identity(None, None, ["B", "R"])
        assert "B" in colors
        assert "R" in colors

        # Test with mana symbols in text
        colors = da.calculate_color_identity(None, "{T}: Add {G}", None)
        assert "G" in colors

    def test_search_cards_text(self, data_access):
        """Test search_cards_text."""
        da = data_access
        mock_cards = MagicMock()
        mock_cards.aggregate.return_value = iter([
            {"name": "Card with Flying", "uuid": "123", "type": "Creature", "manaCost": "{2}{W}", "oracleText": "Flying"}
        ])
        da._collections["mtg_json.cards"] = mock_cards
        da._databases["mtg_json"].list_collection_names.return_value = ["cards", "cardPrices", "cardLegalities", "cardRulings", "keywords"]

        result = da.search_cards_text(r"flying", limit=10)
        assert len(result) == 1
        assert result[0].name == "Card with Flying"


class TestHelperMethods:
    """Tests for helper methods."""

    @pytest.fixture
    def data_access(self):
        """Create MTGDataAccess instance."""
        with patch("training_data.generate_synthetic_data.data_access.MongoClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.admin.command.return_value = {"ok": 1}

            da = MTGDataAccess()
            da._client = mock_client
            yield da

    def test_convert_doc_to_model_success(self, data_access):
        """Test _convert_doc_to_model with valid document."""
        da = data_access
        doc = {"name": "Test", "uuid": "123", "type": "Creature", "manaCost": "{1}"}
        result = da._convert_doc_to_model(doc, CardWithMetadata)
        assert result is not None
        assert result.name == "Test"

    def test_convert_doc_to_model_failure(self, data_access):
        """Test _convert_doc_to_model with invalid document."""
        da = data_access
        doc = {"invalid": "data"}  # Missing required fields
        result = da._convert_doc_to_model(doc, CardWithMetadata)
        assert result is None


class TestPipelineBuilders:
    """Tests for aggregation pipeline builder methods."""

    @pytest.fixture
    def data_access(self):
        """Create MTGDataAccess instance."""
        with patch("training_data.generate_synthetic_data.data_access.MongoClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.admin.command.return_value = {"ok": 1}

            da = MTGDataAccess()
            da._client = mock_client
            yield da

    def test_build_card_enrichment_pipeline(self, data_access):
        """Test _build_card_enrichment_pipeline returns valid pipeline."""
        da = data_access
        pipeline = da._build_card_enrichment_pipeline({"colorIdentity": ["W"]}, 10, 0)

        assert isinstance(pipeline, list)
        assert len(pipeline) > 0
        stages = [list(stage.keys())[0] for stage in pipeline]
        assert "$match" in stages
        assert "$lookup" in stages
        assert "$project" in stages
        assert "$limit" in stages

    def test_build_card_enrichment_pipeline_with_skip(self, data_access):
        """Test pipeline includes $skip when skip > 0."""
        da = data_access
        pipeline = da._build_card_enrichment_pipeline({}, 10, 5)

        stages = [list(stage.keys())[0] for stage in pipeline]
        assert "$skip" in stages

    def test_build_combo_pipeline(self, data_access):
        """Test _build_combo_pipeline returns valid pipeline."""
        da = data_access
        pipeline = da._build_combo_pipeline({"tags": "infinite"}, 20)

        assert isinstance(pipeline, list)
        stages = [list(stage.keys())[0] for stage in pipeline]
        # Pipeline: $match -> $sample -> $addFields (uses transform) -> $addFields (produces transform) -> $project
        assert "$match" in stages
        assert "$sample" in stages
        assert "$addFields" in stages
        assert "$project" in stages

        # Verify match stage includes both status filter and custom filters
        match_stage = [s for s in pipeline if "$match" in s][0]["$match"]
        assert match_stage["status"] == "OK"
        assert match_stage["tags"] == "infinite"

        # Verify sample size value
        sample_stage = [s for s in pipeline if "$sample" in s][0]["$sample"]
        assert sample_stage["size"] == 20

    def test_build_commander_pipeline(self, data_access):
        """Test _build_commander_pipeline returns valid pipeline."""
        da = data_access
        pipeline = da._build_commander_pipeline({"colorIdentity": ["W", "U"]}, 15)

        assert isinstance(pipeline, list)
        stages = [list(stage.keys())[0] for stage in pipeline]
        # Pipeline: $match -> $sample -> $project (with field mapping)
        assert "$match" in stages
        assert "$sample" in stages
        assert "$project" in stages

        # Verify match stage passes through filters
        match_stage = [s for s in pipeline if "$match" in s][0]["$match"]
        assert match_stage["colorIdentity"] == ["W", "U"]

        # Verify sample size value
        sample_stage = [s for s in pipeline if "$sample" in s][0]["$sample"]
        assert sample_stage["size"] == 15

        # Verify project stage maps fields correctly
        project_stage = [s for s in pipeline if "$project" in s][0]["$project"]
        assert project_stage["colorIdentity"] == "$color_identity"
        assert project_stage["numDecks"] is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])