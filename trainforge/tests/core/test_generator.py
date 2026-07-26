"""Tests for TrainForge generator module - BaseGenerator helpers, factory."""

from __future__ import annotations

import pytest

from trainforge.domain import DomainPlugin, TemplateConfig
from trainforge.generator import BaseGenerator, create_generator
from trainforge.models import Model, ModelType


# =============================================================================
# MOCK DOMAIN FOR TESTING
# =============================================================================


class MockDomain(DomainPlugin):
    """Minimal mock domain for generator tests."""

    @property
    def name(self) -> str:
        return "mock"

    @property
    def display_name(self) -> str:
        return "Mock Domain"

    @property
    def system_message(self) -> str:
        return "You are a test assistant."

    @property
    def notation_legend(self) -> str:
        return ""

    def get_data_source(self, config=None):
        raise NotImplementedError("Not needed for unit tests")

    def get_generators(self):
        return []

    def get_categories(self):
        return ["test_category"]


class MockGenerator(BaseGenerator[dict]):
    """Concrete mock generator for testing."""

    def get_data_batches(self) -> list[dict]:
        return [{"id": "batch1"}, {"id": "batch2"}]

    def build_prompt(self, template: TemplateConfig, data_batch: dict) -> str:
        return f"Prompt for {data_batch.get('id', 'unknown')}"

    def get_source_category(self) -> str:
        return "test_category"


# =============================================================================
# _GET_SOURCE_IDENTIFIER
# =============================================================================


class TestGetSourceIdentifier:
    """Test BaseGenerator._get_source_identifier() static method."""

    def test_dict_with_id_field(self):
        """Should extract 'id' from dict."""
        result = MockGenerator._get_source_identifier({"id": "card-123"})
        assert result == "card-123"

    def test_dict_with_underscore_id(self):
        """Should prefer '_id' over 'id'."""
        result = MockGenerator._get_source_identifier(
            {"_id": "mongo-id", "id": "other"}
        )
        assert result == "mongo-id"

    def test_dict_with_name_field(self):
        """Should fall back to 'name' if no id fields."""
        result = MockGenerator._get_source_identifier({"name": "Lightning Bolt"})
        assert result == "Lightning Bolt"

    def test_dict_with_title_field(self):
        """Should use 'title' as fallback."""
        result = MockGenerator._get_source_identifier({"title": "Article Title"})
        assert result == "Article Title"

    def test_dict_no_id_fields(self):
        """Should return truncated dict string when no ID fields exist."""
        result = MockGenerator._get_source_identifier(
            {"foo": "bar", "baz": 123, "qux": True}
        )
        assert len(result) <= 80

    def test_string_input(self):
        """Should return string as-is (truncated to 80 chars)."""
        result = MockGenerator._get_source_identifier("simple-string-id")
        assert result == "simple-string-id"

    def test_int_input(self):
        """Should convert int to string."""
        result = MockGenerator._get_source_identifier(42)
        assert result == "42"

    def test_float_input(self):
        """Should convert float to string."""
        result = MockGenerator._get_source_identifier(3.14)
        assert result == "3.14"


# =============================================================================
# _PARSE_QA
# =============================================================================


class TestParseQA:
    """Test BaseGenerator._parse_qa() method."""

    def setup_method(self):
        self.gen = MockGenerator.__new__(MockGenerator)  # No __init__ needed

    def test_valid_json(self):
        """Should parse valid JSON with question and answer."""
        raw = '{"question": "What is MTG?", "answer": "Magic: The Gathering"}'
        result = self.gen._parse_qa(raw)
        assert result is not None
        assert result.question == "What is MTG?"
        assert result.answer == "Magic: The Gathering"

    def test_json_with_markdown_fences(self):
        """Should strip markdown code fences."""
        raw = '```json\n{"question": "Q?", "answer": "A!"}\n```'
        result = self.gen._parse_qa(raw)
        assert result is not None
        assert result.question == "Q?"

    def test_json_with_extra_text_before(self):
        """Should handle text before JSON block."""
        raw = 'Here is the answer:\n{"question": "Q?", "answer": "A!"}'
        result = self.gen._parse_qa(raw)
        assert result is not None

    def test_nested_json_in_answer(self):
        """Should handle nested JSON structures in answer field."""
        raw = '{"question": "What cards?", "answer": "{\\"cards\\": [\\"Bolt\\"]}"}'
        result = self.gen._parse_qa(raw)
        assert result is not None

    def test_invalid_no_braces(self):
        """Should return None for input without JSON braces."""
        raw = "Just plain text, no JSON here"
        result = self.gen._parse_qa(raw)
        assert result is None

    def test_missing_question_field(self):
        """Should return None when question field is missing."""
        raw = '{"answer": "An answer without a question"}'
        result = self.gen._parse_qa(raw)
        assert result is None

    def test_empty_question(self):
        """Should return None when question is empty string."""
        raw = '{"question": "", "answer": "A!"}'
        result = self.gen._parse_qa(raw)
        assert result is None

    def test_missing_answer_field(self):
        """Should return None when answer field is missing."""
        raw = '{"question": "Q?"}'
        result = self.gen._parse_qa(raw)
        assert result is None

    def test_empty_answer(self):
        """Should return None when answer is empty string."""
        raw = '{"question": "Q?", "answer": ""}'
        result = self.gen._parse_qa(raw)
        assert result is None

    def test_unbalanced_braces(self):
        """Should return None for unbalanced braces."""
        raw = '{"question": "Q?", "answer": "A!"'  # Missing closing brace
        result = self.gen._parse_qa(raw)
        assert result is None


