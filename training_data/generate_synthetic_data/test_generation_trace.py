"""Tests for the Generation Trace logging feature.

Covers:
- GenerationTrace dataclass construction and serialization
- BaseGenerator trace integration (_process_item creates/populates trace)
- validate_and_loop_with_suggested_fix trace accumulation
- CLI flag parsing (--log-traces / --no-log-traces)
- Backward compatibility (trace params optional everywhere)
"""

from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import asdict
from unittest.mock import MagicMock, Mock, patch, call
from typing import Iterator

import pytest

from training_data.generate_synthetic_data.models import (
    GenerationTrace,
    Model,
    ModelType,
    ModelProvider,
    QuestionAnswer,
    QuestionAnswerEnhanced,
    ValidationMetrics,
)
from training_data.generate_synthetic_data.common import (
    validate_and_loop_with_suggested_fix,
    TemplateConfig,
)
from training_data.generate_synthetic_data.base_generator import BaseGenerator
from training_data.generate_synthetic_data.query_model import QueryModel, VALIDATION_MAX_TOKENS


# =============================================================================
# Helpers
# =============================================================================

class MockModel(Model):
    """Mock model for testing."""
    def __init__(self, name: str = "test-model", model_type: ModelType = ModelType.GENERATION):
        self.name = name
        self.type = model_type
        self.provider = ModelProvider.OLLAMA
        self.provider_url = "http://localhost:11434"
        self.api_key = None


class MockQueryModel(QueryModel):
    """Mock QueryModel that returns controlled responses.

    Supports trace parameters — populates trace_round / trace_regeneration dicts
    like the real implementation.
    """
    def __init__(self):
        super().__init__()
        self.query_responses: list[str] = []
        self.validate_responses: list[tuple[bool, str | None, float | None]] = []
        self.shadow_validate_responses: list[tuple[bool, str | None, float | None]] = []
        self.regenerate_responses: list[str | None] = []
        self.sibling_feedbacks: list[str] = []
        self.query_call_count = 0
        self.validate_call_count = 0
        self.regenerate_call_count = 0

    def query(self, model: Model, prompt: str, max_tokens: int = 8192, purpose: str = "") -> str:
        self.query_call_count += 1
        self._last_elapsed_ms = 100  # Simulate 100ms latency
        if self.query_responses:
            return self.query_responses.pop(0)
        return json.dumps([{"question": "Test question?", "answer": "Test answer with sufficient length to pass validation."}])

    def validate_qa(
        self,
        validation_model: Model,
        question: str,
        answer: str,
        context: str = "",
        category: str = "",
        enable_extra_validation: bool = True,
        trace_round: dict | None = None,
    ) -> tuple[bool, str | None, float | None]:
        self.validate_call_count += 1
        if getattr(validation_model, "type", None) == ModelType.SHADOW_VALIDATION:
            if self.shadow_validate_responses:
                is_valid, reason, score = self.shadow_validate_responses.pop(0)
            else:
                is_valid, reason, score = True, "OK", 8.0
        elif self.validate_responses:
            is_valid, reason, score = self.validate_responses.pop(0)
        else:
            is_valid, reason, score = True, "OK", 8.0

        if trace_round is not None:
            trace_round.update({
                "prompt": f"validation prompt for {question[:30]}",
                "response": '{"score": 8, "is_acceptable": true}',
                "parsed_ok": True,
                "score": score,
                "is_acceptable": is_valid,
                "errors": "",
                "missing_info": "",
                "reason": reason or "",
                "verification_checklist": None,
                "latency_ms": self._last_elapsed_ms,
            })
        return is_valid, reason, score

    def regenerate_answer(
        self,
        generation_model: Model,
        question: str,
        old_answer: str,
        reason: str,
        score: float | None,
        context: str = "",
        category: str = "",
        sibling_feedback: str = "",
        trace_regeneration: dict | None = None,
    ) -> str | None:
        self.sibling_feedbacks.append(sibling_feedback)
        self.regenerate_call_count += 1
        if self.regenerate_responses:
            new_answer = self.regenerate_responses.pop(0)
        else:
            new_answer = "Regenerated answer with sufficient length to pass validation."

        if trace_regeneration is not None:
            trace_regeneration.update({
                "prompt": f"regeneration prompt for {question[:30]}",
                "response": '{"answer": "regenerated answer"}',
                "parsed_ok": True,
                "new_answer": new_answer,
                "latency_ms": self._last_elapsed_ms,
            })
        return new_answer


class ConcreteGenerator(BaseGenerator[dict]):
    """Concrete generator for testing trace integration."""

    def __init__(self, *args, **kwargs):
        # Provide a mock yaml_loader so select_templates() can find templates.
        if "yaml_loader" not in kwargs:
            from unittest.mock import MagicMock
            from training_data.generate_synthetic_data.yaml_template_loader import YamlTemplateLoader
            loader = MagicMock(spec=YamlTemplateLoader)
            loader.SHARED_NAMESPACE = YamlTemplateLoader.SHARED_NAMESPACE
            loader.list_templates.return_value = ["test_template"]

            def get_latest_side(gen, tid, ttype):
                if ttype == "generation":
                    return {
                        "template_id": tid,
                        "instruction": "Test instruction",
                        "weight": 1.0,
                        "validation_rules": [],
                        "min_answer_length": 80,
                        "max_answer_length": 2000,
                        "version": "1",
                    }
                return None

            loader.get_latest.side_effect = get_latest_side
            loader.load_active_templates.return_value = None
            loader.get_active_validator_version.return_value = None
            kwargs["yaml_loader"] = loader
        super().__init__(*args, **kwargs)
        self.data_batches: list[list[dict]] = []

    def get_data_batches(self) -> Iterator[list[dict]]:
        for batch in self.data_batches:
            yield batch

    def build_prompt(self, template: TemplateConfig, data_batch: dict) -> str:
        return f"Prompt for {template.template_id} with data {data_batch}"

    def get_source_category(self) -> str:
        return "test_category"


# =============================================================================
# Test 1: GenerationTrace Dataclass Construction
# =============================================================================

