# Technical Plan: Story 040 — MongoDB Versioned Template Store

## 1. Architecture & Design Decisions

### Location of `TemplateStore`
**Decision**: `TemplateStore` lives in the legacy CLI at `training_data/generate_synthetic_data/template_store.py` as the canonical implementation. TrainForge gets a **thin read-only client** at `trainforge/src/trainforge/template_store.py` that reads the same MongoDB collection but does NOT import the legacy package (avoids a cross-package dependency). Both classes share the same MongoDB document schema and collection name.

**Rationale**: The legacy CLI is the active system and owns the write path (seed, upsert). TrainForge only needs read access (get_latest, get_version, list_versions). Duplicating a thin reader is simpler than a shared package and keeps the two codebases independently deployable.

### Collection name
**Decision**: `synthetic_metrics.templates` (same database as `generator_runs` and `generation_traces`).

**Rationale**: Co-locates with the other metrics/metadata collections in `synthetic_metrics` DB. Both codebases already connect to this DB. The `MongoDataSource.DEFAULT_DATABASE = "synthetic_queries"` is for generated Q&A, not metadata.

### `TemplateConfig` unification
**Decision**: Keep both `TemplateConfig` classes (legacy frozen dataclass + TrainForge plain class) unchanged in shape. `TemplateStore.to_template_config()` returns the **legacy** `common.TemplateConfig` (since the store lives in the legacy package). TrainForge's thin client has `to_trainforge_template_config(doc)` that returns `trainforge.domain.TemplateConfig`. Both parse the same `yaml_content`.

**Future**: A shared neutral `TemplateConfig` could be introduced, but that's a larger refactor out of scope here. The two classes have identical fields, so conversion is trivial.

### `is_latest` invariant enforcement
**Decision**: Use a **MongoDB transaction** (or `find_one_and_update` sequence if transactions unavailable) in `upsert()`:
1. Find the current latest doc for `(generator, template_id, template_type)`.
2. If none, insert new doc with `version=1, is_latest=true`.
3. If exists, insert new doc with `version=existing.version+1, is_latest=true`, then update the old doc to `is_latest=false`.
4. Wrap steps 2-3 in a transaction with the unique index as the safety net.

The compound unique index on `(generator, template_id, template_type, version)` prevents race-condition duplicates. If a transaction fails due to a duplicate key, retry or raise.

## 2. Data Model

### MongoDB Document Schema
```python
{
  "_id": ObjectId,                    # auto
  "generator": str,                   # e.g. "combo_query", "__shared__"
  "template_id": str,                 # e.g. "how_does_it_work", "system_message"
  "template_type": str,               # "generation" | "validator"
  "version": int,                     # 1, 2, 3, ...
  "yaml_content": str,                # YAML text (see §4)
  "created_at": str,                  # ISO 8601 timestamp
  "is_latest": bool,                  # exactly one true per (generator, template_id, template_type)
}
```

### Indexes
```python
# Unique — prevents duplicate versions
templates.create_index(
    [("generator", 1), ("template_id", 1), ("template_type", 1), ("version", 1)],
    unique=True,
    name="uniq_gen_tid_type_ver",
)

# Fast latest lookup
templates.create_index(
    [("generator", 1), ("template_id", 1), ("template_type", 1), ("is_latest", 1)],
    name="idx_latest",
)
```

## 3. `TemplateStore` API

