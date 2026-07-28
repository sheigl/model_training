# Technical Plan: Validator Template Migration to YAML

## Overview
Migrate validator prompts from MongoDB/inline construction to YAML files, while preserving the exact `str.replace()` placeholder substitution logic and fallback behavior.

## Architecture Decisions

### Decision 1: Two separate YAML files for validators
- **qa_validation** lives in `templates/shared.yaml` under a `validators:` section (shares file with scaffolding blocks)
- **card_comparison** lives in `templates/comparison_validator.yaml` (unique enough to warrant its own file)

Rationale: QA validator is generator-agnostic and used across all 27 generators, so it belongs with shared scaffolding. Card comparison has different placeholders and is only used by comparison-style generators.

### Decision 2: Reuse `TemplateStore.to_template_config()` verbatim
The static method already converts a dict to `TemplateConfig`. The YAML loader will parse YAML → dict → call this same method. No changes needed here.

### Decision 3: Keep public helper functions as reference
`build_qa_validation_prompt_template()` and `build_card_validation_prompt_template()` in `query_model.py` are kept but marked with a comment that they are reference implementations only. They are no longer called by the production path.

## Files to Modify

### New files
- `training_data/generate_synthetic_data/templates/shared.yaml` — scaffolding + qa_validation validator (created in Story 003)
- `training_data/generate_synthetic_data/templates/comparison_validator.yaml` — card comparison prompt

### Modified files
- `training_data/generate_synthetic_data/query_model.py` — `_resolve_validator_template()` method
- `training_data/generate_synthetic_data/common.py` — may need minor updates if validator template resolution is moved there

## Task Breakdown

### Task 1: Define YAML content for qa_validation (shared.yaml)
Extract the current inline prompt from `__build_qa_validation_prompt()` in `query_model.py`. The template should contain placeholders `{question}`, `{answer}`, `{context}`, `{category}`. Structure in shared.yaml:

```yaml
scaffolding:
  system_message: "..."
  mtg_notation_legend: "..."
  requirements_base: "..."
  output_format: "..."
validators:
  qa_validation: |
    You are a Magic: The Gathering rules expert...
    Question: {question}
    Answer: {answer}
    Context: {context}
    Category: {category}
```

### Task 2: Define YAML content for card_comparison validator
Extract from `__build_card_validation_prompt()` in `query_model.py`. Placeholders include `{card1_name}`, `{card1_type}`, `{card2_name}`, `{card2_type}`, etc. Create `templates/comparison_validator.yaml`:

```yaml
validators:
  card_comparison: |
    You are a Magic: The Gathering rules expert...
    Card 1: {card1_name} ({card1_type})
    Card 2: {card2_name} ({card2_type})
```

### Task 3: Update `_resolve_validator_template()` in query_model.py
Current signature:
```python
def _resolve_validator_template(self, template_id: str, store=None) -> Optional[TemplateConfig]:
```

New signature:
```python
def _resolve_validator_template(self, template_id: str, yaml_loader=None) -> Optional[TemplateConfig]:
```

Logic:
1. If `yaml_loader` is provided and has the template → return it via `to_template_config()`
2. Otherwise → fall back to inline prompt construction (byte-identical to current fallback)

### Task 4: Update validator builder calls in query_model.py
The two public methods that call `_resolve_validator_template()`:
- `build_qa_validation_prompt()` — pass `yaml_loader=self.yaml_loader`
- `build_card_validation_prompt()` — pass `yaml_loader=self.yaml_loader`

### Task 5: Preserve MTG brace safety
The existing code uses `str.replace()` instead of `.format()` to avoid breaking `{card name}` syntax. This logic must remain unchanged in the fallback path and in any YAML-loading substitution.

## Testing Strategy
- Unit test: YAML loader returns correct template for `qa_validation` key from shared.yaml
- Unit test: YAML loader returns correct template for `card_comparison` key from comparison_validator.yaml
- Unit test: `_resolve_validator_template()` with no loader falls back to inline construction (verify output matches current behavior)
- Unit test: MTG braces like `{card name}` are preserved in loaded templates (no `.format()` applied)
- Integration test: Full validation prompt builds correctly end-to-end with YAML template

## Risk Assessment
- **Low risk**: The change is localized to `query_model.py` and new YAML files. Fallback path preserves existing behavior.
- **Migration note**: Since the MongoDB collection is empty, no data migration is needed.
