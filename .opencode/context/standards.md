# Coding Standards for MTG Synthetic Data Generation Pipeline

## Overview
This document defines the coding standards, patterns, and conventions for the synthetic data generation pipeline in `training_data/generate_synthetic_data/`.

---

## Python Standards

### Version & Type Hints
- **Python**: 3.11+
- **Type Hints**: Required for all public functions, methods, and class attributes
- **Pydantic**: v2 (`BaseModel`, `Field`, `ConfigDict`, `computed_field`)
- **Imports**: Use `from __future__ import annotations` for forward references

### Code Style
- **Formatter**: `ruff format` (line length 100)
- **Linter**: `ruff check` with `select = ["E", "F", "I", "UP", "B", "C4", "SIM", "T20"]`
- **Type Checker**: `pyright` or `mypy` in strict mode
- **Naming**: 
  - Classes: `PascalCase`
  - Functions/Methods: `snake_case`
  - Constants: `UPPER_SNAKE_CASE`
  - Private: `_leading_underscore`
  - Type Variables: `T`, `U`, `V` (single uppercase)

### Docstrings
- **Format**: Google style (Args, Returns, Raises, Example)
- **Required**: All public classes, methods, functions
- **Example**:
```python
def get_cards_enriched(
    self,
    filters: dict | None = None,
    limit: int = 100,
) -> list[CardWithMetadata]:
    """Fetch cards with all enrichment joins applied.
    
    Args:
        filters: MongoDB query filter dict (e.g., {"colorIdentity": {"$in": ["W", "U"]}})
        limit: Maximum number of cards to return.
    
    Returns:
        List of CardWithMetadata with prices, legalities, rulings, keywords joined.
    
    Raises:
        PyMongoError: If aggregation pipeline fails.
    """
```

---

## Architecture Patterns

### 1. Base Generator Pattern (Template Method)
All generators inherit from `BaseGenerator[T]`:
```python
class MyGenerator(BaseGenerator[MyDataType]):
    TEMPLATES: ClassVar[list[TemplateConfig]] = [...]
    
    def get_data_batches(self) -> list[MyDataType]: ...
    def build_prompt(self, template: TemplateConfig, data: MyDataType) -> str: ...
    def get_source_category(self) -> str: ...
```

### 2. Data Access Layer (Facade)
Single `MTGDataAccess` class for all MongoDB operations:
- No raw `pymongo` in generators
- All methods return Pydantic models
- Aggregation pipelines for joins
- Context manager for connection lifecycle

### 3. Dependency Injection
- `BaseGenerator` receives `data_access: MTGDataAccess`, `models: dict[ModelType, Model]`, `save_item: Callable`
- No global state; all dependencies passed in `__init__`
- Enables testing with mocks

### 4. Validation Pipeline
- Use `validate_and_loop_with_suggested_fix` from `common.py`
- Pass `build_context` lambda for domain-specific validation context
- Metrics tracked via `ValidationMetrics` (injected)

---

## MongoDB Patterns

### Connection Management
```python
with MTGDataAccess(uri, user, pass) as db:
    db.verify_indexes()
    cards = db.get_cards_enriched(...)
```

### Aggregation Pipelines
- Use `$lookup` for joins (not Python-side loops)
- `$unwind` + `$group` for array flattening
- `$project` to shape output to match Pydantic models
- Always include `{"$limit": limit}` for safety

### Field Naming
- MongoDB: `camelCase` (`colorIdentity`, `edhrecRank`, `manaCost`)
- Pydantic: `snake_case` with `Field(alias="camelCase")`
- Python code: always use `snake_case`

### Indexes
- Verify/create on startup via `verify_indexes()`
- Compound indexes for common filter combinations
- Text indexes for search fields

---

## Pydantic Model Standards

### Base Configuration
```python
from pydantic import BaseModel, ConfigDict, Field

class BaseDomainModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,      # Allow snake_case and alias
        extra="ignore",             # Ignore unknown MongoDB fields
        arbitrary_types_allowed=True,  # For ObjectId, datetime
        use_enum_values=True,       # Serialize enums as values
    )
```