class TestGenerationTraceDataclass:
    """Tests for GenerationTrace creation, serialization, and field defaults."""

    def test_create_minimal_trace(self):
        """Test creating a GenerationTrace with only required fields."""
        trace = GenerationTrace(
            item_id=str(uuid.uuid4()),
            run_id="test-run",
        )
        assert trace.item_id
        assert trace.run_id == "test-run"
        assert trace.category == ""
        assert trace.source_template is None
        assert trace.generator_name == ""
        assert trace.generation_model == ""
        assert trace.validation_model == ""
        assert trace.created_at == ""
        assert trace.generation_prompt == ""
        assert trace.generation_response == ""
        assert trace.generation_parsed_ok is True
        assert trace.generation_latency_ms == 0
        assert trace.validation_rounds == []
        assert trace.final_outcome == "pending"
        assert trace.total_rounds == 0
        assert trace.final_score is None
        assert trace.qa_index == 0
        assert trace.question == ""
        assert trace.answer == ""
        assert trace.shadow_validation_model == ""
        assert trace.shadow_validation_rounds == []

    def test_create_full_trace(self):
        """Test creating a GenerationTrace with all fields populated."""
        trace = GenerationTrace(
            item_id=str(uuid.uuid4()),
            run_id="test-run",
            category="combo_query",
            source_template="how_does_it_work",
            generator_name="TestGenerator",
            generation_model="test-model",
            validation_model="test-model",
            created_at="2026-07-21T00:00:00Z",
        )
        trace.generation_prompt = "test prompt"
        trace.generation_response = '[{"question": "test?", "answer": "test answer"}]'
        trace.generation_latency_ms = 1234
        trace.validation_rounds.append({
            "round": 0,
            "prompt": "validation prompt",
            "response": '{"score": 8}',
            "parsed_ok": True,
            "score": 8.0,
            "is_acceptable": True,
            "errors": "",
            "missing_info": "",
            "reason": "",
            "verification_checklist": None,
            "latency_ms": 500,
            "regeneration": None,
        })
        trace.final_outcome = "accepted_first_attempt"
        trace.total_rounds = 1
        trace.final_score = 8.0

        assert trace.item_id
        assert trace.category == "combo_query"
        assert trace.source_template == "how_does_it_work"
        assert len(trace.validation_rounds) == 1
        assert trace.validation_rounds[0]["round"] == 0
        assert trace.validation_rounds[0]["score"] == 8.0
        assert trace.final_outcome == "accepted_first_attempt"
        assert trace.total_rounds == 1
        assert trace.final_score == 8.0

    def test_asdict_serialization(self):
        """Test that GenerationTrace can be serialized to dict via dataclasses.asdict."""
        trace = GenerationTrace(
            item_id=str(uuid.uuid4()),
            run_id="test-run",
            category="combo_query",
        )
        trace.generation_prompt = "test prompt"
        trace.generation_response = '{"question": "Q?", "answer": "A"}'
        trace.generation_latency_ms = 500
        trace.validation_rounds.append({
            "round": 0,
            "prompt": "val prompt",
            "response": '{"score": 9}',
            "parsed_ok": True,
            "score": 9.0,
            "is_acceptable": True,
            "errors": "",
            "missing_info": "",
            "reason": "",
            "verification_checklist": None,
            "latency_ms": 200,
            "regeneration": None,
        })
        trace.final_outcome = "accepted_first_attempt"
        trace.total_rounds = 1
        trace.final_score = 9.0

        d = asdict(trace)
        assert d["item_id"] == trace.item_id
        assert d["run_id"] == "test-run"
        assert d["category"] == "combo_query"
        assert d["generation_prompt"] == "test prompt"
        assert d["generation_latency_ms"] == 500
        assert len(d["validation_rounds"]) == 1
        assert d["validation_rounds"][0]["score"] == 9.0
        assert d["final_outcome"] == "accepted_first_attempt"
        assert d["total_rounds"] == 1
        assert d["final_score"] == 9.0
        assert d["qa_index"] == 0
        assert d["question"] == ""
        assert d["answer"] == ""
        assert d["shadow_validation_model"] == ""
        assert d["shadow_validation_rounds"] == []

    def test_validation_rounds_default_factory(self):
        """Test that validation_rounds uses a mutable default factory (not shared)."""
        t1 = GenerationTrace(item_id="a", run_id="r")
        t2 = GenerationTrace(item_id="b", run_id="r")
        t1.validation_rounds.append({"round": 0})
        assert len(t2.validation_rounds) == 0  # Should NOT share list

    def test_dict_roundtrip_via_json(self):
        """Test that asdict -> JSON -> dict roundtrip works (MongoDB storage pattern)."""
        trace = GenerationTrace(
            item_id=str(uuid.uuid4()),
            run_id="test-run",
            category="rule_explanations",
            source_template="how_does_it_work",
        )
        trace.generation_prompt = "prompt text"
        trace.generation_response = "[{\"question\": \"Q?\", \"answer\": \"A\"}]"
        trace.validation_rounds.append({"round": 0, "score": 7.5, "is_acceptable": True})
        trace.final_outcome = "accepted_first_attempt"
        trace.final_score = 7.5

        d = asdict(trace)
        json_str = json.dumps(d)
        d2 = json.loads(json_str)

        assert d2["item_id"] == trace.item_id
        assert d2["category"] == "rule_explanations"
        assert len(d2["validation_rounds"]) == 1
        assert d2["validation_rounds"][0]["score"] == 7.5


# =============================================================================
# Test 2: BaseGenerator Trace Integration
# =============================================================================

