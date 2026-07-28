# Technical Plan: Story 045 — Metrics + Trace Template-Version Recording

## 1. Architecture & Design Decisions

### `TemplateConfig.version` field
**Decision**: Add `version: int | None = None` as the **last** field (with a default) to both `TemplateConfig` classes. For the legacy frozen dataclass, a field with a default is allowed (it goes after all non-default fields). For TrainForge's plain class, add it to `__init__` with `=None` default.

`TemplateStore.to_template_config()` populates `version` from `doc["version"]`. Hardcoded fallback templates (class-level `TEMPLATES`) have `version=None` (the default).

### `template_versions` dict shape
**Decision**: `template_versions: dict[str, int | None]` keyed by `template_id` (not by `(template_id, template_type)`). A run uses one generation template version per `template_id`. Validator versions are tracked separately in `validator_template_versions: dict[str, int | None]` (keyed by `template_id` or `"shared"`).

### Indexes on `generation_traces`
Add:
- `(category, template_version)` — for "show me all combo_query traces at version 2".
- `(run_id, template_version)` — for "show me all traces in run X at version Y".

## 2. `TemplateConfig.version` Field

### Legacy `common.py`
```python
@dataclass(frozen=True)
class TemplateConfig:
    template_id: str
    task_instruction: str
    weight: float = 1.0
    validation_rules: list[str] | None = None
    min_answer_length: int = 80
    max_answer_length: int = 2000
    version: int | None = None  # NEW — last field with default
```
No `__post_init__` change needed — `version` has a default.

### TrainForge `domain.py`
```python
class TemplateConfig:
    def __init__(self, template_id, task_instruction, weight=1.0,
                 validation_rules=None, min_answer_length=80,
                 max_answer_length=2000, version=None):  # NEW
        ...
        self.version = version

    @classmethod
    def from_dict(cls, template_id, data):
        return cls(
            template_id=template_id,
            task_instruction=data.get("instruction", ""),
            weight=float(data.get("weight", 1.0)),
            validation_rules=data.get("validation_rules"),
            min_answer_length=int(data.get("min_answer_length", 80)),
            max_answer_length=int(data.get("max_answer_length", 2000)),
            version=data.get("version"),  # NEW — from YAML if present
        )
```

### `TemplateStore.to_template_config()` (legacy)
```python
@staticmethod
def to_template_config(doc: dict) -> TemplateConfig:
    data = yaml.safe_load(doc["yaml_content"]) or {}
    return TemplateConfig(
        template_id=doc["template_id"],
        task_instruction=data.get("instruction", ""),
        weight=float(data.get("weight", 1.0)),
        validation_rules=data.get("validation_rules") or [],
        min_answer_length=int(data.get("min_answer_length", 80)),
        max_answer_length=int(data.get("max_answer_length", 2000)),
        version=doc["version"],  # NEW
    )
```

### TrainForge `TemplateStoreClient.to_template_config()`
Same addition: `version=doc["version"]`.

## 3. `GenerationTrace` Changes

### Legacy `models.py`
```python
@dataclass
class GenerationTrace:
    item_id: str
    run_id: str
    category: str = ""
    source_template: str | None = None
    generator_name: str = ""
    generation_model: str = ""
    validation_model: str = ""
    created_at: str = ""
    generation_prompt: str = ""
    generation_response: str = ""
    generation_parsed_ok: bool = True
    generation_latency_ms: int = 0
    validation_rounds: list = field(default_factory=list)
    final_outcome: str = "pending"
    total_rounds: int = 0
    final_score: float | None = None
    # NEW:
    template_version: int | None = None
    validator_template_version: int | None = None
```

### TrainForge `models.py`
```python
class GenerationTrace(BaseModel):
    ...
    final_score: float | None = None
    # NEW:
    template_version: int | None = None
    validator_template_version: int | None = None
```

### Population in `base_generator._process_item` (legacy)
```python
trace = GenerationTrace(
    item_id=str(uuid.uuid4()),
    run_id=self.metrics.run_id if self.metrics else "",
    category=self.get_source_category(),
    source_template=template.template_id,
    generator_name=self._generator_name,
    generation_model=self.generation_model.name,
    validation_model=self.validation_model.name,
    created_at=datetime.utcnow().isoformat() + "Z",
    # NEW:
    template_version=template.version,
    validator_template_version=self._resolved_validator_version,  # set during validator resolution
)
```

`self._resolved_validator_version` is set in `validate_answer()` when the hybrid validator lookup resolves a version (or None for inline fallback).

### Population in `generator.py generate()` (TrainForge)
```python
trace = GenerationTrace(
    run_id=self.run_id,
    category=category,
    domain=self.domain.name,
    source_template=template.template_id,
    generator_name=self.__class__.__name__,
    generation_model=self.generation_model.name,
    validation_model=self.validation_model.name,
    # NEW:
    template_version=template.version,
    validator_template_version=...,  # from validator resolution
)
```

