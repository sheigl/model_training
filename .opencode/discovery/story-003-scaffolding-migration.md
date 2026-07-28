# Story: Scaffolding Block Migration to YAML

## User Story
As a prompt engineer, I want the shared scaffolding blocks (SYSTEM_MESSAGE, MTG_NOTATION_LEGEND, REQUIREMENTS_BASE, OUTPUT_FORMAT, CARD_COMPARISON_INSTRUCTIONS) stored in YAML files alongside generation templates, so that all template content lives in one place and can be edited without touching Python code.

## Context
Currently 5 scaffolding blocks live as Python constants in `constants.py`:
- `SYSTEM_MESSAGE` — system prompt prefix
- `MTG_NOTATION_LEGEND` — MTG symbol reference (contains `{T}`, `{C}`, etc.)
- `OUTPUT_FORMAT` — JSON output format spec
- `REQUIREMENTS_BASE` — list of 8 requirements
- `CARD_COMPARISON_INSTRUCTIONS` — card comparison analysis rules

These are loaded into `_SCAFFOLDING_CACHE` via `init_scaffolding(store)` from the MongoDB store, with fallback to the `constants.py` imports. Every `build_*_prompt()` function calls `_get_scaffold(key, constants.XXX)`.

The migration moves these blocks into `templates/shared.yaml` while keeping the Python constants as in-memory fallback (no code change needed in prompt builders — they already have the fallback chain).

## Acceptance Criteria
- [ ] `templates/shared.yaml` contains all 5 generation scaffolding blocks under a `scaffolding:` key with sub-keys matching current cache keys (`system_message`, `notation_legend`, `requirements_base`, `output_format`, `card_comparison_instructions`)
- [ ] `REQUIREMENTS_BASE` is stored as a YAML list (not a string) to preserve its structure
- [ ] `init_scaffolding()` in `common.py` reads from the YAML loader instead of MongoDB when a loader is provided
- [ ] When no loader is provided, `init_scaffolding()` remains a no-op and all prompt builders fall back to `constants.py` imports (byte-identical behavior)
- [ ] The `_SCAFFOLDING_KEYS` mapping in `common.py` is updated to reference the YAML loader path instead of MongoDB keys
- [ ] All existing prompt builder functions (`build_commander_prompt`, `build_card_comparision_prompt`, etc.) continue to work without modification — they already use `_get_scaffold(key, fallback)`
- [ ] Unit tests verify: cache populated from YAML, cache empty when no loader, fallback to constants when cache miss

## Technical Plan
**Plan file**: `plans/story-003-scaffolding-migration-plan.md`

The technical design, architecture decisions, and task breakdown for this story
are in the companion plan file linked above.

## Dependencies
- Story 001 (YAML loader module must exist)
- Story 002 (template loading path established)

## Priority: Medium

## Notes
- `MTG_NOTATION_LEGEND` contains braces like `{T}`, `{C}` — these are NOT Python format placeholders; they're literal text. The YAML loader must not interpret them. Using `yaml.safe_load()` is safe since YAML braces in scalar strings are literal.
- The scaffolding cache (`_SCAFFOLDING_CACHE`) can stay as-is — it's a process-wide dict that both the MongoDB path and YAML path populate identically.
