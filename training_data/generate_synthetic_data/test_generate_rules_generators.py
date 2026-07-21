"""Unit tests for the 5 converted rules-grounded generators."""

from dataclasses import dataclass
from unittest.mock import MagicMock, Mock, patch

import pytest

from training_data.generate_synthetic_data.base_generator import BaseGenerator
from training_data.generate_synthetic_data.data_access import MTGDataAccess
from training_data.generate_synthetic_data.domain_models import GlossaryTerm, Rule
from training_data.generate_synthetic_data.generate_glossary_with_examples import (
    GenerateGlossaryWithExamples,
)
from training_data.generate_synthetic_data.generate_rule_edge_cases import (
    GenerateRuleEdgeCases,
)
from training_data.generate_synthetic_data.generate_rule_explanations import (
    GenerateRuleExplanations,
)
from training_data.generate_synthetic_data.generate_rule_interactions import (
    GenerateRuleInteractions,
    ProjectedRulePair,
)
from training_data.generate_synthetic_data.generate_rule_why_questions import (
    GenerateRuleWhyQuestions,
)
from training_data.generate_synthetic_data.models import ModelType, ValidationMetrics


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@dataclass
class MockModel:
    name: str = "test-model"
    type: ModelType = ModelType.GENERATION


def _make_models():
    return {
        ModelType.GENERATION: MockModel("gen", ModelType.GENERATION),
        ModelType.VALIDATION: MockModel("val", ModelType.VALIDATION),
    }


def _make_metrics() -> MagicMock:
    m = MagicMock(spec=ValidationMetrics)
    m.generator_name = "unknown"
    m.generation_model = "unknown"
    m.validation_model = "unknown"
    m.run_id = "test-run-id"
    return m


def _make_data_access():
    da = Mock(spec=MTGDataAccess)
    return da


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_RULES: list[Rule] = [
    Rule(ruleNumber="106.4", section="Mana", text="This is a meaningful rule about mana that has enough characters to pass the length filter for testing purposes."),
    Rule(ruleNumber="116.1", section="Timing and Priority", text="This is a meaningful rule about timing and priority that has enough characters to pass the length filter for testing purposes."),
    Rule(ruleNumber="001.1", section="Players", text="Short intro rule."),
    Rule(ruleNumber="900.1", section="Sanctioned Formats", text="This is a meaningful rule about sanctioned formats but it's in a skipped section so should be filtered out for explanations."),
]

SAMPLE_GLOSSARY: list[GlossaryTerm] = [
    GlossaryTerm(term="Stack", definition="The stack is a zone where spells and abilities wait to resolve. This definition has enough characters."),
    GlossaryTerm(term="X", definition="Short."),
]


# ---------------------------------------------------------------------------
# GenerateRuleExplanations tests
# ---------------------------------------------------------------------------

