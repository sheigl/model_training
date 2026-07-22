# Design: Shared Base Generator Class (Story 001)

## Overview
Create an abstract `BaseGenerator` class in `training_data/generate_synthetic_data/base_generator.py` that provides a shared generation loop, template selection, validation integration, metrics tracking, and MongoDB saving for all 23 synthetic data generators. This will eliminate ~80% code duplication across generators.

## User Story Reference
`.opencode/discovery/story-001-shared-base-generator.md`

---

## Architecture Decisions

### 1. Template Method Pattern for Generation Loop
**Decision**: Use Template Method pattern with abstract hooks for subclass customization.
**Why**: All 23 generators follow the same pattern: fetch data → select template → build prompt → generate → validate → save. The base class implements the invariant loop; subclasses implement variable parts.
**Trade-offs**: 
- ✅ Eliminates duplication, enforces consistency
- ✅ Easy to add cross-cutting concerns (metrics, logging, dry-run)
- ⚠️ Subclasses must implement 3 abstract methods (acceptable boilerplate)

### 2. Template Registry with Weighted Selection
**Decision**: Class-level `TEMPLATES: ClassVar[list[TemplateConfig]]` with `random.choices()` weighted selection.
**Why**: Generators like combos use 4 templates with equal weight; others may need weighted selection. Class variable allows subclass override without instantiation.
**Trade-offs**: 
- ✅ Declarative, easy to read/override
- ⚠️ Class variable shared across instances (acceptable - templates are static config)

### 3. Validation Integration via `validate_and_loop_with_suggested_fix`
**Decision**: Base class calls existing `validate_and_loop_with_suggested_fix` from `common.py` with subclass-provided context builder.
**Why**: Reuses existing sophisticated validation logic (regeneration loop, scoring, metrics). Subclass provides `build_context()` hook for domain-specific context.
**Trade-offs**: 
- ✅ Reuses battle-tested validation pipeline
- ⚠️ Couples base class to `common.py` (acceptable - already a shared module)

### 4. Injected `save_item` Callback for MongoDB Persistence
**Decision**: Base class accepts `save_item: Callable[[QuestionAnswerEnhanced], None]` in constructor.
**Why**: Decouples generation from persistence. Enables dry-run mode (pass no-op), testing (pass mock), and production (pass MongoDB saver).
**Trade-offs**: 
- ✅ Testable, flexible, follows dependency inversion
- ⚠️ Slight indirection (acceptable)

### 5. Rich Console Progress with Configurable Logging
**Decision**: Use `rich.console.Console` and `rich.progress.Progress` for progress bars; configurable log level.
**Why**: Existing generators use `rich.console.Console` and `rich.status.Status`. Consistent UX across all 23 generators.
**Trade-offs**: 
- ✅ Consistent UX, rich progress bars
- ⚠️ Adds `rich` dependency (already in requirements)

---

## Files to Create/Modify

### New Files
| File | Purpose | Key Responsibilities |
|------|---------|---------------------|
| `training_data/generate_synthetic_data/base_generator.py` | Abstract base generator class | Generation loop, template selection, validation integration, metrics, saving, dry-run, progress logging |

### Modified Files
| File | Changes | Reason |
|------|---------|--------|
| `training_data/generate_synthetic_data/common.py` | Export `TemplateConfig`, `ValidationMetrics` (already exported), `QuestionAnswerEnhanced` | Base generator needs these types |
| `training_data/generate_synthetic_data/models.py` | Ensure `ValidationMetrics` has all needed methods | Base generator uses metrics extensively |
| `training_data/generate_synthetic_data/generate_combo_queries.py` | Refactor to inherit from `BaseGenerator` | Proof-of-concept migration |
| `training_data/generate_synthetic_data/generate_article_qa.py` | Refactor to inherit from `BaseGenerator` | Second migration example |

---

## Task Breakdown (Ordered by Dependency)

### Task 1: Create `TemplateConfig` and `BaseGenerator` Class
- **Files**: `base_generator.py` (new), `common.py` (modify exports)
- **Description**: Define `TemplateConfig` dataclass and abstract `BaseGenerator` with all core functionality
- **Acceptance Criteria**: 
  - `TemplateConfig` has `template_id`, `task_instruction`, `weight`, `validation_rules`
  - `BaseGenerator` is abstract with 3 abstract methods: `get_data_batches()`, `build_prompt()`, `get_source_category()`
  - Concrete `generate()` method implements full loop with progress logging
  - `select_template()` uses weighted random selection
  - Dry-run mode works (no MongoDB writes)
  - Metrics tracking integrated with `ValidationMetrics`

