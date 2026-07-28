# Technical Plan: YAML Template File Structure, Directory Layout, and Loader Module

## Overview
Create a `templates/` directory under `training_data/generate_synthetic_data/` with one YAML file per generator category plus a `shared.yaml` for scaffolding and validator prompts. Build a `YamlTemplateLoader` class that mirrors the read surface of `TemplateStore` so downstream code can swap it in with minimal changes.

## Architecture Decisions

### Decision 1: One YAML file per generator category
**Choice:** `templates/combo_query.yaml`, `templates/card_search.yaml`, etc.
**Rationale:** Matches the existing `get_source_category()` return value, making lookup trivial (`f"templates/{category}.yaml"`). Easier to diff and review per-category changes. A monolithic file would be 500+ lines and hard to navigate.

### Decision 2: Shared scaffolding + validators in `shared.yaml`
**Choice:** Single `templates/shared.yaml` with `scaffolding:` and `validators:` top-level keys.
**Rationale:** All generators share the same 5 scaffolding blocks and the shared QA validator. Keeping them together avoids scattering references. Generator-specific validators (e.g. card comparison) go in their own file.

### Decision 3: YAML schema mirrors MongoDB `yaml_content` body
**Choice:** Each generation template entry has keys `template_id`, `instruction`, `weight`, `validation_rules`, `min_answer_length`, `max_answer_length`. The existing `TemplateStore.to_template_config()` static method accepts this shape directly — no parsing changes needed.
**Rationale:** Zero-breakage migration. The YAML body is exactly what was previously stored in `doc["yaml_content"]`.

### Decision 4: No versioning in YAML
**Choice:** Single canonical version per template. The `version` field on `TemplateConfig` will be set to `"1"` (string) when loaded from YAML.
**Rationale:** YAML files are git-tracked; version history is in git commits, not in the data layer. Version override CLI flags become no-ops and are removed in Story 005.

## Files to Create

| File | Description |
|------|-------------|
| `training_data/generate_synthetic_data/templates/__init__.py` | Empty — makes it a package |
| `training_data/generate_synthetic_data/templates/shared.yaml` | Scaffolding blocks + shared validators |
| `training_data/generate_synthetic_data/templates/combo_query.yaml` | 4 generation templates for combo queries |
| `training_data/generate_synthetic_data/templates/card_search.yaml` | Generation templates for card search |
| `training_data/generate_synthetic_data/templates/commander_rules.yaml` | Generation templates for commander knowledge |
| `training_data/generate_synthetic_data/templates/multi_card_usage.yaml` | Generation templates for multi-card usage |
| `training_data/generate_synthetic_data/templates/comparison.yaml` | Generation templates for comparison questions |
| `training_data/generate_synthetic_data/templates/reverse_lookup.yaml` | Generation templates for reverse lookup |
| `training_data/generate_synthetic_data/templates/synergy.yaml` | Generation templates for synergy questions |
| `training_data/generate_synthetic_data/templates/budget_alternative.yaml` | Generation templates for budget alternatives |
| `training_data/generate_synthetic_data/templates/color_identity.yaml` | Generation templates for color identity |
| `training_data/generate_synthetic_data/templates/quick_guideline.yaml` | Generation templates for quick guidelines |
| `training_data/generate_synthetic_data/templates/terminology.yaml` | Generation templates for terminology |
| `training_data/generate_synthetic_data/templates/deckbuilding_theory.yaml` | Generation templates for deckbuilding theory |
| `training_data/generate_synthetic_data/templates/commander_building.yaml` | Generation templates for commander building |
| `training_data/generate_synthetic_data/templates/rules_scenario.yaml` | Generation templates for rules scenarios |
| `training_data/generate_synthetic_data/templates/archetype.yaml` | Generation templates for archetypes |
| `training_data/generate_synthetic_data/templates/game_theory.yaml` | Generation templates for game theory |
| `training_data/generate_synthetic_data/templates/meta_knowledge.yaml` | Generation templates for meta knowledge |
| `training_data/generate_synthetic_data/templates/rule_explanation.yaml` | Generation templates for rule explanations |
| `training_data/generate_synthetic_data/templates/rule_interaction.yaml` | Generation templates for rule interactions |
| `training_data/generate_synthetic_data/templates/glossary_with_examples.yaml` | Generation templates for glossary examples |
| `training_data/generate_synthetic_data/templates/rule_edge_case.yaml` | Generation templates for rule edge cases |
| `training_data/generate_synthetic_data/templates/rule_why.yaml` | Generation templates for rule why questions |
| `training_data/generate_synthetic_data/templates/article_qa.yaml` | Generation templates for article QA |
| `training_data/generate_synthetic_data/templates/guide_qa.yaml` | Generation templates for guide QA |
| `training_data/generate_synthetic_data/templates/staple_analysis.yaml` | Generation templates for staple analysis |
| `training_data/generate_synthetic_data/templates/color_staples.yaml` | Generation templates for color staples |
| `training_data/generate_synthetic_data/templates/salt_analysis.yaml` | Generation templates for salt questions |
| `training_data/generate_synthetic_data/templates/comparison_validator.yaml` | Card comparison validator prompt template |
| `training_data/generate_synthetic_data/yaml_template_loader.py` | New module: `YamlTemplateLoader` class |
| `training_data/generate_synthetic_data/test_yaml_template_loader.py` | Unit tests for the loader |

## Files to Modify

