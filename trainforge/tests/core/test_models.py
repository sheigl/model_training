"""Tests for TrainForge models — provider detection, serialization, metrics."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from trainforge.models import (
    GenerationTrace,
    Model,
    ModelProvider,
    ModelType,
    QuestionAnswerEnhanced,
    ValidationMetrics,
)


# =============================================================================
# MODEL PROVIDER AUTO-DETECTION
# =============================================================================


class TestModelProviderDetection:
    """Test Model._parse_provider() auto-detection logic."""

    def test_detect_ollama_default(self):
        """Models without provider keywords default to Ollama."""
        m = Model(name="qwen2.5:14b", type=ModelType.GENERATION)
        assert m.provider == ModelProvider.OLLAMA

    def test_detect_ollama_local_name(self):
        """Local model names like 'llama3' default to Ollama."""
        m = Model(name="llama3:8b", type=ModelType.GENERATION)
        assert m.provider == ModelProvider.OLLAMA

    def test_detect_anthropic_from_name(self):
        """Names containing 'anthropic' are detected as Anthropic provider."""
        m = Model(name="claude-3-opus-20240229", type=ModelType.VALIDATION)
        # The detection checks for "anthropic" in the name — this model doesn't have it
        assert m.provider == ModelProvider.OLLAMA

    def test_detect_anthropic_explicit(self):
        """Names containing 'anthropic' keyword are detected correctly."""
        m = Model(name="anthropic-claude-3", type=ModelType.VALIDATION)
        assert m.provider == ModelProvider.ANTHROPIC

    def test_detect_openai_from_name(self):
        """Names containing 'openai' are detected as OpenAI provider."""
        m = Model(name="gpt-4o-openai-custom", type=ModelType.GENERATION)
        assert m.provider == ModelProvider.OPENAI

    def test_provider_can_be_explicitly_set(self):
        """Explicitly set provider overrides auto-detection."""
        m = Model(
            name="custom-model",
            type=ModelType.GENERATION,
            provider=ModelProvider.ANTHROPIC,
        )
        assert m.provider == ModelProvider.ANTHROPIC

    def test_provider_url_and_api_key_stored(self):
        """Optional fields are stored correctly."""
        m = Model(
            name="qwen2.5:14b",
            type=ModelType.GENERATION,
            provider_url="http://custom-host:9000",
            api_key="sk-test-key",
        )
        assert m.provider_url == "http://custom-host:9000"
        assert m.api_key == "sk-test-key"


# =============================================================================
# QUESTIONANSWERENHANCED SERIALIZATION
# =============================================================================


class TestQuestionAnswerEnhancedSerialization:
    """Test QuestionAnswerEnhanced serialization/deserialization."""

    def test_basic_serialization(self):
        """Should serialize to dict with all fields."""
        qa = QuestionAnswerEnhanced(
            question="What is MTG?",
            answer="Magic: The Gathering",
            category="terminology",
            domain="mtg",
            validated=True,
            validation_score=95.0,
        )
        d = qa.model_dump()
        assert d["question"] == "What is MTG?"
        assert d["answer"] == "Magic: The Gathering"
        assert d["category"] == "terminology"
        assert d["validated"] is True
        assert d["validation_score"] == 95.0

    def test_exclude_none_serialization(self):
        """Should exclude None fields when requested."""
        qa = QuestionAnswerEnhanced(
            question="Q?",
            answer="A!",
            category=None,
            domain=None,
            source_data=None,
        )
        d = qa.model_dump(exclude_none=True)
        assert "category" not in d
        assert "domain" not in d
        assert "source_data" not in d

    def test_json_roundtrip(self):
        """Should survive JSON serialization and deserialization."""
        qa = QuestionAnswerEnhanced(
            question="What is ETB?",
            answer="Enter the battlefield trigger",
            category="terminology",
            domain="mtg",
            validated=True,
            validation_score=90.0,
            source_template="what_does_this_mean",
            generation_model="qwen2.5:14b",
        )
        json_str = qa.model_dump_json()
        restored = QuestionAnswerEnhanced.model_validate_json(json_str)
        assert restored.question == "What is ETB?"
        assert restored.answer == "Enter the battlefield trigger"
        assert restored.category == "terminology"

    def test_default_field_values(self):
        """Default values should be set correctly."""
        qa = QuestionAnswerEnhanced(question="Q?", answer="A!")
        assert qa.validated is False
        assert qa.validation_score is None
        assert qa.needs_review is True
        assert qa.version == 0
        assert qa.suggested_fix is None
        assert qa.content_hash is None
        assert qa.generated_at is None

    def test_model_copy_preserves_fields(self):
        """model_copy() should preserve all fields."""
        original = QuestionAnswerEnhanced(
            question="Q?",
            answer="A!",
            category="combo_query",
            domain="mtg",
            version=2,
        )
        copy = original.model_copy()
        assert copy.question == "Q?"
        assert copy.category == "combo_query"
        assert copy.version == 2

    def test_model_copy_deep(self):
        """model_copy(deep=True) should deep-copy mutable fields."""
        original = QuestionAnswerEnhanced(
            question="Q?",
            answer="A!",
            source_data=[{"card": "Lightning Bolt"}],
        )
        copy = original.model_copy(deep=True)
        assert copy.source_data == [{"card": "Lightning Bolt"}]
        # Mutating copy shouldn't affect original
        copy.source_data.append({"card": "Fireball"})
        assert len(original.source_data) == 1


# =============================================================================
# VALIDATION METRICS COUNTER METHODS
# =============================================================================


class TestValidationMetrics:
    """Test ValidationMetrics counter methods."""

    def test_default_values(self):
        """All counters should start at zero."""
        m = ValidationMetrics()
        assert m.total_candidates == 0
        assert m.total_validated == 0
        assert m.total_skipped == 0
        assert m.total_passed == 0
        assert m.total_failed == 0
        assert m.total_fix_attempts == 0
        assert m.total_first_attempt_passes == 0
        assert m.total_pass_after_fix == 0
        assert m.total_failed_first_attempt == 0
        assert m.total_failed_after_fixes == 0

    def test_record_candidate(self):
        """Should increment total_candidates and category bucket."""
        m = ValidationMetrics()
        m.record_candidate("combo_query", "how_does_it_work")
        assert m.total_candidates == 1
        assert m.category_stats["combo_query"]["candidates"] == 1
        assert m.template_stats["how_does_it_work"]["candidates"] == 1

    def test_record_candidate_without_template(self):
        """Should work without template parameter."""
        m = ValidationMetrics()
        m.record_candidate("card_search")
        assert m.total_candidates == 1
        assert "card_search" in m.category_stats
        # No template stats should be created
        assert len(m.template_stats) == 0

    def test_record_first_attempt_pass(self):
        """Should increment passed and first_attempt_passes counters."""
        m = ValidationMetrics()
        m.record_first_attempt_pass(92.5, "combo_query", "how_does_it_work")
        assert m.total_passed == 1
        assert m.total_first_attempt_passes == 1
        assert m.category_stats["combo_query"]["passed"] == 1
        assert m.category_stats["combo_query"]["first_attempt_passes"] == 1

    def test_record_first_attempt_pass_with_none_score(self):
        """Should handle None score gracefully."""
        m = ValidationMetrics()
        m.record_first_attempt_pass(None, "card_search")
        assert m.total_passed == 1
        # No scores should be recorded for None
        assert m.category_stats["card_search"]["scores"] == []

    def test_record_pass_after_fix(self):
        """Should increment passed and pass_after_fix counters."""
        m = ValidationMetrics()
        m.record_pass_after_fix(85.0, "comparison", "which_is_better")
        assert m.total_passed == 1
        assert m.total_pass_after_fix == 1

    def test_record_failed_first_attempt(self):
        """Should increment failed and failed_first_attempt counters."""
        m = ValidationMetrics()
        m.record_failed_first_attempt("synergy", "what_synergizes_with")
        assert m.total_failed == 1
        assert m.total_failed_first_attempt == 1

    def test_record_failed_after_fixes(self):
        """Should increment failed and failed_after_fixes counters."""
        m = ValidationMetrics()
        m.record_failed_after_fixes("budget", "cheaper_alternative")
        assert m.total_failed == 1
        assert m.total_failed_after_fixes == 1

    def test_record_fix_attempt(self):
        """Should increment fix_attempts counter."""
        m = ValidationMetrics()
        m.record_fix_attempt("combo_query", "how_does_it_work")
        assert m.total_fix_attempts == 1
        assert m.category_stats["combo_query"]["fix_attempts"] == 1

    def test_record_validation_attempt(self):
        """Should increment validated counter."""
        m = ValidationMetrics()
        m.record_validation_attempt("terminology", "what_does_this_mean")
        assert m.total_validated == 1

    def test_record_skip(self):
        """Should increment skipped counter."""
        m = ValidationMetrics()
        m.record_skip("rules_scenarios")
        assert m.total_skipped == 1

    def test_summary_basic(self):
        """Summary should return correct overall metrics."""
        m = ValidationMetrics(
            generation_model="qwen2.5:14b",
            validation_model="qwen2.5:14b",
        )
        m.record_candidate("cat_a")
        m.record_validation_attempt("cat_a")
        m.record_first_attempt_pass(90.0, "cat_a")

        s = m.summary()
        assert s["total_candidates"] == 1
        assert s["total_validated"] == 1
        assert s["total_passed"] == 1
        assert s["overall_pass_rate"] == 100.0
        assert s["first_attempt_pass_rate"] == 100.0

    def test_summary_zero_division(self):
        """Summary should handle zero validated without crashing."""
        m = ValidationMetrics()
        s = m.summary()
        assert s["overall_pass_rate"] == 0
        assert s["first_attempt_pass_rate"] == 0
        assert s["fix_recovery_rate"] is None

    def test_summary_category_breakdown(self):
        """Summary should include per-category stats."""
        m = ValidationMetrics()
        m.record_candidate("cat_a")
        m.record_validation_attempt("cat_a")
        m.record_first_attempt_pass(80.0, "cat_a")
        m.record_candidate("cat_b")
        m.record_validation_attempt("cat_b")
        m.record_failed_first_attempt("cat_b")

        s = m.summary()
        assert "by_category" in s
        assert len(s["by_category"]) == 2
        assert s["by_category"]["cat_a"]["passed"] == 1
        assert s["by_category"]["cat_b"]["failed"] == 1


# =============================================================================
# GENERATION TRACE DEFAULT VALUES
# =============================================================================


class TestGenerationTrace:
    """Test GenerationTrace default field values."""

    def test_default_values(self):
        """All fields should have sensible defaults."""
        t = GenerationTrace()
        assert len(t.item_id) == 36  # UUID format
        assert t.run_id == ""
        assert t.category == ""
        assert t.domain == ""
        assert t.source_template is None
        assert t.generator_name == ""
        assert t.generation_model == ""
        assert t.validation_model == ""
        assert t.generation_prompt == ""
        assert t.generation_response == ""
        assert t.generation_parsed_ok is True
        assert t.generation_latency_ms == 0
        assert t.validation_rounds == []
        assert t.final_outcome == "pending"
        assert t.total_rounds == 0
        assert t.final_score is None

    def test_created_at_format(self):
        """created_at should be ISO format with Z suffix."""
        t = GenerationTrace()
        assert t.created_at.endswith("Z")
        # Should parse as valid datetime
        datetime.fromisoformat(t.created_at.replace("Z", "+00:00"))

    def test_custom_values(self):
        """Should accept custom values for all fields."""
        t = GenerationTrace(
            run_id="run123",
            category="combo_query",
            domain="mtg",
            generator_name="ComboGenerator",
        )
        assert t.run_id == "run123"
        assert t.category == "combo_query"
        assert t.domain == "mtg"

    def test_serialization(self):
        """Should serialize to dict correctly."""
        t = GenerationTrace(
            run_id="abc",
            category="test",
            final_outcome="accepted_first_attempt",
            total_rounds=1,
            final_score=95.0,
        )
        d = t.model_dump()
        assert d["run_id"] == "abc"
        assert d["final_outcome"] == "accepted_first_attempt"
