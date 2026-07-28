# Technical Plan: Template Loading from YAML Replacing MongoDB Path

## Overview
Replace the MongoDB-based `_load_templates_from_store()` in `BaseGenerator` with a YAML-based `_load_templates_from_source()` that reads from a `YamlTemplateLoader`. The class-level `TEMPLATES` constant remains as the ultimate fallback, preserving byte-identical behavior when no loader is provided.

## Architecture Decisions

### Decision 1: Add `yaml_loader` parameter alongside existing `template_store`
**Choice:** `BaseGenerator.__init__` gains an optional `yaml_loader: YamlTemplateLoader | None = None` parameter. The old `template_store` parameter is deprecated but kept for one release cycle.
**Rationale:** Allows gradual migration. External code that passes `template_store=` continues to work. New code uses `yaml_loader=`. After a transition period, `template_store` can be removed entirely.

### Decision 2: Rename `_load_templates_from_store()` → `_load_templates_from_source()`
**Choice:** Keep the old method name as an alias that delegates to the new one for backward compat during transition.
**Rationale:** Some test code may reference the old name. The delegate approach avoids breakage.

### Decision 3: Reuse `TemplateStore.to_template_config()` via extraction
**Choice:** Extract the dict-to-`TemplateConfig` conversion into a standalone function `_dict_to_template_config(doc: dict) -> TemplateConfig` that both `TemplateStore.to_template_config()` and `YamlTemplateLoader` call.
**Rationale:** DRY — avoids duplicating the field-mapping logic. The YAML loader produces dicts with the same shape as MongoDB docs (minus MongoDB-specific fields like `_id`, `version`, `is_latest`).

### Decision 4: Set `version="1"` on YAML-loaded templates
**Choice:** When building `TemplateConfig` from a YAML entry, set `version="1"` (string).
**Rationale:** `GenerationTrace.template_version` expects a value. Since YAML has no versioning, `"1"` is the canonical constant. Trace queries filtering by version will match all YAML-loaded templates together.

## Files to Create

| File | Changes |
|------|---------|
| (none) | No new files — this story modifies existing ones |

## Files to Modify

### `base_generator.py`

**Changes to `__init__` (lines 71-130):**
- Add `yaml_loader: YamlTemplateLoader | None = None` parameter after `validator_template_version_override`
- Store as `self._yaml_loader = yaml_loader`
- Keep `self._template_store = template_store` for backward compat
- Wire loader into QueryModel: `self._query_model.yaml_loader = yaml_loader` (new attribute on QueryModel)

**Changes to `_load_templates_from_store()` (lines 246-281):**
- Rename method to `_load_templates_from_source()`
- New logic: if `self._yaml_loader` is not None, use it; else if `self._template_store` is not None, use it (deprecated path); else return None
- The per-template lookup loop stays the same shape, just swaps the source

**Changes to `_resolve_validator_version()` (lines 291-314):**
- Simplify: since YAML has no versioning, return `None` when yaml_loader is used (caller treats None as "no override")
- Keep MongoDB path for backward compat

### `query_model.py`

**Changes to `__init__` (lines 22-29):**
- Add `self.yaml_loader = None` attribute alongside `self.template_store = None`

**Changes to `_resolve_validator_template()` (lines 391-425):**
- Add YAML loader path: if `self.yaml_loader` is not None, call it instead of `self.template_store`
- The dict shape from YAML loader matches MongoDB doc shape for the fields we use (`yaml_content` → just return the instruction string directly since YAML loader can return the parsed instruction)

**Simplification option:** Have `YamlTemplateLoader.get_latest()` return a dict with key `instruction` (already parsed) instead of `yaml_content` (raw string). This avoids double-parsing. Update `_resolve_validator_template()` to check for `instruction` key first, then fall back to `yaml_content` parsing.

### `common.py`

**Changes:** No changes needed — `TemplateConfig` dataclass is unchanged. The `_load_templates_from_source()` method will produce `TemplateConfig` objects with the same shape.

## Task Breakdown

1. **Extract `_dict_to_template_config()` function in `common.py`**
   - Move logic from `TemplateStore.to_template_config()` into a standalone function
   - Have `TemplateStore.to_template_config()` delegate to it (backward compat)
   - Add tests for the extracted function

2. **Create `YamlTemplateLoader` in `yaml_template_loader.py`** (from Story 001)
   - Ensure it returns dicts compatible with `_dict_to_template_config()`

3. **Update `BaseGenerator.__init__`** to accept `yaml_loader` parameter
   - Store it alongside `_template_store`
   - Wire into QueryModel

4. **Rename and update `_load_templates_from_store()` → `_load_templates_from_source()`**
   - Check yaml_loader first, then template_store (deprecated), then return None
   - Per-template fallback loop unchanged in shape

5. **Simplify `_resolve_validator_version()`**
   - Return `None` when using yaml_loader (no versioning)
   - Keep MongoDB path for backward compat

6. **Update `QueryModel.__init__`** to accept `yaml_loader`
7. **Update `QueryModel._resolve_validator_template()`** to check yaml_loader first
8. **Update all generator instantiations in `main.py`** (deferred to Story 005)
9. **Run tests:** `pytest training_data/generate_synthetic_data/test_base_generator.py -v` and `test_template_loading.py -v`

## Test Strategy

### New tests in `test_yaml_template_loader.py` (from Story 001):
- Loader loads category files correctly
- Loader returns None for missing files

### Updated tests in `test_template_loading.py`:
- Replace `MagicMock(spec=TemplateStore)` with `YamlTemplateLoader` mock or real instance
- Keep all fallback-to-class-constants tests (they test the same invariant)
- Add tests for yaml_loader path: store-present-with-yaml, store-absent-with-yaml, yaml-missing-falls-back-to-class

### Updated tests in `test_base_generator.py`:
- Check if any test passes `template_store=` — update to use `yaml_loader=` or verify both work

### Verification:
```bash
pytest training_data/generate_synthetic_data/test_base_generator.py training_data/generate_synthetic_data/test_template_loading.py -v
```

## Backward Compatibility

| Scenario | Behavior |
|----------|----------|
| `template_store=None, yaml_loader=None` | Uses class-level `TEMPLATES` — **byte-identical to current** |
| `template_store=store, yaml_loader=None` | Uses MongoDB store (deprecated path) — **unchanged** |
| `template_store=None, yaml_loader=loader` | Uses YAML loader — **new path** |
| `template_store=store, yaml_loader=loader` | YAML loader takes precedence — **explicit override** |

The class-level `TEMPLATES` fallback is preserved in all cases.

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Generator subclasses override `__init__` and don't pass through `yaml_loader` | All 27 generators use `**kwargs` to forward to `super().__init__()` — verified by reading each generator file |
| `_resolve_validator_version()` return type changes from `int | None` to include string `"1"` | Keep returning `None` for YAML path; the trace code already handles `None` (it only records when value is not None) |
| QueryModel receives both `template_store` and `yaml_loader` | yaml_loader takes precedence in `_resolve_validator_template()` — explicit priority order documented in docstring |
