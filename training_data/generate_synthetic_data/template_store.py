"""Versioned template store backed by MongoDB.

This module provides the canonical :class:`TemplateStore` implementation used by
the legacy synthetic-data CLI. The MongoDB document schema (generator, template_id,
template_type, version) is intentionally portable — other tools can adopt it
independently without sharing code.

Document shape (one row per ``(generator, template_id, template_type, version)``)::

    {
      generator: "combo_query",
      template_id: "how_does_it_work",
      template_type: "generation",   # "generation" | "validator"
      version: 1,
      yaml_content: "...",
      created_at: "ISO timestamp",
      is_latest: true                # exactly one doc per key has this=true
    }

The store is constructed from a plain :class:`pymongo.collection.Collection` so it
has no hard dependency on ``MTGDataAccess`` or ``DomainPlugin`` and is reusable
from either codebase.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import yaml
from pymongo import MongoClient
from pymongo.collection import Collection

from .common import TemplateConfig, _dict_to_template_config


class TemplateStore:
    """Versioned template store backed by MongoDB.

    One doc per ``(generator, template_id, template_type, version)``.
    Exactly one doc per ``(generator, template_id, template_type)`` has
    ``is_latest=True``.
    """

    #: Reserved generator namespace for cross-generator scaffolding blocks
    #: (e.g. ``SYSTEM_MESSAGE``, ``MTG_NOTATION_LEGEND``, ``REQUIREMENTS_BASE``).
    SHARED_NAMESPACE = "__shared__"

    def __init__(self, collection: Collection) -> None:
        """Construct from a pymongo collection.

        Example::

            client = MongoClient(uri)
            store = TemplateStore(client["synthetic_metrics"]["templates"])
        """
        self._coll = collection
        self._ensure_indexes()

    @classmethod
    def from_uri(
        cls,
        uri: str,
        username: str | None = None,
        password: str | None = None,
        auth_source: str = "admin",
        db: str = "synthetic_metrics",
        collection: str = "templates",
    ) -> "TemplateStore":
        """Convenience constructor from a MongoDB URI."""
        client = MongoClient(uri, username=username, password=password, authSource=auth_source)
        return cls(client[db][collection])

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------
    def _ensure_indexes(self) -> None:
        """Idempotently create the required indexes.

        * Compound unique index on ``(generator, template_id, template_type, version)``
          prevents duplicate versions and guards against race-condition inserts.
        * Index on ``(generator, template_id, template_type, is_latest)`` speeds
          the latest-lookup path.
        """
        self._coll.create_index(
            [("generator", 1), ("template_id", 1), ("template_type", 1), ("version", 1)],
            unique=True,
            name="uniq_gen_tid_type_ver",
        )
        self._coll.create_index(
            [("generator", 1), ("template_id", 1), ("template_type", 1), ("is_latest", 1)],
            name="idx_latest",
        )

    # ------------------------------------------------------------------
    # Read paths
    # ------------------------------------------------------------------
    def get_latest(self, generator: str, template_id: str, template_type: str) -> dict | None:
        """Return the latest doc for the key, or ``None``."""
        return self._coll.find_one(
            {
                "generator": generator,
                "template_id": template_id,
                "template_type": template_type,
                "is_latest": True,
            }
        )

    def get_version(
        self, generator: str, template_id: str, template_type: str, version: int
    ) -> dict | None:
        """Return a specific version doc, or ``None``."""
        return self._coll.find_one(
            {
                "generator": generator,
                "template_id": template_id,
                "template_type": template_type,
                "version": version,
            }
        )

    def list_versions(self, generator: str, template_id: str, template_type: str) -> list[dict]:
        """Return all version docs for the key, sorted by version descending."""
        return list(
            self._coll.find(
                {
                    "generator": generator,
                    "template_id": template_id,
                    "template_type": template_type,
                }
            ).sort("version", -1)
        )

    # ------------------------------------------------------------------
    # Write paths
    # ------------------------------------------------------------------
    def upsert(
        self, generator: str, template_id: str, template_type: str, yaml_content: str
    ) -> int:
        """Insert a new version, flipping the previous latest to ``is_latest=False``.

        Returns the new version number.

        Idempotent: if ``yaml_content`` matches the current latest, this is a
        no-op and the existing version number is returned.

        Invariant: exactly one doc per ``(generator, template_id, template_type)``
        has ``is_latest=True``. Bumping a version creates a new doc with
        ``is_latest=True`` and flips the previous latest to ``is_latest=False``.
        The compound unique index on ``(generator, template_id, template_type, version)``
        guards against race-condition duplicates.
        """
        existing_latest = self.get_latest(generator, template_id, template_type)
        if existing_latest and existing_latest["yaml_content"] == yaml_content:
            return existing_latest["version"]  # no change needed

        new_version = (existing_latest["version"] + 1) if existing_latest else 1
        now = datetime.utcnow().isoformat() + "Z"

        # Insert new doc first (unique index guards against races)
        self._coll.insert_one(
            {
                "generator": generator,
                "template_id": template_id,
                "template_type": template_type,
                "version": new_version,
                "yaml_content": yaml_content,
                "created_at": now,
                "is_latest": True,
            }
        )
        # Flip old latest
        if existing_latest:
            self._coll.update_one(
                {"_id": existing_latest["_id"]},
                {"$set": {"is_latest": False}},
            )
        return new_version

    def delete_version(
        self, generator: str, template_id: str, template_type: str, version: int
    ) -> bool:
        """Delete a specific version.

        Refuses to delete the only version (raises ``ValueError``). If the
        deleted version was the latest, the next-highest version is promoted to
        ``is_latest=True`` so the invariant is preserved.

        Returns ``True`` if a doc was deleted, ``False`` if the version was
        not found.
        """
        doc = self.get_version(generator, template_id, template_type, version)
        if not doc:
            return False
        if doc["is_latest"]:
            versions = self.list_versions(generator, template_id, template_type)
            if len(versions) == 1:
                raise ValueError("Cannot delete the only version")
            # Promote the next-highest version to latest
            next_latest = max(
                (v for v in versions if v["version"] != version),
                key=lambda v: v["version"],
            )
            self._coll.update_one(
                {"_id": next_latest["_id"]},
                {"$set": {"is_latest": True}},
            )
        self._coll.delete_one({"_id": doc["_id"]})
        return True

    def seed(self, templates: list[dict]) -> dict:
        """Idempotent bulk import.

        Each dict in *templates* must have ``generator``, ``template_id``,
        ``template_type`` and ``yaml_content`` keys. All imported docs are
        inserted at ``version=1`` with ``is_latest=True``. Docs where
        ``(generator, template_id, template_type, version=1)`` already exists
        are skipped.

        Returns ``{"inserted": int, "skipped": int}``.
        """
        inserted = 0
        skipped = 0
        for t in templates:
            existing = self.get_version(t["generator"], t["template_id"], t["template_type"], 1)
            if existing:
                skipped += 1
                continue
            now = datetime.utcnow().isoformat() + "Z"
            self._coll.insert_one(
                {
                    "generator": t["generator"],
                    "template_id": t["template_id"],
                    "template_type": t["template_type"],
                    "version": 1,
                    "yaml_content": t["yaml_content"],
                    "created_at": now,
                    "is_latest": True,
                }
            )
            inserted += 1
        return {"inserted": inserted, "skipped": skipped}

    # ------------------------------------------------------------------
    # Conversion helper
    # ------------------------------------------------------------------
    @staticmethod
    def to_template_config(doc: dict) -> TemplateConfig:
        """Parse ``yaml_content`` into a legacy :class:`common.TemplateConfig`.

        Delegates to :func:`common._dict_to_template_config` for the actual
        conversion so that both MongoDB docs and YAML loader dicts share the
        same logic.
        """
        return _dict_to_template_config(doc)