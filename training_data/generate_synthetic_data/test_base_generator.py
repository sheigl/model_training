"""Unit tests for BaseGenerator and TemplateConfig."""

import json
from unittest.mock import MagicMock, Mock, patch
from typing import Iterator

import pytest

from training_data.generate_synthetic_data.base_generator import BaseGenerator, TemplateConfig
from training_data.generate_synthetic_data.models import (
    Model,
    ModelType,
    ModelProvider,
    QuestionAnswer,
    QuestionAnswerEnhanced,
    ValidationMetrics,
)
from training_data.generate_synthetic_data.query_model import QueryModel


class MockModel(Model):
    """Mock model for testing."""
    def __init__(self, name: str = "test-model", model_type: ModelType = ModelType.GENERATION):
        self.name = name
        self.type = model_type
        self.provider = ModelProvider.OLLAMA
        self.provider_url = "http://localhost:11434"
        self.api_key = None


class MockQueryModel(QueryModel):
    """Mock QueryModel for testing."""
    def __init__(self):
        super().__init__()
        self.query_responses = []
        self.validate_responses = []
        self.regenerate_responses = []
        self.query_call_count = 0
        self.validate_call_count = 0
        self.regenerate_call_count = 0

    def query(self, model: Model, prompt: str, max_tokens: int = 8192) -> str:
        self.query_call_count += 1
        if self.query_responses:
            return self.query_responses.pop(0)
        return json.dumps([{"question": "Test question?", "answer": "Test answer with sufficient length to pass validation."}])

    def validate_qa(self, validation_model: Model, question: str, answer: str, context: str = "", category: str = "", enable_extra_validation: bool = True, trace_round: dict | None = None):
        self.validate_call_count += 1
        if self.validate_responses:
            return self.validate_responses.pop(0)
        return True, "OK", 8.0

    def regenerate_answer(self, generation_model: Model, question: str, old_answer: str, reason: str, score: float | None, context: str = "", category: str = "", sibling_feedback: str = "", trace_regeneration: dict | None = None) -> str | None:
        self.regenerate_call_count += 1
        if self.regenerate_responses:
            return self.regenerate_responses.pop(0)
        return "Regenerated answer with sufficient length to pass validation."


