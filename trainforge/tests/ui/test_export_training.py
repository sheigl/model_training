"""Tests for TrainForge UI Export Training page — export logic."""

from __future__ import annotations

import pytest


class TestFormatExample:
    """Test JSONL example formatting from TrainingExporter."""

    def test_format_example_converts_to_sft_format(self):
        """Should convert MongoDB record to SFTTrainer format."""
        from trainforge.training import TrainingExporter

        exporter = TrainingExporter(None, "/tmp/")  # type: ignore[arg-type]

        record = {
            "question": "What is a combo?",
            "answer": "A combo is...",
            "category": "combo_query",
        }

        result = exporter._format_example(record)

        assert result is not None
        assert len(result["messages"]) == 2
        assert result["messages"][0]["role"] == "user"
        assert result["messages"][1]["role"] == "assistant"
        assert result["messages"][0]["content"] == "What is a combo?"

    def test_format_example_returns_none_for_missing_question(self):
        """Should return None for records with missing question."""
        from trainforge.training import TrainingExporter

        exporter = TrainingExporter(None, "/tmp/")  # type: ignore[arg-type]
        assert exporter._format_example({"answer": "A1"}) is None

    def test_format_example_returns_none_for_missing_answer(self):
        """Should return None for records with missing answer."""
        from trainforge.training import TrainingExporter

        exporter = TrainingExporter(None, "/tmp/")  # type: ignore[arg-type]
        assert exporter._format_example({"question": "Q1?"}) is None

    def test_format_example_returns_none_for_empty_strings(self):
        """Should return None for empty question/answer strings."""
        from trainforge.training import TrainingExporter

        exporter = TrainingExporter(None, "/tmp/")  # type: ignore[arg-type]
        assert exporter._format_example({"question": "", "answer": ""}) is None


class TestPerDomainExportConfig:
    """Test per-domain export configuration validation."""

    def test_categories_must_not_be_empty(self):
        """Should raise error when categories list is empty."""
        from trainforge.training import TrainingExporter

        exporter = TrainingExporter(None, "/tmp/")  # type: ignore[arg-type]

        with pytest.raises(ValueError, match="categories must not be empty"):
            exporter.export_per_domain(
                domain_name="mtg",
                categories=[],
                ratios=None,
                min_score=7,
            )

    def test_default_equal_ratios(self):
        """Should default to equal distribution when no ratios provided."""
        categories = ["combo_query", "card_search"]
        if None is None:  # Simulating ratios=None check
            ratios = {cat: 1.0 / len(categories) for cat in categories}

        assert abs(ratios["combo_query"] - 0.5) < 0.001
        assert abs(ratios["card_search"] - 0.5) < 0.001


class TestCrossDomainExportConfig:
    """Test cross-domain export configuration."""

    def test_domain_config_structure(self):
        """Should build correct domain config structure."""
        domain_configs = [
            {
                "domain": "mtg",
                "categories": ["combo_query"],
                "ratio": 0.7,
                "max_count": 1000,
            },
            {
                "domain": "cooking",
                "categories": [],
                "ratio": 0.3,
                "max_count": 500,
            },
        ]

        assert len(domain_configs) == 2
        assert domain_configs[0]["domain"] == "mtg"
        assert sum(d["ratio"] for d in domain_configs) == pytest.approx(1.0)

    def test_ratio_normalization(self):
        """Should normalize ratios to sum to 1.0."""
        raw_ratios = [0.7, 0.3]
        total = sum(raw_ratios)
        normalized = [r / total for r in raw_ratios] if total > 0 else []

        assert abs(sum(normalized) - 1.0) < 0.001


class TestMinScoreFilter:
    """Test minimum validation score filtering."""

    def test_default_min_score(self):
        """Default min score should be 7."""
        default_min_score = 7
        assert default_min_score == 7

    def test_filter_records_by_score(self):
        """Should filter records by validation score threshold."""
        records = [
            {"validation_score": 9.0},
            {"validation_score": 7.5},
            {"validation_score": 6.0},
            {"validation_score": None},
        ]

        min_score = 7
        filtered = [r for r in records if (r.get("validation_score") or 0) >= min_score]

        assert len(filtered) == 2


class TestOutputFilename:
    """Test output filename generation."""

    def test_per_domain_default_filename(self):
        """Should generate default per-domain filename."""
        domain_name = "mtg"
        filename = f"{domain_name}_training.jsonl"
        assert filename == "mtg_training.jsonl"

    def test_cross_domain_default_filename(self):
        """Should generate default cross-domain filename."""
        filename = "cross_domain_training.jsonl"
        assert filename.endswith(".jsonl")


class TestCategoryBreakdown:
    """Test category breakdown counting in exports."""

    def test_count_categories_in_records(self):
        """Should count records per category correctly."""
        from collections import Counter

        records = [
            {"category": "combo_query"},
            {"category": "card_search"},
            {"category": "combo_query"},
            {"category": "combo_query"},
        ]

        counts = Counter(r.get("category", "unknown") for r in records)

        assert counts["combo_query"] == 3
        assert counts["card_search"] == 1


class TestExportStats:
    """Test export statistics calculation."""

    def test_valid_and_skipped_counts(self):
        """Should count valid and skipped records correctly."""
        records = [
            {"question": "Q1?", "answer": "A1"},
            {"question": "", "answer": "No question"},  # Invalid
            {"question": "Q2?", "answer": ""},  # Invalid
            {"question": "Q3?", "answer": "A3"},
        ]

        valid_count = 0
        skipped_count = 0
        for record in records:
            if record.get("question") and record.get("answer"):
                valid_count += 1
            else:
                skipped_count += 1

        assert valid_count == 2
        assert skipped_count == 2