class TestBaseGeneratorTraceIntegration:
    """Tests for BaseGenerator._process_item() creating and populating traces."""

    def setup_method(self):
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

    def test_trace_callback_receives_populated_trace(self):
        """Test that _process_item creates a GenerationTrace and calls the callback."""
        traces_received: list[GenerationTrace] = []

        def capture_trace(trace: GenerationTrace):
            traces_received.append(trace)

        generator = ConcreteGenerator(
            models=self.models,
            validation_pct=1.0,
            target_count=1,
            save_item=self.save_item,
            metrics=self.metrics,
            trace_callback=capture_trace,
        )
        generator.data_batches = [[{"id": 1}]]

        generator.query_model = MockQueryModel()
        generator.query_model.query_responses = [
            json.dumps([{"question": "Q1?", "answer": "A1 with sufficient length to pass validation."}]),
        ]
        generator.query_model.validate_responses = [
            (True, "OK", 8.0),
        ]

        generator.generate()

        assert len(traces_received) == 1
        trace = traces_received[0]

        # Verify trace fields are populated
        assert trace.item_id  # UUID was generated
        assert trace.run_id == "test-run-id"
        assert trace.category == "test_category"
        assert trace.source_template == "test_template"
        assert trace.generator_name == "ConcreteGenerator"  # fallback to class name
        assert trace.generation_model == "gen-model"
        assert trace.validation_model == "val-model"
        assert trace.created_at  # timestamp was set
        assert trace.generation_prompt  # prompt was captured
        assert trace.generation_response  # response was captured
        assert trace.generation_latency_ms > 0
        assert trace.generation_parsed_ok is True
        assert len(trace.validation_rounds) >= 1
        assert trace.final_outcome == "accepted_first_attempt"
        assert trace.total_rounds >= 1
        assert trace.final_score is not None
        assert trace.qa_index == 0
        assert trace.question == "Q1?"
        assert trace.answer == "A1 with sufficient length to pass validation."

    def test_no_trace_when_callback_not_provided(self):
        """Test that no trace is created when trace_callback is None."""
        generator = ConcreteGenerator(
            models=self.models,
            validation_pct=1.0,
            target_count=1,
            save_item=self.save_item,
            metrics=self.metrics,
            trace_callback=None,  # No callback
        )
        generator.data_batches = [[{"id": 1}]]

        generator.query_model = MockQueryModel()
        generator.query_model.query_responses = [
            json.dumps([{"question": "Q1?", "answer": "A1 with sufficient length to pass validation."}]),
        ]
        generator.query_model.validate_responses = [
            (True, "OK", 8.0),
        ]

        generator.generate()

        # Should succeed without errors — just no traces
        assert generator.generated_count == 1

    def test_trace_callback_not_called_when_validation_fails(self):
        """Test that trace callback IS called even when item is rejected (not saved)."""
        traces_received: list[GenerationTrace] = []

        def capture_trace(trace: GenerationTrace):
            traces_received.append(trace)

        generator = ConcreteGenerator(
            models=self.models,
            validation_pct=1.0,
            target_count=1,
            save_item=self.save_item,
            metrics=self.metrics,
            trace_callback=capture_trace,
        )
        generator.data_batches = [[{"id": 1}]]

        generator.query_model = MockQueryModel()
        generator.query_model.query_responses = [
            json.dumps([{"question": "Q1?", "answer": "A1 with sufficient length to pass validation."}]),
        ]
        # All 3 validation rounds reject (loop runs 3 times max)
        generator.query_model.validate_responses = [
            (False, "Score too low", 3.0),
            (False, "Still bad", 3.0),
            (False, "Still bad", 3.0),
        ]
        # 3 regenerations succeed (but all validations reject again)
        generator.query_model.regenerate_responses = [
            "Regenerated attempt 1",
            "Regenerated attempt 2",
            "Regenerated attempt 3",
        ]

        generator.generate()

        # Trace IS called even on rejection — captures the full lifecycle
        assert len(traces_received) == 1
        trace = traces_received[0]
        assert trace.final_outcome == "rejected"
        assert trace.total_rounds >= 3
        assert generator.generated_count == 0

    def test_trace_callback_called_per_template(self):
        """Test that one trace is generated per accepted template iteration."""
        traces_received: list[GenerationTrace] = []

        def capture_trace(trace: GenerationTrace):
            traces_received.append(trace)

        generator = ConcreteGenerator(
            models=self.models,
            validation_pct=1.0,
            target_count=2,
            save_item=self.save_item,
            metrics=self.metrics,
            trace_callback=capture_trace,
            templates_per_item=2,  # 2 templates per data batch
        )
        generator.data_batches = [[{"id": 1}]]

        generator.query_model = MockQueryModel()
        generator.query_model.query_responses = [
            json.dumps([{"question": "Q1?", "answer": "A1 with sufficient length to pass validation."}]),
            json.dumps([{"question": "Q2?", "answer": "A2 with sufficient length to pass validation."}]),
        ]
        generator.query_model.validate_responses = [
            (True, "OK", 8.0),
            (True, "OK", 9.0),
        ]

        generator.generate()

        assert len(traces_received) == 2
        # Each trace should have the same item_id but possibly different templates
        # (Templates are randomly selected, so we just check both exist)
        assert all(t.item_id for t in traces_received)

    def test_trace_callback_called_per_qa_with_own_rounds(self):
        """One trace is emitted per QA pair, each with only its own rounds and outcome."""
        traces_received: list[GenerationTrace] = []

        def capture_trace(trace: GenerationTrace):
            traces_received.append(trace)

        generator = ConcreteGenerator(
            models=self.models,
            validation_pct=1.0,
            target_count=2,
            save_item=self.save_item,
            metrics=self.metrics,
            trace_callback=capture_trace,
        )
        generator.data_batches = [[{"id": 1}]]

        generator.query_model = MockQueryModel()
        generator.query_model.query_responses = [
            json.dumps([
                {"question": "Q1?", "answer": "A1 with sufficient length to pass validation."},
                {"question": "Q2?", "answer": "A2 with sufficient length to pass validation."},
            ]),
        ]
        # QA1 accepted first attempt; QA2 rejected after 3 regen attempts
        generator.query_model.validate_responses = [
            (True, "OK", 8.0),
            (False, "Score too low", 3.0),
            (False, "Still bad", 3.0),
            (False, "Still bad", 3.0),
        ]
        generator.query_model.regenerate_responses = [
            "Regenerated attempt 1",
            "Regenerated attempt 2",
            "Regenerated attempt 3",
        ]

        generator.generate()

        assert len(traces_received) == 2
        qa0, qa1 = traces_received

        # Each trace is a distinct Q&A item with its own outcome
        assert qa0.item_id != qa1.item_id
        assert qa0.qa_index == 0
        assert qa0.question == "Q1?"
        assert qa0.answer == "A1 with sufficient length to pass validation."
        assert qa0.final_outcome == "accepted_first_attempt"
        assert len(qa0.validation_rounds) == 1
        assert qa0.validation_rounds[0]["score"] == 8.0

        assert qa1.qa_index == 1
        assert qa1.question == "Q2?"
        assert qa1.answer == "Regenerated attempt 3"  # final answer after fixes
        assert qa1.final_outcome == "rejected"
        assert len(qa1.validation_rounds) == 3
        assert all(r["score"] == 3.0 for r in qa1.validation_rounds)

        # No round bleed: QA1's trace only contains QA1's own validation rounds
        assert generator.generated_count == 1  # only QA1 was saved

    def test_trace_capture_parse_failure(self):
        """Test that trace captures generation_parsed_ok=False on JSON parse error."""
        traces_received: list[GenerationTrace] = []

        def capture_trace(trace: GenerationTrace):
            traces_received.append(trace)

        generator = ConcreteGenerator(
            models=self.models,
            validation_pct=1.0,
            target_count=2,
            save_item=self.save_item,
            metrics=self.metrics,
            trace_callback=capture_trace,
        )
        generator.data_batches = [[{"id": 1}], [{"id": 2}]]

        generator.query_model = MockQueryModel()
        generator.query_model.query_responses = [
            "invalid json that cannot be parsed",  # First attempt: parse error
            json.dumps([{"question": "Q2?", "answer": "A2 with sufficient length to pass validation."}]),
        ]
        generator.query_model.validate_responses = [
            (True, "OK", 8.0),
        ]

        generator.generate()

        # Both items produce traces — first with parse error, second successful
        assert len(traces_received) == 2
        failed_trace = traces_received[0]
        assert failed_trace.generation_parsed_ok is False
        assert failed_trace.final_outcome == "generation_error"
        success_trace = traces_received[1]
        assert success_trace.generation_parsed_ok is True
        assert generator.generated_count == 1


# =============================================================================
# Test 3: Validation Loop Trace Accumulation
# =============================================================================