## 4. `ValidationMetrics` Changes

### Legacy `models.py`
```python
class ValidationMetrics:
    def __init__(self, metrics_collection=None, run_id=None, ...):
        ...
        self.template_versions: dict[str, int | None] = {}        # NEW
        self.validator_template_versions: dict[str, int | None] = {}  # NEW

    def record_template_version(self, template_id: str, version: int | None,
                                 is_validator: bool = False) -> None:
        """Record which template version was used for a template_id."""
        if is_validator:
            self.validator_template_versions[template_id] = version
        else:
            self.template_versions[template_id] = version

    def summary(self) -> dict:
        ...
        return {
            ...existing fields...,
            "template_versions": self.template_versions,             # NEW
            "validator_template_versions": self.validator_template_versions,  # NEW
            "by_category": _build_substats(self.category_stats),
            "by_template": _build_substats(self.template_stats),
        }
```

### TrainForge `models.py`
```python
class ValidationMetrics(BaseModel):
    ...
    template_stats: dict[str, dict] = Field(default_factory=dict)
    # NEW:
    template_versions: dict[str, int | None] = Field(default_factory=dict)
    validator_template_versions: dict[str, int | None] = Field(default_factory=dict)

    def record_template_version(self, template_id: str, version: int | None,
                                 is_validator: bool = False) -> None:
        if is_validator:
            self.validator_template_versions[template_id] = version
        else:
            self.template_versions[template_id] = version

    def summary(self) -> dict[str, Any]:
        ...
        return {
            ...existing fields...,
            "template_versions": self.template_versions,
            "validator_template_versions": self.validator_template_versions,
            "by_category": _substats(self.category_stats),
            "by_template": _substats(self.template_stats),
        }
```

### When to call `record_template_version`
In `BaseGenerator._process_item` (legacy) and `BaseGenerator.generate()` (TrainForge), after selecting a template:
```python
if self.metrics:
    self.metrics.record_template_version(template.template_id, template.version)
```
And after resolving the validator:
```python
if self.metrics:
    self.metrics.record_template_version("validator", self._resolved_validator_version, is_validator=True)
```

## 5. MongoDB Persistence Shape

### `synthetic_metrics.generator_runs` (updated)
```json
{
  "_id": "uuid",
  "run_id": "uuid",
  "generator_name": "GenerateComboQueries",
  "updated_at": "ISO",
  "created_at": "ISO",
  "metrics": {
    "generation_model": "qwen2.5:14b",
    "validation_model": "qwen2.5:14b",
    "total_candidates": 100,
    ...
    "template_versions": {"how_does_it_work": 2, "what_do_i_need": 1},
    "validator_template_versions": {"validator": 1},
    "by_category": {...},
    "by_template": {...}
  }
}
```

### `synthetic_metrics.generation_traces` (updated)
```json
{
  "_id": "uuid",
  "run_id": "uuid",
  "item_id": "uuid",
  "category": "combo_query",
  "source_template": "how_does_it_work",
  "template_version": 2,                      // NEW
  "validator_template_version": 1,            // NEW
  "generator_name": "GenerateComboQueries",
  ...
  "final_outcome": "accepted_first_attempt"
}
```

### New indexes on `generation_traces`
```python
generation_traces.create_index(
    [("category", 1), ("template_version", 1)], name="idx_category_version")
generation_traces.create_index(
    [("run_id", 1), ("template_version", 1)], name="idx_run_version")
```

## 6. Validator Version Tracking

In `BaseGenerator.validate_answer()` (legacy) and `validator.py` (TrainForge), the hybrid validator lookup (from Stories 042/043) resolves a version. Store it:
```python
# Legacy BaseGenerator
def validate_answer(self, qa, template, data_batch, source_data, trace=None, ...):
    # Resolve validator version (hybrid lookup)
    self._resolved_validator_version = self._resolve_validator_version(template)
    ...

def _resolve_validator_version(self, template) -> int | None:
    if self._template_store is None:
        return None
    category = self.get_source_category()
    # 1. Generator-specific validator
    doc = self._template_store.get_latest(category, "validator", "validator")
    if doc:
        return doc["version"]
    # 2. Shared validator
    doc = self._template_store.get_latest("__shared__", "qa_validation", "validator")
    if doc:
        return doc["version"]
    return None
```

## 7. Files to Modify