| File | Changes |
|------|---------|
| `training_data/generate_synthetic_data/template_store.py` | No changes needed — `to_template_config()` is reused as-is |
| `.gitignore` | Add `templates/*.yaml`? No — YAML files are committed. Maybe add `templates/__pycache__/` |

## YAML Schema Design

### Generation template entry (per-category file)
Each category YAML file contains a list of templates:
```yaml
# templates/combo_query.yaml
- template_id: how_does_it_work
  instruction: |
    Generate exactly 3 Q&A pairs explaining HOW this combo works.
    Focus on: the sequence of steps, what triggers what...
  weight: 1.0
  validation_rules:
    - "Answer must explain each card's role in the combo"
    - "All card names and effects must be accurate"
  min_answer_length: 80
  max_answer_length: 2000

- template_id: what_do_i_need
  instruction: |
    Generate exactly 3 Q&A pairs focused on the REQUIREMENTS...
  weight: 1.0
  validation_rules: []
  min_answer_length: 80
  max_answer_length: 2000
```

### Shared scaffolding + validators
```yaml
# templates/shared.yaml
scaffolding:
  system_message: |
    <system>
    You are an expert Magic: The Gathering rules advisor...
    </system>
  notation_legend: |
    <reference>
    MTG NOTATION:
    - {T}: Tap (rotate card 90°; only if untapped)
    ...
    </reference>
  output_format: |
    OUTPUT FORMAT — respond with this JSON structure...
  requirements_base:
    - "At least one question MUST come from the perspective..."
    - "Questions must be varied and natural-sounding."
    # ... 6 more items
  card_comparison_instructions: |
    CRITICAL ANALYSIS REQUIREMENTS:
    Before writing your answer, analyze step-by-step...

validators:
  qa_validation: |
    {SYSTEM_MESSAGE placeholder resolved}
    Category: {category}
    Source material the answer should be grounded in:
    {context}
    ... (full prompt with {question}, {answer}, {context}, {category} placeholders)
```

### Per-generator validator override
```yaml
# templates/comparison_validator.yaml
instruction: |
  {MTG_NOTATION_LEGEND placeholder resolved}
  You are a Magic: The Gathering expert reviewing a comparison answer...
  Card 1: {card1_name}
  ... (full prompt with {card1_name}, {card1_type}, etc. placeholders)
```

## Task Breakdown

1. **Create `templates/` directory and `__init__.py`**
2. **Create `yaml_template_loader.py`** — implement `YamlTemplateLoader` class:
   - `__init__(self, templates_dir: str = None)` — resolves path relative to package root
   - `get_latest(self, generator: str, template_id: str, template_type: str) -> dict | None`
   - `list_versions(self, generator, template_id, template_type) -> list` (returns `[]`)
   - Internal `_load_category_file(category)` — reads YAML, returns list of entries
   - Internal `_load_shared()` — reads `shared.yaml`, returns scaffolding/validator dicts
   - `SHARED_NAMESPACE = "__shared__"` constant (same as `TemplateStore`)
3. **Write `test_yaml_template_loader.py`** — tests for: load existing file, missing file returns None, malformed YAML raises error, schema aliases work (`task_instruction` → `instruction`)
4. **Extract generation templates from all 27 generators into YAML files** — write a small script or do manually using the extraction logic from `seed_templates.py::extract_legacy()`
5. **Extract shared scaffolding blocks into `shared.yaml`** — use values from `constants.py`
6. **Extract validator templates into YAML** — use output of `build_qa_validation_prompt_template()` and `build_card_validation_prompt_template()` from `query_model.py`
7. **Verify all 27 category YAML files exist and parse correctly**

## Test Strategy

New tests in `test_yaml_template_loader.py`:
- `test_load_category_file_returns_list_of_dicts` — load an existing file, verify structure
- `test_load_missing_category_returns_none` — non-existent file → None
- `test_load_shared_scaffolding` — verify all 5 scaffolding keys present
- `test_load_shared_validators` — verify qa_validation key present with placeholders
- `test_get_latest_generation_template` — load a generation template, verify fields
- `test_get_latest_missing_returns_none` — missing template_id → None
- `test_malformed_yaml_raises_descriptive_error` — syntax error in YAML → ValueError with message
- `test_task_instruction_alias` — entry with `task_instruction` key (not `instruction`) works
- `test_list_versions_returns_empty` — no versioning support

Reuse existing tests:
- `TemplateStore.to_template_config()` tests in `test_template_store.py` still apply since the method is unchanged

## Migration Path

1. Create YAML files and loader module (this story)
2. Update `BaseGenerator` to use YAML loader (Story 002)
3. Update scaffolding loading (Story 003)
4. Update validator loading (Story 004)
5. Clean up CLI (Story 005)
6. Repurpose seed script (Story 006)
7. Update tests (Story 007)

Each story is independently testable — after Story 001, the loader exists but isn't wired into production code yet.

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| YAML file path resolution breaks in different run contexts | Resolve relative to `Path(__file__).parent / "templates"` — absolute at import time |
| Large instruction strings in YAML are hard to edit | Use YAML block scalars (`|`) for multi-line content; each file is ~20-80 lines |
| MTG braces `{T}`, `{C}` in YAML values could be misinterpreted | YAML block scalars treat them as literal text; `yaml.safe_load()` does not interpret braces |
| Forgetting to add a new generator's YAML file | The loader returns `None` for missing files, which triggers the class-constant fallback — safe but silent. Add a startup validation check in Story 002. |
