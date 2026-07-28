"""Tests for template version tracking in metrics and traces (Story 045).

Verifies:
- TemplateConfig has a `version` field that defaults to None
- GenerationTrace has version fields that default to None
- ValidationMetrics tracks template versions and includes them in summary()
- TemplateStore.to_template_config() populates version from doc
"""

from __future__ import annotations

import pytest
import yaml

from .common import TemplateConfig
from .models import GenerationTrace, ValidationMetrics
from .template_store import TemplateStore


# =============================================================================
# TemplateConfig
# =============================================================================


class TestTemplateConfigVersion:
    """TemplateConfig.version field tests."""

    def test_template_config_has_version_field(self) -> None:
        """Construct with version=2, verify it is stored."""
        tc = TemplateConfig("tid", "do stuff", version=2)
        assert tc.version == 2

    def test_template_config_version_defaults_none(self) -> None:
        """Construct without version — must default to None."""
        tc = TemplateConfig("tid", "do stuff")
        assert tc.version is None

    def test_template_config_frozen_with_version(self) -> None:
        """Frozen dataclass: cannot assign after construction."""
        tc = TemplateConfig("tid", "do stuff", version=3)
        with pytest.raises(AttributeError):
            tc.version = 4  # type: ignore[misc]


# =============================================================================
# GenerationTrace
# =============================================================================


class TestGenerationTraceVersion:
    """GenerationTrace version field tests."""

    def test_trace_has_version_fields(self) -> None:
        """Construct with explicit version fields, verify stored."""
        trace = GenerationTrace(
            item_id="i1",
            run_id="r1",
            template_version=2,
            validator_template_version=3,
        )
        assert trace.template_version == 2
        assert trace.validator_template_version == 3

    def test_trace_version_defaults_none(self) -> None:
        """Construct without version fields — must default to None."""
        trace = GenerationTrace(item_id="i1", run_id="r1")
        assert trace.template_version is None
        assert trace.validator_template_version is None


# =============================================================================
# ValidationMetrics
# =============================================================================


class TestValidationMetricsVersion:
    """ValidationMetrics template version tracking tests."""

    def test_record_template_version(self) -> None:
        """record_template_version populates the correct dict."""
        m = ValidationMetrics(run_id="r1")
        m.record_template_version("how_does_it_work", 2)
        assert m.template_versions == {"how_does_it_work": 2}

    def test_record_validator_template_version(self) -> None:
        """record_template_version with is_validator=True populates validator dict."""
        m = ValidationMetrics(run_id="r1")
        m.record_template_version("shared", 5, is_validator=True)
        assert m.validator_template_versions == {"shared": 5}

    def test_multiple_template_versions(self) -> None:
        """Multiple calls accumulate into the dicts."""
        m = ValidationMetrics(run_id="r1")
        m.record_template_version("tid1", 1)
        m.record_template_version("tid2", 3)
        assert m.template_versions == {"tid1": 1, "tid2": 3}

    def test_overwrite_template_version(self) -> None:
        """Calling again with same template_id overwrites."""
        m = ValidationMetrics(run_id="r1")
        m.record_template_version("tid", 1)
        m.record_template_version("tid", 2)
        assert m.template_versions == {"tid": 2}

    def test_summary_includes_versions(self) -> None:
        """summary() dict contains template_versions and validator_template_versions."""
        m = ValidationMetrics(run_id="r1")
        m.record_template_version("tid", 4)
        m.record_template_version("shared", 2, is_validator=True)
        s = m.summary()
        assert "template_versions" in s
        assert "validator_template_versions" in s
        assert s["template_versions"] == {"tid": 4}
        assert s["validator_template_versions"] == {"shared": 2}

    def test_summary_versions_default_empty(self) -> None:
        """summary() versions are empty dicts when nothing recorded."""
        m = ValidationMetrics(run_id="r1")
        s = m.summary()
        assert s["template_versions"] == {}
        assert s["validator_template_versions"] == {}


# =============================================================================
# TemplateStore.to_template_config — version populated
# =============================================================================


class TestTemplateStoreVersion:
    """TemplateStore.to_template_config populates version from doc."""

    def test_store_to_template_config_populates_version(self) -> None:
        """Mock doc with version=3 → TemplateConfig.version == 3."""
        doc = {
            "template_id": "test_tid",
            "version": 3,
            "yaml_content": yaml.dump({
                "instruction": "Test instruction",
                "weight": 1.5,
            }),
        }
        tc = TemplateStore.to_template_config(doc)
        assert tc.version == 3
        assert tc.template_id == "test_tid"
        assert tc.task_instruction == "Test instruction"
        assert tc.weight == 1.5

    def test_store_to_template_config_version_none_when_missing(self) -> None:
        """Doc without 'version' key → TemplateConfig.version is None."""
        doc = {
            "template_id": "test_tid",
            "yaml_content": yaml.dump({"instruction": "Test instruction"}),
        }
        tc = TemplateStore.to_template_config(doc)
        assert tc.version is None
