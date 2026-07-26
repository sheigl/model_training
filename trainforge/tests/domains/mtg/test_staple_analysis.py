"""Tests for StapleAnalysisGenerator."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from trainforge.domain import TemplateConfig
from trainforge.domains.mtg.generators.staple_analysis import (
    StapleAnalysisGenerator,
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
def sample_cards():
    """Return sample game-changer card dicts."""
    return [
        {
            "name": "Cyclonic Rift",
            "type": "Instant",
            "oracle_text": "Return target nonland permanent you don't control to its owner's hand.",
            "mana_cost": "{1}{U}",
            "num_decks": 250000,
            "salt": 3.2,
            "tags": ["removal", "blue"],
            "color_identity": ["U"],
            "edhrecRank": 5,
        },
        {
            "name": "Smothering Tithe",
            "type": "Enchantment",
            "oracle_text": "Whenever an opponent draws a card, that player may pay {2}. If they don't, you create a Treasure token.",
            "mana_cost": "{3}{W}",
            "num_decks": 200000,
            "salt": 2.8,
            "tags": ["ramp", "white"],
            "color_identity": ["W"],
            "edhrecRank": 8,
        },
        {
            "name": "Dockside Extortionist",
            "type": "Creature",
            "oracle_text": "When Dockside Extortionist enters the battlefield, create X Treasure tokens, where X is the number of artifacts and enchantments your opponents control.",
            "mana_cost": "{1}{R}",
            "num_decks": 180000,
            "salt": 4.0,
            "tags": ["ramp", "red"],
            "color_identity": ["R"],
            "edhrecRank": None,  # Uses edhrec_rank fallback
            "edhrec_rank": 12,
        },
    ]


@pytest.fixture
def generator(mock_domain):
    """Create a StapleAnalysisGenerator."""
    gen = StapleAnalysisGenerator(
        domain=mock_domain,
        generation_model=Model(name="test-gen", type=ModelType.GENERATION),
        validation_model=Model(name="test-val", type=ModelType.VALIDATION),
    )
    return gen


@pytest.fixture
def template():
    """Create a simple template for testing."""
    return TemplateConfig(
        template_id="staple_analysis",
        task_instruction="Analyze why {card_name} is a staple based on: {card_detail}",
    )


# =============================================================================
# GET_SOURCE_CATEGORY
# =============================================================================


class TestGetSourceCategory:
    def test_returns_correct_category(self, generator):
        """Should return 'staple_analysis'."""
        assert generator.get_source_category() == "staple_analysis"


# =============================================================================
# GET_DATA_BATCHES
# =============================================================================


class TestGetDataBatches:
    def test_returns_card_dicts_from_game_changers(self, generator, sample_cards):
        """Should return card dicts from get_game_changers()."""
        ds = MagicMock()
        ds.get_game_changers.return_value = sample_cards
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()

        assert len(batches) == 3
        assert all(isinstance(b, dict) for b in batches)
        assert batches[0]["name"] == "Cyclonic Rift"
        assert batches[1]["name"] == "Smothering Tithe"
        assert batches[2]["name"] == "Dockside Extortionist"

    def test_calls_get_game_changers_with_limit(self, generator):
        """Should call get_game_changers with default limit."""
        ds = MagicMock()
        ds.get_game_changers.return_value = []
        generator.domain.get_data_source.return_value = ds

        generator.get_data_batches()
        ds.get_game_changers.assert_called_once()
        assert ds.get_game_changers.call_args[1].get("limit") is not None

    def test_empty_cards_list(self, generator):
        """Should handle empty cards list gracefully."""
        ds = MagicMock()
        ds.get_game_changers.return_value = []
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()
        assert batches == []


# =============================================================================
# BUILD_PROMPT
# =============================================================================


class TestBuildPrompt:
    def test_includes_card_name_and_details(self, generator, template):
        """Should include card name and details in the prompt."""
        card = {
            "name": "Cyclonic Rift",
            "type": "Instant",
            "oracle_text": "Return target nonland permanent.",
            "mana_cost": "{1}{U}",
            "num_decks": 250000,
            "salt": 3.2,
            "tags": ["removal"],
            "color_identity": ["U"],
            "edhrecRank": 5,
        }
        prompt = generator.build_prompt(template, card)

        assert "<reference>test notation</reference>" in prompt
        assert "<task>" in prompt
        assert "</task>" in prompt
        assert "Cyclonic Rift" in prompt
        assert "Instant" in prompt
        assert "{1}{U}" in prompt
        assert "250,000" in prompt or "250000" in prompt
        assert "3.20" in prompt or "3.2" in prompt

    def test_includes_edhrec_rank_when_present(self, generator, template):
        """Should include EDHREC rank when available."""
        card = {"name": "Sol Ring", "type": "Artifact", "oracle_text": "Add {C}{C}.", "mana_cost": "{1}", "num_decks": 500000, "salt": 0.5, "tags": [], "color_identity": [], "edhrecRank": 1}
        prompt = generator.build_prompt(template, card)

        assert "EDHREC Rank: #1" in prompt

    def test_handles_edhrec_rank_none(self, generator, template):
        """Should omit EDHREC rank line when rank is None."""
        card = {"name": "Sol Ring", "type": "Artifact", "oracle_text": "Add {C}{C}.", "mana_cost": "{1}", "num_decks": 500000, "salt": 0.5, "tags": [], "color_identity": [], "edhrecRank": None, "edhrec_rank": None}
        prompt = generator.build_prompt(template, card)

        assert "EDHREC Rank" not in prompt

    def test_handles_edhrec_rank_fallback(self, generator, template):
        """Should use edhrec_rank when edhrecRank is None."""
        card = {"name": "Test Card", "type": "Creature", "oracle_text": "Test.", "mana_cost": "{2}", "num_decks": 100000, "salt": 1.0, "tags": [], "color_identity": [], "edhrecRank": None, "edhrec_rank": 42}
        prompt = generator.build_prompt(template, card)

        assert "EDHREC Rank: #42" in prompt

    def test_wraps_in_task_tags(self, generator, template):
        """Should wrap the prompt in <task> tags."""
        card = {"name": "Rhystic Study", "type": "Enchantment", "oracle_text": "Draw.", "mana_cost": "{2}{U}", "num_decks": 300000, "salt": 3.5, "tags": [], "color_identity": ["U"]}
        prompt = generator.build_prompt(template, card)

        assert "<task>" in prompt
        assert "</task>" in prompt


# =============================================================================
# BUILD_CONTEXT
# =============================================================================


class TestBuildContext:
    def test_returns_formatted_context(self, generator):
        """Should return context with category, card name, type, salt, and decks."""
        card = {
            "name": "Cyclonic Rift",
            "type": "Instant",
            "salt": 3.2,
            "num_decks": 250000,
        }
        context = generator.build_context(card)

        assert context is not None
        assert "staple_analysis" in context
        assert "Cyclonic Rift" in context
        assert "Instant" in context
        assert "3.20" in context or "3.2" in context
        assert "250000" in context or "250,000" in context

    def test_handles_unknown_card(self, generator):
        """Should handle dict with missing keys."""
        context = generator.build_context({})
        assert context is not None
        assert "staple_analysis" in context
        assert "Unknown" in context
