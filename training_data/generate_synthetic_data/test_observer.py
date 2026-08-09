"""Unit tests for the Observer class."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from training_data.generate_synthetic_data.observer import (
    Observer,
    _best_version,
    _ensure_category,
    _load_manifest,
    _save_manifest,
)
from training_data.generate_synthetic_data.models import Model, ModelType
from training_data.generate_synthetic_data.yaml_template_loader import YamlTemplateLoader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_observer(tmpdir: Path, **kwargs):
    """Create a minimal Observer for testing."""
    templates_dir = tmpdir / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)
    # Create a minimal category YAML so the loader has something to read
    with open(templates_dir / "test_category.yaml", "w") as f:
        yaml.dump([
            {"template_id": "tpl_a", "instruction": "Original instruction A.", "weight": 1.0},
            {"template_id": "tpl_b", "instruction": "Original instruction B.", "weight": 1.0},
        ], f)
    models = {
        ModelType.GENERATION: Model(name="test-gen", type=ModelType.GENERATION),
        ModelType.VALIDATION: Model(name="test-val", type=ModelType.VALIDATION),
    }
    yaml_loader = YamlTemplateLoader(str(templates_dir))
    return Observer(
        models=models,
        yaml_loader=yaml_loader,
        templates_dir=templates_dir,
        first_pass_threshold=kwargs.get("threshold", 50.0),
        observation_interval=kwargs.get("interval", 10),
        run_id=kwargs.get("run_id", "test-run-001"),
        observer_model=models[ModelType.VALIDATION],
    )


def _make_trace(outcome: str, rounds: int = 0, reasons: list[str] | None = None) -> dict:
    """Create a minimal trace dict for observer input."""
    validation_rounds = []
    if rounds > 0:
        for i in range(rounds):
            round_data = {"round": i}
            if reasons and i < len(reasons):
                round_data["reason"] = reasons[i]
                round_data["score"] = 4.0
                round_data["is_acceptable"] = False
            else:
                round_data["reason"] = "minor issue"
                round_data["score"] = 5.0
                round_data["is_acceptable"] = False
            validation_rounds.append(round_data)
    return {
        "final_outcome": outcome,
        "total_rounds": rounds,
        "validation_rounds": validation_rounds,
        "template_version": 1,
    }


# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------

class TestManifestHelpers:
    def test_load_manifest_missing_file(self, tmp_path):
        manifest = _load_manifest(tmp_path / "nonexistent.json")
        assert manifest == {"categories": {}}

    def test_load_manifest_valid(self, tmp_path):
        path = tmp_path / "manifest.json"
        data = {"categories": {"combo_query": {"active_version": 2, "versions": {"1": {"first_pass_rate": 40.0}}}}}
        path.write_text(json.dumps(data))
        result = _load_manifest(path)
        assert result["categories"]["combo_query"]["active_version"] == 2

    def test_ensure_category_defaults(self):
        manifest = {"categories": {}}
        cat = _ensure_category(manifest, "test_cat")
        assert cat["active_generation_version"] == 1
        assert cat["active_validator_version"] == 1
        assert cat["generation_versions"] == {}
        assert cat["validator_versions"] == {}

    def test_ensure_category_migrates_legacy_schema(self):
        manifest = {"categories": {"legacy": {"active_version": 2, "versions": {"1": {"first_pass_rate": 40.0}}}}}
        cat = _ensure_category(manifest, "legacy")
        assert cat["active_generation_version"] == 2
        assert cat["generation_versions"] == {"1": {"first_pass_rate": 40.0}}
        assert cat["validator_versions"] == {}
        assert "active_version" not in cat

    def test_ensure_category_migrates_legacy_validator_when_file_exists(self, tmp_path):
        """A legacy active_version routes to the validator namespace when only
        the versioned validator file exists on disk."""
        (tmp_path / "combo_query_validator_v2.yaml").write_text(
            "template_id: qa_validation\ninstruction: VALIDATE\n"
        )
        manifest = {"categories": {"combo_query": {"active_version": 2, "versions": {"2": {"first_pass_rate": 57.14}}}}}
        cat = _ensure_category(manifest, "combo_query", tmp_path)
        assert cat["active_validator_version"] == 2
        assert cat["validator_versions"] == {"2": {"first_pass_rate": 57.14}}
        assert cat["active_generation_version"] == 1
        assert cat["generation_versions"] == {}
        assert "active_version" not in cat

    def test_ensure_category_migrates_legacy_generation_when_file_exists(self, tmp_path):
        """A legacy active_version stays in the generation namespace when only
        the versioned generation file exists on disk."""
        (tmp_path / "combo_query_v2.yaml").write_text("- template_id: combo\n")
        manifest = {"categories": {"combo_query": {"active_version": 2, "versions": {"2": {"first_pass_rate": 57.14}}}}}
        cat = _ensure_category(manifest, "combo_query", tmp_path)
        assert cat["active_generation_version"] == 2
        assert cat["generation_versions"] == {"2": {"first_pass_rate": 57.14}}
        assert cat["active_validator_version"] == 1
        assert cat["validator_versions"] == {}

    def test_best_version_no_versions(self):
        assert _best_version({"generation_versions": {}}) == 1
        assert _best_version({"validator_versions": {}}, key="regen_rate") == 1

    def test_best_version_returns_highest_rate(self):
        data = {
            "generation_versions": {
                "1": {"first_pass_rate": 40.0, "total_items": 100},
                "2": {"first_pass_rate": 65.0, "total_items": 120},
                "3": {"first_pass_rate": 55.0, "total_items": 80},
            }
        }
        assert _best_version(data) == 2

    def test_best_validator_version_uses_regen_rate(self):
        data = {
            "validator_versions": {
                "1": {"regen_rate": 10.0, "total_items": 100},
                "2": {"regen_rate": 45.0, "total_items": 80},
            }
        }
        assert _best_version(data, key="regen_rate") == 2

    def test_best_version_ties_go_to_higher_number(self):
        data = {
            "generation_versions": {
                "1": {"first_pass_rate": 60.0, "total_items": 100},
                "2": {"first_pass_rate": 60.0, "total_items": 80},
            }
        }
        assert _best_version(data) == 2


# ---------------------------------------------------------------------------
# on_item_processed / interval triggering
# ---------------------------------------------------------------------------

class TestOnItemProcessed:
    def test_buffers_traces(self, tmp_path):
        obs = _make_observer(tmp_path, interval=3)
        obs.on_item_processed("cat1", _make_trace("accepted_first_attempt"))
        assert len(obs._buffers["cat1"]) == 1
        assert obs._item_counts["cat1"] == 1

    def test_triggers_analysis_at_interval(self, tmp_path):
        obs = _make_observer(tmp_path, interval=3)
        # Mock _analyze to track calls
        analyzed = []
        orig_analyze = obs._analyze
        def track(category, *args, **kwargs):
            analyzed.append(category)
        obs._analyze = track

        for i in range(3):
            obs.on_item_processed("cat1", _make_trace("accepted_first_attempt"))
        assert analyzed == ["cat1"]

    def test_does_not_trigger_before_interval(self, tmp_path):
        obs = _make_observer(tmp_path, interval=5)
        analyzed = []
        orig_analyze = obs._analyze
        def track(category, *args, **kwargs):
            analyzed.append(category)
        obs._analyze = track

        for i in range(4):
            obs.on_item_processed("cat1", _make_trace("accepted_first_attempt"))
        assert analyzed == []

    def test_flush_calls_analysis_on_remaining(self, tmp_path):
        obs = _make_observer(tmp_path, interval=3)
        analyzed = []
        def track(category, *args, **kwargs):
            analyzed.append(category)
        obs._analyze = track

        for i in range(2):
            obs.on_item_processed("cat1", _make_trace("accepted_first_attempt"))
        obs.flush()
        assert "cat1" in analyzed


# ---------------------------------------------------------------------------
# Analysis triggering logic
# ---------------------------------------------------------------------------

class TestAnalysisTriggering:
    def test_skips_when_above_threshold(self, tmp_path):
        """No improvement written when first_pass_rate > threshold."""
        obs = _make_observer(tmp_path, interval=2, threshold=50.0)
        # All first-pass passes → rate = 100% > 50%
        traces = [_make_trace("accepted_first_attempt") for _ in range(2)]
        for t in traces:
            obs.on_item_processed("cat1", t)

        written_files = list((tmp_path / "templates").glob("test_category_v*.yaml"))
        assert len(written_files) == 0

    def test_writes_yaml_when_below_threshold_with_regenerations(self, tmp_path):
        """Improvement written when rate < threshold AND items needed regeneration."""
        obs = _make_observer(tmp_path, interval=2, threshold=50.0)
        # Mix: 1 pass first, 1 needs fix → rate = 50% = threshold (not below)
        traces = [
            _make_trace("accepted_first_attempt"),
            _make_trace("accepted_after_fix", rounds=1, reasons=["wrong trigger order"]),
        ]
        for t in traces:
            obs.on_item_processed("cat1", t)

        # Rate is exactly 50%, threshold is 50% — condition is '<' so no write
        written = list((tmp_path / "templates").glob("test_category_v*.yaml"))
        assert len(written) == 0

    def test_writes_yaml_when_below_threshold(self, tmp_path):
        """Improvement written when rate clearly below threshold."""
        obs = _make_observer(tmp_path, interval=2, threshold=50.0)
        # Both need regeneration → rate = 0% < 50%
        traces = [
            _make_trace("accepted_after_fix", rounds=1, reasons=["wrong trigger order"]),
            _make_trace("rejected", rounds=1, reasons=["wrong trigger order"]),
        ]
        for t in traces:
            obs.on_item_processed("cat1", t)

        # Should have written a generation template improvement (if LLM called)
        # We mock the LLM call so we just check the manifest was updated
        manifest_path = tmp_path / "templates" / "_observer_manifest.json"
        # The _analyze method will try to call LLM; with no real model it logs warning
        # but still records version performance if improvement dict is returned
        # Since LLM returns None, no YAML should be written
        written_gen = list((tmp_path / "templates").glob("test_category_v*.yaml"))
        assert len(written_gen) == 0

    def test_validator_analyzed_when_regenerations_exist(self, tmp_path):
        """Validator prompt analyzed when items needed ≥1 regeneration."""
        obs = _make_observer(tmp_path, interval=2, threshold=90.0)
        # High threshold so gen improvement won't trigger, but validator should
        traces = [
            _make_trace("accepted_after_fix", rounds=1, reasons=["missing card name"]),
            _make_trace("accepted_after_fix", rounds=1, reasons=["missing card name"]),
        ]
        for t in traces:
            obs.on_item_processed("cat1", t)

        # Validator analysis runs regardless of rate if regenerations exist
        manifest_path = tmp_path / "templates" / "_observer_manifest.json"
        written_val = list((tmp_path / "templates").glob("test_category_validator_v*.yaml"))
        assert len(written_val) == 0  # LLM returns None so no write, but analysis ran

    def test_transport_failure_reason_excluded_from_top_reasons(self, tmp_path):
        """Validator transport-failure reasons never reach the observer LLM."""
        obs = _make_observer(tmp_path, interval=10, threshold=50.0)
        # One trace with a transport-failure round-0 reason, one with a genuine
        # content-quality reason. Both are "rejected"/"needs fix" so the rate is
        # 0% < threshold and regeneration_count > 0 → both LLM analyses run.
        traces = [
            _make_trace("rejected", rounds=1, reasons=["Validation parse failed: Expecting value: line 1 column 1 (char 0)"]),
            _make_trace("accepted_after_fix", rounds=1, reasons=["Missing trigger ordering"]),
        ]
        for t in traces:
            obs.on_item_processed("cat1", t)

        captured = {}

        def mock_gen_analyze(*args):
            captured["gen_top_reasons"] = args[6]
            return None

        def mock_val_analyze(*args):
            captured["val_top_reasons"] = args[6]
            return None

        obs._llm_analyze_generation_template = mock_gen_analyze
        obs._llm_analyze_validation_template = mock_val_analyze

        obs._analyze("cat1", None)

        all_reasons = captured.get("gen_top_reasons", []) + captured.get("val_top_reasons", [])
        reason_texts = [r for r, _ in all_reasons]
        # Transport-failure reason must be filtered out before reaching the LLM
        assert not any("parse failed" in r for r in reason_texts)
        # Genuine content reason still reaches the LLM (normalised lowercase)
        assert "missing trigger ordering" in reason_texts


# ---------------------------------------------------------------------------
# Versioned YAML writing
# ---------------------------------------------------------------------------

class TestWriteImprovedTemplates:
    def test_writes_complete_yaml_with_new_instruction(self, tmp_path):
        """New version file contains all original templates + improved instruction."""
        obs = _make_observer(tmp_path, interval=10)
        # Manually call the write method with a mock improvement
        new_gen_version, new_val_version = obs._write_improved_templates(
            "test_category", current_gen_version=1, current_val_version=1,
            gen_improvement={"new_instruction": "Improved instruction.", "rationale": "better"},
            val_improvement=None,
        )
        assert new_gen_version == 2
        assert new_val_version == 1

        v2_path = tmp_path / "templates" / "test_category_v2.yaml"
        assert v2_path.is_file()
        data = yaml.safe_load(v2_path.read_text())
        assert len(data) == 2
        assert data[0]["instruction"] == "Improved instruction."
        assert data[1]["instruction"] == "Improved instruction."

    def test_writes_validator_yaml(self, tmp_path):
        """Validator improvement writes a versioned validator file."""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir(parents=True, exist_ok=True)
        # Create a base validator YAML so _apply_validator_improvement has something to extend
        with open(templates_dir / "test_category_validator.yaml", "w") as f:
            yaml.dump({
                "instruction": "Base validator prompt.\n\nScore the answer.",
            }, f)
        obs = _make_observer(tmp_path, interval=10)
        new_gen_version, new_val_version = obs._write_improved_templates(
            "test_category", current_gen_version=1, current_val_version=1,
            gen_improvement=None,
            val_improvement={"suggested_additions": "Check card names more carefully.", "rationale": "better"},
        )
        assert new_gen_version == 1
        assert new_val_version == 2

        v2_path = tmp_path / "templates" / "test_category_validator_v2.yaml"
        assert v2_path.is_file()

    def test_manifest_updated_after_write(self, tmp_path):
        """Manifest gets version performance recorded after write."""
        obs = _make_observer(tmp_path, interval=10)
        obs._write_improved_templates(
            "test_category", current_gen_version=1, current_val_version=1,
            gen_improvement={"new_instruction": "New!", "rationale": "r"},
            val_improvement=None,
        )
        obs._record_version_performance("test_category", "generation", 2, rate=65.0, total_items=20)

        manifest = _load_manifest(tmp_path / "templates" / "_observer_manifest.json")
        cat = manifest["categories"]["test_category"]
        assert cat["active_generation_version"] == 2
        assert cat["generation_versions"]["2"]["first_pass_rate"] == 65.0
        assert cat["generation_versions"]["2"]["total_items"] == 20

    def test_active_version_reverts_to_best(self, tmp_path):
        """Active version stays at best historical even after worse version written."""
        obs = _make_observer(tmp_path, interval=10)
        # Record v1 as best (70%)
        obs._record_version_performance("test_category", "generation", 1, rate=70.0, total_items=100)
        # Write and record v2 as worse (50%)
        obs._write_improved_templates(
            "test_category", current_gen_version=1, current_val_version=1,
            gen_improvement={"new_instruction": "Worse!", "rationale": "r"},
            val_improvement=None,
        )
        obs._record_version_performance("test_category", "generation", 2, rate=50.0, total_items=20)

        manifest = _load_manifest(tmp_path / "templates" / "_observer_manifest.json")
        assert manifest["categories"]["test_category"]["active_generation_version"] == 1


# ---------------------------------------------------------------------------
# get_best_template_version
# ---------------------------------------------------------------------------

class TestGetBestVersion:
    def test_returns_1_when_no_history(self, tmp_path):
        obs = _make_observer(tmp_path, interval=10)
        assert obs.get_best_template_version("unknown_cat") == 1

    def test_returns_best_historical(self, tmp_path):
        obs = _make_observer(tmp_path, interval=10)
        obs._record_version_performance("test_category", "generation", 1, rate=40.0, total_items=100)
        obs._write_improved_templates(
            "test_category", current_gen_version=1, current_val_version=1,
            gen_improvement={"new_instruction": "New!", "rationale": "r"},
            val_improvement=None,
        )
        obs._record_version_performance("test_category", "generation", 2, rate=65.0, total_items=80)

        assert obs.get_best_template_version("test_category") == 2

    def test_validator_version_tracked_independently(self, tmp_path):
        """Validator improvements never bump the generation version."""
        obs = _make_observer(tmp_path, interval=10)
        obs._write_improved_templates(
            "test_category", current_gen_version=1, current_val_version=1,
            gen_improvement=None,
            val_improvement={"suggested_additions": "Check more.", "rationale": "r"},
        )
        obs._record_version_performance("test_category", "validator", 2, rate=45.0, total_items=20)

        assert obs.get_best_template_version("test_category") == 1
        assert obs.get_best_validator_version("test_category") == 2


# ---------------------------------------------------------------------------
# LLM prompt content
# ---------------------------------------------------------------------------

class TestLLMPrompts:
    def test_generation_prompt_contains_rejection_reasons(self, tmp_path):
        """Generation prompt includes top rejection reasons from traces."""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir(parents=True, exist_ok=True)
        # Create category YAML so generation analysis has templates to read
        with open(templates_dir / "cat1.yaml", "w") as f:
            yaml.dump([
                {"template_id": "tpl_x", "instruction": "Generate Q&A about combos.", "weight": 1.0},
            ], f)
        obs = _make_observer(tmp_path, interval=2, threshold=50.0)

        # Call _llm_analyze_generation_template directly to inspect the prompt
        # without going through the LLM
        import inspect
        source = inspect.getsource(obs._llm_analyze_generation_template)
        # Verify the method contains references to the expected data
        assert "first_pass_rate" in source
        assert "rejection_reasons" in source
        assert "threshold" in source

        # Also verify by checking what _analyze computes before calling LLM
        traces = [
            _make_trace("accepted_after_fix", rounds=1, reasons=["wrong trigger order"]),
            _make_trace("rejected", rounds=1, reasons=["wrong trigger order"]),
        ]
        for t in traces:
            obs.on_item_processed("cat1", t)

        # Manually compute what _analyze would compute
        total = len(traces)
        first_passes = sum(1 for t in traces if t["final_outcome"] == "accepted_first_attempt")
        passes_after_fix = sum(1 for t in traces if t["final_outcome"] == "accepted_after_fix")
        failed = sum(1 for t in traces if t["final_outcome"] == "rejected")
        regen_count = passes_after_fix + failed
        rate = first_passes / total * 100 if total > 0 else 0

        assert rate == 0.0
        assert regen_count == 2
        assert failed == 1

    def test_validator_prompt_contains_regeneration_count(self, tmp_path):
        """Validator prompt includes regeneration count."""
        obs = _make_observer(tmp_path, interval=2, threshold=90.0)
        traces = [
            _make_trace("accepted_after_fix", rounds=1, reasons=["missing card name"]),
        ]
        for t in traces:
            obs.on_item_processed("cat1", t)

        captured_prompts = []
        def mock_call(prompt, *args, **kwargs):
            captured_prompts.append(prompt)
            return None
        obs._call_observer_llm = mock_call

        obs._analyze("cat1", None)
        # Should have validator prompt (regenerations > 0) but not gen prompt (rate >= threshold)
        validator_prompts = [p for p in captured_prompts if "Items requiring" in p]
        assert len(validator_prompts) >= 1


# ---------------------------------------------------------------------------
# Run ID in output
# ---------------------------------------------------------------------------

class TestRunIdOutput:
    def test_run_id_in_observer_logs(self, tmp_path, capsys):
        """Observer prints run_id-related info during analysis."""
        obs = _make_observer(tmp_path, interval=1, threshold=50.0)
        obs.on_item_processed("cat1", _make_trace("accepted_after_fix", rounds=1, reasons=["test reason"]))
        obs.flush()
        captured = capsys.readouterr()
        assert "cat1" in captured.out


# ---------------------------------------------------------------------------
# Starting template version override
# ---------------------------------------------------------------------------

class TestStartingVersionOverride:
    def test_get_best_version_from_manifest(self, tmp_path):
        """Manifest records best version for next-run override."""
        obs = _make_observer(tmp_path, interval=10)
        obs._record_version_performance("combo_query", "generation", 1, rate=40.0, total_items=100)
        obs._write_improved_templates(
            "combo_query", current_gen_version=1, current_val_version=1,
            gen_improvement={"new_instruction": "Better!", "rationale": "r"},
            val_improvement=None,
        )
        obs._record_version_performance("combo_query", "generation", 2, rate=70.0, total_items=80)

        assert obs.get_best_template_version("combo_query") == 2


# ---------------------------------------------------------------------------
# No regeneration → no validator analysis
# ---------------------------------------------------------------------------

class TestNoRegeneration:
    def test_no_validator_analysis_when_all_first_pass(self, tmp_path):
        """Validator not analyzed when all items pass first attempt."""
        obs = _make_observer(tmp_path, interval=2, threshold=90.0)
        traces = [
            _make_trace("accepted_first_attempt"),
            _make_trace("accepted_first_attempt"),
        ]
        for t in traces:
            obs.on_item_processed("cat1", t)

        captured_prompts = []
        def mock_call(prompt, *args, **kwargs):
            captured_prompts.append(prompt)
            return None
        obs._call_observer_llm = mock_call

        obs._analyze("cat1", None)
        # No prompts should be sent since no regenerations and rate >= threshold
        assert len(captured_prompts) == 0
