"""Unit tests for GenerateCommanderKnowledge."""

from __future__ import annotations

import sys
import os
from unittest.mock import MagicMock

# Ensure the generate_synthetic_data package is on the path for imports.
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(__file__), "..", "training_data", "generate_synthetic_data"
    ),
)

from training_data.generate_synthetic_data.generate_commander_knowledge import (
    GenerateCommanderKnowledge,
    CommanderKnowledgeBatch,
)
from training_data.generate_synthetic_data.models import (
    Model,
    ModelType,
    QuestionAnswerEnhanced,
)
from training_data.generate_synthetic_data.common import (
    TemplateConfig,
    MTG_NOTATION_LEGEND,
)
from training_data.generate_synthetic_data.data_access import MTGDataAccess
from training_data.generate_synthetic_data.domain_models import Rule, CardWithMetadata


def _make_data_access():
    """Return a mocked data_access with one rule and one card available."""
    da = MagicMock(spec=MTGDataAccess)
    da.get_rules.return_value = [
        Rule(
            rule_number="903.5",
            section="903",
            text="Each Commander deck is subject to the following deck construction rules. "
            "903.5a Each deck must contain exactly 100 cards, including its commander.",
        )
    ]
    da.get_cards_enriched.return_value = [
        CardWithMetadata(
            name="Sol Ring",
            type="Artifact",
            mana_cost="{1}",
            text="{T}: Add {C}.",
            color_identity=[],
        )
    ]
    return da


