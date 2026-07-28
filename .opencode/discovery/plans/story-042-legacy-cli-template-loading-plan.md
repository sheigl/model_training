# Technical Plan: Story 042 — Legacy CLI Template Loading Integration

## 1. Architecture & Design Decisions

### `_SCAFFOLDING_CACHE` approach for `common.py`
**Decision**: Add a module-level `_SCAFFOLDING_CACHE: dict[str, str | list[str]]` in `common.py`, populated by a new `init_scaffolding(store: TemplateStore | None)` function called once at startup in `main.py`. Each `build_*_prompt()` function reads scaffolding via `_get_scaffold(key, fallback)` which checks the cache first, then falls back to the `constants.py` import. **No function signatures change.**

This avoids touching ~20 function signatures and keeps the diff small.

### `template_store` threading
- `BaseGenerator.__init__` gains `template_store: TemplateStore | None = None` and `template_version_override: int | None = None`.
- `QueryModel` gains `template_store: TemplateStore | None = None` set via a setter or constructor param. Since `BaseGenerator` constructs `QueryModel()` internally (`self._query_model = QueryModel()`), the base generator sets `self._query_model.template_store = self._template_store` after construction.

### Hybrid validator lookup order
1. Generator-specific validator doc: `(generator=<category>, template_id="validator", template_type="validator")`.
2. Shared validator doc: `(generator="__shared__", template_id="qa_validation", template_type="validator")`.
3. Inline fallback: current `__build_qa_validation_prompt` construction.

## 2. `BaseGenerator` Changes

### `__init__` signature additions
```python
def __init__(
    self,
    models: dict[ModelType, Model],
    validation_pct: float,
    target_count: int,
    save_item: Callable[[QuestionAnswerEnhanced], None],
    metrics: ValidationMetrics | None = None,
    generator_name: str | None = None,
    dry_run: bool = False,
    max_regeneration_attempts: int = 3,
    batch_size: int = 1,
    templates_per_item: int = 1,
    enable_extra_validation: bool = True,
    trace_callback: Callable[[GenerationTrace], None] | None = None,
    # NEW:
    template_store: TemplateStore | None = None,
    template_version_override: int | None = None,
    validator_template_version_override: int | None = None,
):
    ...
    self._template_store = template_store
    self._template_version_override = template_version_override
    self._validator_template_version_override = validator_template_version_override
    # Wire store into QueryModel
    self._query_model.template_store = template_store
```

### `select_templates()` rewrite with fallback chain
```python
def select_templates(self, k: int = 1) -> list[TemplateConfig]:
    store_templates = self._load_templates_from_store()
    templates = store_templates if store_templates else self.TEMPLATES
    if not templates:
        raise ValueError(f"{self.__class__.__name__} must define TEMPLATES")
    weights = [t.weight for t in templates]
    return random.choices(templates, weights=weights, k=k)

def _load_templates_from_store(self) -> list[TemplateConfig] | None:
    """Load templates from store with fallback. Returns None if store unavailable/empty."""
    if self._template_store is None:
        return None
    category = self.get_source_category()
    # Find all template_ids for this generator (from class TEMPLATES as the key set)
    result = []
    for class_template in self.TEMPLATES:
        tid = class_template.template_id
        if self._template_version_override is not None:
            doc = self._template_store.get_version(
                category, tid, "generation", self._template_version_override)
            if doc is None:
                logger.warning(
                    "Template version %s not found for %s/%s — falling back to latest",
                    self._template_version_override, category, tid)
                doc = self._template_store.get_latest(category, tid, "generation")
        else:
            doc = self._template_store.get_latest(category, tid, "generation")
        if doc:
            result.append(TemplateStore.to_template_config(doc))
        else:
            # Store has no doc for this template_id — use class constant
            result.append(class_template)
    return result if result else None
```

### `generate()` guard update
```python
def generate(self) -> None:
    # Use store templates if available, else class TEMPLATES
    templates = self._load_templates_from_store() or self.TEMPLATES
    if not templates:
        raise ValueError(f"{self.__class__.__name__} must define TEMPLATES")
    ...
```

## 3. `common.py` Changes

