# Technical Plan: Scaffolding Block Migration to YAML

## Overview
Move the 5 shared scaffolding blocks from `constants.py` Python constants into `templates/shared.yaml`, while keeping the Python constants as in-memory fallback. The existing `_get_scaffold(key, fallback)` pattern in `common.py` already supports this — only `init_scaffolding()` needs to read from YAML instead of MongoDB.

## Architecture Decisions

### Decision 1: Keep Python constants as fallback
**Choice:** Do NOT remove the constants from `constants.py`. They remain as the fallback value in every `_get_scaffold(key, constants.XXX)` call.
**Rationale:** Zero risk of breakage. If YAML loading fails or the loader is None, behavior is identical. Constants also serve as documentation of what each block contains.

### Decision 2: `init_scaffolding()` gains a `yaml_loader` parameter
**Choice:** Change signature from `init_scaffolding(store: TemplateStore | None)` to `init_scaffolding(yaml_loader: YamlTemplateLoader | None = None, store: TemplateStore | None = None)`.
**Rationale:** Supports both YAML and MongoDB paths during transition. YAML path takes precedence.

### Decision 3: `_SCAFFOLDING_KEYS` stays unchanged
**Choice:** The tuple list `[( "SYSTEM_MESSAGE", "system_message", str), ...]` remains the same. Only the lookup target changes (YAML vs MongoDB).
**Rationale:** The cache key names and expected types are identical between YAML and MongoDB paths.

## Files to Create

| File | Changes |
|------|---------|
| `templates/shared.yaml` | Created in Story 001 — contains scaffolding blocks |

## Files to Modify

### `common.py`

**Changes to `init_scaffolding()` (lines 42-57):**
```python
# BEFORE:
def init_scaffolding(store: "TemplateStore | None") -> None:
    if store is None:
        return
    shared = store.SHARED_NAMESPACE
    for key, tid, _expected_type in _SCAFFOLDING_KEYS:
        doc = store.get_latest(shared, tid, "generation")
        if doc:
            data = yaml.safe_load(doc["yaml_content"]) or {}
            content = data.get("content", "")
            _SCAFFOLDING_CACHE[key] = content

# AFTER:
def init_scaffolding(
    yaml_loader: "YamlTemplateLoader | None" = None,
    store: "TemplateStore | None" = None,
) -> None:
    if yaml_loader is not None:
        _load_scaffolding_from_yaml(yaml_loader)
    elif store is not None:
        _load_scaffolding_from_store(store)
```

**New helper `_load_scaffolding_from_yaml()`:**
```python
def _load_scaffolding_from_yaml(loader: YamlTemplateLoader) -> None:
    """Populate scaffolding cache from YAML shared.yaml."""
    doc = loader.get_latest("__shared__", "scaffolding", "generation")
    if doc is None:
        return
    # The YAML loader returns the parsed dict for shared.yaml scaffolding entry
    scaffold_data = doc.get("scaffolding", {}) if isinstance(doc, dict) else {}
    for key, _tid, expected_type in _SCAFFOLDING_KEYS:
        content = scaffold_data.get(key.lower().replace("_", ""), None)
        if content is not None:
            if expected_type == list and isinstance(content, str):
                content = content.split("\n")
            _SCAFFOLDING_CACHE[key] = content
```

Wait — actually the YAML structure in `shared.yaml` uses keys like `system_message`, `notation_legend` which map directly to `_SCAFFOLDING_KEYS` entries. Let me reconsider the mapping.

**Revised approach:** The `_SCAFFOLDING_KEYS` tuples use cache key names (`SYSTEM_MESSAGE`) but the YAML uses snake_case (`system_message`). A simple lookup dict bridges them:
```python
_CACHE_KEY_TO_YAML_KEY = {
    "SYSTEM_MESSAGE": "system_message",
    "MTG_NOTATION_LEGEND": "notation_legend",
    "OUTPUT_FORMAT": "output_format",
    "CARD_COMPARISON_INSTRUCTIONS": "card_comparison_instructions",
    "REQUIREMENTS_BASE": "requirements_base",
}
```