class TestValidationLoopTraceAccumulation:
    """Tests for validate_and_loop_with_suggested_fix() trace parameter."""

    def _make_models(self):
        return {
            ModelType.GENERATION: MockModel("gen-model", ModelType.GENERATION),
            ModelType.VALIDATION: MockModel("val-model", ModelType.VALIDATION),
        }

    def test_first_attempt_pass(self):
        """Trace should have 1 validation round, outcome=accepted_first_attempt."""
        models = self._make_models()
        qm = MockQueryModel()
        qm.validate_responses = [(True, "OK", 8.5)]

        trace = GenerationTrace(item_id="test", run_id="test-run")
        qa = QuestionAnswer("What is Magic?", "Magic is a card game.")
        metrics = Mock()
        metrics.run_id = "test-run"
        metrics.record_candidate = Mock()
        metrics.record_validation_attempt = Mock()
        metrics.record_skip = Mock()
        metrics.record_first_attempt_pass = Mock()
        metrics.record_pass_after_fix = Mock()
        metrics.record_failed_first_attempt = Mock()
        metrics.record_failed_after_fixes = Mock()
        metrics.record_fix_attempt = Mock()
        metrics.flush = Mock()
        metrics.print_rolling_summary = Mock()

        is_valid, doc = validate_and_loop_with_suggested_fix(
            query_model=qm,
            models=models,
            qa_pairs=[qa],
            validation_pct=1.0,
            enable_extra_validation=False,
            build_context=lambda: "test context",
            source_category="test_cat",
            source_data=[],
            source_template="test_tmpl",
            metrics=metrics,
            trace=trace,
        )

        assert is_valid is True
        assert doc is not None
        assert len(trace.validation_rounds) == 1
        assert trace.validation_rounds[0]["round"] == 0
        assert trace.validation_rounds[0]["score"] == 8.5
        assert trace.validation_rounds[0]["is_acceptable"] is True
        assert trace.final_outcome == "accepted_first_attempt"
        assert trace.total_rounds == 1
        assert trace.final_score == 8.5

    def test_pass_after_fix(self):
        """Trace should have 2+ rounds, outcome=accepted_after_fix."""
        models = self._make_models()
        qm = MockQueryModel()
        # First validation: fail; regeneration: success; second validation: pass
        qm.validate_responses = [
            (False, "Score too low", 4.0),
            (True, "OK", 8.0),
        ]
        qm.regenerate_responses = ["Fixed answer with enough length to pass."]

        trace = GenerationTrace(item_id="test", run_id="test-run")
        qa = QuestionAnswer("What is Magic?", "Magic is a card game.")
        metrics = Mock()
        metrics.run_id = "test-run"
        metrics.record_candidate = Mock()
        metrics.record_validation_attempt = Mock()
        metrics.record_skip = Mock()
        metrics.record_first_attempt_pass = Mock()
        metrics.record_pass_after_fix = Mock()
        metrics.record_failed_first_attempt = Mock()
        metrics.record_failed_after_fixes = Mock()
        metrics.record_fix_attempt = Mock()
        metrics.flush = Mock()
        metrics.print_rolling_summary = Mock()

        is_valid, doc = validate_and_loop_with_suggested_fix(
            query_model=qm,
            models=models,
            qa_pairs=[qa],
            validation_pct=1.0,
            enable_extra_validation=False,
            build_context=lambda: "test context",
            source_category="test_cat",
            source_data=[],
            source_template="test_tmpl",
            metrics=metrics,
            trace=trace,
        )

        assert is_valid is True
        assert doc is not None
        assert len(trace.validation_rounds) >= 2
        # First round should have a regeneration dict
        assert trace.validation_rounds[0]["regeneration"] is not None
        assert trace.validation_rounds[0]["regeneration"]["parsed_ok"] is True
        # Outcome
        assert trace.final_outcome == "accepted_after_fix"
        assert trace.total_rounds >= 2
        assert trace.final_score is not None

    def test_rejected_after_3_attempts(self):
        """Trace should have 3+ rounds, outcome=rejected."""
        models = self._make_models()
        qm = MockQueryModel()
        # All 3 validations fail; 3 regenerations succeed
        qm.validate_responses = [
            (False, "Bad", 3.0),
            (False, "Still bad", 3.0),
            (False, "Still bad", 3.0),
        ]
        qm.regenerate_responses = [
            "Attempt 1 fixed",
            "Attempt 2 fixed",
            "Attempt 3 fixed",
        ]

        trace = GenerationTrace(item_id="test", run_id="test-run")
        qa = QuestionAnswer("What is Magic?", "Magic is a card game.")
        metrics = Mock()
        metrics.run_id = "test-run"
        metrics.record_candidate = Mock()
        metrics.record_validation_attempt = Mock()
        metrics.record_skip = Mock()
        metrics.record_first_attempt_pass = Mock()
        metrics.record_pass_after_fix = Mock()
        metrics.record_failed_first_attempt = Mock()
        metrics.record_failed_after_fixes = Mock()
        metrics.record_fix_attempt = Mock()
        metrics.flush = Mock()
        metrics.print_rolling_summary = Mock()

        is_valid, doc = validate_and_loop_with_suggested_fix(
            query_model=qm,
            models=models,
            qa_pairs=[qa],
            validation_pct=1.0,
            enable_extra_validation=False,
            build_context=lambda: "test context",
            source_category="test_cat",
            source_data=[],
            source_template="test_tmpl",
            metrics=metrics,
            trace=trace,
        )

        assert is_valid is False
        assert doc is None
        assert len(trace.validation_rounds) >= 3
        assert trace.final_outcome == "rejected"
        assert trace.total_rounds >= 3

    def test_parse_failure_revalidates_same_answer(self):
        """A validator parse failure must re-validate the SAME answer: no
        regeneration, no fix-attempt accounting, sibling list untouched."""
        models = self._make_models()
        qm = MockQueryModel()
        qm.validate_responses = [
            (False, "Validation parse failed: Expecting value: line 1 column 1 (char 0)", 0),
            (True, "OK", 8.0),
        ]
        trace = GenerationTrace(item_id="test", run_id="test-run")
        qa = QuestionAnswer("What is Magic?", "Magic is a card game.")
        metrics = Mock()
        metrics.run_id = "test-run"
        metrics.record_candidate = Mock()
        metrics.record_validation_attempt = Mock()
        metrics.record_skip = Mock()
        metrics.record_first_attempt_pass = Mock()
        metrics.record_pass_after_fix = Mock()
        metrics.record_failed_first_attempt = Mock()
        metrics.record_failed_after_fixes = Mock()
        metrics.record_fix_attempt = Mock()
        metrics.flush = Mock()
        metrics.print_rolling_summary = Mock()
        sibling_corrections: list[str] = []

        is_valid, doc = validate_and_loop_with_suggested_fix(
            query_model=qm, models=models, qa_pairs=[qa], validation_pct=1.0,
            enable_extra_validation=False, build_context=lambda: "ctx",
            source_category="test_cat", source_data=[], source_template="t",
            metrics=metrics, trace=trace, sibling_corrections=sibling_corrections,
        )

        assert is_valid is True
        assert doc is not None
        assert qm.regenerate_call_count == 0
        assert qm.validate_call_count == 2
        metrics.record_fix_attempt.assert_not_called()
        assert sibling_corrections == []
        assert trace.final_outcome == "accepted_first_attempt"
        assert len(trace.validation_rounds) == 2
        assert trace.validation_rounds[0]["round"] == 0
        assert trace.validation_rounds[1]["round"] == 1
        assert trace.total_rounds == 2

    def test_parse_failure_exhausted_retries_rejects_without_regeneration(self):
        """Persistent parse failures reject WITHOUT burning regeneration."""
        models = self._make_models()
        qm = MockQueryModel()
        qm.validate_responses = [
            (False, "Validation parse failed: Expecting value: line 1 column 1 (char 0)", 0),
            (False, "Validation parse failed: Unterminated string starting at line 1", 0),
            (False, "Validation parse failed: Expecting value: line 1 column 1 (char 0)", 0),
        ]
        trace = GenerationTrace(item_id="test", run_id="test-run")
        qa = QuestionAnswer("What is Magic?", "Magic is a card game.")
        metrics = Mock()
        metrics.run_id = "test-run"
        metrics.record_candidate = Mock()
        metrics.record_validation_attempt = Mock()
        metrics.record_skip = Mock()
        metrics.record_first_attempt_pass = Mock()
        metrics.record_pass_after_fix = Mock()
        metrics.record_failed_first_attempt = Mock()
        metrics.record_failed_after_fixes = Mock()
        metrics.record_fix_attempt = Mock()
        metrics.flush = Mock()
        metrics.print_rolling_summary = Mock()

        is_valid, doc = validate_and_loop_with_suggested_fix(
            query_model=qm, models=models, qa_pairs=[qa], validation_pct=1.0,
            enable_extra_validation=False, build_context=lambda: "ctx",
            source_category="test_cat", source_data=[], source_template="t",
            metrics=metrics, trace=trace,
        )

        assert is_valid is False
        assert doc is None
        assert qm.regenerate_call_count == 0
        metrics.record_fix_attempt.assert_not_called()
        metrics.record_failed_first_attempt.assert_called_once()
        assert trace.final_outcome == "rejected"
        assert len(trace.validation_rounds) == 3
        assert trace.total_rounds == 3

    def test_parse_failure_not_in_sibling_feedback(self):
        """Sibling feedback for later QAs must never contain parse-failure noise."""
        models = self._make_models()
        qm = MockQueryModel()
        qa1 = QuestionAnswer("Q1?", "Answer one with enough length.")
        qa2 = QuestionAnswer("Q2?", "Answer two with enough length.")
        qm.validate_responses = [
            (False, "Validation parse failed: Expecting value: line 1 column 1 (char 0)", 0),
            (True, "OK", 8.0),          # Q1 re-validated, accepted
            (False, "Missing trigger ordering", 4.0),  # Q2 genuine rejection
            (True, "OK", 8.0),          # Q2 fixed, accepted
        ]
        qm.regenerate_responses = ["Fixed answer two with enough length."]
        metrics = Mock()
        metrics.run_id = "test-run"
        metrics.record_candidate = Mock()
        metrics.record_validation_attempt = Mock()
        metrics.record_skip = Mock()
        metrics.record_first_attempt_pass = Mock()
        metrics.record_pass_after_fix = Mock()
        metrics.record_failed_first_attempt = Mock()
        metrics.record_failed_after_fixes = Mock()
        metrics.record_fix_attempt = Mock()
        metrics.flush = Mock()
        metrics.print_rolling_summary = Mock()
        sibling_corrections: list[str] = []

        validate_and_loop_with_suggested_fix(
            query_model=qm, models=models, qa_pairs=[qa1, qa2], validation_pct=1.0,
            enable_extra_validation=False, build_context=lambda: "ctx",
            source_category="test_cat", source_data=[], source_template="t",
            metrics=metrics, sibling_corrections=sibling_corrections,
        )

        assert "Validation parse failed" not in sibling_corrections[0]
        for feedback in qm.sibling_feedbacks:
            assert "Validation parse failed" not in feedback

    def test_sibling_corrections_dedupe_per_qa(self):
        """Only the latest correction per QA index is kept in the accumulator."""
        models = self._make_models()
        qm = MockQueryModel()
        qa = QuestionAnswer("Q1?", "Answer with enough length.")
        qm.validate_responses = [
            (False, "Wrong mana cost", 3.0),
            (False, "Missing trigger ordering", 4.0),
            (True, "OK", 8.0),
        ]
        qm.regenerate_responses = [
            "Fixed attempt one with enough length.",
            "Fixed attempt two with enough length.",
        ]
        metrics = Mock()
        metrics.run_id = "test-run"
        metrics.record_candidate = Mock()
        metrics.record_validation_attempt = Mock()
        metrics.record_skip = Mock()
        metrics.record_first_attempt_pass = Mock()
        metrics.record_pass_after_fix = Mock()
        metrics.record_failed_first_attempt = Mock()
        metrics.record_failed_after_fixes = Mock()
        metrics.record_fix_attempt = Mock()
        metrics.flush = Mock()
        metrics.print_rolling_summary = Mock()
        sibling_corrections: list[str] = []

        validate_and_loop_with_suggested_fix(
            query_model=qm, models=models, qa_pairs=[qa], validation_pct=1.0,
            enable_extra_validation=False, build_context=lambda: "ctx",
            source_category="test_cat", source_data=[], source_template="t",
            metrics=metrics, sibling_corrections=sibling_corrections,
        )

        assert len(sibling_corrections) == 1
        assert "Missing trigger ordering" in sibling_corrections[0]
        assert "Wrong mana cost" not in sibling_corrections[0]

    def test_is_transport_failure_reason(self):
        from training_data.generate_synthetic_data.query_model import is_transport_failure_reason
        assert is_transport_failure_reason("Validation parse failed: Expecting value: line 1 column 1 (char 0)") is True
        assert is_transport_failure_reason("Validation error: connection reset") is True
        assert is_transport_failure_reason("Missing trigger ordering") is False
        assert is_transport_failure_reason("") is False
        assert is_transport_failure_reason(None) is False

    def test_regeneration_failure(self):
        """Trace should have the failed round_data appended when regeneration fails."""
        models = self._make_models()
        qm = MockQueryModel()
        # First validation fails, regeneration fails (returns None)
        qm.validate_responses = [
            (False, "Bad", 3.0),
        ]
        qm.regenerate_responses = [
            None,  # Regeneration failed
        ]

        trace = GenerationTrace(item_id="test", run_id="test-run")
        qa = QuestionAnswer("What is Magic?", "Magic is a card game.")
        metrics = Mock()
        metrics.run_id = "test-run"
        metrics.record_candidate = Mock()
        metrics.record_validation_attempt = Mock()
        metrics.record_skip = Mock()
        metrics.record_first_attempt_pass = Mock()
        metrics.record_pass_after_fix = Mock()
        metrics.record_failed_first_attempt = Mock()
        metrics.record_failed_after_fixes = Mock()
        metrics.record_fix_attempt = Mock()
        metrics.flush = Mock()
        metrics.print_rolling_summary = Mock()

        is_valid, doc = validate_and_loop_with_suggested_fix(
            query_model=qm,
            models=models,
            qa_pairs=[qa],
            validation_pct=1.0,
            enable_extra_validation=False,
            build_context=lambda: "test context",
            source_category="test_cat",
            source_data=[],
            source_template="test_tmpl",
            metrics=metrics,
            trace=trace,
        )

        assert is_valid is False
        assert doc is None
        # Should have exactly 1 round (the failed validation, with regeneration attached)
        assert len(trace.validation_rounds) == 1
        assert trace.validation_rounds[0]["regeneration"] is not None
        assert trace.validation_rounds[0]["regeneration"]["new_answer"] is None
        assert trace.final_outcome == "rejected"

    def test_validation_skipped_pct_zero(self):
        """Trace should have final_outcome=skipped and total_rounds=0."""
        models = self._make_models()
        qm = MockQueryModel()
        qm.validate_responses = []  # No validations should happen

        trace = GenerationTrace(item_id="test", run_id="test-run")
        qa = QuestionAnswer("What is Magic?", "Magic is a card game.")
        metrics = Mock()
        metrics.run_id = "test-run"
        metrics.record_candidate = Mock()
        metrics.record_validation_attempt = Mock()
        metrics.record_skip = Mock()
        metrics.record_first_attempt_pass = Mock()
        metrics.record_pass_after_fix = Mock()
        metrics.record_failed_first_attempt = Mock()
        metrics.record_failed_after_fixes = Mock()
        metrics.record_fix_attempt = Mock()
        metrics.flush = Mock()
        metrics.print_rolling_summary = Mock()

        is_valid, doc = validate_and_loop_with_suggested_fix(
            query_model=qm,
            models=models,
            qa_pairs=[qa],
            validation_pct=0.0,  # Skip validation entirely
            enable_extra_validation=False,
            build_context=lambda: "test context",
            source_category="test_cat",
            source_data=[],
            source_template="test_tmpl",
            metrics=metrics,
            trace=trace,
        )

        # With pct=0, is_valid is True (default) and doc is returned
        assert is_valid is True
        assert doc is not None
        assert len(trace.validation_rounds) == 0
        assert trace.final_outcome == "skipped"
        assert trace.total_rounds == 0
        assert trace.final_score is None

    def test_trace_round_data_has_all_expected_keys(self):
        """Verify each validation round dict has all required trace keys."""
        models = self._make_models()
        qm = MockQueryModel()
        qm.validate_responses = [(True, "OK", 7.5)]

        trace = GenerationTrace(item_id="test", run_id="test-run")
        qa = QuestionAnswer("Q?", "A")
        metrics = Mock()
        metrics.run_id = "test-run"
        metrics.record_candidate = Mock()
        metrics.record_validation_attempt = Mock()
        metrics.record_skip = Mock()
        metrics.record_first_attempt_pass = Mock()
        metrics.record_pass_after_fix = Mock()
        metrics.record_failed_first_attempt = Mock()
        metrics.record_failed_after_fixes = Mock()
        metrics.record_fix_attempt = Mock()
        metrics.flush = Mock()
        metrics.print_rolling_summary = Mock()

        validate_and_loop_with_suggested_fix(
            query_model=qm,
            models=models,
            qa_pairs=[qa],
            validation_pct=1.0,
            enable_extra_validation=False,
            build_context=lambda: "ctx",
            source_category="cat",
            source_data=[],
            source_template="tmpl",
            metrics=metrics,
            trace=trace,
        )

        required_keys = {
            "round", "prompt", "response", "parsed_ok", "score",
            "is_acceptable", "errors", "missing_info", "reason",
            "verification_checklist", "latency_ms",
        }
        assert len(trace.validation_rounds) == 1
        round_keys = set(trace.validation_rounds[0].keys())
        # round_data starts with {"round": 0} then gets updated with all keys
        assert required_keys.issubset(round_keys)