### Module-level cache + init function
```python
# common.py
import logging
logger = logging.getLogger(__name__)

_SCAFFOLDING_CACHE: dict[str, str | list[str]] = {}

def init_scaffolding(store: TemplateStore | None) -> None:
    """Populate the scaffolding cache from the template store. Called once at startup."""
    if store is None:
        return
    for key, tid in [
        ("SYSTEM_MESSAGE", "system_message"),
        ("MTG_NOTATION_LEGEND", "notation_legend"),
        ("OUTPUT_FORMAT", "output_format"),
        ("CARD_COMPARISON_INSTRUCTIONS", "card_comparison_instructions"),
    ]:
        doc = store.get_latest("__shared__", tid, "generation")
        if doc:
            data = yaml.safe_load(doc["yaml_content"]) or {}
            _SCAFFOLDING_CACHE[key] = data.get("content", "")
    # REQUIREMENTS_BASE is a list
    doc = store.get_latest("__shared__", "requirements_base", "generation")
    if doc:
        data = yaml.safe_load(doc["yaml_content"]) or {}
        _SCAFFOLDING_CACHE["REQUIREMENTS_BASE"] = data.get("content", [])

def _get_scaffold(key: str, fallback) -> str | list[str]:
    """Return cached scaffold or fallback constant."""
    return _SCAFFOLDING_CACHE.get(key, fallback)
```

### Representative `build_*_prompt` change
```python
def build_commander_prompt() -> str:
    MTG_NOTATION_LEGEND = _get_scaffold("MTG_NOTATION_LEGEND", constants.MTG_NOTATION_LEGEND)
    # ... rest unchanged, uses local MTG_NOTATION_LEGEND
```

Only the first line of each `build_*_prompt` changes (replace the `constants` import reference with `_get_scaffold(...)`). This is a mechanical edit across ~20 functions.

## 4. `query_model.py` Changes

### `QueryModel` gains `template_store` attribute
```python
class QueryModel:
    def __init__(self):
        self.anthropic_client = None
        self._last_elapsed_ms = 0
        self.template_store = None  # NEW

    def _resolve_validator_template(self, category: str) -> str | None:
        """Hybrid validator lookup. Returns prompt template text or None (use inline)."""
        if self.template_store is None:
            return None
        # 1. Generator-specific validator
        doc = self.template_store.get_latest(category, "validator", "validator")
        if doc:
            data = yaml.safe_load(doc["yaml_content"]) or {}
            return data.get("instruction")
        # 2. Shared validator
        doc = self.template_store.get_latest("__shared__", "qa_validation", "validator")
        if doc:
            data = yaml.safe_load(doc["yaml_content"]) or {}
            return data.get("instruction")
        return None
```

### `__build_qa_validation_prompt` rewrite
```python
def __build_qa_validation_prompt(self, question, answer, context="", category="", enable_extra_validation=True):
    stored = self._resolve_validator_template(category)
    if stored:
        # Use stored template, substituting placeholders
        return stored.format(question=question, answer=answer, context=context or "",
                              category=category, ...)
    # FALLBACK: current inline construction (unchanged)
    ...  # existing code
```

## 5. `main.py` Changes

```python
# After MongoDB connection
from .template_store import TemplateStore
from .common import init_scaffolding

template_store = TemplateStore.from_uri(args.mongo_uri, args.mongo_user, args.mongo_pass)
init_scaffolding(template_store)

# Each generator block:
if args.combo_queries > 0:
    gen = GenerateComboQueries(
        data_access=data_access,
        models=models,
        validation_pct=args.validation_pct,
        target_count=args.combo_queries,
        save_item=save_fn,
        metrics=metrics,
        dry_run=args.dry_run,
        template_store=template_store,                              # NEW
        template_version_override=args.combo_queries_template_version,  # NEW (Story 044)
    )
    gen.generate()
```

## 6. Fallback Chain Specification

| Condition | Behavior |
|-----------|----------|
| `template_store=None` | Use class-level `TEMPLATES` constant (current behavior) |
| Store present, no doc for `(category, tid, "generation")` | Use class-level `TemplateConfig` for that template_id |
| Store present, version override set, version exists | Use that version |
| Store present, version override set, version missing | Log warning, use latest, then class constant |
| Store present, latest exists | Use latest doc |
| Validator: generator-specific doc exists | Use it |
| Validator: no generator-specific, shared doc exists | Use shared |
| Validator: neither | Inline `__build_qa_validation_prompt` fallback |

