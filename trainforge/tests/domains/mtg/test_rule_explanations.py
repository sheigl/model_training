"""Tests for RuleExplanationsGenerator."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from trainforge.domain import TemplateConfig
from trainforge.domains.mtg.generators.rule_explanations import (
    RuleExplanationsGenerator,
)
from trainforge.models import Model, ModelType


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_domain():
    """Create a mock domain."""
    domain = MagicMock()
    domain.name = "mtg"
    domain.notation_legend = "<reference>test notation</reference>"
    return domain


@pytest.fixture
def raw_rules():
    """Return sample raw rule dicts — including excluded sections."""
    return [
        {"ruleNumber": "001.1", "section": "0", "text": "Introduction to the comprehensive rules document."},
        {"ruleNumber": "005.1", "section": "5", "text": "More introduction content about game concepts."},
        {"ruleNumber": "100.1", "section": "100", "text": "These rules cover the basics of playing Magic: The Gathering, a trading card game."},
        {"ruleNumber": "101.1", "section": "101", "text": "Whenever a player would mulligan, they may reveal their hand and shuffle it into its owner's library. This allows players to find a better starting hand."},
        {"ruleNumber": "500.1", "section": "500", "text": "A turn consists of five phases in order: beginning, precombat main, combat, postcombat main, and ending."},
        {"ruleNumber": "702.1a", "section": "702", "text": "First strike is a static ability that modifies the combat damage step to create two separate damage steps."},
        {"ruleNumber": "901.1", "section": "900", "text": "Glossary of terms and definitions for Magic: The Gathering rules."},
        {"ruleNumber": "X01.1", "section": "X", "text": "A rule with unparseable section number."},
        {"ruleNumber": "104.3b", "section": "104", "text": "A player can't lose the game."},
    ]


@pytest.fixture
def generator(mock_domain):
    """Create a RuleExplanationsGenerator."""
    gen = RuleExplanationsGenerator(
        domain=mock_domain,
        generation_model=Model(name="test-gen", type=ModelType.GENERATION),
        validation_model=Model(name="test-val", type=ModelType.VALIDATION),
    )
    return gen


@pytest.fixture
def template():
    """Create a simple template for testing."""
    return TemplateConfig(
        template_id="plain_english",
        task_instruction="Explain rule {rule_number}: {rule_text}",
    )


# =============================================================================
# GET_SOURCE_CATEGORY
# =============================================================================


class TestGetSourceCategory:
    def test_returns_correct_category(self, generator):
        """Should return 'rule_explanations'."""
        assert generator.get_source_category() == "rule_explanations"


# =============================================================================
# GET_DATA_BATCHES
# =============================================================================


class TestGetDataBatches:
    def test_excludes_sections_000_005_and_900s(self, generator, raw_rules):
        """Should exclude intro sections (000-005) and appendices (900+)."""
        ds = MagicMock()
        ds.get_rules.return_value = raw_rules
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()

        rule_numbers = {b["ruleNumber"] for b in batches}
        assert "001.1" not in rule_numbers, "Should exclude section 0"
        assert "005.1" not in rule_numbers, "Should exclude section 5"
        assert "901.1" not in rule_numbers, "Should exclude section 900+"

    def test_includes_valid_sections(self, generator, raw_rules):
        """Should include rules from sections 6-899."""
        ds = MagicMock()
        ds.get_rules.return_value = raw_rules
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()

        rule_numbers = {b["ruleNumber"] for b in batches}
        assert "100.1" in rule_numbers
        assert "101.1" in rule_numbers
        assert "500.1" in rule_numbers
        assert "702.1a" in rule_numbers

    def test_filters_short_text(self, generator, raw_rules):
        """Should exclude rules with text <= 50 chars."""
        ds = MagicMock()
        ds.get_rules.return_value = raw_rules
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()

        # 104.3b: "A player can't lose the game." = 31 chars, should be excluded
        # X01.1: should be excluded (unparseable section = 0)
        for batch in batches:
            assert len(batch.get("text", "")) > 50
            rule_num = batch.get("ruleNumber", "")
            assert not rule_num.startswith("X"), "Should exclude unparseable rule numbers"

    def test_calls_get_rules_with_limit_500(self, generator):
        """Should call get_rules with limit=500."""
        ds = MagicMock()
        ds.get_rules.return_value = []
        generator.domain.get_data_source.return_value = ds

        generator.get_data_batches()
        ds.get_rules.assert_called_once_with(limit=500)

    def test_empty_rules_list(self, generator):
        """Should handle empty rules list."""
        ds = MagicMock()
        ds.get_rules.return_value = []
        generator.domain.get_data_source.return_value = ds

        assert generator.get_data_batches() == []

    def test_unparseable_sections_excluded(self, generator):
        """Should exclude rules with non-numeric rule numbers."""
        ds = MagicMock()
        ds.get_rules.return_value = [
            {"ruleNumber": "ABC", "section": "X", "text": "Some rule with weird numbering."},
            {"ruleNumber": "", "section": "", "text": "Another unparseable rule number."},
            {"ruleNumber": "100.1", "section": "100", "text": "A valid rule with sufficient text content for inclusion."},
        ]
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()

        assert len(batches) == 1
        assert batches[0]["ruleNumber"] == "100.1"


# =============================================================================
# BUILD_PROMPT
# =============================================================================


class TestBuildPrompt:
    def test_formats_task_instruction_with_rule_data(self, generator, template):
        """Should format template instruction with rule_number, rule_text, section."""
        rule = {
            "ruleNumber": "702.1a",
            "section": "702",
            "rule_text": "First strike modifies combat.",
            "text": "First strike modifies combat damage step.",
        }
        prompt = generator.build_prompt(template, rule)

        assert "<reference>test notation</reference>" in prompt
        assert "702.1a" in prompt
        assert "First strike modifies combat" in prompt
        assert "<task>" in prompt
        assert "</task>" in prompt

    def test_wraps_in_task_tags(self, generator, template):
        """Should wrap the prompt in <task> tags."""
        rule = {"ruleNumber": "500.1", "section": "500", "text": "A turn has five phases."}
        prompt = generator.build_prompt(template, rule)

        assert "<task>" in prompt
        assert "</task>" in prompt


# =============================================================================
# BUILD_CONTEXT
# =============================================================================


class TestBuildContext:
    def test_returns_formatted_context(self, generator):
        """Should return context with category, rule, section, and text."""
        rule = {"ruleNumber": "100.1", "section": "100", "text": "Basic game rules."}
        context = generator.build_context(rule)

        assert context is not None
        assert "rule_explanations" in context
        assert "100.1" in context
        assert "100" in context
        assert "Basic game rules" in context