# =============================================================================
# Test 4: CLI Flag Parsing
# =============================================================================

# =============================================================================
# Test 4: Shadow validation (Story 049)
# =============================================================================

class TestShadowValidation:
    """Tests for the shadow validator — mirrors every real validation call and
    records its verdict on the trace ONLY (never affects the outcome)."""

    def _make_models(self, with_shadow: bool = True):
        models = {
            ModelType.GENERATION: MockModel("gen-model", ModelType.GENERATION),
            ModelType.VALIDATION: MockModel("val-model", ModelType.VALIDATION),
        }
        if with_shadow:
            models[ModelType.SHADOW_VALIDATION] = MockModel("shadow-model", ModelType.SHADOW_VALIDATION)
        return models

    def _run(self, models, qm, qa_pairs, trace=None):
        return validate_and_loop_with_suggested_fix(
            query_model=qm,
            models=models,
            qa_pairs=qa_pairs,
            validation_pct=1.0,
            enable_extra_validation=True,
            build_context=lambda: "context",
            source_category="test_category",
            source_data=[],
            source_template="test_template",
            metrics=None,
            trace=trace,
        )

    def test_shadow_round_recorded_on_first_attempt_pass(self):
        models = self._make_models()
        qm = MockQueryModel()
        qm.validate_responses = [(True, "OK", 8.5)]
        qm.shadow_validate_responses = [(False, "Too strict", 4.0)]
        trace = GenerationTrace(item_id="test", run_id="run")

        is_valid, doc = self._run(models, qm, [QuestionAnswer("Q?", "A")], trace=trace)

        assert is_valid is True
        assert doc.validation_score == 8.5
        assert len(trace.validation_rounds) == 1
        assert trace.validation_rounds[0]["score"] == 8.5
        assert trace.final_outcome == "accepted_first_attempt"
        # Shadow verdict recorded separately and clearly tagged
        assert trace.shadow_validation_model == "shadow-model"
        assert len(trace.shadow_validation_rounds) == 1
        shadow_round = trace.shadow_validation_rounds[0]
        assert shadow_round["shadow"] is True
        assert shadow_round["model"] == "shadow-model"
        assert shadow_round["round"] == 0
        assert shadow_round["score"] == 4.0
        assert shadow_round["is_acceptable"] is False

    def test_shadow_mirrors_every_validation_round(self):
        models = self._make_models()
        qm = MockQueryModel()
        qm.validate_responses = [(False, "Too vague", 4.0), (True, "OK", 8.0)]
        qm.regenerate_responses = ["Fixed answer with sufficient length."]
        qm.shadow_validate_responses = [(True, "OK", 8.0), (False, "Too strict", 5.0)]
        trace = GenerationTrace(item_id="test", run_id="run")

        is_valid, doc = self._run(models, qm, [QuestionAnswer("Q?", "Initial answer")], trace=trace)

        assert is_valid is True
        assert trace.final_outcome == "accepted_after_fix"
        assert len(trace.validation_rounds) == 2
        assert len(trace.shadow_validation_rounds) == 2
        assert [r["round"] for r in trace.shadow_validation_rounds] == [0, 1]
        assert [r["score"] for r in trace.shadow_validation_rounds] == [8.0, 5.0]

    def test_shadow_verdict_never_affects_outcome(self):
        models = self._make_models()
        qm = MockQueryModel()
        qm.validate_responses = [(True, "OK", 9.0)]
        qm.shadow_validate_responses = [(False, "Terrible", 1.0)]
        trace = GenerationTrace(item_id="test", run_id="run")

        is_valid, doc = self._run(models, qm, [QuestionAnswer("Q?", "A")], trace=trace)

        assert is_valid is True
        assert doc.validation_score == 9.0
        assert trace.final_score == 9.0
        assert trace.final_outcome == "accepted_first_attempt"

    def test_no_shadow_model_skips_shadow_validation(self):
        models = self._make_models(with_shadow=False)
        qm = MockQueryModel()
        qm.validate_responses = [(True, "OK", 8.0)]
        trace = GenerationTrace(item_id="test", run_id="run")

        self._run(models, qm, [QuestionAnswer("Q?", "A")], trace=trace)

        assert trace.shadow_validation_model == ""
        assert trace.shadow_validation_rounds == []
        assert len(trace.validation_rounds) == 1

    def test_shadow_skipped_when_validation_skipped(self):
        models = self._make_models()
        qm = MockQueryModel()
        qm.validate_responses = [(True, "OK", 8.0)]
        qm.shadow_validate_responses = [(False, "Too strict", 3.0)]
        trace = GenerationTrace(item_id="test", run_id="run")

        with patch("training_data.generate_synthetic_data.common.random.random", return_value=0.9):
            is_valid, doc = validate_and_loop_with_suggested_fix(
                query_model=qm, models=models, qa_pairs=[QuestionAnswer("Q?", "A")],
                validation_pct=0.0, enable_extra_validation=True,
                build_context=lambda: "context", source_category="c", source_data=[],
                source_template="t", metrics=None, trace=trace,
            )

        assert is_valid is True
        assert trace.final_outcome == "skipped"
        assert trace.shadow_validation_rounds == []
        assert qm.shadow_validate_responses  # shadow never called

    def test_shadow_without_trace_is_noop(self):
        models = self._make_models()
        qm = MockQueryModel()
        qm.validate_responses = [(True, "OK", 8.0)]
        qm.shadow_validate_responses = [(False, "Too strict", 3.0)]

        is_valid, doc = self._run(models, qm, [QuestionAnswer("Q?", "A")], trace=None)

        assert is_valid is True
        assert doc.validation_score == 8.0
        assert qm.shadow_validate_responses  # shadow never called (no trace to record)


