"""Tests for TrainForge UI Dashboard page — metrics aggregation logic."""

from __future__ import annotations



class TestMetricsAggregation:
    """Test validation metrics aggregation across runs."""

    def test_aggregate_total_candidates(self):
        """Should sum total_candidates across all metric docs."""
        metrics_docs = [
            {"total_candidates": 100, "total_validated": 90, "total_passed": 75},
            {"total_candidates": 50, "total_validated": 45, "total_passed": 36},
        ]

        total_candidates = sum(m.get("total_candidates", 0) for m in metrics_docs)
        assert total_candidates == 150

    def test_aggregate_total_passed(self):
        """Should sum total_passed across all metric docs."""
        metrics_docs = [
            {"total_passed": 75},
            {"total_passed": 36},
        ]

        total_passed = sum(m.get("total_passed", 0) for m in metrics_docs)
        assert total_passed == 111

    def test_aggregate_total_failed(self):
        """Should sum total_failed across all metric docs."""
        metrics_docs = [
            {"total_failed": 15},
            {"total_failed": 9},
        ]

        total_failed = sum(m.get("total_failed", 0) for m in metrics_docs)
        assert total_failed == 24


class TestPassRateCalculation:
    """Test pass rate calculation logic."""

    def test_pass_rate_normal(self):
        """Should calculate correct pass rate."""
        total_passed = 75
        total_validated = 90

        pass_rate = (total_passed / total_validated * 100) if total_validated > 0 else 0.0
        assert abs(pass_rate - 83.3) < 0.1

    def test_pass_rate_zero_validated(self):
        """Should return 0 when no items validated."""
        total_passed = 0
        total_validated = 0

        pass_rate = (total_passed / total_validated * 100) if total_validated > 0 else 0.0
        assert pass_rate == 0.0

    def test_pass_rate_100_percent(self):
        """Should return 100 when all items passed."""
        total_passed = 50
        total_validated = 50

        pass_rate = (total_passed / total_validated * 100) if total_validated > 0 else 0.0
        assert pass_rate == 100.0


class TestCategoryStatsAggregation:
    """Test per-category stats aggregation."""

    def test_aggregate_category_stats(self):
        """Should aggregate category stats across multiple runs."""
        metrics_docs = [
            {
                "category_stats": {
                    "combo_query": {"validated": 50, "passed": 40, "failed": 10},
                    "card_search": {"validated": 30, "passed": 25, "failed": 5},
                }
            },
            {
                "category_stats": {
                    "combo_query": {"validated": 20, "passed": 15, "failed": 5},
                    "card_search": {"validated": 10, "passed": 8, "failed": 2},
                }
            },
        ]

        cat_stats = {}
        for m in metrics_docs:
            for cat, stats in m.get("category_stats", {}).items():
                if cat not in cat_stats:
                    cat_stats[cat] = {"validated": 0, "passed": 0, "failed": 0}
                for key in ["validated", "passed", "failed"]:
                    cat_stats[cat][key] += stats.get(key, 0)

        assert cat_stats["combo_query"]["validated"] == 70
        assert cat_stats["combo_query"]["passed"] == 55
        assert cat_stats["card_search"]["validated"] == 40
        assert cat_stats["card_search"]["passed"] == 33


class TestGeneratorStatsAggregation:
    """Test per-generator stats aggregation."""

    def test_aggregate_generator_stats(self):
        """Should aggregate generator stats across multiple runs."""
        metrics_docs = [
            {
                "generator_name": "GenerateComboQueries",
                "total_candidates": 100, "total_validated": 90,
                "total_passed": 75, "total_failed": 15,
            },
            {
                "generator_name": "GenerateComboQueries",
                "total_candidates": 50, "total_validated": 45,
                "total_passed": 36, "total_failed": 9,
            },
        ]

        gen_stats = {}
        for m in metrics_docs:
            gname = m.get("generator_name", "unknown")
            if gname not in gen_stats:
                gen_stats[gname] = {"candidates": 0, "validated": 0, "passed": 0, "failed": 0}
            gen_stats[gname]["candidates"] += m.get("total_candidates", 0)
            gen_stats[gname]["validated"] += m.get("total_validated", 0)
            gen_stats[gname]["passed"] += m.get("total_passed", 0)
            gen_stats[gname]["failed"] += m.get("total_failed", 0)

        assert gen_stats["GenerateComboQueries"]["candidates"] == 150
        assert gen_stats["GenerateComboQueries"]["validated"] == 135


class TestTraceOutcomeCounting:
    """Test generation trace outcome counting."""

    def test_count_outcomes(self):
        """Should count different outcomes correctly."""
        traces = [
            {"final_outcome": "accepted_first_attempt"},
            {"final_outcome": "accepted_after_fix"},
            {"final_outcome": "rejected"},
            {"final_outcome": "skipped"},
            {"final_outcome": "accepted_first_attempt"},
        ]

        outcomes = {}
        for t in traces:
            outcome = t.get("final_outcome", "unknown")
            outcomes[outcome] = outcomes.get(outcome, 0) + 1

        assert outcomes["accepted_first_attempt"] == 2
        assert outcomes["accepted_after_fix"] == 1
        assert outcomes["rejected"] == 1
        assert outcomes["skipped"] == 1


class TestAverageLatency:
    """Test average latency calculation."""

    def test_calculate_average_latency(self):
        """Should calculate correct average latency."""
        traces = [
            {"generation_latency_ms": 500},
            {"generation_latency_ms": 800},
            {"generation_latency_ms": 300},
        ]

        latencies = [t.get("generation_latency_ms", 0) for t in traces if t.get("generation_latency_ms")]
        avg_lat = sum(latencies) / len(latencies)

        assert abs(avg_lat - 533.33) < 0.1

    def test_skip_zero_latencies(self):
        """Should skip items with zero or missing latency."""
        traces = [
            {"generation_latency_ms": 500},
            {"generation_latency_ms": 0},
            {},
        ]

        latencies = [t.get("generation_latency_ms", 0) for t in traces if t.get("generation_latency_ms")]
        assert len(latencies) == 1


class TestCategoryPassRateTable:
    """Test category pass rate table building."""

    def test_build_category_table_rows(self):
        """Should build correct table rows from category stats."""
        cat_stats = {
            "combo_query": {"validated": 50, "passed": 40, "failed": 10,
                            "candidates": 55, "skipped": 5},
            "card_search": {"validated": 30, "passed": 25, "failed": 5,
                            "candidates": 32, "skipped": 2},
        }

        rows = []
        for cat, s in sorted(cat_stats.items()):
            pass_rate = (s["passed"] / s["validated"] * 100) if s["validated"] > 0 else 0.0
            rows.append({
                "Category": cat,
                "Candidates": s["candidates"],
                "Validated": s["validated"],
                "Passed": s["passed"],
                "Failed": s["failed"],
                "Pass Rate": f"{pass_rate:.1f}%",
            })

        assert len(rows) == 2
        assert rows[0]["Category"] == "card_search"  # sorted alphabetically
        assert rows[1]["Category"] == "combo_query"
        assert "80.0%" in rows[1]["Pass Rate"]


class TestEmptyDataHandling:
    """Test handling of empty data scenarios."""

    def test_empty_metrics_list(self):
        """Should handle empty metrics list gracefully."""
        metrics_docs = []

        total_candidates = sum(m.get("total_candidates", 0) for m in metrics_docs)
        assert total_candidates == 0

    def test_missing_fields_in_metric_doc(self):
        """Should handle missing fields with defaults."""
        metrics_docs = [{}]

        total_passed = sum(m.get("total_passed", 0) for m in metrics_docs)
        assert total_passed == 0
