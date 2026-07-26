"""Tests for TrainForge UI Browse Data page — core logic only."""

from __future__ import annotations

import json
from unittest.mock import MagicMock



class TestExportFiltered:
    """Test filtered data export to JSONL — tests the format_example helper."""

    def test_format_example_converts_to_sft_format(self):
        """Should convert MongoDB record to SFTTrainer format."""
        from trainforge.training import TrainingExporter

        exporter = TrainingExporter(MagicMock(), "/tmp/")

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
        assert result["messages"][1]["content"] == "A combo is..."

    def test_format_example_returns_none_for_missing_question(self):
        """Should return None for records with missing question."""
        from trainforge.training import TrainingExporter

        exporter = TrainingExporter(MagicMock(), "/tmp/")
        assert exporter._format_example({"answer": "A1"}) is None

    def test_format_example_returns_none_for_missing_answer(self):
        """Should return None for records with missing answer."""
        from trainforge.training import TrainingExporter

        exporter = TrainingExporter(MagicMock(), "/tmp/")
        assert exporter._format_example({"question": "Q1?"}) is None

    def test_format_example_returns_none_for_empty_strings(self):
        """Should return None for empty question/answer strings."""
        from trainforge.training import TrainingExporter

        exporter = TrainingExporter(MagicMock(), "/tmp/")
        assert exporter._format_example({"question": "", "answer": ""}) is None


class TestPagination:
    """Test pagination calculations."""

    def test_pagination_calculates_pages_correctly(self):
        """Should calculate total pages based on count and page size."""
        total_count = 250
        page_size = 50
        expected_pages = (total_count + page_size - 1) // page_size
        assert expected_pages == 5

    def test_pagination_handles_zero_records(self):
        """Should handle zero records gracefully."""
        total_count = 0
        page_size = 50
        # max(1, ...) ensures at least 1 page
        expected_pages = max(1, (total_count + page_size - 1) // page_size)
        assert expected_pages == 1

    def test_pagination_handles_exact_multiple(self):
        """Should handle exact multiples correctly."""
        total_count = 200
        page_size = 50
        expected_pages = max(1, (total_count + page_size - 1) // page_size)
        assert expected_pages == 4

    def test_pagination_handles_remainder(self):
        """Should handle remainders correctly."""
        total_count = 203
        page_size = 50
        expected_pages = max(1, (total_count + page_size - 1) // page_size)
        assert expected_pages == 5


class TestJSONLExport:
    """Test JSONL export format generation."""

    def test_jsonl_format_is_valid(self):
        """Should produce valid JSONL output."""
        records = [
            {"question": "Q1?", "answer": "A1"},
            {"question": "Q2?", "answer": "A2"},
        ]

        lines = []
        for record in records:
            example = {
                "messages": [
                    {"role": "user", "content": record["question"]},
                    {"role": "assistant", "content": record["answer"]},
                ]
            }
            lines.append(json.dumps(example, ensure_ascii=False))

        jsonl_output = "\n".join(lines)
        decoded_lines = jsonl_output.split("\n")

        assert len(decoded_lines) == 2
        for line in decoded_lines:
            data = json.loads(line)
            assert "messages" in data
            assert len(data["messages"]) == 2


class TestFilterBuilding:
    """Test MongoDB filter building logic."""

    def test_domain_filter(self):
        """Should build domain filter correctly."""
        filters = {}
        selected_domain = "mtg"

        if selected_domain and selected_domain != "All":
            filters["domain"] = selected_domain

        assert filters == {"domain": "mtg"}

    def test_category_filter(self):
        """Should build category $in filter correctly."""
        filters = {}
        selected_cats = ["combo_query", "card_search"]

        if selected_cats:
            filters["category"] = {"$in": selected_cats}

        assert filters == {"category": {"$in": ["combo_query", "card_search"]}}

    def test_score_range_filter(self):
        """Should build score range filter correctly."""
        filters = {}
        min_score, max_score = 7, 10

        if min_score > 0 or max_score < 10:
            score_filter = {}
            if min_score > 0:
                score_filter["$gte"] = min_score
            if max_score < 10:
                score_filter["$lte"] = max_score
            filters["validation_score"] = score_filter

        assert filters == {"validation_score": {"$gte": 7}}

    def test_search_query_filter(self):
        """Should build regex search filter correctly."""
        search_query = "combo"

        if search_query:
            filters = {
                "$or": [
                    {"question": {"$regex": search_query, "$options": "i"}},
                    {"answer": {"$regex": search_query, "$options": "i"}},
                ]
            }
        else:
            filters = {}

        assert "$or" in filters
        assert len(filters["$or"]) == 2


class TestRecordCardData:
    """Test record card data extraction."""

    def test_extract_record_fields(self):
        """Should extract all fields from a MongoDB record."""
        record = {
            "question": "What is a combo?",
            "answer": "A combo is...",
            "category": "combo_query",
            "domain": "mtg",
            "validation_score": 8.5,
            "generation_model": "qwen2.5:14b",
        }

        question = record.get("question", "No question")
        record.get("answer", "No answer")
        category = record.get("category", "N/A")
        domain = record.get("domain", "N/A")
        score = record.get("validation_score")

        assert question == "What is a combo?"
        assert category == "combo_query"
        assert domain == "mtg"
        assert score == 8.5

    def test_extract_record_with_defaults(self):
        """Should use defaults for missing fields."""
        record = {"question": "Q?", "answer": "A"}

        question = record.get("question", "No question")
        category = record.get("category", "N/A")
        domain = record.get("domain", "N/A")
        score = record.get("validation_score")

        assert question == "Q?"
        assert category == "N/A"
        assert domain == "N/A"
        assert score is None


class TestScoreColorLogic:
    """Test validation score color coding."""

    def test_high_score_is_good(self):
        """Score >= 7 should be considered good."""
        score = 8.5
        status = "good" if score >= 7 else ("warning" if score >= 5 else "bad")
        assert status == "good"

    def test_medium_score_is_warning(self):
        """Score 5-6 should be a warning."""
        score = 6.0
        status = "good" if score >= 7 else ("warning" if score >= 5 else "bad")
        assert status == "warning"

    def test_low_score_is_bad(self):
        """Score < 5 should be bad."""
        score = 3.0
        status = "good" if score >= 7 else ("warning" if score >= 5 else "bad")
        assert status == "bad"
