# Story: Shared Base Generator Class

## User Story
As a **developer maintaining the synthetic data generation pipeline**, I want a **shared abstract base generator class** that provides common generation loop, template selection, validation integration, and metrics tracking, so that **all 23 generators can inherit consistent behavior and reduce code duplication by ~80%**.

## Context
Currently, 23 generator classes in `training_data/generate_synthetic_data/` each implement their own generation loop, validation calls, MongoDB saving, and metrics tracking. The two well-designed generators (combos, rules) have rich validation with HARD REJECT rules, while 21 others have minimal validation. A shared base class will enforce consistent patterns across all generators.

## Acceptance Criteria
- [ ] Abstract base class `BaseGenerator` in `training_data/generate_synthetic_data/base_generator.py`
- [ ] Common generation loop with configurable target count and batch processing
- [ ] Template selection system supporting multiple templates per generator with weighted selection
- [ ] Integrated validation pipeline using existing `validate_and_loop_with_suggested_fix` with configurable validation percentage
- [ ] Metrics tracking via `ValidationMetrics` (candidates, validated, passed, failed, fix attempts, scores)
- [ ] MongoDB document saving via injected `save_item` callback
- [ ] Context building hook for subclasses to provide rich validation context
- [ ] Source category and template tracking on all generated documents
- [ ] Configurable regeneration attempts (default 3) with exponential backoff
- [ ] Progress logging with Rich console (current count, target, percentage)
- [ ] Error handling with graceful continuation (log error, continue to next item)
- [ ] Dry-run mode support for testing without MongoDB writes

## MongoDB Collections/Queries Needed
- None directly (base class only)
- Subclasses will use collections via Unified Data Access Layer (Story 2)

## Template Definitions
Base class provides template registry pattern:
```python
class BaseGenerator:
    TEMPLATES: ClassVar[list[TemplateConfig]] = []  # Subclasses override
    
    def select_template(self) -> TemplateConfig:
        """Weighted random selection from TEMPLATES"""
```

Each `TemplateConfig`:
- `template_id`: str (unique identifier)
- `task_instruction`: str (the prompt instruction for LLM)
- `weight`: float (selection probability)
- `validation_rules`: list[str] (HARD REJECT rules specific to this template)

## Validation Criteria (HARD REJECT Rules)
Base class enforces these universal HARD REJECT rules:
- [ ] Answer is not a string (must be single string, not array)
- [ ] Answer contains markdown formatting (bold, italics, bullet points)
- [ ] Answer references rule numbers directly (must explain conversationally)
- [ ] Answer < 80 characters (insufficient detail)
- [ ] Question/answer missing or empty
- [ ] JSON parsing fails
- [ ] Validation score < 7/10 after 3 regeneration attempts

Subclasses add template-specific HARD REJECT rules via `TemplateConfig.validation_rules`.

## Dependencies
- None (foundation story)

## Priority: High
## Story Points: 8

## Notes
- This replaces the repetitive `__init__`, `generate_*_questions`, validation loop, and metrics code in all 23 generators
- Existing generators (combos, rules) should be refactored to inherit from this base
- The `QueryModel` and `validate_and_loop_with_suggested_fix` from `common.py` are used internally
- Subclasses only implement: `get_data_batches()`, `build_prompt(template, data)`, `get_source_category()`