class TestGenerateRuleExplanations:
    def test_templates_defined(self):
        assert len(GenerateRuleExplanations.TEMPLATES) == 3
        ids = {t.template_id for t in GenerateRuleExplanations.TEMPLATES}
        assert "plain_english" in ids
        assert "in_game_scenario" in ids
        assert "edge_case" in ids

    def test_skip_sections(self):
        # Original file had 005 (Formats overview) in the set too
        expected = {"000", "001", "002", "003", "004", "005", "900"}
        assert GenerateRuleExplanations.SKIP_SECTIONS == expected

    def test_source_category(self):
        gen = GenerateRuleExplanations(
            data_access=_make_data_access(),
            models=_make_models(),
            validation_pct=1.0,
            target_count=5,
            save_item=Mock(),
        )
        assert gen.get_source_category() == "rule_explanation"

    def test_get_data_batches_filters_skip_sections(self):
        da = _make_data_access()
        # Only return rules that pass the filter (not in SKIP_SECTIONS)
        da.get_rules.return_value = [
            Rule(ruleNumber="106.4", section="Mana", text="A" * 60),
            Rule(ruleNumber="001.1", section="Players", text="B" * 60),  # skipped
            Rule(ruleNumber="900.1", section="Sanctioned", text="C" * 60),  # skipped
        ]

        gen = GenerateRuleExplanations(
            data_access=da,
            models=_make_models(),
            validation_pct=1.0,
            target_count=5,
            save_item=Mock(),
        )

        batches = list(gen.get_data_batches())
        # Only the 106.4 rule should pass (not in SKIP_SECTIONS)
        assert len(batches) == 1
        assert batches[0][0].rule_number == "106.4"

    def test_get_data_batches_filters_short_text(self):
        da = _make_data_access()
        da.get_rules.return_value = [
            Rule(ruleNumber="106.4", section="Mana", text="Short"),  # <50 chars
            Rule(ruleNumber="106.5", section="Mana", text="A" * 60),  # passes
        ]

        gen = GenerateRuleExplanations(
            data_access=da,
            models=_make_models(),
            validation_pct=1.0,
            target_count=5,
            save_item=Mock(),
        )

        batches = list(gen.get_data_batches())
        assert len(batches) == 1
        assert batches[0][0].rule_number == "106.5"

    def test_build_prompt_uses_common_builder(self):
        da = _make_data_access()
        da.get_rules.return_value = []

        gen = GenerateRuleExplanations(
            data_access=da,
            models=_make_models(),
            validation_pct=1.0,
            target_count=5,
            save_item=Mock(),
        )

        rule = Rule(ruleNumber="116.1", section="Timing", text="Priority rules.")
        template = GenerateRuleExplanations.TEMPLATES[0]

        prompt = gen.build_prompt(template, rule)
        assert "116.1" in prompt
        assert "Priority rules." in prompt

    def test_templates_per_item_is_2(self):
        da = _make_data_access()
        da.get_rules.return_value = []

        gen = GenerateRuleExplanations(
            data_access=da,
            models=_make_models(),
            validation_pct=1.0,
            target_count=5,
            save_item=Mock(),
        )
        assert gen.templates_per_item == 2


# ---------------------------------------------------------------------------
# GenerateRuleInteractions tests
# ---------------------------------------------------------------------------

class TestGenerateRuleInteractions:
    def test_templates_defined(self):
        assert len(GenerateRuleInteractions.TEMPLATES) == 3
        ids = {t.template_id for t in GenerateRuleInteractions.TEMPLATES}
        assert "plain_english" in ids
        assert "in_game_scenario" in ids
        assert "edge_case" in ids

    def test_interaction_pairs_defined(self):
        pairs = GenerateRuleInteractions.INTERACTION_PAIRS
        # Original file had 37 interaction pairs
        assert len(pairs) >= 35
        assert ("601", "116") in pairs
        assert ("603", "704") in pairs

    def test_source_category(self):
        gen = GenerateRuleInteractions(
            data_access=_make_data_access(),
            models=_make_models(),
            validation_pct=1.0,
            target_count=5,
            save_item=Mock(),
        )
        assert gen.get_source_category() == "rule_interaction"

    def test_get_data_batches_yields_pairs(self):
        da = _make_data_access()
        # Provide rules for sections 603 and 704 which interact in INTERACTION_PAIRS
        rule_603 = Rule(ruleNumber="603.1", section="Triggers", text="A" * 70)
        rule_704 = Rule(ruleNumber="704.1", section="SBAs", text="B" * 70)
        da.get_rules.return_value = [rule_603, rule_704]

        gen = GenerateRuleInteractions(
            data_access=da,
            models=_make_models(),
            validation_pct=1.0,
            target_count=5,
            save_item=Mock(),
        )

        # Mock random.choice: first call returns section pair, subsequent calls return rules
        choice_calls = 0
        def mock_choice(seq):
            nonlocal choice_calls
            if isinstance(seq[0], tuple):  # INTERACTION_PAIRS list of tuples
                choice_calls += 1
                return ("603", "704")
            else:  # rules lists (Rule objects)
                return seq[0]

        with patch("training_data.generate_synthetic_data.generate_rule_interactions.random.choice", side_effect=mock_choice):
            batches = list(gen.get_data_batches())

        assert len(batches) >= 1
        for batch in batches:
            assert isinstance(batch[0], ProjectedRulePair)
            assert batch[0].rule1_number != ""
            assert batch[0].rule2_number != ""

    def test_build_prompt_contains_both_rules(self):
        da = _make_data_access()
        da.get_rules.return_value = []

        gen = GenerateRuleInteractions(
            data_access=da,
            models=_make_models(),
            validation_pct=1.0,
            target_count=5,
            save_item=Mock(),
        )

        pair = ProjectedRulePair(
            name="601+116",
            rule1_number="601.2a",
            rule1_text="Casting rules text here.",
            rule2_number="116.1b",
            rule2_text="Priority rules text here.",
            sections=["601", "116"],
        )

        template = GenerateRuleInteractions.TEMPLATES[0]
        prompt = gen.build_prompt(template, pair)

        assert "601.2a" in prompt
        assert "Casting rules text here." in prompt
        assert "116.1b" in prompt
        assert "Priority rules text here." in prompt
        assert template.task_instruction in prompt

    def test_templates_per_item_is_2(self):
        da = _make_data_access()
        da.get_rules.return_value = []

        gen = GenerateRuleInteractions(
            data_access=da,
            models=_make_models(),
            validation_pct=1.0,
            target_count=5,
            save_item=Mock(),
        )
        assert gen.templates_per_item == 2