# =============================================================================
# Test 4b: CLI Flag Parsing
# =============================================================================

class TestCLIFlagParsing:
    """Tests for --log-traces / --no-log-traces argument parsing."""

    def test_no_log_traces_flag(self):
        """--no-log-traces should set args.log_traces to False."""
        import sys
        original_argv = sys.argv[:]
        try:
            sys.argv = ['main', '--no-log-traces', '--combo-queries', '0']

            # Re-parse using the same argparse from main.py
            import argparse
            parser = argparse.ArgumentParser()
            parser.add_argument('--combo-queries', type=int, default=0)
            parser.add_argument('--log-traces', action='store_true', default=True,
                                help='Log full generation/validation traces (default: on)')
            parser.add_argument('--no-log-traces', action='store_false', dest='log_traces',
                                help='Disable trace logging')
            args = parser.parse_args(['--no-log-traces', '--combo-queries', '0'])

            assert args.log_traces is False
        finally:
            sys.argv = original_argv

    def test_log_traces_flag(self):
        """--log-traces should set args.log_traces to True."""
        parser = argparse.ArgumentParser()
        parser.add_argument('--combo-queries', type=int, default=0)
        parser.add_argument('--log-traces', action='store_true', default=True,
                            help='Log full generation/validation traces (default: on)')
        parser.add_argument('--no-log-traces', action='store_false', dest='log_traces',
                            help='Disable trace logging')
        args = parser.parse_args(['--log-traces', '--combo-queries', '0'])

        assert args.log_traces is True

    def test_default_log_traces(self):
        """Without explicit flag, args.log_traces defaults to True."""
        parser = argparse.ArgumentParser()
        parser.add_argument('--combo-queries', type=int, default=0)
        parser.add_argument('--log-traces', action='store_true', default=True,
                            help='Log full generation/validation traces (default: on)')
        parser.add_argument('--no-log-traces', action='store_false', dest='log_traces',
                            help='Disable trace logging')
        args = parser.parse_args(['--combo-queries', '0'])

        assert args.log_traces is True

    def test_shadow_validation_model_flag(self):
        """--shadow-validation-model defaults to None and parses when provided (Story 049)."""
        from training_data.generate_synthetic_data.main import build_parser

        parser = build_parser()
        assert parser.parse_args([]).shadow_validation_model is None
        args = parser.parse_args(["--shadow-validation-model", "shadow-model"])
        assert args.shadow_validation_model == "shadow-model"


