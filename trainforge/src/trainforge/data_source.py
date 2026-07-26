"""Data source abstraction layer — domain-agnostic storage interface."""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from typing import Any

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

logger = logging.getLogger(__name__)


# =============================================================================
# ABSTRACT DATA SOURCE
# =============================================================================


class DataSource(ABC):
    """Abstract interface for domain data storage.

    Implementations handle connecting to a backend (MongoDB, PostgreSQL, etc.)
    and providing typed access to records. The generic framework only interacts
    through this interface — it never touches MongoDB directly.
    """

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the data backend."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Close connection and release resources."""
        ...

    @abstractmethod
    def get_records(
        self, collection: str, filters: dict | None = None, limit: int = 100, skip: int = 0
    ) -> list[dict]:
        """Fetch records from a collection with optional filtering.

        Args:
            collection: Collection/table name
            filters: Query filter dict (backend-specific format)
            limit: Maximum number of records to return
            skip: Number of records to skip (pagination)

        Returns:
            List of record dicts
        """
        ...

    @abstractmethod
    def save_record(self, collection: str, record: dict, dedup_key: str | None = None) -> bool:
        """Save a single record, optionally skipping duplicates.

        Args:
            collection: Collection/table name
            record: Record dict to save
            dedup_key: If set, skip insert if a document with this key already exists

        Returns:
            True if inserted, False if skipped (duplicate)
        """
        ...

    @abstractmethod
    def search(
        self, collection: str, query: str, field: str | None = None, limit: int = 50
    ) -> list[dict]:
        """Full-text or regex search within a collection.

        Args:
            collection: Collection/table name
            query: Search string (treated as regex)
            field: Specific field to search (None = all fields)
            limit: Maximum results

        Returns:
            Matching record dicts
        """
        ...

    @abstractmethod
    def count(self, collection: str, filters: dict | None = None) -> int:
        """Count records matching a filter."""
        ...

    @abstractmethod
    def delete_records(self, collection: str, filters: dict) -> int:
        """Delete records matching a filter. Returns count of deleted records."""
        ...

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


# =============================================================================
# MONGODB IMPLEMENTATION
# =============================================================================


class MongoDataSource(DataSource):
    """MongoDB-backed data source implementation."""

    DEFAULT_DATABASE = "synthetic_queries"

    def __init__(
        self,
        uri: str = "mongodb://localhost:27017",
        username: str | None = None,
        password: str | None = None,
        auth_source: str = "admin",
        max_pool_size: int = 50,
        min_pool_size: int = 5,
    ):
        self.uri = uri
        self.username = username
        self.password = password
        self.auth_source = auth_source
        self.max_pool_size = max_pool_size
        self.min_pool_size = min_pool_size

        self._client: MongoClient | None = None
        self._databases: dict[str, Database] = {}
        self._lock = threading.RLock()

    def connect(self) -> None:
        with self._lock:
            if self._client is not None:
                return
            self._client = MongoClient(
                self.uri,
                username=self.username,
                password=self.password,
                authSource=self.auth_source,
                maxPoolSize=self.max_pool_size,
                minPoolSize=self.min_pool_size,
            )
            self._client.admin.command("ping")
            logger.info("MongoDB connection established")

    def close(self) -> None:
        with self._lock:
            if self._client is not None:
                self._client.close()
                self._client = None
                self._databases.clear()
                logger.info("MongoDB connection closed")

    def _ensure_connected(self) -> MongoClient:
        if self._client is None:
            self.connect()
        assert self._client is not None
        return self._client

    def _get_db(self, name: str) -> Database:
        client = self._ensure_connected()
        if name not in self._databases:
            self._databases[name] = client[name]
        return self._databases[name]

    def _get_collection(self, db_name: str, coll_name: str) -> Collection:
        return self._get_db(db_name)[coll_name]

    # --- Abstract method implementations ---

    def get_records(
        self, collection: str, filters: dict | None = None, limit: int = 100, skip: int = 0
    ) -> list[dict]:
        """Fetch records. Collection name can be 'db.coll' or just 'coll' (uses default db)."""
        parts = collection.split(".", 1)
        if len(parts) == 2:
            db_name, coll_name = parts
        else:
            db_name = self.DEFAULT_DATABASE
            coll_name = collection

        coll = self._get_collection(db_name, coll_name)
        cursor = coll.find(filters or {}).skip(skip).limit(limit)
        return list(cursor)

    def save_record(
        self, collection: str, record: dict, dedup_key: str | None = None
    ) -> bool:
        parts = collection.split(".", 1)
        if len(parts) == 2:
            db_name, coll_name = parts
        else:
            db_name = self.DEFAULT_DATABASE
            coll_name = collection

        coll = self._get_collection(db_name, coll_name)

        if dedup_key and dedup_key in record:
            existing = coll.find_one({dedup_key: record[dedup_key]})
            if existing:
                return False  # Duplicate

        coll.insert_one(record)
        return True

    def search(
        self, collection: str, query: str, field: str | None = None, limit: int = 50
    ) -> list[dict]:
        parts = collection.split(".", 1)
        if len(parts) == 2:
            db_name, coll_name = parts
        else:
            db_name = self.DEFAULT_DATABASE
            coll_name = collection

        coll = self._get_collection(db_name, coll_name)

        if field:
            filter_doc = {field: {"$regex": query, "$options": "i"}}
        else:
            # Search across common text fields
            filter_doc = {
                "$or": [
                    {k: {"$regex": query, "$options": "i"}}
                    for k in ["question", "answer", "category", "name"]
                ]
            }

        return list(coll.find(filter_doc).limit(limit))

    def count(self, collection: str, filters: dict | None = None) -> int:
        parts = collection.split(".", 1)
        if len(parts) == 2:
            db_name, coll_name = parts
        else:
            db_name = self.DEFAULT_DATABASE
            coll_name = collection

        coll = self._get_collection(db_name, coll_name)
        return coll.count_documents(filters or {})

    def delete_records(self, collection: str, filters: dict) -> int:
        parts = collection.split(".", 1)
        if len(parts) == 2:
            db_name, coll_name = parts
        else:
            db_name = self.DEFAULT_DATABASE
            coll_name = collection

        coll = self._get_collection(db_name, coll_name)
        result = coll.delete_many(filters)
        return result.deleted_count

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
        if coll is None:
            return []
        return list(coll.aggregate(pipeline, allowDiskUse=allow_disk_use))