### Task 2: Implement Template Selection & Validation Integration
- **Files**: `base_generator.py`
- **Description**: Complete template registry, weighted selection, validation pipeline integration
- **Acceptance Criteria**:
  - `TEMPLATES` class variable works with subclass override
  - `select_template()` uses `random.choices()` with weights
  - Validation uses `validate_and_loop_with_suggested_fix` with subclass `build_context()`
  - HARD REJECT rules enforced (answer not string, markdown, rule refs, <80 chars, empty, JSON parse fail, score <7 after 3 retries)

### Task 3: Implement Metrics Tracking & Progress Logging
- **Files**: `base_generator.py`
- **Description**: Integrate `ValidationMetrics` recording, Rich progress bars, rolling summaries
- **Acceptance Criteria**:
  - Metrics recorded per candidate, validation attempt, pass/fail, fix attempts
  - Rich progress bar shows current/target/percentage
  - Rolling summary printed every 10 candidates
  - Graceful error handling (log error, continue to next item)

### Task 4: Refactor `GenerateComboQueries` to Inherit from `BaseGenerator`
- **Files**: `generate_combo_queries.py`, `base_generator.py`
- **Description**: Migrate the most complex generator as proof-of-concept
- **Acceptance Criteria**:
  - Class inherits from `BaseGenerator`
  - Implements 3 abstract methods
  - Defines `TEMPLATES` with 4 combo templates
  - Produces identical output to original
  - All existing tests pass

### Task 5: Refactor `GenerateArticleQA` to Inherit from `BaseGenerator`
- **Files**: `generate_article_qa.py`
- **Description**: Migrate a simpler generator to validate pattern works for different data shapes
- **Acceptance Criteria**:
  - Class inherits from `BaseGenerator`
  - Implements 3 abstract methods
  - Defines `TEMPLATES` (single template or multiple)
  - Produces identical output to original

### Task 6: Update Remaining 21 Generators (Batch)
- **Files**: All 21 remaining generator files
- **Description**: Systematic migration using established pattern
- **Acceptance Criteria**: All generators inherit from `BaseGenerator`, zero raw generation loops remain

---

## Data Models / Interfaces