### Aliases
```python
class Card(BaseDomainModel):
    name: str
    mana_cost: str | None = Field(alias="manaCost", default=None)
    color_identity: list[str] = Field(alias="colorIdentity", default_factory=list)
    edhrec_rank: int | None = Field(alias="edhrecRank", default=None)
```

### Computed Properties
```python
@property
def cmc(self) -> float:
    """Converted mana cost from mana_cost string."""
    if not self.mana_cost:
        return 0.0
    # Parse {2}{W}{U} -> 4.0
    ...

@property
def is_commander_legal(self) -> bool:
    return self.legalities.get("commander") == "legal"
```

### Serialization for LLM Prompts
```python
def to_prompt_detail(self) -> str:
    """Format for LLM context - consistent across all generators."""
    lines = [
        f"Name: {self.name}",
        f"Type: {self.type}",
        f"Cost: {self.mana_cost}",
        f"Text: {self.text or self.oracle_text}",
    ]
    if self.edhrec_rank:
        lines.append(f"EDHREC Rank: {self.edhrec_rank}")
    return "\n".join(lines)
```

---

## Generator Implementation Standards

### Required Structure
```python
class GenerateMyFormat(BaseGenerator[MyDataType]):
    TEMPLATES: ClassVar[list[TemplateConfig]] = [
        TemplateConfig("template_id", "Instruction...", weight=1.0),
    ]
    
    def __init__(
        self,
        data_access: MTGDataAccess,
        models: dict[ModelType, Model],
        validation_pct: float,
        target_count: int,
        save_item: Callable[[QuestionAnswerEnhanced], None],
        metrics: ValidationMetrics | None = None,
        **kwargs,
    ):
        super().__init__(
            data_access=data_access,
            models=models,
            validation_pct=validation_pct,
            target_count=target_count,
            save_item=save_item,
            metrics=metrics,
            **kwargs,
        )
    
    def get_data_batches(self) -> list[MyDataType]:
        return self.data_access.get_my_data_enriched(limit=self.target_count * 2)
    
    def build_prompt(self, template: TemplateConfig, data: MyDataType) -> str:
        return f"{SYSTEM_MESSAGE}\n{MTG_NOTATION_LEGEND}\n{template.task_instruction}\n..."
    
    def get_source_category(self) -> str:
        return "my_format"
    
    def build_context(self, template: TemplateConfig, data: MyDataType) -> str:
        return f"Category: {self.get_source_category()}\nTemplate: {template.template_id}\nData: {data.to_prompt_detail()}"
```

### Template Configuration
- Define in `constants.py` as `TemplateConfig` lists
- Each template: `template_id`, `task_instruction`, `weight`, `validation_rules`
- Use `random.choices(TEMPLATES, weights=[t.weight for t in TEMPLATES])` for selection

### Error Handling
```python
try:
    response = self.query_model.query(self.models[ModelType.GENERATION], prompt)
    qa_pairs = [QuestionAnswer(**qa) for qa in json.loads(response)]
except json.JSONDecodeError as e:
    logger.warning(f"JSON parse failed: {e}")
    if self.metrics:
        self.metrics.record_candidate(self.get_source_category(), template.template_id)
    continue  # Graceful continuation
except Exception as e:
    logger.error(f"Generation error: {type(e).__name__}: {e}")
    continue
```

---

## Testing Standards

### Unit Tests
- **Location**: `training_data/generate_synthetic_data/` (same directory as source)
- **Framework**: `pytest` with `pytest-asyncio` if needed
- **Mocking**: `unittest.mock` for `MTGDataAccess`, `QueryModel`, `MongoClient`
- **Coverage Target**: 80%+ for new code

### Test File Naming
- Generator tests: `test_generate_{module_name}.py` in the same directory
- Example: `test_generate_meta_knowledge.py` for `generate_meta_knowledge.py`

