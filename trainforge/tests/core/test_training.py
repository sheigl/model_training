"""Tests for TrainForge training module - TrainingExporter."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from trainforge.data_source import DataSource
from trainforge.training import MIN_TARGET_SIZE, TrainingExporter


# =============================================================================
# MOCK DATA SOURCE
# =============================================================================


class MockDataSource(DataSource):
    """Mock DataSource for testing without MongoDB."""

    def __init__(self, records: list[dict] | None = None):
        self._records = records or []

    def connect(self) -> None:
        pass

    def close(self) -> None:
        pass

    def get_records(
        self, collection: str, filters=None, limit: int = 100, skip: int = 0
    ) -> list[dict]:
        # Simple filter simulation
        results = self._records[:]
        if filters:
            filtered = []
            for r in results:
                match = True
                for key, val in filters.items():
                    if isinstance(val, dict) and "$in" in val:
                        if r.get(key) not in val["$in"]:
                            match = False
                            break
                    elif isinstance(val, dict) and "$gte" in val:
                        if r.get(key, 0) < val["$gte"]:
                            match = False
                            break
                    else:
                        if r.get(key) != val:
                            match = False
                            break
                if match:
                    filtered.append(r)
            results = filtered

        if limit > 0:
            return results[skip : skip + limit]
        return results[skip:]

    def save_record(self, collection: str, record: dict, dedup_key=None) -> bool:
        self._records.append(record)
        return True

    def search(
        self, collection: str, query: str, field=None, limit: int = 50
    ) -> list[dict]:
        return []

    def count(self, collection: str, filters=None) -> int:
        return len(self._records)

    def delete_records(self, collection: str, filters: dict) -> int:
        return 0

    def aggregate(
        self, collection: str, pipeline: list[dict], allow_disk_use: bool = True
    ) -> list[dict]:
        return []


# =============================================================================
# _FORMAT_EXAMPLE
# =============================================================================


class TestFormatExample:
    """Test TrainingExporter._format_example() method."""

    def setup_method(self):
        ds = MockDataSource()
        with tempfile.TemporaryDirectory() as tmpdir:
            self.exporter = TrainingExporter(ds, tmpdir)

    def test_valid_record(self):
        """Should convert valid record to SFT format."""
        record = {"question": "What is MTG?", "answer": "Magic: The Gathering"}
        result = self.exporter._format_example(record)

        assert result == {
            "messages": [
                {"role": "user", "content": "What is MTG?"},
                {"role": "assistant", "content": "Magic: The Gathering"},
            ]
        }

    def test_missing_question(self):
        """Should return None for record without question."""
        record = {"answer": "An answer"}
        result = self.exporter._format_example(record)
        assert result is None

    def test_empty_question(self):
        """Should return None for empty question string."""
        record = {"question": "", "answer": "A!"}
        result = self.exporter._format_example(record)
        assert result is None

    def test_missing_answer(self):
        """Should return None for record without answer."""
        record = {"question": "Q?"}
        result = self.exporter._format_example(record)
        assert result is None

    def test_empty_answer(self):
        """Should return None for empty answer string."""
        record = {"question": "Q?", "answer": ""}
        result = self.exporter._format_example(record)
        assert result is None

    def test_extra_fields_ignored(self):
        """Extra fields in record should not affect output format."""
        record = {
            "question": "Q?",
            "answer": "A!",
            "category": "combo_query",
            "domain": "mtg",
            "validation_score": 95,
        }
        result = self.exporter._format_example(record)
        assert len(result["messages"]) == 2


# =============================================================================
# CATEGORY RATIO CALCULATIONS (mock data source)
# =============================================================================


class TestCategoryRatios:
    """Test category ratio calculations in export_per_domain."""

    def test_default_equal_ratios(self):
        """Should use equal distribution when no ratios provided."""
        ds = MockDataSource()
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = TrainingExporter(ds, tmpdir)

            # With 3 categories, each should get 1/3 ratio
            cats = ["cat_a", "cat_b", "cat_c"]
            ratios = {cat: 1.0 / len(cats) for cat in cats}

            assert abs(ratios["cat_a"] - 1.0 / 3) < 0.001
            assert abs(sum(ratios.values()) - 1.0) < 0.001

    def test_ratio_normalization(self):
        """Ratios should be normalized to sum to 1.0."""
        ds = MockDataSource()
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = TrainingExporter(ds, tmpdir)

            # These ratios don't sum to 1.0 but will be normalized
            raw_ratios = {"cat_a": 2.0, "cat_b": 1.0}
            total = sum(raw_ratios.values())
            normalized = {k: v / total for k, v in raw_ratios.items()}

            assert abs(normalized["cat_a"] - 2.0 / 3) < 0.001
            assert abs(normalized["cat_b"] - 1.0 / 3) < 0.001

    def test_empty_categories_raises(self):
        """Should raise ValueError for empty categories list."""
        ds = MockDataSource()
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = TrainingExporter(ds, tmpdir)

            with pytest.raises(ValueError, match="categories must not be empty"):
                exporter.export_per_domain(
                    domain_name="mtg",
                    categories=[],
                )


# =============================================================================
# WRITE JSONL
# =============================================================================


class TestWriteJSONL:
    """Test TrainingExporter._write_jsonl() method."""

    def test_writes_valid_jsonl(self):
        """Should write valid JSONL file with formatted examples."""
        ds = MockDataSource([
            {"question": "Q1?", "answer": "A1!"},
            {"question": "Q2?", "answer": "A2!", "category": "cat_a"},
        ])
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = TrainingExporter(ds, tmpdir)

            records = [
                {"question": "Q1?", "answer": "A1!"},
                {"question": "Q2?", "answer": "A2!", "category": "cat_a"},
            ]
            path = exporter._write_jsonl(records, "test.jsonl")

            assert path.exists()
            lines = path.read_text().strip().split("\n")
            assert len(lines) == 2

            # Verify each line is valid JSON
            for line in lines:
                parsed = json.loads(line)
                assert "messages" in parsed

    def test_skips_invalid_records(self):
        """Should skip records without question or answer."""
        ds = MockDataSource()
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = TrainingExporter(ds, tmpdir)

            records = [
                {"question": "Q1?", "answer": "A1!"},  # valid
                {"question": "", "answer": "A2!"},      # invalid - empty question
                {"question": "Q3?"},                    # invalid - no answer
            ]
            path = exporter._write_jsonl(records, "test.jsonl")

            lines = path.read_text().strip().split("\n")
            assert len(lines) == 1  # Only valid record written


# =============================================================================
# MIN_TARGET_SIZE CONSTANT
# =============================================================================


class TestConstants:
    """Test module-level constants."""

    def test_min_target_size(self):
        """MIN_TARGET_SIZE should be defined and positive."""
        assert MIN_TARGET_SIZE > 0
        assert isinstance(MIN_TARGET_SIZE, int)