```python
# In common.py (add to existing file)
from dataclasses import dataclass
from typing import ClassVar, Callable, Any
from abc import ABC, abstractmethod
import random
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

@dataclass(frozen=True)
class TemplateConfig:
    """Configuration for a generation template."""
    template_id: str                    # Unique identifier (e.g., "how_does_it_work")
    task_instruction: str               # Prompt instruction for LLM
    weight: float = 1.0                 # Selection weight (higher = more likely)
    validation_rules: list[str] = None  # Template-specific HARD REJECT rules
    
    def __post_init__(self):
        if self.validation_rules is None:
            object.__setattr__(self, 'validation_rules', [])


# In base_generator.py (new file)
from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Callable, Any
from dataclasses import dataclass
import random
import time
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn

from common import TemplateConfig, validate_and_loop_with_suggested_fix, QuestionAnswer, QuestionAnswerEnhanced
from models import ValidationMetrics, ModelType, Model
from query_model import QueryModel

T = TypeVar('T')  # Data batch type

console = Console()

class BaseGenerator(ABC, Generic[T]):
    """
    Abstract base class for all synthetic data generators.
    
    Subclasses must implement:
    - get_data_batches(): Yield data batches for generation
    - build_prompt(template, data_batch): Build LLM prompt for a template + data
    - get_source_category(): Return category string for metrics/tracking
    
    Subclasses should define:
    - TEMPLATES: ClassVar[list[TemplateConfig]] - Available templates with weights
    """
    
    # Subclasses override with their templates
    TEMPLATES: ClassVar[list[TemplateConfig]] = []
    
    # Universal HARD REJECT rules (enforced by base class)
    UNIVERSAL_HARD_REJECT_RULES: ClassVar[list[str]] = [
        "Answer is not a single string (must not be array)",
        "Answer contains markdown formatting (bold, italics, bullet points)",
        "Answer references rule numbers directly (must explain conversationally)",
        "Answer is less than 80 characters (insufficient detail)",
        "Question or answer is missing or empty",
        "JSON parsing fails",
        "Validation score < 7/10 after 3 regeneration attempts",
    ]
    
    def __init__(
        self,
        models: dict[ModelType, Model],
        validation_pct: float,
        target_count: int,
        save_item: Callable[[QuestionAnswerEnhanced], None],
        metrics: ValidationMetrics | None = None,
        dry_run: bool = False,
        max_regeneration_attempts: int = 3,
        batch_size: int = 1,
        templates_per_item: int = 1,
        enable_extra_validation: bool = True,
    ):
        """
        Initialize the base generator.
        
        Args:
            models: Dict with ModelType.GENERATION and ModelType.VALIDATION keys
            validation_pct: Percentage of items to validate (0.0-1.0)
            target_count: Target number of items to generate
            save_item: Callback to save a validated QuestionAnswerEnhanced
            metrics: Optional ValidationMetrics instance for tracking
            dry_run: If True, don't call save_item (for testing)
            max_regeneration_attempts: Max retries after validation failure (default 3)
            batch_size: Items per generation batch (default 1)
            templates_per_item: Number of templates to apply per data item (default 1)
            enable_extra_validation: Enable detailed verification checklist
        """
        self.models = models
        self.validation_pct = validation_pct
        self.target_count = target_count
        self.save_item = save_item
        self.metrics = metrics
        self.dry_run = dry_run
        self.max_regeneration_attempts = max_regeneration_attempts
        self.batch_size = batch_size
        self.templates_per_item = templates_per_item
        self.enable_extra_validation = enable_extra_validation
        
        self.query_model = QueryModel()
        self.generated_count = 0
        self._start_time = time.time()
    
    @abstractmethod
    def get_data_batches(self) -> list[T]:
        """
        Fetch and return all data batches needed for generation.
        
        Returns:
            List of data items, each will have templates_per_item templates applied.
        """
        ...
    
    @abstractmethod
    def build_prompt(self, template: TemplateConfig, data_batch: T) -> str:
        """
        Build the LLM prompt for a specific template and data batch.
        
        Args:
            template: The selected TemplateConfig
            data_batch: One item from get_data_batches()
            
        Returns:
            Complete prompt string for the generation model
        """
        ...
    
    @abstractmethod
    def get_source_category(self) -> str:
        """Return the source category string for metrics and tracking."""
        ...
    
    def get_source_data(self, data_batch: T) -> list[Any]:
        """
        Extract source data references for the generated document.
        Override if source data structure differs from data_batch.
        """
        return [data_batch] if data_batch else []
    
    def build_context(self, template: TemplateConfig, data_batch: T) -> str:
        """
        Build validation context for the generated Q&A.
        Override to provide rich, domain-specific context for validation.
        
        Default implementation returns minimal context.
        """
        return f"Category: {self.get_source_category()}\nTemplate: {template.template_id}"
    
    def select_template(self) -> TemplateConfig:
        """Weighted random template selection from TEMPLATES."""
        if not self.TEMPLATES:
            raise ValueError(f"{self.__class__.__name__} must define TEMPLATES class variable")
        
        weights = [t.weight for t in self.TEMPLATES]
        return random.choices(self.TEMPLATES, weights=weights, k=1)[0]
    
    def validate_answer(
        self,
        qa: QuestionAnswer,
        template: TemplateConfig,
        data_batch: T,
        source_data: list[Any]
    ) -> tuple[bool, QuestionAnswerEnhanced | None]:
        """
        Run validation pipeline with regeneration loop.
        Returns (is_valid, enhanced_doc_or_none).
        """
        qa_pairs = [qa]
        
        is_valid, doc = validate_and_loop_with_suggested_fix(
            query_model=self.query_model,
            models=self.models,
            qa_pairs=qa_pairs,
            validation_pct=self.validation_pct,
            enable_extra_validation=self.enable_extra_validation,
            build_context=lambda: self.build_context(template, data_batch),
            source_category=self.get_source_category(),
            source_data=source_data,
            source_template=template.template_id,
            metrics=self.metrics
        )
        
        return is_valid, doc
    
    def generate(self) -> None:
        """
        Main generation loop - Template Method pattern.
        Orchestrates: fetch data → select template → build prompt → generate → validate → save
        """
        if not self.TEMPLATES:
            raise ValueError(f"{self.__class__.__name__} must define TEMPLATES class variable")
        
        data_batches = self.get_data_batches()
        if not data_batches:
            console.print(f"[yellow]No data batches found for {self.__class__.__name__}[/yellow]")
            return
        
        console.print(f"\n[bold cyan]=== GENERATING {self.target_count:,} {self.get_source_category().upper()} ===[/bold cyan]")
        console.print(f"  Data batches: {len(data_batches):,}")
        console.print(f"  Templates per item: {self.templates_per_item}")
        console.print(f"  Validation %: {self.validation_pct * 100:.0f}%")
        console.print(f"  Dry run: {self.dry_run}")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"Generating {self.get_source_category()}",
                total=self.target_count
            )
            
            for data_batch in data_batches:
                if self.generated_count >= self.target_count:
                    break
                
                # Select templates for this data batch
                selected_templates = [
                    self.select_template() 
                    for _ in range(self.templates_per_item)
                ]
                
                for template in selected_templates:
                    if self.generated_count >= self.target_count:
                        break
                    
                    try:
                        # Build prompt and generate
                        prompt = self.build_prompt(template, data_batch)
                        response = self.query_model.query(
                            self.models[ModelType.GENERATION], 
                            prompt
                        )
                        
                        # Parse JSON response
                        import json
                        qa_data = json.loads(response)
                        qa_pairs = [
                            QuestionAnswer(qa["question"], qa["answer"]) 
                            for qa in qa_data
                        ]
                        
                        # Validate each Q&A pair
                        source_data = self.get_source_data(data_batch)
                        
                        for qa in qa_pairs:
                            if self.generated_count >= self.target_count:
                                break
                            
                            is_valid, doc = self.validate_answer(
                                qa, template, data_batch, source_data
                            )
                            
                            if is_valid and doc:
                                if not self.dry_run:
                                    self.save_item(doc)
                                self.generated_count += 1
                                progress.advance(task)
                    
                    except json.JSONDecodeError as e:
                        console.print(f"[red]  ✗ JSON parse error: {e}[/red]")
                        if self.metrics:
                            self.metrics.record_candidate(self.get_source_category(), template.template_id)
                    except Exception as e:
                        console.print(f"[red]  ✗ Error generating: {type(e).__name__}: {e}[/red]")
                        if self.metrics:
                            self.metrics.record_candidate(self.get_source_category(), template.template_id)
                        continue
        
        elapsed = time.time() - self._start_time
        console.print(f"\n[green]✓ Completed {self.generated_count:,} {self.get_source_category()} in {elapsed:.1f}s[/green]")
        if self.metrics:
            self.metrics.flush()
            self.metrics.print_rolling_summary(interval=1)
```