### Test Patterns
```python
# Test data access method
def test_get_cards_enriched_returns_typed_models(mock_mongo):
    db = MTGDataAccess(client=mock_mongo)
    cards = db.get_cards_enriched(limit=5)
    
    assert len(cards) == 5
    assert all(isinstance(c, CardWithMetadata) for c in cards)
    assert cards[0].prices is not None  # Joined
    assert cards[0].rulings is not None  # Joined

# Test generator abstract methods
def test_my_generator_implements_abstract_methods():
    gen = GenerateMyFormat(data_access=mock_db, ...)
    assert hasattr(gen, "get_data_batches")
    assert hasattr(gen, "build_prompt")
    assert hasattr(gen, "get_source_category")
```

### Topic-Based Generator Test Pattern (BaseGenerator[str])
Each topic-based generator test file should follow this structure:
```python
"""Unit tests for Generate{GeneratorName}."""

import json
from unittest.mock import Mock

import pytest

from training_data.generate_synthetic_data.models import (
    Model, ModelType, ModelProvider,
)
from training_data.generate_synthetic_data.query_model import QueryModel
from training_data.generate_synthetic_data.generate_{module} import Generate{ClassName}


class MockModel(Model):
    def __init__(self, name="test-model", model_type=ModelType.GENERATION):
        self.name = name
        self.type = model_type
        self.provider = ModelProvider.OLLAMA
        self.provider_url = "http://localhost:11434"
        self.api_key = None


@pytest.fixture
def models():
    return {
        ModelType.GENERATION: MockModel("gen", ModelType.GENERATION),
        ModelType.VALIDATION: MockModel("val", ModelType.VALIDATION),
    }


@pytest.fixture
def generator(models):
    return Generate{ClassName}(
        models=models,
        validation_pct=1.0,
        target_count=10,
        save_item=Mock(),
        metrics=Mock(),
        dry_run=True,
    )


class Test{ClassName}:
    def test_templates_defined(self, generator):
        """TEMPLATES must be defined with at least 2 template configs."""
        assert len(generator.TEMPLATES) == 2
        ids = {t.template_id for t in generator.TEMPLATES}
        assert "general_advice" in ids

    def test_source_category(self, generator):
        """get_source_category returns correct string."""
        assert generator.get_source_category() == "{category}"

    def test_data_batches_cycles(self, generator):
        """get_data_batches yields all items from the class-level list."""
        batches = []
        for batch in generator.get_data_batches():
            batches.append(batch[0])
            if len(batches) >= {total_items}:
                break
        assert len(batches) == {total_items}

    def test_build_prompt_includes_context(self, generator):
        """build_prompt includes topic context and MTG_NOTATION_LEGEND."""
        template = generator.TEMPLATES[0]
        topic = generator.{CLASS_LEVEL_LIST}[0][0]
        prompt = generator.build_prompt(template, topic)
        assert "{mtg_notation_check}" in prompt
        assert topic in prompt

    def test_build_context_metadata(self, generator):
        """build_context returns category, template_id, and domain label."""
        template = generator.TEMPLATES[0]
        topic = generator.{CLASS_LEVEL_LIST}[0][0]
        context = generator.build_context(template, topic)
        assert generator.get_source_category() in context
        assert template.template_id in context

    def test_dry_run_no_save(self, models):
        """dry_run=True should not call save_item."""
        save_item = Mock()
        gen = Generate{ClassName}(
            models=models,
            validation_pct=1.0,
            target_count=1,
            save_item=save_item,
            dry_run=True,
        )
        gen.query_model = Mock(spec=QueryModel)
        gen.query_model.query.return_value = json.dumps([
            {"question": "Test?", "answer": "Test answer with sufficient length."}
        ])
        gen.query_model.validate_qa.return_value = (True, "OK", 8.0)
        gen.generate()
        save_item.assert_not_called()
        assert gen.generated_count == 1
```

