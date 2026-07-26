"""Tests for RuleInteractionsGenerator."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from trainforge.domain import TemplateConfig
from trainforge.domains.mtg.generators.rule_interactions import (
    RuleInteractionsGenerator,
    _extract_section,
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
    """Return sample rule dicts across multiple sections.

    Includes rules matching the interaction pairs for sections
    601, 116, 603, 704, 702, 120, etc.
    """
    return [
        {"ruleNumber": "116.1", "section": "116", "text": "Priority is the order in which players may take actions."},
        {"ruleNumber": "116.2", "section": "116", "text": "The active player receives priority at the beginning of each step."},
        {"ruleNumber": "120.1", "section": "120", "text": "Damage is a loss of life that can be prevented by prevention effects."},
        {"ruleNumber": "121.1", "section": "121", "text": "A counter is a marker placed on an object or player that modifies its characteristics."},
        {"ruleNumber": "400.1", "section": "400", "text": "A zone is a place where objects can be during a game. There are six zones."},
        {"ruleNumber": "404.1", "section": "404", "text": "Exile is a zone for objects that are removed from the game."},
        {"ruleNumber": "506.1", "section": "506", "text": "The combat phase has five steps: beginning of combat, declare attackers, declare blockers, combat damage, and end of combat."},
        {"ruleNumber": "510.1", "section": "510", "text": "Combat damage is dealt during the combat damage step."},
        {"ruleNumber": "601.1", "section": "601", "text": "To cast a spell is to take it from where it is and put it onto the stack."},
        {"ruleNumber": "601.2", "section": "601", "text": "To cast a spell, a player follows a series of steps in order."},
        {"ruleNumber": "603.1", "section": "603", "text": "Triggered abilities have a trigger condition and an effect."},
        {"ruleNumber": "604.1", "section": "604", "text": "Static abilities are written as statements that are continuously in effect."},
        {"ruleNumber": "613.1", "section": "613", "text": "Continuous effects from static abilities are applied in a series of layers."},
        {"ruleNumber": "614.1", "section": "614", "text": "Some effects replace events. These are called replacement effects."},
        {"ruleNumber": "700.1", "section": "700", "text": "Additional rules cover topics like linked abilities and color indicators."},
        {"ruleNumber": "702.1", "section": "702", "text": "Keyword abilities are usually one or two words that describe a common ability."},
        {"ruleNumber": "704.1", "section": "704", "text": "State-based actions are game actions that happen automatically."},
        {"ruleNumber": "706.1", "section": "706", "text": "To copy an object, a player creates a token that is a copy of that object."},
        {"ruleNumber": "800.1", "section": "800", "text": "Multiplayer rules modify the game for more than two players."},
        {"ruleNumber": "903.1", "section": "903", "text": "Commander is a variant that uses a legendary creature as a commander."},
        # Short text (< 60 chars, should be excluded)
        {"ruleNumber": "106.1", "section": "106", "text": "Mana is the resource."},
        # Another section 106 with longer text
        {"ruleNumber": "106.2", "section": "106", "text": "Mana is produced by mana abilities and can be spent to pay costs."},
        # Section 118
        {"ruleNumber": "118.1", "section": "118", "text": "A cost is an action or payment necessary to take a game action."},
        # Section 608
        {"ruleNumber": "608.1", "section": "608", "text": "To resolve a spell or ability, a player follows the steps in this section."},
        # Section 400 additional
        {"ruleNumber": "400.5", "section": "400", "text": "When an object changes zones, it becomes a new object with no memory of its previous existence."},
    ]


@pytest.fixture
def generator(mock_domain):
    """Create a RuleInteractionsGenerator."""
    gen = RuleInteractionsGenerator(
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
        task_instruction=(
            "Generate exactly 3 Q&A pairs explaining how these two rules "
            "interact in plain English."
        ),
    )


# =============================================================================
# UNIT: _extract_section
# =============================================================================


class TestExtractSection:
    def test_section_from_dotted_rule_number(self):
        """Should extract section from '601.1' -> '601'."""
        assert _extract_section({"ruleNumber": "601.1"}) == "601"

    def test_section_from_dotted_with_suffix(self):
        """Should extract section from '601.1a' -> '601'."""
        assert _extract_section({"ruleNumber": "601.1a"}) == "601"

    def test_section_without_dot(self):
        """Should extract first 3 chars from '106a' -> '106'."""
        assert _extract_section({"ruleNumber": "106a"}) == "106"

    def test_empty_rule_number(self):
        """Should return empty string for missing rule number."""
        assert _extract_section({"ruleNumber": ""}) == ""
        assert _extract_section({}) == ""


# =============================================================================
# GET_SOURCE_CATEGORY
# =============================================================================


class TestGetSourceCategory:
    def test_returns_correct_category(self, generator):
        """Should return 'rule_interactions'."""
        assert generator.get_source_category() == "rule_interactions"


# =============================================================================
# CONSTANTS
# =============================================================================


class TestInteractionPairs:
    def test_has_37_pairs(self):
        """Should define exactly 37 interaction pairs."""
        assert len(RuleInteractionsGenerator.INTERACTION_PAIRS) == 37

    def test_pairs_are_section_strings(self):
        """Each pair should be two strings."""
        for sec1, sec2 in RuleInteractionsGenerator.INTERACTION_PAIRS:
            assert isinstance(sec1, str)
            assert isinstance(sec2, str)
            assert len(sec1) <= 4
            assert len(sec2) <= 4


# =============================================================================
# GET_DATA_BATCHES
# =============================================================================


class TestGetDataBatches:
    def test_builds_interaction_pairs(self, generator, raw_rules):
        """Should build interaction pairs from matching sections."""
        ds = MagicMock()
        ds.get_rules.return_value = raw_rules
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()

        assert len(batches) > 0
        for rule1, rule2 in batches:
            assert isinstance(rule1, dict)
            assert isinstance(rule2, dict)
            assert "ruleNumber" in rule1
            assert "ruleNumber" in rule2
            assert "text" in rule1
            assert "text" in rule2

    def test_filters_short_rule_text(self, generator, raw_rules):
        """Should exclude rules with text <= 60 chars."""
        ds = MagicMock()
        ds.get_rules.return_value = raw_rules
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()

        # 106.1 has only 23 chars, should be excluded
        for rule1, rule2 in batches:
            assert len(rule1.get("text", "")) > 60
            assert len(rule2.get("text", "")) > 60

    def test_call_get_rules_with_limit_500(self, generator):
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

        batches = generator.get_data_batches()
        assert batches == []

    def test_no_matching_sections(self, generator):
        """Should handle when no rules match interaction pairs."""
        ds = MagicMock()
        ds.get_rules.return_value = [
            {"ruleNumber": "999.1", "section": "999", "text": "A rule about something completely unrelated that is still long enough to pass the text filter."},
        ]
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()
        assert batches == []


# =============================================================================
# BUILD_PROMPT
# =============================================================================


class TestBuildPrompt:
    def test_includes_rules_and_task(self, generator, template):
        """Should include both rules and task instruction."""
        rule1 = {"ruleNumber": "601.1", "section": "601", "text": "To cast a spell is to take it and put it onto the stack."}
        rule2 = {"ruleNumber": "116.1", "section": "116", "text": "Priority is the order in which players may take actions."}

        prompt = generator.build_prompt(template, (rule1, rule2))

        assert "<reference>test notation</reference>" in prompt
        assert "<rules>" in prompt
        assert "</rules>" in prompt
        assert "<task>" in prompt
        assert "</task>" in prompt
        assert "601.1" in prompt
        assert "116.1" in prompt
        assert "cast a spell" in prompt
        assert "Priority" in prompt

    def test_wraps_in_rules_tags(self, generator, template):
        """Should wrap the rules in <rules> tags."""
        rule1 = {"ruleNumber": "100.1", "section": "100", "text": "Basic game rules."}
        rule2 = {"ruleNumber": "101.1", "section": "101", "text": "Mulligan rules."}

        prompt = generator.build_prompt(template, (rule1, rule2))

        assert "<rules>" in prompt
        assert "</rules>" in prompt
        assert "AUTHORITATIVE RULES" in prompt
        assert "treat these as ground truth" in prompt

    def test_requirements_included(self, generator, template):
        """Should include the detailed requirements section."""
        rule1 = {"ruleNumber": "100.1", "section": "100", "text": "Basic game rules."}
        rule2 = {"ruleNumber": "101.1", "section": "101", "text": "Mulligan rules."}

        prompt = generator.build_prompt(template, (rule1, rule2))

        assert "REQUIREMENTS:" in prompt
        assert "Do not reference rule numbers in questions" in prompt
        assert "plain text only" in prompt


# =============================================================================
# BUILD_CONTEXT
# =============================================================================


class TestBuildContext:
    def test_returns_formatted_context(self, generator):
        """Should return context with category and rule info."""
        rule1 = {"ruleNumber": "601.1", "section": "601", "text": "Casting rules."}
        rule2 = {"ruleNumber": "116.1", "section": "116", "text": "Priority rules."}

        context = generator.build_context((rule1, rule2))

        assert context is not None
        assert "rule_interactions" in context
        assert "Rule 1: 601.1" in context
        assert "Rule 2: 116.1" in context
        assert "Sections: 601 + 116" in context
