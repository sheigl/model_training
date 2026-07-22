"""Unit tests for GenerateArchetypes."""

from __future__ import annotations

import sys
import os
from unittest.mock import MagicMock, patch

# Ensure the generate_synthetic_data package is on the path for imports.
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(__file__), "..", "training_data", "generate_synthetic_data"
    ),
)

from training_data.generate_synthetic_data.generate_archetypes import GenerateArchetypes
from training_data.generate_synthetic_data.models import (
    Model,
    ModelType,
    QuestionAnswerEnhanced,
)
from training_data.generate_synthetic_data.common import (
    TemplateConfig,
    MTG_NOTATION_LEGEND,
)


def _make_instance(**overrides) -> GenerateArchetypes:
    """Create a GenerateArchetypes with mocked dependencies."""
    defaults = dict(
        models={
            ModelType.GENERATION: Model(name="test-gen", type=ModelType.GENERATION),
            ModelType.VALIDATION: Model(name="test-val", type=ModelType.VALIDATION),
        },
        validation_pct=1.0,
        target_count=100,
        save_item=MagicMock(),
        metrics=None,
        dry_run=False,
    )
    defaults.update(overrides)
    return GenerateArchetypes(**defaults)


class TestTemplatesDefined:
    def test_has_two_templates(self):
        gen = _make_instance()
        assert len(gen.TEMPLATES) == 2

    def test_template_ids(self):
        gen = _make_instance()
        ids = {t.template_id for t in gen.TEMPLATES}
        assert ids == {"general_advice", "example_driven"}

    def templates_are_config_instances(self):
        gen = _make_instance()
        for t in gen.TEMPLATES:
            assert isinstance(t, TemplateConfig)


class TestDataBatches:
    def test_yields_all_archetypes(self):
        gen = _make_instance()
        batches: list[list[str]] = []
        iterator = gen.get_data_batches()
        for _ in range(len(gen.ARCHETYPES)):
            batches.append(next(iterator))
        archetype_names = [b[0] for b in batches]
        expected_names = [a[0] for a in gen.ARCHETYPES]
        assert archetype_names == expected_names

    def test_has_10_archetypes(self):
        gen = _make_instance()
        assert len(gen.ARCHETYPES) == 10

    def test_is_infinite_iterator(self):
        gen = _make_instance()
        iterator = gen.get_data_batches()
        for _ in range(len(gen.ARCHETYPES) + 5):
            next(iterator)

    def test_yields_lists(self):
        gen = _make_instance()
        iterator = gen.get_data_batches()
        batch = next(iterator)
        assert isinstance(batch, list)
        assert len(batch) == 1
        assert isinstance(batch[0], str)


class TestSourceCategory:
    def test_returns_correct_category(self):
        gen = _make_instance()
        assert gen.get_source_category() == "archetype"


class TestBuildPrompt:
    def test_includes_archetype_name(self):
        gen = _make_instance()
        template = gen.TEMPLATES[0]
        archetype_name = gen.ARCHETYPES[0][0]
        prompt = gen.build_prompt(template, archetype_name)
        assert archetype_name in prompt

    def test_includes_archetype_context(self):
        gen = _make_instance()
        template = gen.TEMPLATES[0]
        archetype_name = gen.ARCHETYPES[0][0]
        expected_context = gen.ARCHETYPES[0][1]
        prompt = gen.build_prompt(template, archetype_name)
        assert expected_context in prompt

    def test_includes_mtg_notation_legend(self):
        gen = _make_instance()
        template = gen.TEMPLATES[0]
        archetype_name = gen.ARCHETYPES[0][0]
        prompt = gen.build_prompt(template, archetype_name)
        assert MTG_NOTATION_LEGEND in prompt

    def test_includes_output_format(self):
        gen = _make_instance()
        template = gen.TEMPLATES[0]
        archetype_name = gen.ARCHETYPES[0][0]
        prompt = gen.build_prompt(template, archetype_name)
        assert "question" in prompt
        assert "answer" in prompt

    def test_includes_task_tags(self):
        gen = _make_instance()
        template = gen.TEMPLATES[0]
        archetype_name = gen.ARCHETYPES[0][0]
        prompt = gen.build_prompt(template, archetype_name)
        assert "<task>" in prompt
        assert "</task>" in prompt


class TestBuildContext:
    def test_returns_category_and_template(self):
        gen = _make_instance()
        template = gen.TEMPLATES[0]
        archetype_name = gen.ARCHETYPES[0][0]
        context = gen.build_context(template, archetype_name)
        assert "archetype" in context
        assert template.template_id in context

    def test_includes_archetype_name(self):
        gen = _make_instance()
        template = gen.TEMPLATES[0]
        archetype_name = gen.ARCHETYPES[0][0]
        context = gen.build_context(template, archetype_name)
        assert archetype_name in context

    def test_includes_archetype_context(self):
        gen = _make_instance()
        template = gen.TEMPLATES[0]
        archetype_name = gen.ARCHETYPES[0][0]
        expected_context = gen.ARCHETYPES[0][1]
        context = gen.build_context(template, archetype_name)
        assert expected_context in context


class TestNoPymongoImport:
    def test_no_pymongo_import(self):
        """Verify the module doesn't import pymongo directly."""
        import training_data.generate_synthetic_data.generate_archetypes as mod

        source = open(mod.__file__).read()
        assert "import pymongo" not in source
        assert "from pymongo" not in source


class TestDryRun:
    def test_dry_run_does_not_call_save_item(self):
        save_item = MagicMock()
        gen = _make_instance(save_item=save_item, dry_run=True, target_count=1)
        mock_qm = MagicMock()
        gen.query_model = mock_qm

        mock_qm.query.return_value = '[{"question": "Test Q?", "answer": "Test answer that is long enough to pass validation and provides useful archetype strategy information about aggro decks in Commander."}]'
        mock_qm.validate_qa.return_value = (True, "Looks good", 9.0)

        with patch.object(
            gen,
            "validate_answer",
            return_value=(True, QuestionAnswerEnhanced("Q", "A")),
        ):
            with patch.object(gen, "select_templates", return_value=[gen.TEMPLATES[0]]):
                gen._process_item(gen.ARCHETYPES[0][0])

        save_item.assert_not_called()
        assert gen.generated_count == 1