# ---------------------------------------------------------------------------
# GenerateGlossaryWithExamples tests
# ---------------------------------------------------------------------------

class TestGenerateGlossaryWithExamples:
    def test_templates_defined(self):
        assert len(GenerateGlossaryWithExamples.TEMPLATES) == 1
        assert GenerateGlossaryWithExamples.TEMPLATES[0].template_id == "glossary_example"

    def test_source_category(self):
        gen = GenerateGlossaryWithExamples(
            data_access=_make_data_access(),
            models=_make_models(),
            validation_pct=1.0,
            target_count=5,
            save_item=Mock(),
        )
        assert gen.get_source_category() == "glossary_with_examples"

    def test_get_data_batches_filters_short_definitions(self):
        da = _make_data_access()
        da.get_glossary.return_value = [
            GlossaryTerm(term="X", definition="Short"),  # <30 chars, filtered out
            GlossaryTerm(term="Stack", definition="A" * 40),  # passes
        ]

        gen = GenerateGlossaryWithExamples(
            data_access=da,
            models=_make_models(),
            validation_pct=1.0,
            target_count=5,
            save_item=Mock(),
        )

        batches = list(gen.get_data_batches())
        assert len(batches) == 1
        assert batches[0][0].term == "Stack"

    def test_build_prompt_uses_common_builder(self):
        da = _make_data_access()
        da.get_glossary.return_value = []

        gen = GenerateGlossaryWithExamples(
            data_access=da,
            models=_make_models(),
            validation_pct=1.0,
            target_count=5,
            save_item=Mock(),
        )

        term = GlossaryTerm(term="Stack", definition="The stack is where spells wait.")
        template = GenerateGlossaryWithExamples.TEMPLATES[0]

        prompt = gen.build_prompt(template, term)
        assert "Stack" in prompt
        assert "The stack is where spells wait." in prompt


# ---------------------------------------------------------------------------
# GenerateRuleEdgeCases tests
# ---------------------------------------------------------------------------