### Integration Tests
- **Location**: `tests/integration/`
- **Run**: `pytest tests/integration/` (requires MongoDB)
- **Fixtures**: Real MongoDB test database with sample data

---

## Logging & Observability

### Console Output
- Use `rich.console.Console` for user-facing output
- Use `rich.progress.Progress` for generation loops
- Structured logging via `logger` module (already configured)

### Metrics
- `ValidationMetrics` tracks: candidates, validated, passed, failed, fix attempts, scores
- Flush to MongoDB every 10 candidates (`print_rolling_summary(interval=10)`)
- Run ID shared across all generators in a process

### Dry Run Mode
- All generators support `dry_run=True` (no MongoDB writes)
- Use for testing and CI

---

## Dependency Management

### Allowed Dependencies (in `pyproject.toml` / `requirements.txt`)
- `pymongo` - MongoDB driver
- `pydantic` - Data models
- `rich` - Console UI
- `ollama` / `anthropic` / `openai` - LLM clients
- `python-dotenv` - Environment config
- `bson` - ObjectId support

### Adding New Dependencies
1. Justify in PR description
2. Prefer stdlib over third-party
3. Pin versions in `requirements.txt`

---

## Git & CI Conventions

### Branches
- `main` - Production ready
- `feature/*` - New features
- `fix/*` - Bug fixes
- `refactor/*` - Code improvements

### Commits
- Conventional commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`
- Reference issue: `feat: add base generator (issue #123)`

### CI Pipeline
1. `ruff check` - Lint
2. `ruff format --check` - Format
3. `pyright` - Type check
4. `pytest tests/unit/` - Unit tests
5. `pytest tests/integration/` - Integration (if MongoDB available)

---

## Migration Checklist (for existing generators)

### Data-Driven Generators (use MTGDataAccess)
When refactoring a generator that reads from MongoDB:

- [ ] Inherit from `BaseGenerator[T]` where T is the data model type
- [ ] Define `TEMPLATES` class variable with TemplateConfig dataclasses
- [ ] Implement `get_data_batches()` using `data_access` methods
- [ ] Implement `build_prompt()` using `template` + `data`
- [ ] Implement `get_source_category()`
- [ ] Override `build_context()` for rich validation context
- [ ] Override `get_source_data()` if data structure differs from data_batch
- [ ] Remove `__init__` (use base), `generate_*()`, manual validation loop
- [ ] Remove raw `pymongo` imports and collection dependencies
- [ ] Update `main.py` to pass `data_access` instance
- [ ] Test with `--dry-run` first
- [ ] Verify output matches pre-refactor format

### Topic-Based Generators (BaseGenerator[str])
When refactoring a generator with hardcoded topics (no data_access):

- [ ] Inherit from `BaseGenerator[str]`
- [ ] Define `TEMPLATES` class variable with 2 TemplateConfig dataclasses
- [ ] Preserve all original topics/terms/archetypes as class-level constant (e.g., TOPICS, TERMS, ARCHETYPES)
- [ ] Implement `get_data_batches()` that cycles through the class-level list
- [ ] Implement `build_prompt()` that looks up context by name, uses MTG_NOTATION_LEGEND + OUTPUT_FORMAT
- [ ] Implement `get_source_category()` returning the category string
- [ ] Implement `build_context()` returning category + template_id + domain-specific label
- [ ] Remove `__init__` (use base class), `generate_*()` method, manual validation loop
- [ ] Remove raw `pymongo` imports, `QueryModel()` instantiation, manual JSON parsing
- [ ] Remove `from .logger import print` — base class uses rich.console
- [ ] Update `main.py`: use keyword args constructor + `.generate()` instead of positional args + `.generate_*()`
- [ ] Add `dry_run` support via base class parameter
- [ ] Write unit tests following the test pattern in Testing Standards above
- [ ] Test with `--dry-run` first
- [ ] Verify output matches pre-refactor category and data coverage