"""Unit tests for :meth:`TemplateStore.to_template_config`.

This is a pure static method that parses a dict into :class:`TemplateConfig`
and is reused by the YAML loader. MongoDB CRUD behaviour is tested elsewhere
or is no longer relevant after the YAML template migration.
"""

from __future__ import annotations

import pytest

from training_data.generate_synthetic_data.common import TemplateConfig
from training_data.generate_synthetic_data.template_store import TemplateStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_doc(
    generator: str = "combo_query",
    template_id: str = "how_does_it_work",
    template_type: str = "generation",
    version: int = 1,
    yaml_content: str = "instruction: hi\n",
    is_latest: bool = True,
    oid: str | None = None,
) -> dict:
    """Build a fake template doc."""
    return {
        "_id": oid if oid is not None else f"{generator}-{template_id}-{template_type}-v{version}",
        "generator": generator,
        "template_id": template_id,
        "template_type": template_type,
        "version": version,
        "yaml_content": yaml_content,
        "created_at": "2026-07-26T00:00:00Z",
        "is_latest": is_latest,
    }


# ---------------------------------------------------------------------------
# to_template_config
# ---------------------------------------------------------------------------
class TestToTemplateConfig:
    def test_to_template_config_full(self):
        yaml_body = (
            "instruction: |\n"
            "  Generate exactly 3 Q&A pairs explaining HOW this combo works.\n"
            "weight: 2.5\n"
            "validation_rules:\n"
            "  - \"Answer must explain each card's role in the combo\"\n"
            "  - \"All card names and effects must be accurate\"\n"
            "min_answer_length: 100\n"
            "max_answer_length: 3000\n"
        )
        doc = _make_doc(template_id="how_does_it_work", yaml_content=yaml_body)

        cfg = TemplateStore.to_template_config(doc)

        assert isinstance(cfg, TemplateConfig)
        assert cfg.template_id == "how_does_it_work"
        assert cfg.task_instruction.startswith("Generate exactly 3")
        assert cfg.weight == 2.5
        assert cfg.validation_rules == [
            "Answer must explain each card's role in the combo",
            "All card names and effects must be accurate",
        ]
        assert cfg.min_answer_length == 100
        assert cfg.max_answer_length == 3000

    def test_to_template_config_defaults(self):
        """Missing YAML fields fall back to TemplateConfig defaults."""
        doc = _make_doc(template_id="minimal", yaml_content="instruction: hi\n")

        cfg = TemplateStore.to_template_config(doc)

        assert cfg.template_id == "minimal"
        assert cfg.task_instruction == "hi"
        assert cfg.weight == 1.0
        assert cfg.validation_rules == []
        assert cfg.min_answer_length == 80
        assert cfg.max_answer_length == 2000

    def test_to_template_config_empty_yaml(self):
        """Empty yaml_content yields defaults (safe_load returns None)."""
        doc = _make_doc(template_id="empty", yaml_content="")

        cfg = TemplateStore.to_template_config(doc)

        assert cfg.template_id == "empty"
        assert cfg.task_instruction == ""
        assert cfg.weight == 1.0
        assert cfg.validation_rules == []

    def test_to_template_config_uses_doc_template_id(self):
        """The template_id comes from the doc, not the YAML body."""
        doc = _make_doc(template_id="from_doc", yaml_content="instruction: x\n")
        cfg = TemplateStore.to_template_config(doc)
        assert cfg.template_id == "from_doc"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
