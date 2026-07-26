"""Tests for RuleWhyQuestionsGenerator."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from trainforge.domain import TemplateConfig
from trainforge.domains.mtg.generators.rule_why_questions import (
    RuleWhyQuestionsGenerator,
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
    """Return sample raw rule dicts across different sections with sufficient text length."""
    return [
        {"ruleNumber": "101.1", "section": "1", "text": "Whenever a player would mulligan, they may reveal their hand and shuffle it into its owner's library. This is the fundamental rule for taking mulligans."},
        {"ruleNumber": "150.1a", "section": "150", "text": "A player's hand is the zone in which they hold cards that they have drawn during the game. Cards in hand are private information unless an effect says otherwise."},
        {"ruleNumber": "401.1", "section": "400", "text": "A player may rearrange their library at any time. A player may look at their own library if a spell or ability instructs them to search."},
        {"ruleNumber": "702.1a", "section": "700", "text": "First strike is a static ability that modifies the rules for the combat damage step to create two separate damage steps for creatures with first strike."},
        {"ruleNumber": "702.2a", "section": "700", "text": "A creature with deathtouch puts a -1/-1 counter on each creature it deals damage to. Deathtouch is a static ability that changes the combat rules."},
        {"ruleNumber": "901.1", "section": "900", "text": "This section contains the glossary of terms and definitions for Magic: The Gathering comprehensive rules."},
        {"ruleNumber": "2.1", "section": "2", "text": "Short text that should be filtered out due to length requirements."},
        {"ruleNumber": "300.1", "section": "300", "text": "Cards with the planeswalker card type are permanents and have a subtype. Planeswalkers enter the battlefield with loyalty counters."},
        {"ruleNumber": "500.1", "section": "500", "text": "A turn consists of five phases in order: beginning, precombat main, combat, postcombat main, and ending phase."},
    ]


@pytest.fixture
def generator(mock_domain):
    """Create a RuleWhyQuestionsGenerator."""
    gen = RuleWhyQuestionsGenerator(
        domain=mock_domain,
        generation_model=Model(name="test-gen", type=ModelType.GENERATION),
        validation_model=Model(name="test-val", type=ModelType.VALIDATION),
    )
    return gen


@pytest.fixture
def template():
    """Create a simple template for testing."""
    return TemplateConfig(
        template_id="why_this_rule",
        task_instruction="Generate a Q&A explaining why this rule exists: {rule_number}",
    )


# =============================================================================
# GET_SOURCE_CATEGORY
# =============================================================================


class TestGetSourceCategory:
    def test_returns_correct_category(self, generator):
        """Should return 'rule_why_questions'."""
        assert generator.get_source_category() == "rule_why_questions"


# =============================================================================
# GET_DATA_BATCHES
# =============================================================================


class TestGetDataBatches:
    def test_filters_principle_sections(self, generator, raw_rules):
        """Should only include rules from sections 100-199, 400-499, 700-799."""
        ds = MagicMock()
        ds.get_rules.return_value = raw_rules
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()

        assert len(batches) >= 1
        for batch in batches:
            assert isinstance(batch, dict)
            section = int(batch["ruleNumber"].split(".")[0])
            assert 100 <= section <= 199 or 400 <= section <= 499 or 700 <= section <= 799
            assert len(batch.get("text", "")) >= 100

    def test_filters_short_text(self, generator, raw_rules):
        """Should exclude rules with text < 100 chars."""
        ds = MagicMock()
        ds.get_rules.return_value = raw_rules
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()

        for batch in batches:
            assert len(batch.get("text", "")) >= 100

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


# =============================================================================
# BUILD_PROMPT
# =============================================================================


class TestBuildPrompt:
    def test_includes_rule_data_and_why_question(self, generator, template):
        """Should include rule data and the 'why' question structure."""
        rule = {
            "ruleNumber": "702.1a",
            "section": "700",
            "text": "First strike modifies the combat damage step.",
        }
        prompt = generator.build_prompt(template, rule)

        assert "<reference>test notation</reference>" in prompt
        assert "702.1a" in prompt
        assert "First strike modifies" in prompt
        assert "Explain WHY" in prompt or "why this rule" in prompt.lower() or "designed" in prompt

    def test_wraps_in_task_tags(self, generator, template):
        """Should wrap the prompt in <task> tags."""
        rule = {"ruleNumber": "101.1", "section": "1", "text": "A rule about mulligans."}
        prompt = generator.build_prompt(template, rule)

        assert "<task>" in prompt
        assert "</task>" in prompt


# =============================================================================
# BUILD_CONTEXT
# =============================================================================


class TestBuildContext:
    def test_returns_formatted_context(self, generator):
        """Should return context with category, rule, section, and text."""
        rule = {"ruleNumber": "702.1a", "section": "700", "text": "First strike rules."}
        context = generator.build_context(rule)

        assert context is not None
        assert "rule_why_questions" in context
        assert "702.1a" in context
        assert "700" in context
        assert "First strike rules" in context
