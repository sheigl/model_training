"""Tests for RuleEdgeCasesGenerator."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from trainforge.domain import TemplateConfig
from trainforge.domains.mtg.generators.rule_edge_cases import (
    RuleEdgeCasesGenerator,
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
    """Return sample raw rule dicts across various sections."""
    return [
        {"ruleNumber": "701.1a", "section": "701", "text": "To sacrifice a permanent, its controller moves it from the battlefield to its owner's graveyard. It's an action with a cost or effect."},
        {"ruleNumber": "702.1a", "section": "702", "text": "First strike is a static ability that modifies the rules for the combat damage step to create two separate damage steps."},
        {"ruleNumber": "703.1", "section": "703", "text": "State-based actions are game actions that happen automatically when certain conditions are met. They are checked whenever a player would receive priority."},
        {"ruleNumber": "704.1", "section": "704", "text": "Turn-based actions are actions that happen automatically when a step or phase starts. They don't use the stack."},
        {"ruleNumber": "708.1", "section": "708", "text": "A face-down permanent has no name, mana cost, color, or abilities. Face-down permanents are controlled by their controller."},
        {"ruleNumber": "709.1", "section": "709", "text": "This section covers meld cards which combine two cards into one creature."},
        {"ruleNumber": "101.1", "section": "1", "text": "A short rule from section 1 that should be excluded."},
        {"ruleNumber": "800.1", "section": "800", "text": "This is an out-of-range section rule that should also be excluded."},
    ]


@pytest.fixture
def generator(mock_domain):
    """Create a RuleEdgeCasesGenerator."""
    gen = RuleEdgeCasesGenerator(
        domain=mock_domain,
        generation_model=Model(name="test-gen", type=ModelType.GENERATION),
        validation_model=Model(name="test-val", type=ModelType.VALIDATION),
    )
    return gen


@pytest.fixture
def template():
    """Create a simple template for testing."""
    return TemplateConfig(
        template_id="unusual_interaction",
        task_instruction="Explore an edge case about rule {rule_number}",
    )


# =============================================================================
# GET_SOURCE_CATEGORY
# =============================================================================


class TestGetSourceCategory:
    def test_returns_correct_category(self, generator):
        """Should return 'rule_edge_cases'."""
        assert generator.get_source_category() == "rule_edge_cases"


# =============================================================================
# GET_DATA_BATCHES
# =============================================================================


class TestGetDataBatches:
    def test_filters_sections_701_to_708(self, generator, raw_rules):
        """Should only include rules from sections 701-708."""
        ds = MagicMock()
        ds.get_rules.return_value = raw_rules
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()

        for batch in batches:
            rule_num = batch.get("ruleNumber", "")
            section = int(rule_num.split(".")[0]) if "." in rule_num else int(rule_num)
            assert 701 <= section <= 708, f"Rule {rule_num} has section {section} not in 701-708"

    def test_filters_short_text(self, generator, raw_rules):
        """Should exclude rules with text < 80 chars."""
        ds = MagicMock()
        ds.get_rules.return_value = raw_rules
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()

        for batch in batches:
            assert len(batch.get("text", "")) >= 80

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

    def test_excludes_section_709_and_below_701(self, generator, raw_rules):
        """Should exclude sections outside 701-708."""
        ds = MagicMock()
        ds.get_rules.return_value = raw_rules
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()

        rule_numbers = {b["ruleNumber"] for b in batches}
        assert "709.1" not in rule_numbers
        assert "101.1" not in rule_numbers
        assert "800.1" not in rule_numbers


# =============================================================================
# BUILD_PROMPT
# =============================================================================


class TestBuildPrompt:
    def test_includes_edge_case_prompt_structure(self, generator, template):
        """Should include edge case prompt with text and section."""
        rule = {
            "ruleNumber": "701.1a",
            "section": "701",
            "text": "To sacrifice a permanent.",
        }
        prompt = generator.build_prompt(template, rule)

        assert "<reference>test notation</reference>" in prompt
        assert "701.1a" in prompt
        assert "To sacrifice a permanent" in prompt
        assert "701" in prompt
        assert "edge case" in prompt.lower()

    def test_wraps_in_task_tags(self, generator, template):
        """Should wrap the prompt in <task> tags."""
        rule = {"ruleNumber": "702.1a", "section": "702", "text": "First strike ability."}
        prompt = generator.build_prompt(template, rule)

        assert "<task>" in prompt
        assert "</task>" in prompt


# =============================================================================
# BUILD_CONTEXT
# =============================================================================


class TestBuildContext:
    def test_returns_formatted_context(self, generator):
        """Should return context with category, rule, section, and text."""
        rule = {"ruleNumber": "703.1", "section": "703", "text": "State-based actions check."}
        context = generator.build_context(rule)

        assert context is not None
        assert "rule_edge_cases" in context
        assert "703.1" in context
        assert "703" in context
        assert "State-based actions check" in context

    def test_returns_none_for_no_data(self, generator):
        """Should handle empty rule dict."""
        context = generator.build_context({})
        assert context is not None
        assert "rule_edge_cases" in context