class ConcreteGenerator(BaseGenerator[dict]):
    """Concrete implementation for testing."""
    TEMPLATES = [
        TemplateConfig("template_a", "Instruction A", weight=1.0),
        TemplateConfig("template_b", "Instruction B", weight=2.0),
        TemplateConfig("template_c", "Instruction C", weight=1.0),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data_batches = []

    def get_data_batches(self) -> Iterator[list[dict]]:
        for batch in self.data_batches:
            yield batch

    def build_prompt(self, template: TemplateConfig, data_batch: dict) -> str:
        return f"Prompt for {template.template_id} with data {data_batch}"

    def get_source_category(self) -> str:
        return "test_category"


class TestTemplateConfig:
    """Tests for TemplateConfig dataclass."""

    def test_default_values(self):
        """Test default values for optional fields."""
        config = TemplateConfig("test", "instruction")
        assert config.template_id == "test"
        assert config.task_instruction == "instruction"
        assert config.weight == 1.0
        assert config.validation_rules == []
        assert config.min_answer_length == 80
        assert config.max_answer_length == 2000

    def test_custom_values(self):
        """Test custom values for all fields."""
        config = TemplateConfig(
            template_id="custom",
            task_instruction="Custom instruction",
            weight=2.5,
            validation_rules=["rule1", "rule2"],
            min_answer_length=100,
            max_answer_length=3000,
        )
        assert config.template_id == "custom"
        assert config.task_instruction == "Custom instruction"
        assert config.weight == 2.5
        assert config.validation_rules == ["rule1", "rule2"]
        assert config.min_answer_length == 100
        assert config.max_answer_length == 3000

    def test_frozen_dataclass(self):
        """Test that TemplateConfig is frozen (immutable)."""
        config = TemplateConfig("test", "instruction")
        with pytest.raises(AttributeError):
            config.template_id = "modified"


class TestTemplateSelection:
    """Tests for template selection logic."""

    def setup_method(self):
        """Set up test fixtures."""
        self.models = {
            ModelType.GENERATION: MockModel("gen-model", ModelType.GENERATION),
            ModelType.VALIDATION: MockModel("val-model", ModelType.VALIDATION),
        }
        self.save_item = Mock()
        self.metrics = Mock()
        self.metrics.generator_name = "unknown"
        self.metrics.generation_model = "unknown"
        self.metrics.validation_model = "unknown"
        self.metrics.run_id = "test-run-id"
        self.metrics.flush = Mock()
        self.metrics.print_rolling_summary = Mock()
        self.metrics.record_candidate = Mock()
        self.metrics.record_validation_attempt = Mock()
        self.metrics.record_skip = Mock()
        self.metrics.record_first_attempt_pass = Mock()
        self.metrics.record_pass_after_fix = Mock()
        self.metrics.record_failed_first_attempt = Mock()
        self.metrics.record_failed_after_fixes = Mock()
        self.metrics.record_fix_attempt = Mock()

    def test_select_templates_equal_weights(self):
        """Test template selection with equal weights."""
        generator = ConcreteGenerator(
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
        )
        generator.data_batches = [[{"id": 1}]]

        # Select many templates to test distribution
        selected = generator.select_templates(k=1000)
        counts = {t.template_id: selected.count(t) for t in generator.TEMPLATES}

        # With weights 1.0, 2.0, 1.0, template_b should be selected ~50% of the time
        assert counts["template_b"] > counts["template_a"]
        assert counts["template_b"] > counts["template_c"]
        assert abs(counts["template_a"] - counts["template_c"]) < 100  # roughly equal

    def test_select_templates_custom_weights(self):
        """Test template selection respects custom weights."""
        generator = ConcreteGenerator(
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
        )
        generator.data_batches = [[{"id": 1}]]

        # Override templates with extreme weights
        generator.TEMPLATES = [
            TemplateConfig("rare", "Rare", weight=0.1),
            TemplateConfig("common", "Common", weight=10.0),
        ]

        selected = generator.select_templates(k=1000)
        counts = {t.template_id: selected.count(t) for t in generator.TEMPLATES}

        # Common should be selected much more often
        assert counts["common"] > counts["rare"] * 50

    def test_select_single_template(self):
        """Test select_template returns single template."""
        generator = ConcreteGenerator(
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
        )
        generator.data_batches = [[{"id": 1}]]

        template = generator.select_template()
        assert isinstance(template, TemplateConfig)
        assert template.template_id in ["template_a", "template_b", "template_c"]

    def test_empty_templates_raises_error(self):
        """Test that empty TEMPLATES raises ValueError."""
        class EmptyGenerator(BaseGenerator[dict]):
            TEMPLATES = []

            def get_data_batches(self) -> Iterator[list[dict]]:
                yield []

            def build_prompt(self, template: TemplateConfig, data_batch: dict) -> str:
                return ""

            def get_source_category(self) -> str:
                return "empty"

        generator = EmptyGenerator(
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
        )

        with pytest.raises(ValueError, match="must define TEMPLATES"):
            generator.select_template()


class TestGenerationLoop:
    """Tests for the main generation loop."""

    def setup_method(self):
        """Set up test fixtures."""
        self.models = {
            ModelType.GENERATION: MockModel("gen-model", ModelType.GENERATION),
            ModelType.VALIDATION: MockModel("val-model", ModelType.VALIDATION),
        }
        self.save_item = Mock()
        self.metrics = Mock()
        self.metrics.generator_name = "unknown"
        self.metrics.generation_model = "unknown"
        self.metrics.validation_model = "unknown"
        self.metrics.run_id = "test-run-id"
        self.metrics.flush = Mock()
        self.metrics.print_rolling_summary = Mock()
        self.metrics.record_candidate = Mock()
        self.metrics.record_validation_attempt = Mock()
        self.metrics.record_skip = Mock()
        self.metrics.record_first_attempt_pass = Mock()
        self.metrics.record_pass_after_fix = Mock()
        self.metrics.record_failed_first_attempt = Mock()
        self.metrics.record_failed_after_fixes = Mock()
        self.metrics.record_fix_attempt = Mock()

    def test_dry_run_mode(self):
        """Test that dry_run=True doesn't call save_item."""
        generator = ConcreteGenerator(
            models=self.models,
            validation_pct=1.0,
            target_count=2,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )
        generator.data_batches = [[{"id": 1}], [{"id": 2}]]

        # Mock query model to return valid responses
        generator.query_model = MockQueryModel()
        generator.query_model.query_responses = [
            json.dumps([{"question": "Q1?", "answer": "A1 with sufficient length to pass validation."}]),
            json.dumps([{"question": "Q2?", "answer": "A2 with sufficient length to pass validation."}]),
        ]
        generator.query_model.validate_responses = [
            (True, "OK", 8.0),
            (True, "OK", 8.0),
        ]

        generator.generate()

        # save_item should not be called in dry_run mode
        self.save_item.assert_not_called()
        assert generator.generated_count == 2

    def test_normal_mode_calls_save_item(self):
        """Test that normal mode calls save_item for valid items."""
        generator = ConcreteGenerator(
            models=self.models,
            validation_pct=1.0,
            target_count=2,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=False,
        )
        generator.data_batches = [[{"id": 1}], [{"id": 2}]]

        generator.query_model = MockQueryModel()
        generator.query_model.query_responses = [
            json.dumps([{"question": "Q1?", "answer": "A1 with sufficient length to pass validation."}]),
            json.dumps([{"question": "Q2?", "answer": "A2 with sufficient length to pass validation."}]),
        ]
        generator.query_model.validate_responses = [
            (True, "OK", 8.0),
            (True, "OK", 8.0),
        ]

        generator.generate()

        assert self.save_item.call_count == 2
        assert generator.generated_count == 2

    def test_templates_per_item(self):
        """Test that templates_per_item applies multiple templates per data batch."""
        generator = ConcreteGenerator(
            models=self.models,
            validation_pct=1.0,
            target_count=4,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
            templates_per_item=2,
        )
        generator.data_batches = [[{"id": 1}], [{"id": 2}]]

        generator.query_model = MockQueryModel()
        generator.query_model.query_responses = [
            json.dumps([{"question": "Q1?", "answer": "A1 with sufficient length to pass validation."}]),
            json.dumps([{"question": "Q2?", "answer": "A2 with sufficient length to pass validation."}]),
            json.dumps([{"question": "Q3?", "answer": "A3 with sufficient length to pass validation."}]),
            json.dumps([{"question": "Q4?", "answer": "A4 with sufficient length to pass validation."}]),
        ]
        generator.query_model.validate_responses = [
            (True, "OK", 8.0),
            (True, "OK", 8.0),
            (True, "OK", 8.0),
            (True, "OK", 8.0),
        ]

        generator.generate()

        # 2 data batches * 2 templates_per_item = 4 generations
        assert generator.generated_count == 4
        assert generator.query_model.query_call_count == 4

    def test_stops_at_target_count(self):
        """Test that generation stops when target_count is reached."""
        generator = ConcreteGenerator(
            models=self.models,
            validation_pct=1.0,
            target_count=2,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )
        # Provide more data batches than target_count
        generator.data_batches = [[{"id": i}] for i in range(10)]

        generator.query_model = MockQueryModel()
        generator.query_model.query_responses = [
            json.dumps([{"question": f"Q{i}?", "answer": f"A{i} with sufficient length to pass validation."}])
            for i in range(10)
        ]
        generator.query_model.validate_responses = [
            (True, "OK", 8.0) for _ in range(10)
        ]

        generator.generate()

        assert generator.generated_count == 2
        assert generator.query_model.query_call_count == 2

    def test_validation_skip_percentage(self):
        """Test that validation_pct controls validation sampling."""
        generator = ConcreteGenerator(
            models=self.models,
            validation_pct=0.0,  # No validation
            target_count=3,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )
        generator.data_batches = [[{"id": i}] for i in range(3)]

        generator.query_model = MockQueryModel()
        generator.query_model.query_responses = [
            json.dumps([{"question": f"Q{i}?", "answer": f"A{i} with sufficient length to pass validation."}])
            for i in range(3)
        ]

        generator.generate()

        # With validation_pct=0, validate_qa should not be called
        assert generator.query_model.validate_call_count == 0
        assert generator.generated_count == 3

    def test_error_handling_continues_loop(self):
        """Test that errors in generation don't stop the loop."""
        generator = ConcreteGenerator(
            models=self.models,
            validation_pct=1.0,
            target_count=3,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )
        generator.data_batches = [[{"id": 1}], [{"id": 2}], [{"id": 3}]]

        generator.query_model = MockQueryModel()
        # First response causes JSON error, second succeeds, third causes exception
        generator.query_model.query_responses = [
            "invalid json",  # Will cause JSONDecodeError
            json.dumps([{"question": "Q2?", "answer": "A2 with sufficient length to pass validation."}]),
            json.dumps([{"question": "Q3?", "answer": "A3 with sufficient length to pass validation."}]),
        ]
        generator.query_model.validate_responses = [
            (True, "OK", 8.0),
            (True, "OK", 8.0),
        ]

        generator.generate()

        # Should have processed all 3 items despite first error
        assert generator.generated_count == 2  # First failed, next 2 succeeded
        assert generator.query_model.query_call_count == 3

    def test_json_parse_error_recorded_in_metrics(self):
        """Test that JSON parse errors are recorded in metrics."""
        generator = ConcreteGenerator(
            models=self.models,
            validation_pct=1.0,
            target_count=1,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )
        generator.data_batches = [[{"id": 1}]]

        generator.query_model = MockQueryModel()
        generator.query_model.query_responses = ["invalid json"]

        generator.generate()

        # Metrics should record the candidate
        self.metrics.record_candidate.assert_called()


class TestValidationIntegration:
    """Tests for validation pipeline integration."""

    def setup_method(self):
        """Set up test fixtures."""
        self.models = {
            ModelType.GENERATION: MockModel("gen-model", ModelType.GENERATION),
            ModelType.VALIDATION: MockModel("val-model", ModelType.VALIDATION),
        }
        self.save_item = Mock()
        self.metrics = Mock()
        self.metrics.generator_name = "unknown"
        self.metrics.generation_model = "unknown"
        self.metrics.validation_model = "unknown"
        self.metrics.run_id = "test-run-id"
        self.metrics.flush = Mock()
        self.metrics.print_rolling_summary = Mock()
        self.metrics.record_candidate = Mock()
        self.metrics.record_validation_attempt = Mock()
        self.metrics.record_skip = Mock()
        self.metrics.record_first_attempt_pass = Mock()
        self.metrics.record_pass_after_fix = Mock()
        self.metrics.record_failed_first_attempt = Mock()
        self.metrics.record_failed_after_fixes = Mock()
        self.metrics.record_fix_attempt = Mock()

    def test_validate_answer_calls_validate_and_loop(self):
        """Test that validate_answer calls the validation pipeline correctly."""
        generator = ConcreteGenerator(
            models=self.models,
            validation_pct=1.0,
            target_count=1,
            save_item=self.save_item,
            metrics=self.metrics,
        )
        generator.data_batches = [[{"id": 1}]]

        qa = QuestionAnswer("Test question?", "Test answer with sufficient length.")
        template = TemplateConfig("test_template", "Test instruction")
        data_batch = {"id": 1}
        source_data = [data_batch]

        # Mock the validation function
        with patch("training_data.generate_synthetic_data.base_generator.validate_and_loop_with_suggested_fix") as mock_validate:
            mock_validate.return_value = (True, Mock(spec=QuestionAnswerEnhanced))

            is_valid, doc = generator.validate_answer(qa, template, data_batch, source_data)

            assert is_valid is True
            mock_validate.assert_called_once()
            call_args = mock_validate.call_args
            assert call_args.kwargs["source_category"] == "test_category"
            assert call_args.kwargs["source_template"] == "test_template"
            assert call_args.kwargs["source_data"] == source_data

    def test_build_context_default(self):
        """Test default build_context implementation."""
        generator = ConcreteGenerator(
            models=self.models,
            validation_pct=1.0,
            target_count=1,
            save_item=self.save_item,
            metrics=self.metrics,
        )
        template = TemplateConfig("test_template", "Test instruction")
        data_batch = {"id": 1}

        context = generator.build_context(template, data_batch)

        assert "Category: test_category" in context
        assert "Template: test_template" in context

    def test_get_source_data_default(self):
        """Test default get_source_data implementation."""
        generator = ConcreteGenerator(
            models=self.models,
            validation_pct=1.0,
            target_count=1,
            save_item=self.save_item,
            metrics=self.metrics,
        )
        data_batch = {"id": 1, "name": "Test"}

        source_data = generator.get_source_data(data_batch)

        assert source_data == [data_batch]

    def test_get_source_data_none(self):
        """Test get_source_data with None input."""
        generator = ConcreteGenerator(
            models=self.models,
            validation_pct=1.0,
            target_count=1,
            save_item=self.save_item,
            metrics=self.metrics,
        )

        source_data = generator.get_source_data(None)

        assert source_data == []


class TestParseGenerationResponse:
    """Tests for JSON response parsing."""

    def setup_method(self):
        """Set up test fixtures."""
        self.models = {
            ModelType.GENERATION: MockModel("gen-model", ModelType.GENERATION),
            ModelType.VALIDATION: MockModel("val-model", ModelType.VALIDATION),
        }
        self.save_item = Mock()
        self.metrics = Mock()
        self.metrics.generator_name = "unknown"
        self.metrics.generation_model = "unknown"
        self.metrics.validation_model = "unknown"
        self.metrics.run_id = "test-run-id"
        self.metrics.flush = Mock()
        self.metrics.print_rolling_summary = Mock()
        self.metrics.record_candidate = Mock()
        self.metrics.record_validation_attempt = Mock()
        self.metrics.record_skip = Mock()
        self.metrics.record_first_attempt_pass = Mock()
        self.metrics.record_pass_after_fix = Mock()
        self.metrics.record_failed_first_attempt = Mock()
        self.metrics.record_failed_after_fixes = Mock()
        self.metrics.record_fix_attempt = Mock()

    def test_parse_valid_json_array(self):
        """Test parsing valid JSON array response."""
        generator = ConcreteGenerator(
            models=self.models,
            validation_pct=1.0,
            target_count=1,
            save_item=self.save_item,
            metrics=self.metrics,
        )

        response = json.dumps([
            {"question": "Q1?", "answer": "A1"},
            {"question": "Q2?", "answer": "A2"},
        ])

        qa_pairs = generator._parse_generation_response(response)

        assert len(qa_pairs) == 2
        assert qa_pairs[0].question == "Q1?"
        assert qa_pairs[0].answer == "A1"
        assert qa_pairs[1].question == "Q2?"
        assert qa_pairs[1].answer == "A2"

    def test_parse_json_with_markdown_fences(self):
        """Test parsing JSON wrapped in markdown code fences."""
        generator = ConcreteGenerator(
            models=self.models,
            validation_pct=1.0,
            target_count=1,
            save_item=self.save_item,
            metrics=self.metrics,
        )

        response = """```json
[
    {"question": "Q1?", "answer": "A1"}
]
```"""

        qa_pairs = generator._parse_generation_response(response)

        assert len(qa_pairs) == 1
        assert qa_pairs[0].question == "Q1?"
        assert qa_pairs[0].answer == "A1"

    def test_parse_json_with_extra_text(self):
        """Test parsing JSON embedded in extra text."""
        generator = ConcreteGenerator(
            models=self.models,
            validation_pct=1.0,
            target_count=1,
            save_item=self.save_item,
            metrics=self.metrics,
        )

        response = """Here is the response:
[
    {"question": "Q1?", "answer": "A1"}
]
End of response."""

        qa_pairs = generator._parse_generation_response(response)

        assert len(qa_pairs) == 1
        assert qa_pairs[0].question == "Q1?"
        assert qa_pairs[0].answer == "A1"

    def test_parse_invalid_json_raises(self):
        """Test that invalid JSON raises JSONDecodeError."""
        generator = ConcreteGenerator(
            models=self.models,
            validation_pct=1.0,
            target_count=1,
            save_item=self.save_item,
            metrics=self.metrics,
        )

        response = "not valid json at all"

        with pytest.raises(json.JSONDecodeError):
            generator._parse_generation_response(response)


class TestProperties:
    """Tests for property accessors."""

    def setup_method(self):
        """Set up test fixtures."""
        self.models = {
            ModelType.GENERATION: MockModel("gen-model", ModelType.GENERATION),
            ModelType.VALIDATION: MockModel("val-model", ModelType.VALIDATION),
        }
        self.save_item = Mock()
        self.metrics = Mock()
        self.metrics.generator_name = "unknown"
        self.metrics.generation_model = "unknown"
        self.metrics.validation_model = "unknown"
        self.metrics.run_id = "test-run-id"
        self.metrics.flush = Mock()
        self.metrics.print_rolling_summary = Mock()
        self.metrics.record_candidate = Mock()
        self.metrics.record_validation_attempt = Mock()
        self.metrics.record_skip = Mock()
        self.metrics.record_first_attempt_pass = Mock()
        self.metrics.record_pass_after_fix = Mock()
        self.metrics.record_failed_first_attempt = Mock()
        self.metrics.record_failed_after_fixes = Mock()
        self.metrics.record_fix_attempt = Mock()

    def test_generation_model_property(self):
        """Test generation_model property returns correct model."""
        generator = ConcreteGenerator(
            models=self.models,
            validation_pct=1.0,
            target_count=1,
            save_item=self.save_item,
            metrics=self.metrics,
        )

        assert generator.generation_model == self.models[ModelType.GENERATION]

    def test_validation_model_property(self):
        """Test validation_model property returns correct model."""
        generator = ConcreteGenerator(
            models=self.models,
            validation_pct=1.0,
            target_count=1,
            save_item=self.save_item,
            metrics=self.metrics,
        )

        assert generator.validation_model == self.models[ModelType.VALIDATION]

    def test_query_model_property(self):
        """Test query_model property getter/setter."""
        generator = ConcreteGenerator(
            models=self.models,
            validation_pct=1.0,
            target_count=1,
            save_item=self.save_item,
            metrics=self.metrics,
        )

        custom_query_model = MockQueryModel()
        generator.query_model = custom_query_model

        assert generator.query_model == custom_query_model


if __name__ == "__main__":
    pytest.main([__file__, "-v"])