# =============================================================================
# CREATE_GENERATOR FACTORY
# =============================================================================


class TestCreateGenerator:
    """Test create_generator() factory function."""

    def test_basic_creation(self):
        """Should create a generator instance with required params."""
        domain = MockDomain()
        gen_model = Model(name="qwen2.5:14b", type=ModelType.GENERATION)
        val_model = Model(name="qwen2.5:14b", type=ModelType.VALIDATION)

        gen = create_generator(
            domain=domain,
            generator_class=MockGenerator,
            generation_model=gen_model,
            validation_model=val_model,
        )

        assert isinstance(gen, MockGenerator)
        assert gen.domain is domain
        assert gen.generation_model == gen_model

    def test_raises_without_generation_model(self):
        """Should raise ValueError if generation_model is None."""
        with pytest.raises(ValueError, match="required"):
            create_generator(
                domain=MockDomain(),
                generator_class=MockGenerator,
                generation_model=None,
                validation_model=Model(name="x", type=ModelType.VALIDATION),
            )

    def test_raises_without_validation_model(self):
        """Should raise ValueError if validation_model is None."""
        with pytest.raises(ValueError, match="required"):
            create_generator(
                domain=MockDomain(),
                generator_class=MockGenerator,
                generation_model=Model(name="x", type=ModelType.GENERATION),
                validation_model=None,
            )

    def test_passes_through_optional_params(self):
        """Should pass optional params to constructor."""
        domain = MockDomain()
        gen_model = Model(name="qwen2.5:14b", type=ModelType.GENERATION)
        val_model = Model(name="qwen2.5:14b", type=ModelType.VALIDATION)

        gen = create_generator(
            domain=domain,
            generator_class=MockGenerator,
            generation_model=gen_model,
            validation_model=val_model,
            run_id="custom-run-123",
            max_items=50,
        )

        assert gen.run_id == "custom-run-123"
        assert gen.max_items == 50


# =============================================================================
# GENERATOR INIT BEHAVIOR
# =============================================================================


class TestGeneratorInit:
    """Test BaseGenerator initialization behavior."""

    def test_default_run_id(self):
        """Should generate a short run_id if not provided."""
        domain = MockDomain()
        gen_model = Model(name="qwen2.5:14b", type=ModelType.GENERATION)
        val_model = Model(name="qwen2.5:14b", type=ModelType.VALIDATION)

        gen = MockGenerator(
            domain=domain,
            generation_model=gen_model,
            validation_model=val_model,
        )

        assert len(gen.run_id) == 8  # UUID truncated to 8 chars

    def test_custom_run_id(self):
        """Should use provided run_id."""
        domain = MockDomain()
        gen_model = Model(name="qwen2.5:14b", type=ModelType.GENERATION)
        val_model = Model(name="qwen2.5:14b", type=ModelType.VALIDATION)

        gen = MockGenerator(
            domain=domain,
            generation_model=gen_model,
            validation_model=val_model,
            run_id="my-run-id",
        )

        assert gen.run_id == "my-run-id"

    def test_metrics_created_if_none(self):
        """Should create default ValidationMetrics if not provided."""
        domain = MockDomain()
        gen_model = Model(name="qwen2.5:14b", type=ModelType.GENERATION)
        val_model = Model(name="qwen2.5:14b", type=ModelType.VALIDATION)

        gen = MockGenerator(
            domain=domain,
            generation_model=gen_model,
            validation_model=val_model,
        )

        assert gen.metrics is not None
        assert gen.metrics.generator_name == "MockGenerator"

    def test_shared_metrics_updated(self):
        """Should update shared metrics with generator info."""
        from trainforge.models import ValidationMetrics

        domain = MockDomain()
        gen_model = Model(name="qwen2.5:14b", type=ModelType.GENERATION)
        val_model = Model(name="qwen2.5:14b", type=ModelType.VALIDATION)
        shared_metrics = ValidationMetrics(run_id="shared-run")

        gen = MockGenerator(
            domain=domain,
            generation_model=gen_model,
            validation_model=val_model,
            metrics=shared_metrics,
        )

        assert gen.metrics is shared_metrics
        assert gen.metrics.generator_name == "MockGenerator"