```python
# training_data/generate_synthetic_data/template_store.py

from datetime import datetime
from typing import Any
import yaml
from pymongo.collection import Collection
from pymongo import MongoClient
from .common import TemplateConfig


class TemplateStore:
    """Versioned template store backed by MongoDB.

    One doc per (generator, template_id, template_type, version).
    Exactly one doc per (generator, template_id, template_type) has is_latest=True.
    """

    def __init__(self, collection: Collection):
        """Construct from a pymongo collection (e.g. client['synthetic_metrics']['templates'])."""
        self._coll = collection
        self._ensure_indexes()

    @classmethod
    def from_uri(cls, uri: str, username: str | None = None, password: str | None = None,
                 auth_source: str = "admin", db: str = "synthetic_metrics",
                 collection: str = "templates") -> "TemplateStore":
        """Convenience constructor from a MongoDB URI."""
        client = MongoClient(uri, username=username, password=password, authSource=auth_source)
        return cls(client[db][collection])

    def _ensure_indexes(self) -> None:
        """Idempotently create indexes."""
        self._coll.create_index(
            [("generator", 1), ("template_id", 1), ("template_type", 1), ("version", 1)],
            unique=True, name="uniq_gen_tid_type_ver",
        )
        self._coll.create_index(
            [("generator", 1), ("template_id", 1), ("template_type", 1), ("is_latest", 1)],
            name="idx_latest",
        )

    def get_latest(self, generator: str, template_id: str, template_type: str) -> dict | None:
        """Return the latest doc for the key, or None."""
        return self._coll.find_one({
            "generator": generator, "template_id": template_id,
            "template_type": template_type, "is_latest": True,
        })

    def get_version(self, generator: str, template_id: str, template_type: str,
                    version: int) -> dict | None:
        """Return a specific version doc, or None."""
        return self._coll.find_one({
            "generator": generator, "template_id": template_id,
            "template_type": template_type, "version": version,
        })

    def list_versions(self, generator: str, template_id: str,
                      template_type: str) -> list[dict]:
        """Return all version docs for the key, sorted by version descending."""
        return list(self._coll.find({
            "generator": generator, "template_id": template_id,
            "template_type": template_type,
        }).sort("version", -1))

    def upsert(self, generator: str, template_id: str, template_type: str,
               yaml_content: str) -> int:
        """Insert a new version, flipping the previous latest to is_latest=False.

        Returns the new version number.
        Idempotent: if yaml_content matches the current latest, no-op.
        """
        existing_latest = self.get_latest(generator, template_id, template_type)
        if existing_latest and existing_latest["yaml_content"] == yaml_content:
            return existing_latest["version"]  # no change needed

        new_version = (existing_latest["version"] + 1) if existing_latest else 1
        now = datetime.utcnow().isoformat() + "Z"

        # Insert new doc first (unique index guards against races)
        self._coll.insert_one({
            "generator": generator, "template_id": template_id,
            "template_type": template_type, "version": new_version,
            "yaml_content": yaml_content, "created_at": now, "is_latest": True,
        })
        # Flip old latest
        if existing_latest:
            self._coll.update_one(
                {"_id": existing_latest["_id"]},
                {"$set": {"is_latest": False}},
            )
        return new_version

    def delete_version(self, generator: str, template_id: str, template_type: str,
                       version: int) -> bool:
        """Delete a specific version. Refuses to delete the only/latest version."""
        doc = self.get_version(generator, template_id, template_type, version)
        if not doc:
            return False
        if doc["is_latest"]:
            versions = self.list_versions(generator, template_id, template_type)
            if len(versions) == 1:
                raise ValueError("Cannot delete the only version")
            # Promote the next-highest version to latest
            next_latest = max((v for v in versions if v["version"] != version),
                               key=lambda v: v["version"])
            self._coll.update_one({"_id": next_latest["_id"]},
                                  {"$set": {"is_latest": True}})
        self._coll.delete_one({"_id": doc["_id"]})
        return True

    def seed(self, templates: list[dict]) -> dict:
        """Idempotent bulk import. Each dict has generator, template_id, template_type, yaml_content.

        Skips docs where (generator, template_id, template_type, version=1) already exists.
        Returns {"inserted": int, "skipped": int}.
        """
        inserted = 0
        skipped = 0
        for t in templates:
            existing = self.get_version(t["generator"], t["template_id"],
                                        t["template_type"], 1)
            if existing:
                skipped += 1
                continue
            now = datetime.utcnow().isoformat() + "Z"
            self._coll.insert_one({
                "generator": t["generator"], "template_id": t["template_id"],
                "template_type": t["template_type"], "version": 1,
                "yaml_content": t["yaml_content"], "created_at": now,
                "is_latest": True,
            })
            inserted += 1
        return {"inserted": inserted, "skipped": skipped}

    @staticmethod
    def to_template_config(doc: dict) -> TemplateConfig:
        """Parse yaml_content into a legacy common.TemplateConfig."""
        data = yaml.safe_load(doc["yaml_content"]) or {}
        return TemplateConfig(
            template_id=doc["template_id"],
            task_instruction=data.get("instruction", ""),
            weight=float(data.get("weight", 1.0)),
            validation_rules=data.get("validation_rules") or [],
            min_answer_length=int(data.get("min_answer_length", 80)),
            max_answer_length=int(data.get("max_answer_length", 2000)),
        )
```

## 4. `yaml_content` Schema

The `yaml_content` field stores YAML text with this structure:

```yaml
# For template_type="generation"
instruction: |
  Generate exactly 3 Q&A pairs explaining HOW this combo works.
  ...
weight: 1.0
validation_rules:
  - "Answer must explain each card's role in the combo"
  - "All card names and effects must be accurate"
min_answer_length: 80
max_answer_length: 2000
```

