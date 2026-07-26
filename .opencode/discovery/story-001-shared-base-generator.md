# Story: Shared Base Generator Class

## User Story
As a **developer maintaining the synthetic data generation pipeline**, I want a **shared abstract base generator class** that provides common generation loop, template selection, validation integration, and metrics tracking, so that **all generators can inherit consistent behavior and reduce code duplication**.

## Context
This story was originally scoped to BUILD the base generator. **It has been implemented in BOTH codebases:**

### Old CLI Implementation (`training_data/generate_synthetic_data/base_generator.py`) ✅ COMPLETE
- 418-line `BaseGenerator(ABC, Generic[T])` with template method pattern
- Used by all 27 old CLI generators
- Provides: `generate()`, `_process_item()`, `select_templates()`, `validate_answer()`, `_parse_generation_response()`

### TrainForge Implementation (`trainforge/src/trainforge/generator.py`) ✅ COMPLETE
- 480-line `BaseGenerator(ABC, Generic[T])` with generic DomainPlugin integration
- Factory function `create_generator()` for shared initialization
- Provides same template method pattern with domain-agnostic validation

No further work needed on this story — both implementations are complete.

## Acceptance Criteria (Verification)
- [x] Abstract base class `BaseGenerator` in `base_generator.py` — EXISTING
- [x] Common generation loop with configurable target count and batch processing — EXISTING
- [x] Template selection system supporting multiple templates per generator with weighted selection — EXISTING
- [x] Integrated validation pipeline using existing `validate_and_loop_with_suggested_fix` with configurable validation percentage — EXISTING
- [x] Metrics tracking via `ValidationMetrics` (candidates, validated, passed, failed, fix attempts, scores) — EXISTING
- [x] MongoDB document saving via injected `save_item` callback — EXISTING
- [x] Context building hook for subclasses to provide rich validation context — EXISTING
- [x] Source category and template tracking on all generated documents — EXISTING
- [x] Configurable regeneration attempts (default 3) with exponential backoff — EXISTING
- [x] Progress logging with Rich console (current count, target, percentage) — EXISTING
- [x] Error handling with graceful continuation (log error, continue to next item) — EXISTING
- [x] Dry-run mode support for testing without MongoDB writes — EXISTING

## Dependencies
- None (foundation story)

## Priority: High

## Notes
- Old CLI file: `training_data/generate_synthetic_data/base_generator.py`
- TrainForge file: `trainforge/src/trainforge/generator.py`
- Both implementations are complete and production-ready
- TrainForge version uses `DomainPlugin` instead of direct model dicts — the key architectural difference
- If generators are ported to TrainForge, they'll inherit from the TrainForge `BaseGenerator[T]`
