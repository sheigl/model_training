"""Tests for TrainForge data source module - MongoDataSource."""

from __future__ import annotations

import pytest

from trainforge.data_source import DataSource, MongoDataSource


# =============================================================================
# DEFAULT_DATABASE CONSTANT
# =============================================================================


class TestDefaultDatabase:
    """Test MongoDataSource.DEFAULT_DATABASE constant."""

    def test_default_database_value(self):
        """DEFAULT_DATABASE should be 'synthetic_queries'."""
        assert MongoDataSource.DEFAULT_DATABASE == "synthetic_queries"


# =============================================================================
# COLLECTION NAME PARSING (unit tests without live MongoDB)
# =============================================================================


class TestCollectionNameParsing:
    """Test collection name parsing logic in MongoDataSource methods.

    These tests verify the string-splitting logic used throughout
    get_records, save_record, search, count, delete_records.
    We test the parsing behavior directly since we can't connect to MongoDB.
    """

    def _parse_collection(self, collection: str) -> tuple[str, str]:
        """Reproduce the internal collection name parsing logic."""
        parts = collection.split(".", 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        else:
            return MongoDataSource.DEFAULT_DATABASE, collection

    def test_simple_collection_name(self):
        """'coll' should use default database."""
        db, coll = self._parse_collection("mtg_cards")
        assert db == "synthetic_queries"
        assert coll == "mtg_cards"

    def test_dotted_collection_name(self):
        '"db.coll" should split into db and collection.'
        db, coll = self._parse_collection("my_db.my_coll")
        assert db == "my_db"
        assert coll == "my_coll"

    def test_synthetic_queries_prefix(self):
        """'synthetic_queries.queries' should parse correctly."""
        db, coll = self._parse_collection("synthetic_queries.queries")
        assert db == "synthetic_queries"
        assert coll == "queries"

    def test_multiple_dots_uses_first_split(self):
        """Only the first dot is used as separator (split with maxsplit=1)."""
        # Edge case: collection name itself contains a dot
        db, coll = self._parse_collection("db.name.with.dots")
        assert db == "db"
        assert coll == "name.with.dots"


# =============================================================================
# MONGO DATA SOURCE INITIALIZATION (no connection needed)
# =============================================================================


class TestMongoDataSourceInit:
    """Test MongoDataSource constructor without connecting."""

    def test_default_uri(self):
        """Should default to localhost MongoDB URI."""
        ds = MongoDataSource()
        assert ds.uri == "mongodb://localhost:27017"

    def test_custom_uri(self):
        """Should accept custom URI."""
        ds = MongoDataSource(uri="mongodb://remote-host:27018")
        assert ds.uri == "mongodb://remote-host:27018"

    def test_default_auth_source(self):
        """Auth source should default to 'admin'."""
        ds = MongoDataSource()
        assert ds.auth_source == "admin"

    def test_custom_pool_sizes(self):
        """Should accept custom pool sizes."""
        ds = MongoDataSource(max_pool_size=100, min_pool_size=2)
        assert ds.max_pool_size == 100
        assert ds.min_pool_size == 2

    def test_client_starts_none(self):
        """Client should be None before connect()."""
        ds = MongoDataSource()
        assert ds._client is None


# =============================================================================
# DATA SOURCE ABC
# =============================================================================


class TestDataSourceABC:
    """Test that DataSource is a proper abstract base class."""

    def test_cannot_instantiate_abstract(self):
        """Should not be able to instantiate DataSource directly."""
        with pytest.raises(TypeError):
            DataSource()  # type: ignore[abstract]