```yaml
# For shared scaffolding (generator="__shared__")
content: |
  <system>
  You are an expert Magic: The Gathering rules advisor...
  </system>
# For REQUIREMENTS_BASE (a list)
content:
  - "At least one question MUST come from..."
  - "Questions must be varied..."
```

```yaml
# For template_type="validator"
instruction: |
  You are a quality validator for training data...
verification_block: |
  <rules>...</rules>
scoring_guide: |
  9-10: Excellent...
```

## 5. Shared Scaffolding Namespace

`generator="__shared__"` is a reserved namespace for cross-generator scaffolding blocks. Each block is a `template_id`:

| template_id | template_type | Source constant |
|-------------|---------------|-----------------|
| `system_message` | `generation` | `constants.SYSTEM_MESSAGE` |
| `notation_legend` | `generation` | `constants.MTG_NOTATION_LEGEND` |
| `requirements_base` | `generation` | `constants.REQUIREMENTS_BASE` (list) |
| `output_format` | `generation` | `constants.OUTPUT_FORMAT` |
| `card_comparison_instructions` | `generation` | `constants.CARD_COMPARISON_INSTRUCTIONS` |
| `validation_checklist` | `validator` | `constants.VALIDATION_CHECKLIST` |
| `validation_scoring_guide` | `validator` | `constants.VALIDATION_SCORING_GUIDE` |
| `qa_validation` | `validator` | `query_model.__build_qa_validation_prompt` body |

## 6. Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `training_data/generate_synthetic_data/template_store.py` | **NEW** | `TemplateStore` class (canonical) |
| `trainforge/src/trainforge/template_store.py` | **NEW** (Story 043) | Thin read-only client |

No existing files modified in this story.

## 7. Task Breakdown
1. Create `template_store.py` with `TemplateStore` class and all methods.
2. Implement `_ensure_indexes` (idempotent).
3. Implement `get_latest`, `get_version`, `list_versions` (read paths).
4. Implement `upsert` with `is_latest` flip logic + idempotent content check.
5. Implement `delete_version` with latest-promotion guard.
6. Implement `seed` (idempotent bulk import).
7. Implement `to_template_config` static method (YAML → `TemplateConfig`).
8. Implement `from_uri` convenience constructor.
9. Write unit tests (`tests/test_template_store.py`) with a mocked pymongo collection.

## 8. Backward-Compat Strategy
This story is purely additive — no existing file is modified. `TemplateStore` is only used when explicitly constructed and passed. Default behavior of all generators is unchanged.

## 9. Test Approach
**File**: `training_data/generate_synthetic_data/tests/test_template_store.py` (or `tests/` per existing convention).

**Mocking**: Use `unittest.mock.MagicMock` for the pymongo collection, or `mongomock` if available. Verify `find_one`, `insert_one`, `update_one`, `create_index` calls.

**Test cases**:
- `test_upsert_new` — first upsert creates version 1, is_latest=True.
- `test_upsert_bump_version` — second upsert creates version 2, flips version 1 to is_latest=False.
- `test_upsert_idempotent_content` — upsert with identical yaml_content is a no-op.
- `test_get_latest` — returns the is_latest=True doc.
- `test_get_version` — returns the specified version.
- `test_list_versions` — returns all versions sorted descending.
- `test_seed_idempotent` — seed twice, second run skips all.
- `test_delete_version_promotes_latest` — deleting latest promotes next.
- `test_delete_only_version_raises` — refuses to delete the only version.
- `test_to_template_config` — parses yaml_content into TemplateConfig.
- `test_ensure_indexes_idempotent` — calling twice doesn't error.

## 10. Risks & Open Questions
- **Transactions**: `upsert` uses insert-then-update (not a transaction) for simplicity. The unique index is the safety net. If a race causes a duplicate-key error on insert, the caller should retry. A true transaction version could be added later. **Open**: does the deployment support MongoDB transactions (replica set required)?
- **`yaml_content` for `build_*_prompt` functions**: These embed full prompt scaffolds with f-string placeholders. Storing them as YAML with `instruction` field may not capture the full scaffold. **Decision**: for `build_*_prompt`-derived docs, store the full prompt template under a `prompt_template` key in yaml_content, and the integration story (042) reads `prompt_template` if present. The seed story (041) decides the exact extraction.
- **`TemplateConfig` frozen dataclass**: Adding `version` field (Story 045) to a frozen dataclass is fine with a default value. Not this story's concern.