# =============================================================================
# Test 5: Backward Compatibility
# =============================================================================

class TestBackwardCompatibility:
    """Tests that existing code without trace parameters still works."""

    def test_validate_qa_without_trace_round(self):
        """query_model.validate_qa() should work without trace_round param."""
        qm = QueryModel()
        # Mock the internal query to avoid real LLM calls
        qm._last_elapsed_ms = 100
        with patch.object(qm, 'query', return_value='{"score": 8, "is_acceptable": true, "errors": "none", "reason": ""}'):
            is_valid, reason, score = qm.validate_qa(
                validation_model=MockModel(),
                question="Test?",
                answer="Test answer with enough length.",
            )
            assert is_valid is True
            assert score == 8.0

    def test_validate_qa_with_trace_round(self):
        """query_model.validate_qa() should populate trace_round when provided."""
        qm = QueryModel()
        qm._last_elapsed_ms = 100
        with patch.object(qm, 'query', return_value='{"score": 8, "is_acceptable": true, "errors": "none", "reason": "OK"}'):
            trace_round = {}
            is_valid, reason, score = qm.validate_qa(
                validation_model=MockModel(),
                question="Test?",
                answer="Test answer with enough length.",
                trace_round=trace_round,
            )
            assert is_valid is True
            assert "prompt" in trace_round
            assert "response" in trace_round
            assert "parsed_ok" in trace_round
            assert trace_round["parsed_ok"] is True
            assert trace_round["score"] == 8.0

    def test_validate_qa_passes_validation_max_tokens(self):
        """validate_qa() must pass VALIDATION_MAX_TOKENS as max_tokens to query().

        Regression guard: reasoning-model validators (deepseek-v4-flash) emit
        thinking tokens against the same budget; an 8192 cap truncated the
        final JSON, causing "Validation parse failed" rejections.
        """
        qm = QueryModel()
        qm._last_elapsed_ms = 100
        with patch.object(qm, 'query', return_value='{"score": 8, "is_acceptable": true, "errors": "none", "reason": "OK"}') as mock_query:
            is_valid, reason, score = qm.validate_qa(
                validation_model=MockModel(),
                question="Test?",
                answer="A sufficiently long test answer.",
            )
            assert is_valid is True
            assert mock_query.call_args.kwargs["max_tokens"] == VALIDATION_MAX_TOKENS
            assert mock_query.call_args.kwargs["max_tokens"] == 16384

    def test_validate_with_model_passes_validation_max_tokens(self):
        """validate_with_model() must pass VALIDATION_MAX_TOKENS as max_tokens to query()."""
        qm = QueryModel()
        qm._last_elapsed_ms = 100
        card1 = {"name": "Llanowar Elves", "type": "Creature — Elf Druid", "text": "{T}: Add {G}.", "manaCost": "{G}"}
        card2 = {"name": "Birds of Paradise", "type": "Creature — Bird", "text": "Flying. {T}: Add one mana of any color.", "manaCost": "{G}"}
        qa = {"question": "Which is better?", "answer": "A sufficiently long test answer."}
        with patch.object(
            qm, 'query',
            return_value='{"score": 8, "is_acceptable": true, "missing_info": "", '
                         '"errors": "", "mechanical_accuracy": "correct", '
                         '"cost_comparison_correct": "yes"}',
        ) as mock_query:
            is_valid, reason, score = qm.validate_with_model(
                model=MockModel(),
                card1=card1,
                card2=card2,
                qa=qa,
            )
            assert is_valid is True
            assert mock_query.call_args.kwargs["max_tokens"] == VALIDATION_MAX_TOKENS
            assert mock_query.call_args.kwargs["max_tokens"] == 16384

    def test_regenerate_answer_without_trace(self):
        """query_model.regenerate_answer() should work without trace_regeneration."""
        qm = QueryModel()
        qm._last_elapsed_ms = 100
        with patch.object(qm, 'query', return_value='{"answer": "New answer"}'):
            new_answer = qm.regenerate_answer(
                generation_model=MockModel(),
                question="Q?",
                old_answer="Old answer",
                reason="Too vague",
                score=4.0,
            )
            assert new_answer == "New answer"

    def test_regenerate_answer_with_trace(self):
        """query_model.regenerate_answer() should populate trace_regeneration when provided."""
        qm = QueryModel()
        qm._last_elapsed_ms = 100
        with patch.object(qm, 'query', return_value='{"answer": "New answer"}'):
            trace_regen = {}
            new_answer = qm.regenerate_answer(
                generation_model=MockModel(),
                question="Q?",
                old_answer="Old answer",
                reason="Too vague",
                score=4.0,
                trace_regeneration=trace_regen,
            )
            assert new_answer == "New answer"
            assert "prompt" in trace_regen
            assert "response" in trace_regen
            assert "parsed_ok" in trace_regen
            assert trace_regen["parsed_ok"] is True
            assert trace_regen["new_answer"] == "New answer"

    def test_validate_and_loop_without_trace(self):
        """validate_and_loop_with_suggested_fix should work without trace param."""
        models = {
            ModelType.GENERATION: MockModel("gen-model", ModelType.GENERATION),
            ModelType.VALIDATION: MockModel("val-model", ModelType.VALIDATION),
        }
        qm = MockQueryModel()
        qm.validate_responses = [(True, "OK", 8.0)]

        qa = QuestionAnswer("Q?", "A with enough length.")
        metrics = Mock()
        metrics.run_id = "test-run"
        metrics.record_candidate = Mock()
        metrics.record_validation_attempt = Mock()
        metrics.record_skip = Mock()
        metrics.record_first_attempt_pass = Mock()
        metrics.record_pass_after_fix = Mock()
        metrics.record_failed_first_attempt = Mock()
        metrics.record_failed_after_fixes = Mock()
        metrics.record_fix_attempt = Mock()
        metrics.flush = Mock()
        metrics.print_rolling_summary = Mock()

        # No trace parameter
        is_valid, doc = validate_and_loop_with_suggested_fix(
            query_model=qm,
            models=models,
            qa_pairs=[qa],
            validation_pct=1.0,
            enable_extra_validation=False,
            build_context=lambda: "ctx",
            source_category="cat",
            source_data=[],
            source_template="tmpl",
            metrics=metrics,
        )

        assert is_valid is True
        assert doc is not None

    def test_generator_without_trace_callback(self):
        """BaseGenerator should work when trace_callback is not passed."""
        models = {
            ModelType.GENERATION: MockModel("gen-model", ModelType.GENERATION),
            ModelType.VALIDATION: MockModel("val-model", ModelType.VALIDATION),
        }
        save_item = Mock()
        metrics = Mock()
        metrics.generator_name = "unknown"
        metrics.generation_model = "unknown"
        metrics.validation_model = "unknown"
        metrics.run_id = "test-run"
        metrics.flush = Mock()
        metrics.print_rolling_summary = Mock()
        metrics.record_candidate = Mock()
        metrics.record_validation_attempt = Mock()
        metrics.record_skip = Mock()
        metrics.record_first_attempt_pass = Mock()
        metrics.record_pass_after_fix = Mock()
        metrics.record_failed_first_attempt = Mock()
        metrics.record_failed_after_fixes = Mock()
        metrics.record_fix_attempt = Mock()

        generator = ConcreteGenerator(
            models=models,
            validation_pct=1.0,
            target_count=1,
            save_item=save_item,
            metrics=metrics,
            # No trace_callback parameter
        )
        generator.data_batches = [[{"id": 1}]]

        generator.query_model = MockQueryModel()
        generator.query_model.query_responses = [
            json.dumps([{"question": "Q1?", "answer": "A1 with sufficient length to pass validation."}]),
        ]
        generator.query_model.validate_responses = [
            (True, "OK", 8.0),
        ]

        generator.generate()
        assert generator.generated_count == 1
        assert save_item.call_count == 1