---

## Integration Points with Existing Code

### 1. `common.py` - Validation Function
The base generator uses `validate_and_loop_with_suggested_fix` from `common.py` unchanged. This function handles:
- Validation percentage sampling
- Regeneration loop (max 3 attempts)
- Score tracking
- Metrics recording

### 2. `models.py` - ValidationMetrics
Base generator calls these methods on `ValidationMetrics`:
- `record_candidate(category, template)`
- `record_validation_attempt(category, template)`
- `record_skip(category, template)`
- `record_first_attempt_pass(score, category, template)`
- `record_pass_after_fix(score, category, template)`
- `record_failed_first_attempt(category, template)`
- `record_failed_after_fixes(category, template)`
- `record_fix_attempt(category, template)`
- `flush()` - writes to MongoDB
- `print_rolling_summary(interval)`

### 3. `query_model.py` - QueryModel
Base generator uses `QueryModel.query()` for generation and `QueryModel.validate_qa()` for validation.

### 4. `constants.py` - Template Definitions
Existing template constants (`COMBO_QUESTION_TEMPLATES`, `RULE_EXPLANATION_TEMPLATES`, etc.) are converted to `TemplateConfig` lists in each subclass.

---

## Migration Strategy for Existing Generators

### Phase 1: Base Class + 2 Pilot Generators (Tasks 1-5)
1. Create `base_generator.py` with `TemplateConfig` and `BaseGenerator`
2. Export `TemplateConfig` from `common.py`
3. Refactor `GenerateComboQueries` (most complex) → validates pattern works for complex data
4. Refactor `GenerateArticleQA` (simpler) → validates pattern works for different data shapes

### Phase 2: Batch Migration (Task 6)
For each remaining generator:
1. Change class to inherit from `BaseGenerator`
2. Define `TEMPLATES` class variable from existing constants
3. Implement 3 abstract methods:
   - `get_data_batches()` - extract data fetching logic
   - `build_prompt(template, data)` - extract prompt building logic
   - `get_source_category()` - return category string