class TestGenerateRuleEdgeCases:
    def test_templates_defined(self):
        assert len(GenerateRuleEdgeCases.TEMPLATES) == 1
        assert GenerateRuleEdgeCases.TEMPLATES[0].template_id == "edge_case"

    def test_source_category(self):
        gen = GenerateRuleEdgeCases(
            data_access=_make_data_access(),
            models=_make_models(),
            validation_pct=1.0,
            target_count=5,
            save_item=Mock(),
        )
        assert gen.get_source_category() == "rule_edge_case"

    def test_get_data_batches_filters_by_complex_sections(self):
        da = _make_data_access()
        # 116 is in COMPLEX_RULE_SECTIONS, 001 is not
        da.get_rules.return_value = [
            Rule(ruleNumber="116.1", section="Timing", text="A" * 90),  # passes (complex + long enough)
            Rule(ruleNumber="001.1", section="Players", text="B" * 90),  # not in complex sections
            Rule(ruleNumber="702.1", section="Keywords", text="C" * 90),  # passes (complex + long enough)
        ]

        gen = GenerateRuleEdgeCases(
            data_access=da,
            models=_make_models(),
            validation_pct=1.0,
            target_count=5,
            save_item=Mock(),
        )

        batches = list(gen.get_data_batches())
        assert len(batches) == 2
        nums = {b[0].rule_number for b in batches}
        assert "116.1" in nums
        assert "702.1" in nums

    def test_get_data_batches_filters_short_text(self):
        da = _make_data_access()
        da.get_rules.return_value = [
            Rule(ruleNumber="116.1", section="Timing", text="Short"),  # <80 chars
            Rule(ruleNumber="702.1", section="Keywords", text="A" * 90),  # passes
        ]

        gen = GenerateRuleEdgeCases(
            data_access=da,
            models=_make_models(),
            validation_pct=1.0,
            target_count=5,
            save_item=Mock(),
        )

        batches = list(gen.get_data_batches())
        assert len(batches) == 1
        assert batches[0][0].rule_number == "702.1"

    def test_build_prompt_includes_section_name(self):
        da = _make_data_access()
        da.get_rules.return_value = []

        gen = GenerateRuleEdgeCases(
            data_access=da,
            models=_make_models(),
            validation_pct=1.0,
            target_count=5,
            save_item=Mock(),
        )

        rule = Rule(ruleNumber="116.1", section="Timing", text="Priority rules.")
        template = GenerateRuleEdgeCases.TEMPLATES[0]

        prompt = gen.build_prompt(template, rule)
        assert "116.1" in prompt
        # 116 maps to "Timing and Priority" in COMPLEX_RULE_SECTIONS
        assert "Timing and Priority" in prompt


# ---------------------------------------------------------------------------
# GenerateRuleWhyQuestions tests
# ---------------------------------------------------------------------------