## 7. Files to Modify

| File | Change |
|------|--------|
| `base_generator.py` | `__init__` gains 3 params; `select_templates` + `generate` use store; `_load_templates_from_store` helper |
| `common.py` | `_SCAFFOLDING_CACHE`, `init_scaffolding()`, `_get_scaffold()`; ~20 `build_*_prompt` functions use `_get_scaffold` |
| `query_model.py` | `QueryModel.template_store` attr; `_resolve_validator_template()`; `__build_qa_validation_prompt` + `__build_card_validation_prompt` use store |
| `main.py` | Construct `TemplateStore`, call `init_scaffolding()`, pass `template_store` to each generator |

## 8. Task Breakdown
1. Add `_SCAFFOLDING_CACHE`, `init_scaffolding()`, `_get_scaffold()` to `common.py`.
2. Update ~20 `build_*_prompt` functions to use `_get_scaffold` (mechanical).
3. Add `template_store` attribute to `QueryModel`; add `_resolve_validator_template()`.
4. Rewrite `__build_qa_validation_prompt` and `__build_card_validation_prompt` with store lookup + fallback.
5. Add `template_store`, `template_version_override`, `validator_template_version_override` params to `BaseGenerator.__init__`.
6. Add `_load_templates_from_store()` helper; update `select_templates()` and `generate()`.
7. Wire `self._query_model.template_store = template_store` in `BaseGenerator.__init__`.
8. Update `main.py`: construct `TemplateStore`, call `init_scaffolding()`, pass store to generators.
9. Run existing test suite — verify all pass with `template_store=None` (default).
10. Write new unit tests for store-present, store-absent, version-override, validator-override paths.

## 9. Backward-Compat Strategy
- All new params default to `None`/`None`/`None`.
- With `template_store=None`: `_load_templates_from_store()` returns `None` → `select_templates()` uses `self.TEMPLATES` (class constant) → byte-identical to current behavior.
- `_get_scaffold(key, fallback)` returns `fallback` when cache empty → `build_*_prompt` functions use `constants.*` → byte-identical.
- `_resolve_validator_template()` returns `None` when store None → `__build_qa_validation_prompt` uses inline construction → byte-identical.
- **All existing unit tests pass unchanged** because they construct generators without `template_store`.

## 10. Test Approach
**File**: `training_data/generate_synthetic_data/tests/test_template_loading.py`

**Test cases**:
- `test_select_templates_store_present` — mock store returns docs, verify `TemplateConfig` from store used.
- `test_select_templates_store_absent` — `template_store=None`, verify class `TEMPLATES` used.
- `test_select_templates_version_override` — override set, verify `get_version` called.
- `test_select_templates_version_missing_falls_back` — override set but version missing, verify latest used + warning logged.
- `test_validator_override` — generator-specific validator doc exists, verify used.
- `test_validator_shared_fallback` — no generator-specific, shared exists, verify shared used.
- `test_validator_inline_fallback` — store None, verify inline construction.
- `test_scaffolding_cache_populated` — `init_scaffolding` called, verify cache has values.
- `test_scaffolding_fallback` — cache empty, verify `constants.*` used.
- `test_existing_tests_pass` — run full existing suite, verify 0 regressions.

## 11. Risks & Open Questions
- **Frozen `TemplateConfig`**: `TemplateStore.to_template_config()` constructs new `TemplateConfig` instances — fine, frozen dataclass allows construction with all fields.
- **`QueryModel` constructed inside `BaseGenerator`**: `self._query_model = QueryModel()` — must set `self._query_model.template_store` after construction. Done in `__init__`.
- **Name-mangled private methods**: `__build_qa_validation_prompt` is `_QueryModel__build_qa_validation_prompt`. The rewrite stays inside the class so name mangling is preserved.
- **`build_*_prompt` functions are module-level**: They read `_SCAFFOLDING_CACHE` which is module-global. Thread safety: the cache is populated once at startup before any generation runs, so no race.
- **`init_scaffolding` must be called before any generation**: `main.py` calls it right after `TemplateStore` construction. If a test constructs a generator without calling `init_scaffolding`, the cache is empty → fallback to constants → correct behavior.