4. Optionally override `build_context()` for rich validation context
5. Remove `__init__`, `generate_*()`, and all loop/validation/saving code
6. Update `main.py` to pass `save_item` callback (already compatible)

### Template Migration Examples

**Combo Queries** (from `COMBO_QUESTION_TEMPLATES`):
```python
class GenerateComboQueries(BaseGenerator[ProjectedCombo]):
    TEMPLATES = [
        TemplateConfig("how_does_it_work", COMBO_QUESTION_TEMPLATES[0]["task_instruction"], 1.0),
        TemplateConfig("what_do_i_need", COMBO_QUESTION_TEMPLATES[1]["task_instruction"], 1.0),
        TemplateConfig("why_does_this_work", COMBO_QUESTION_TEMPLATES[2]["task_instruction"], 1.0),
        TemplateConfig("what_is_the_result", COMBO_QUESTION_TEMPLATES[3]["task_instruction"], 1.0),
    ]
    
    def get_data_batches(self) -> list[ProjectedCombo]:
        return self._extract_combo_data(...)  # existing logic
    
    def build_prompt(self, template: TemplateConfig, combo: ProjectedCombo) -> str:
        return self._build_combo_prompt(...)  # existing logic
    
    def get_source_category(self) -> str:
        return "combo_query"
```

**Article QA** (single template):
```python
class GenerateArticleQa(BaseGenerator[dict]):
    TEMPLATES = [
        TemplateConfig("article_qa", "Generate 4 Q&A from this EDHREC article...", 1.0),
    ]
    
    def get_data_batches(self) -> list[dict]:
        # existing article fetching logic
        ...
    
    def build_prompt(self, template: TemplateConfig, article: dict) -> str:
        return build_article_qa_prompt(article["title"], article["content"])
    
    def get_source_category(self) -> str:
        return "article_qa"
```

---

## Testing Strategy

### Unit Tests for BaseGenerator
- **Template Selection**: Verify weighted selection respects weights
- **Dry Run Mode**: Verify `save_item` not called when `dry_run=True`
- **Validation Integration**: Mock `validate_and_loop_with_suggested_fix`, verify called with correct args
- **Metrics Recording**: Mock `ValidationMetrics`, verify methods called
- **Error Handling**: Verify exceptions logged and loop continues
- **Progress Tracking**: Verify `generated_count` increments correctly

### Integration Tests (per generator)
- **Combo Queries**: Generate 10 items, verify output matches pre-refactor format
- **Article QA**: Generate 10 items, verify output matches pre-refactor format
- **All Generators**: Run with `--dry-run` flag, verify no MongoDB writes

### Regression Tests
- Run full `--phase1` generation, compare output counts/categories with baseline
- Verify `ValidationMetrics` documents in MongoDB have same structure

---

## Potential Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Base class too rigid for some generators | Medium | High | Provide ample hook methods (`build_context`, `get_source_data`, `select_template` overrideable) |
| Migration breaks existing generator logic | Medium | High | Pilot with 2 generators first; comprehensive integration tests |
| Metrics double-counting | Low | Medium | Base class owns all metrics calls; subclasses don't call metrics directly |
| Template weight changes behavior | Low | Low | Document weight defaults; match original `random.sample(k=2)` behavior with equal weights |
| Dry-run mode not tested in CI | Medium | Low | Add `--dry-run` to CI pipeline for all generators |

---

## Handoff to Implementer

**Design Document**: This file (`.opencode/design/story-001-shared-base-generator.md`)

**User Story**: `.opencode/discovery/story-001-shared-base-generator.md`

**Estimated Complexity**: High (foundational, affects all 23 generators)

**Key Files to Create/Modify**:
1. `training_data/generate_synthetic_data/base_generator.py` (NEW - main deliverable)
2. `training_data/generate_synthetic_data/common.py` (add `TemplateConfig` export)
3. `training_data/generate_synthetic_data/generate_combo_queries.py` (refactor)
4. `training_data/generate_synthetic_data/generate_article_qa.py` (refactor)

**Start With**: Task 1 - Create `base_generator.py` with `TemplateConfig` and `BaseGenerator` class

**Acceptance Criteria** (from user story):
- [ ] Abstract base class `BaseGenerator` in `base_generator.py`
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