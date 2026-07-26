"""Tests for ColorStaplesGenerator."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from trainforge.domain import TemplateConfig
from trainforge.domains.mtg.generators.color_staples import (
    ColorStaplesGenerator,
)
from trainforge.models import Model, ModelType


# =============================================================================
# FIXTURES
# =============================================================================


def _make_card(name: str, color: str, rank: int = 1) -> dict:
    """Create a sample card dict with given name, color identity, and rank."""
    return {
        "name": name,
        "type": "Creature",
        "mana_cost": f"{{{rank}}}{{{color[0].upper()}}}",
        "num_decks": 50000 - (rank * 1000),
        "edhrecRank": rank,
        "oracle_text": f"Sample oracle text for {name}.",
    }


@pytest.fixture
def mock_domain():
    """Create a mock domain."""
    domain = MagicMock()
    domain.name = "mtg"
    domain.notation_legend = "<reference>test notation</reference>"
    return domain


@pytest.fixture
def generator(mock_domain):
    """Create a ColorStaplesGenerator."""
    gen = ColorStaplesGenerator(
        domain=mock_domain,
        generation_model=Model(name="test-gen", type=ModelType.GENERATION),
        validation_model=Model(name="test-val", type=ModelType.VALIDATION),
    )
    return gen


@pytest.fixture
def template():
    """Create a simple template for testing."""
    return TemplateConfig(
        template_id="staples_for_color",
        task_instruction="Generate questions about {color} staples: {card_list}",
    )


# =============================================================================
# GET_SOURCE_CATEGORY
# =============================================================================


class TestGetSourceCategory:
    def test_returns_correct_category(self, generator):
        """Should return 'color_staples'."""
        assert generator.get_source_category() == "color_staples"


# =============================================================================
# GET_DATA_BATCHES
# =============================================================================


class TestGetDataBatches:
    def test_splits_each_color_into_3_sub_batches(self, generator):
        """30 cards per color should yield 3 sub-batches of 10 per color = 18 total."""
        ds = MagicMock()

        def mock_get_top_cards(color: str, limit: int = 30):
            return [_make_card(f"{color.title()} Card {i}", color, i) for i in range(1, 31)]

        ds.get_top_cards_by_color.side_effect = mock_get_top_cards
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()

        # 6 colors × 3 sub-batches = 18 total
        assert len(batches) == 18
        assert all(isinstance(b, tuple) and len(b) == 2 for b in batches)
        assert all(isinstance(b[0], str) for b in batches)
        assert all(isinstance(b[1], list) for b in batches)

    def test_each_sub_batch_has_up_to_10_cards(self, generator):
        """Each sub-batch should contain at most 10 cards."""
        ds = MagicMock()

        def mock_get_top_cards(color: str, limit: int = 30):
            return [_make_card(f"{color.title()} Card {i}", color, i) for i in range(1, 31)]

        ds.get_top_cards_by_color.side_effect = mock_get_top_cards
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()

        for _, cards in batches:
            assert len(cards) <= 10

    def test_correct_sub_batch_card_counts(self, generator):
        """30 cards should split into batches of 10, 10, 10."""
        ds = MagicMock()

        def mock_get_top_cards(color: str, limit: int = 30):
            return [_make_card(f"{color.title()} Card {i}", color, i) for i in range(1, 31)]

        ds.get_top_cards_by_color.side_effect = mock_get_top_cards
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()

        # First sub-batch of each color: 10 cards
        assert len(batches[0][1]) == 10
        # Second sub-batch of each color: 10 cards
        assert len(batches[1][1]) == 10
        # Third sub-batch of each color: 10 cards
        assert len(batches[2][1]) == 10

    def test_color_names_in_batches(self, generator):
        """Should include all 6 color names across batches."""
        ds = MagicMock()

        def mock_get_top_cards(color: str, limit: int = 30):
            return [_make_card(f"{color.title()} Card {i}", color, i) for i in range(1, 31)]

        ds.get_top_cards_by_color.side_effect = mock_get_top_cards
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()

        colors_in_batches = {b[0] for b in batches}
        assert colors_in_batches == {"white", "blue", "black", "red", "green", "colorless"}

    def test_calls_get_top_cards_by_color_for_each_color(self, generator):
        """Should call get_top_cards_by_color for each of the 6 colors."""
        ds = MagicMock()
        ds.get_top_cards_by_color.return_value = []
        generator.domain.get_data_source.return_value = ds

        generator.get_data_batches()

        assert ds.get_top_cards_by_color.call_count == 6
        for color in ["white", "blue", "black", "red", "green", "colorless"]:
            ds.get_top_cards_by_color.assert_any_call(color, limit=30)

    def test_empty_cards_for_color_skipped(self, generator):
        """Should skip colors that return no cards."""
        ds = MagicMock()

        def mock_get_top_cards(color: str, limit: int = 30):
            if color == "blue":
                return []
            return [_make_card(f"{color.title()} Card {i}", color, i) for i in range(1, 11)]

        ds.get_top_cards_by_color.side_effect = mock_get_top_cards
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()

        # 5 colors with cards × 1 sub-batch = 5 (blue produces none)
        assert len(batches) == 5
        colors_in_batches = {b[0] for b in batches}
        assert "blue" not in colors_in_batches

    def test_less_than_10_cards_single_batch(self, generator):
        """5 cards should produce a single sub-batch of 5."""
        ds = MagicMock()

        def mock_get_top_cards(color: str, limit: int = 30):
            return [_make_card(f"{color.title()} Card {i}", color, i) for i in range(1, 6)]

        ds.get_top_cards_by_color.side_effect = mock_get_top_cards
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()

        # 6 colors × 1 sub-batch = 6
        assert len(batches) == 6
        assert len(batches[0][1]) == 5

    def test_11_cards_two_sub_batches(self, generator):
        """11 cards should produce 2 sub-batches (10 + 1)."""
        ds = MagicMock()

        def mock_get_top_cards(color: str, limit: int = 30):
            return [_make_card(f"{color.title()} Card {i}", color, i) for i in range(1, 12)]

        ds.get_top_cards_by_color.side_effect = mock_get_top_cards
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()

        # 6 colors × 2 sub-batches = 12
        assert len(batches) == 12


# =============================================================================
# BUILD_PROMPT
# =============================================================================


class TestBuildPrompt:
    def test_includes_color_name_and_card_list(self, generator, template):
        """Should include color name and card details in the prompt."""
        cards = [
            {"name": "Swords to Plowshares", "type": "Instant", "mana_cost": "{W}", "num_decks": 300000, "edhrecRank": 1},
            {"name": "Path to Exile", "type": "Instant", "mana_cost": "{W}", "num_decks": 280000, "edhrecRank": 2},
        ]
        prompt = generator.build_prompt(template, ("white", cards))

        assert "<reference>test notation</reference>" in prompt
        assert "<task>" in prompt
        assert "</task>" in prompt
        assert "white" in prompt
        assert "Swords to Plowshares" in prompt
        assert "Path to Exile" in prompt
        assert "#1" in prompt
        assert "#2" in prompt

    def test_limits_to_15_cards_in_prompt(self, generator, template):
        """Should show at most 15 cards in the prompt."""
        cards = [{"name": f"Card {i}", "type": "Creature", "mana_cost": "{1}", "num_decks": 1000, "edhrecRank": i} for i in range(1, 25)]
        prompt = generator.build_prompt(template, ("red", cards))

        # Should have at most 15 cards listed
        assert "Card 15" in prompt
        assert "Card 16" not in prompt

    def test_wraps_in_task_tags(self, generator, template):
        """Should wrap the prompt in <task> tags."""
        cards = [{"name": "Sol Ring", "type": "Artifact", "mana_cost": "{1}", "num_decks": 500000}]
        prompt = generator.build_prompt(template, ("colorless", cards))

        assert "<task>" in prompt
        assert "</task>" in prompt


# =============================================================================
# BUILD_CONTEXT
# =============================================================================


class TestBuildContext:
    def test_returns_formatted_context(self, generator):
        """Should return context with category, color, top cards, and total count."""
        cards = [{"name": f"Card {i}"} for i in range(1, 11)]
        context = generator.build_context(("blue", cards))

        assert context is not None
        assert "color_staples" in context
        assert "blue" in context
        assert "Card 1" in context
        assert "Card 10" in context
        assert "Total staples fetched: 10" in context

    def test_handles_empty_card_list(self, generator):
        """Should handle empty card list."""
        context = generator.build_context(("white", []))
        assert context is not None
        assert "color_staples" in context
        assert "white" in context
        assert "Total staples fetched: 0" in context
