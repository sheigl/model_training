"""MongoDB-backed metrics for the generator dashboard.

Reads ``ValidationMetrics`` documents from ``synthetic_metrics.generator_runs``
and recent ``generation_traces``. Degrades gracefully when MongoDB is
unreachable (returns ``None`` / ``[]`` instead of raising).
"""

from __future__ import annotations

from pymongo import DESCENDING, MongoClient

RUNS_COLLECTION = "generator_runs"
TRACES_COLLECTION = "generation_traces"


class MetricsStore:
    def __init__(
        self,
        uri: str = "mongodb://localhost:27017/",
        username: str = "root",
        password: str = "whatever",
    ):
        self._client = MongoClient(
            uri,
            username=username,
            password=password,
            authSource="admin",
            serverSelectionTimeoutMS=2000,
            connectTimeoutMS=2000,
        )
        db = self._client["synthetic_metrics"]
        self._runs = db[RUNS_COLLECTION]
        self._traces = db[TRACES_COLLECTION]
        self._connected = self._check()

    def _check(self) -> bool:
        try:
            self._client.admin.command("ping")
            return True
        except Exception:
            return False

    @property
    def connected(self) -> bool:
        if not self._connected:
            return False
        try:
            self._client.admin.command("ping")
            return True
        except Exception:
            self._connected = False
            return False

    def latest(self, generator_name: str) -> dict | None:
        """Return the most recent metrics doc for a generator (or None)."""
        if not self.connected:
            return None
        try:
            doc = self._runs.find_one(
                {"generator_name": generator_name},
                sort=[("updated_at", DESCENDING)],
            )
        except Exception:
            return None
        if not doc:
            return None
        return {
            "updated_at": doc.get("updated_at"),
            "run_id": doc.get("run_id"),
            "metrics": doc.get("metrics", {}),
        }

    def recent_traces(self, category: str, limit: int = 25) -> list[dict]:
        """Return the most recent generation traces for a category."""
        if not self.connected:
            return []
        try:
            cursor = (
                self._traces.find({"category": category})
                .sort("created_at", DESCENDING)
                .limit(limit)
            )
            return [
                {
                    "final_outcome": t.get("final_outcome", "pending"),
                    "created_at": t.get("created_at"),
                    "source_template": t.get("source_template"),
                    "generation_latency_ms": t.get("generation_latency_ms"),
                    "template_version": t.get("template_version"),
                }
                for t in cursor
            ]
        except Exception:
            return []