def _make_instance(**overrides) -> GenerateCommanderKnowledge:
    """Create a GenerateCommanderKnowledge with mocked dependencies."""
    defaults = dict(
        data_access=_make_data_access(),
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
    return GenerateCommanderKnowledge(**defaults)


class TestTemplatesDefined:
    def test_has_two_templates(self):
        gen = _make_instance()
        assert len(gen.TEMPLATES) == 2

    def test_template_ids(self):
        gen = _make_instance()
        ids = {t.template_id for t in gen.TEMPLATES}
        assert ids == {"general_advice", "example_driven"}

    def test_templates_are_config_instances(self):
        gen = _make_instance()
        for t in gen.TEMPLATES:
            assert isinstance(t, TemplateConfig)


class TestDataBatches:
    def test_yields_commander_knowledge_batch(self):
        gen = _make_instance()
        batch = next(gen.get_data_batches())
        assert isinstance(batch, CommanderKnowledgeBatch)

    def test_yields_all_subtopics(self):
        gen = _make_instance()
        batches: list[CommanderKnowledgeBatch] = []
        iterator = gen.get_data_batches()
        for _ in range(len(gen.COMMANDER_SUBTOPICS)):
            batches.append(next(iterator))
        topic_names = [b.topic for b in batches]
        expected_names = [t[0] for t in gen.COMMANDER_SUBTOPICS]
        assert topic_names == expected_names

    def test_has_8_subtopics(self):
        gen = _make_instance()
        assert len(gen.COMMANDER_SUBTOPICS) == 8

    def test_is_infinite_iterator(self):
        gen = _make_instance()
        iterator = gen.get_data_batches()
        for _ in range(len(gen.COMMANDER_SUBTOPICS) + 5):
            next(iterator)

    def test_batch_includes_topic_context(self):
        gen = _make_instance()
        batch = next(gen.get_data_batches())
        assert batch.topic_context
        assert batch.topic == gen.COMMANDER_SUBTOPICS[0][0]

    def test_batch_grounded_with_rules_and_cards(self):
        gen = _make_instance()
        batch = next(gen.get_data_batches())
        assert any(r.rule_number == "903.5" for r in batch.relevant_rules)
        assert any(c.name == "Sol Ring" for c in batch.key_cards)


class TestSourceCategory:
    def test_returns_correct_category(self):
        gen = _make_instance()
        assert gen.get_source_category() == "commander_rules"


class TestBuildPrompt:
    def _first_batch(self, gen):
        return next(gen.get_data_batches())

    def test_includes_subtopic_context(self):
        gen = _make_instance()
        template = gen.TEMPLATES[0]
        prompt = gen.build_prompt(template, self._first_batch(gen))
        assert gen.COMMANDER_SUBTOPICS[0][0] in prompt

    def test_includes_mtg_notation_legend(self):
        gen = _make_instance()
        template = gen.TEMPLATES[0]
        prompt = gen.build_prompt(template, self._first_batch(gen))
        assert MTG_NOTATION_LEGEND in prompt

    def test_includes_output_format(self):
        gen = _make_instance()
        template = gen.TEMPLATES[0]
        prompt = gen.build_prompt(template, self._first_batch(gen))
        assert "question" in prompt
        assert "answer" in prompt

    def test_includes_task_tags(self):
        gen = _make_instance()
        template = gen.TEMPLATES[0]
        prompt = gen.build_prompt(template, self._first_batch(gen))
        assert "<task>" in prompt
        assert "</task>" in prompt

    def test_includes_rules_block(self):
        gen = _make_instance()
        template = gen.TEMPLATES[0]
        prompt = gen.build_prompt(template, self._first_batch(gen))
        assert "<rules>" in prompt
        assert "</rules>" in prompt
        assert "903.5" in prompt

    def test_includes_commanders_and_key_cards_blocks(self):
        gen = _make_instance()
        template = gen.TEMPLATES[0]
        prompt = gen.build_prompt(template, self._first_batch(gen))
        assert "<commanders>" in prompt
        assert "</commanders>" in prompt
        assert "<key_cards>" in prompt
        assert "</key_cards>" in prompt
        assert "Sol Ring" in prompt

    def test_prompt_requires_real_cards_only(self):
        gen = _make_instance()
        template = gen.TEMPLATES[0]
        prompt = gen.build_prompt(template, self._first_batch(gen))
        assert "do not invent" in prompt.lower() or "never invent" in prompt.lower()

    def test_prompt_grounded_in_rules(self):
        gen = _make_instance()
        template = gen.TEMPLATES[0]
        prompt = gen.build_prompt(template, self._first_batch(gen))
        assert "ground truth" in prompt.lower() or "authoritative" in prompt.lower()


class TestBuildContext:
    def test_returns_category_and_template(self):
        gen = _make_instance()
        template = gen.TEMPLATES[0]
        batch = next(gen.get_data_batches())
        context = gen.build_context(template, batch)
        assert "commander_rules" in context
        assert template.template_id in context

    def test_includes_topic_name(self):
        gen = _make_instance()
        template = gen.TEMPLATES[0]
        batch = next(gen.get_data_batches())
        context = gen.build_context(template, batch)
        assert batch.topic in context

    def test_includes_topic_context(self):
        gen = _make_instance()
        template = gen.TEMPLATES[0]
        batch = next(gen.get_data_batches())
        context = gen.build_context(template, batch)
        assert batch.topic_context in context

    def test_includes_grounding_data(self):
        gen = _make_instance()
        template = gen.TEMPLATES[0]
        batch = next(gen.get_data_batches())
        context = gen.build_context(template, batch)
        assert "903.5" in context
        assert "Sol Ring" in context


class TestGetSourceData:
    def test_includes_rules_and_cards(self):
        gen = _make_instance()
        batch = next(gen.get_data_batches())
        sources = gen.get_source_data(batch)
        rule_sources = [s for s in sources if "rule_number" in s]
        card_sources = [s for s in sources if "name" in s]
        assert any(s["rule_number"] == "903.5" for s in rule_sources)
        assert any(s["name"] == "Sol Ring" for s in card_sources)

    def test_sources_include_card_roles(self):
        gen = _make_instance()
        batch = next(gen.get_data_batches())
        sources = gen.get_source_data(batch)
        for s in sources:
            if "name" in s:
                assert s["role"] in {"commander", "key_card"}


class TestDryRun:
    def test_dry_run_does_not_call_save_item(self):
        save_item = MagicMock()
        gen = _make_instance(save_item=save_item, dry_run=True, target_count=1)
        mock_qm = MagicMock()
        gen.query_model = mock_qm

        mock_qm.query.return_value = '[{"question": "Test Q?", "answer": "Test answer that is long enough to pass validation checks and provides accurate Commander rules information."}]'
        mock_qm.validate_qa.return_value = (True, "Looks good", 9.0)

        batch = next(gen.get_data_batches())

        from unittest.mock import patch

        with patch.object(
            gen,
            "validate_answer",
            return_value=(True, QuestionAnswerEnhanced("Q", "A")),
        ):
            with patch.object(gen, "select_templates", return_value=[gen.TEMPLATES[0]]):
                gen._process_item(batch)

        save_item.assert_not_called()
        assert gen.generated_count == 1