| File | Change |
|------|--------|
| `training_data/generate_synthetic_data/common.py` | `TemplateConfig` gains `version` field |
| `training_data/generate_synthetic_data/models.py` | `GenerationTrace` gains 2 fields; `ValidationMetrics` gains 2 dicts + `record_template_version` + `summary()` update |
| `training_data/generate_synthetic_data/base_generator.py` | `_process_item` populates trace version; `validate_answer` resolves validator version; `record_template_version` called |
| `training_data/generate_synthetic_data/template_store.py` | `to_template_config` populates `version` |
| `training_data/generate_synthetic_data/main.py` | Add new indexes on `generation_traces` |
| `trainforge/src/trainforge/domain.py` | `TemplateConfig` gains `version` field |
| `trainforge/src/trainforge/models.py` | `GenerationTrace` + `ValidationMetrics` gain fields + methods |
| `trainforge/src/trainforge/generator.py` | `generate()` populates trace version + calls `record_template_version` |
| `trainforge/src/trainforge/template_store.py` | `to_template_config` populates `version` |

## 8. Task Breakdown
1. Add `version` field to legacy `common.TemplateConfig` + TrainForge `domain.TemplateConfig`.
2. Update `TemplateStore.to_template_config` + `TemplateStoreClient.to_template_config` to populate `version`.
3. Add `template_version` + `validator_template_version` to legacy `GenerationTrace` dataclass.
4. Add same fields to TrainForge `GenerationTrace` Pydantic model.
5. Add `template_versions` + `validator_template_versions` dicts + `record_template_version()` to legacy `ValidationMetrics`.
6. Add same to TrainForge `ValidationMetrics`.
7. Update `summary()` in both to include the new dicts.
8. Update legacy `base_generator._process_item`: populate `trace.template_version` + `trace.validator_template_version`.
9. Add `_resolve_validator_version()` to legacy `BaseGenerator`; call `metrics.record_template_version`.
10. Update TrainForge `generator.generate()`: populate trace version + call `metrics.record_template_version`.
11. Add new indexes on `generation_traces` in `main.py`.
12. Write unit tests.

## 9. Backward-Compat Strategy
- `TemplateConfig.version` defaults to `None` → existing hardcoded templates have `version=None` → no behavior change.
- `GenerationTrace` new fields default to `None` → existing trace construction (without the fields) still works.
- `ValidationMetrics` new dicts default to `{}` → existing `summary()` callers get extra keys but no existing keys removed.
- Existing MongoDB docs are untouched (additive). Queries filtering on `template_version` must handle `null` (use `{"$exists": true}` or `{"$ne": null}`).
- All existing unit tests pass: they construct `TemplateConfig`/`GenerationTrace`/`ValidationMetrics` without `version` → defaults apply → no assertion breaks.

## 10. Test Approach
**Files**: `training_data/generate_synthetic_data/tests/test_metrics_trace_version.py` + `trainforge/tests/core/test_metrics_trace_version.py`

**Test cases**:
- `test_template_config_has_version_field` — construct with `version=2`, verify.
- `test_template_config_version_defaults_none` — construct without version, verify `None`.
- `test_store_to_template_config_populates_version` — mock doc with `version=3`, verify `TemplateConfig.version == 3`.
- `test_trace_carries_version_from_store` — template from store has version, verify `trace.template_version` set.
- `test_trace_version_null_for_hardcoded` — class-level template (version=None), verify `trace.template_version is None`.
- `test_trace_validator_version` — validator resolved from store, verify `trace.validator_template_version`.
- `test_metrics_record_template_version` — call `record_template_version`, verify dict.
- `test_metrics_summary_includes_versions` — `summary()` has `template_versions` + `validator_template_versions`.
- `test_metrics_persisted_shape` — mock `save_to_mongo`, verify doc has new fields.
- `test_trace_persisted_shape` — mock trace save, verify doc has `template_version` + `validator_template_version`.
- `test_existing_tests_pass` — full suite, 0 regressions.

## 11. Risks & Open Questions
- **Frozen dataclass field ordering**: `version` must come after all fields without defaults. Current `TemplateConfig` has `template_id` (no default) and `task_instruction` (no default) first, then `weight`, `validation_rules`, `min_answer_length`, `max_answer_length` (all with defaults). Adding `version` at the end with a default is safe.
- **Pydantic model migration**: Adding fields with defaults to a Pydantic `BaseModel` is backward-compatible. No migration needed.
- **`template_versions` keyed by `template_id`**: A run may use multiple template_ids per generator (e.g. combo_query has 4). The dict captures all. If the same `template_id` is used at different versions in one run (unlikely — version override is per-generator), the last one wins. **Open**: should it be `dict[str, list[int]]`? Recommendation: keep `dict[str, int]` — a generator uses one version per template_id per run.
- **Query patterns**: Analysts will query "traces where combo_query used version 2". The `(category, template_version)` index supports this. `null` versions (hardcoded fallback) are excluded by `{"template_version": {"$ne": null}}`.