**Changes to `init_scaffolding()` — final version:**
```python
def init_scaffolding(
    yaml_loader: "YamlTemplateLoader | None" = None,
    store: "TemplateStore | None" = None,
) -> None:
    """Populate the scaffolding cache. YAML path takes precedence."""
    if yaml_loader is not None:
        _populate_from_yaml(yaml_loader)
    elif store is not None:
        _populate_from_store(store)

def _populate_from_yaml(loader: YamlTemplateLoader) -> None:
    """Load scaffolding from templates/shared.yaml via YAML loader."""
    doc = loader.get_latest("__shared__", "scaffolding", "generation")
    if doc is None:
        return
    scaffold_data = doc if isinstance(doc, dict) else {}
    for cache_key, yaml_key in _CACHE_KEY_TO_YAML_KEY.items():
        content = scaffold_data.get(yaml_key)
        if content is not None:
            _SCAFFOLDING_CACHE[cache_key] = content

def _populate_from_store(store: "TemplateStore") -> None:
    """Legacy MongoDB path — unchanged from current behavior."""
    shared = store.SHARED_NAMESPACE
    for key, tid, _expected_type in _SCAFFOLDING_KEYS:
        doc = store.get_latest(shared, tid, "generation")
        if doc:
            data = yaml.safe_load(doc["yaml_content"]) or {}
            content = data.get("content", "")
            _SCAFFOLDING_CACHE[key] = content
```

**Add `_CACHE_KEY_TO_YAML_KEY` mapping near `_SCAFFOLDING_KEYS`:**
```python
_CACHE_KEY_TO_YAML_KEY: dict[str, str] = {
    "SYSTEM_MESSAGE": "system_message",
    "MTG_NOTATION_LEGEND": "notation_legend",
    "OUTPUT_FORMAT": "output_format",
    "CARD_COMPARISON_INSTRUCTIONS": "card_comparison_instructions",
    "REQUIREMENTS_BASE": "requirements_base",
}
```

## Task Breakdown

1. **Create `templates/shared.yaml`** with scaffolding section (from Story 001)
2. **Add `_CACHE_KEY_TO_YAML_KEY` mapping** in `common.py` near `_SCAFFOLDING_KEYS`
3. **Refactor `init_scaffolding()`** to accept `yaml_loader` and delegate to `_populate_from_yaml()` or `_populate_from_store()`
4. **Update `main.py`** call site (deferred to Story 005) — change `init_scaffolding(template_store)` to `init_scaffolding(yaml_loader=loader)`
5. **Add tests** in `test_template_loading.py`:
   - `test_init_scaffolding_from_yaml_populates_cache`
   - `test_init_scaffolding_yaml_takes_precedence_over_store`
   - `test_init_scaffolding_none_is_noop` (existing test, still passes)
6. **Verify existing prompt builder tests** still pass (`test_build_commander_prompt_uses_cache`, etc.)

## Test Strategy

Existing tests that must continue to pass:
- `test_scaffolding_init_none_is_noop` — no loader → no-op
- `test_scaffolding_fallback_to_constants` — empty cache → constants fallback
- `test_scaffolding_cache_hit` — cached value returned
- `test_build_commander_prompt_uses_cache` — prompt contains cached legend
- `test_build_commander_prompt_falls_back_to_constants` — no cache → constants
- `test_build_card_comparision_prompt_uses_cache` — both scaffolds present
- `test_reset_scaffolding_cache` — clears cache

New tests to add:
- `test_init_scaffolding_from_yaml_populates_cache` — mock yaml_loader returning shared.yaml data
- `test_init_scaffolding_yaml_precedence` — both loader and store provided, YAML wins
- `test_init_scaffolding_yaml_missing_key_uses_fallback` — YAML has partial data, missing keys use constants

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| YAML key names don't match cache key names | Use explicit `_CACHE_KEY_TO_YAML_KEY` mapping — no ambiguity |
| `REQUIREMENTS_BASE` is a list in constants but could be loaded as string from YAML | YAML block scalar with `- item` syntax produces a Python list; verified at test time |
| MTG braces `{T}` in `notation_legend` YAML value | YAML block scalars (`|`) preserve braces literally — no interpretation |