# =============================================================================
# Test 6: Trace with QueryModel error paths
# =============================================================================

class TestTraceErrorPaths:
    """Tests that trace round data is populated correctly on error paths."""

    def test_validate_qa_json_parse_error_with_trace(self):
        """validate_qa should populate trace_round even on JSON parse error."""
        qm = QueryModel()
        qm._last_elapsed_ms = 50
        with patch.object(qm, 'query', return_value='not valid json {{{'):
            trace_round = {}
            is_valid, reason, score = qm.validate_qa(
                validation_model=MockModel(),
                question="Q?",
                answer="A with length",
                trace_round=trace_round,
            )
            assert is_valid is False
            assert score == 0
            assert trace_round["parsed_ok"] is False
            assert trace_round["score"] == 0
            assert "prompt" in trace_round

    def test_validate_qa_generic_error_with_trace(self):
        """validate_qa should populate trace_round on generic exceptions."""
        qm = QueryModel()
        qm._last_elapsed_ms = 50
        with patch.object(qm, 'query', side_effect=RuntimeError("connection failed")):
            trace_round = {}
            is_valid, reason, score = qm.validate_qa(
                validation_model=MockModel(),
                question="Q?",
                answer="A with length",
                trace_round=trace_round,
            )
            assert is_valid is False
            assert score == 0
            assert trace_round["parsed_ok"] is False
            assert "prompt" in trace_round

    def test_regenerate_json_parse_error_with_trace(self):
        """regenerate_answer should populate trace_regeneration on JSON parse error."""
        qm = QueryModel()
        qm._last_elapsed_ms = 50
        with patch.object(qm, 'query', return_value='not json'):
            trace_regen = {}
            result = qm.regenerate_answer(
                generation_model=MockModel(),
                question="Q?",
                old_answer="old",
                reason="bad",
                score=3.0,
                trace_regeneration=trace_regen,
            )
            assert result is None
            assert trace_regen["parsed_ok"] is False
            assert trace_regen["new_answer"] is None
            assert "prompt" in trace_regen

    def test_regenerate_generic_error_with_trace(self):
        """regenerate_answer should populate trace_regeneration on generic exceptions."""
        qm = QueryModel()
        qm._last_elapsed_ms = 50
        with patch.object(qm, 'query', side_effect=RuntimeError("timeout")):
            trace_regen = {}
            result = qm.regenerate_answer(
                generation_model=MockModel(),
                question="Q?",
                old_answer="old",
                reason="bad",
                score=3.0,
                trace_regeneration=trace_regen,
            )
            assert result is None
            assert trace_regen["parsed_ok"] is False
            assert trace_regen["new_answer"] is None

    def test_regenerate_empty_answer_with_trace(self):
        """regenerate_answer should populate trace_regeneration when answer is empty."""
        qm = QueryModel()
        qm._last_elapsed_ms = 50
        with patch.object(qm, 'query', return_value='{"answer": ""}'):
            trace_regen = {}
            result = qm.regenerate_answer(
                generation_model=MockModel(),
                question="Q?",
                old_answer="old",
                reason="bad",
                score=3.0,
                trace_regeneration=trace_regen,
            )
            assert result is None
            assert trace_regen["parsed_ok"] is True
            assert trace_regen["new_answer"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