class TestGenerateRuleWhyQuestions:
    def test_templates_defined(self):
        assert len(GenerateRuleWhyQuestions.TEMPLATES) == 1
        assert GenerateRuleWhyQuestions.TEMPLATES[0].template_id == "why"

    def test_principle_sections(self):
        expected = [
            "116", "117", "118", "120",
            "601", "602", "603", "604", "608",
            "700", "701", "702", "704", "706",
        ]
        assert GenerateRuleWhyQuestions.PRINCIPLE_SECTIONS == expected

    def test_source_category(self):
        gen = GenerateRuleWhyQuestions(
            data_access=_make_data_access(),
            models=_make_models(),
            validation_pct=1.0,
            target_count=5,
            save_item=Mock(),
        )
        assert gen.get_source_category() == "rule_why"

    def test_get_data_batches_filters_by_principle_sections(self):
        da = _make_data_access()
        # 603 is in PRINCIPLE_SECTIONS, 901 is not
        da.get_rules.return_value = [
            Rule(ruleNumber="603.1", section="Triggers", text="A" * 110),  # passes
            Rule(ruleNumber="901.1", section="Commander", text="B" * 110),  # not in principle sections
            Rule(ruleNumber="704.1", section="SBAs", text="C" * 110),  # passes
        ]

        gen = GenerateRuleWhyQuestions(
            data_access=da,
            models=_make_models(),
            validation_pct=1.0,
            target_count=5,
            save_item=Mock(),
        )

        batches = list(gen.get_data_batches())
        assert len(batches) == 2
        nums = {b[0].rule_number for b in batches}
        assert "603.1" in nums
        assert "704.1" in nums

    def test_get_data_batches_filters_short_text(self):
        da = _make_data_access()
        da.get_rules.return_value = [
            Rule(ruleNumber="603.1", section="Triggers", text="Short"),  # <100 chars
            Rule(ruleNumber="704.1", section="SBAs", text="A" * 110),  # passes
        ]

        gen = GenerateRuleWhyQuestions(
            data_access=da,
            models=_make_models(),
            validation_pct=1.0,
            target_count=5,
            save_item=Mock(),
        )

        batches = list(gen.get_data_batches())
        assert len(batches) == 1
        assert batches[0][0].rule_number == "704.1"

    def test_build_prompt_uses_common_builder(self):
        da = _make_data_access()
        da.get_rules.return_value = []

        gen = GenerateRuleWhyQuestions(
            data_access=da,
            models=_make_models(),
            validation_pct=1.0,
            target_count=5,
            save_item=Mock(),
        )

        rule = Rule(ruleNumber="603.7", section="Triggers", text="Triggered ability rules.")
        template = GenerateRuleWhyQuestions.TEMPLATES[0]

        prompt = gen.build_prompt(template, rule)
        assert "603.7" in prompt
        assert "Triggered ability rules." in prompt


# ---------------------------------------------------------------------------
# Integration: all generators inherit from BaseGenerator correctly
# ---------------------------------------------------------------------------

class TestBaseGeneratorInheritance:
    """Verify all 5 generators properly extend BaseGenerator."""

    def test_rule_explanations_is_base_generator(self):
        gen = GenerateRuleExplanations(
            data_access=_make_data_access(),
            models=_make_models(),
            validation_pct=1.0,
            target_count=5,
            save_item=Mock(),
        )
        assert isinstance(gen, BaseGenerator)

    def test_rule_interactions_is_base_generator(self):
        gen = GenerateRuleInteractions(
            data_access=_make_data_access(),
            models=_make_models(),
            validation_pct=1.0,
            target_count=5,
            save_item=Mock(),
        )
        assert isinstance(gen, BaseGenerator)

    def test_glossary_is_base_generator(self):
        gen = GenerateGlossaryWithExamples(
            data_access=_make_data_access(),
            models=_make_models(),
            validation_pct=1.0,
            target_count=5,
            save_item=Mock(),
        )
        assert isinstance(gen, BaseGenerator)

    def test_edge_cases_is_base_generator(self):
        gen = GenerateRuleEdgeCases(
            data_access=_make_data_access(),
            models=_make_models(),
            validation_pct=1.0,
            target_count=5,
            save_item=Mock(),
        )
        assert isinstance(gen, BaseGenerator)

    def test_why_questions_is_base_generator(self):
        gen = GenerateRuleWhyQuestions(
            data_access=_make_data_access(),
            models=_make_models(),
            validation_pct=1.0,
            target_count=5,
            save_item=Mock(),
        )
        assert isinstance(gen, BaseGenerator)


# ---------------------------------------------------------------------------
# ProjectedRulePair tests
# ---------------------------------------------------------------------------

class TestProjectedRulePair:
    def test_creation(self):
        pair = ProjectedRulePair(
            name="601+116",
            rule1_number="601.2a",
            rule1_text="Casting rules.",
            rule2_number="116.1b",
            rule2_text="Priority rules.",
            sections=["601", "116"],
        )
        assert pair.name == "601+116"
        assert pair.rule1_number == "601.2a"
        assert pair.sections == ["601", "116"]

    def test_is_dataclass(self):
        from dataclasses import is_dataclass
        assert is_dataclass(ProjectedRulePair)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
