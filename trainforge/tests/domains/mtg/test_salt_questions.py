"""Tests for SaltQuestionsGenerator."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from trainforge.domain import TemplateConfig
from trainforge.domains.mtg.generators.salt_questions import (
    SaltQuestionsGenerator,
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
def sample_salty_cards():
    """Return 10 sample salty card dicts."""
    cards = []
    for i in range(10):
        cards.append(
            {
                "name": f"Salt Card {i + 1}",
                "type": "Creature" if i % 2 == 0 else "Instant",
                "oracle_text": f"Powerful effect number {i + 1} that frustrates opponents.",
                "mana_cost": f"{{{i + 1}}}{'U' if i % 2 == 0 else 'R'}",
                "num_decks": 50000 + (i * 10000),
                "salt": 1.5 + (i * 0.2),
                "tags": ["stax", "control"] if i % 3 == 0 else ["aggro"],
                "color_identity": ["U"] if i % 2 == 0 else ["R"],
                "edhrecRank": i + 1,
            }
        )
    return cards


@pytest.fixture
def generator(mock_domain):
    """Create a SaltQuestionsGenerator."""
    gen = SaltQuestionsGenerator(
        domain=mock_domain,
        generation_model=Model(name="test-gen", type=ModelType.GENERATION),
        validation_model=Model(name="test-val", type=ModelType.VALIDATION),
    )
    return gen


@pytest.fixture
def template():
    """Create a simple template for testing."""
    return TemplateConfig(
        template_id="why_is_this_salty",
        task_instruction="Generate questions about why these cards are salty",
    )


# =============================================================================
# GET_SOURCE_CATEGORY
# =============================================================================


class TestGetSourceCategory:
    def test_returns_correct_category(self, generator):
        """Should return 'salt_questions'."""
        assert generator.get_source_category() == "salt_questions"


# =============================================================================
# GET_DATA_BATCHES
# =============================================================================


class TestGetDataBatches:
    def test_groups_cards_into_batches_of_8(self, generator, sample_salty_cards):
        """Should split 10 cards into 2 batches: first of 8, second of 2."""
        ds = MagicMock()
        ds.get_salty_cards.return_value = sample_salty_cards
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()

        assert len(batches) == 2
        assert len(batches[0]) == 8
        assert len(batches[1]) == 2
        assert all(isinstance(b, list) for b in batches)
        assert all(isinstance(c, dict) for b in batches for c in b)

    def test_first_batch_contains_first_8_cards(self, generator, sample_salty_cards):
        """First batch should have cards 0-7."""
        ds = MagicMock()
        ds.get_salty_cards.return_value = sample_salty_cards
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()

        assert batches[0][0]["name"] == "Salt Card 1"
        assert batches[0][7]["name"] == "Salt Card 8"
        assert batches[1][0]["name"] == "Salt Card 9"
        assert batches[1][1]["name"] == "Salt Card 10"

    def test_calls_get_salty_cards_with_params(self, generator):
        """Should call get_salty_cards with min_salt=1.2 and limit=100."""
        ds = MagicMock()
        ds.get_salty_cards.return_value = []
        generator.domain.get_data_source.return_value = ds

        generator.get_data_batches()
        ds.get_salty_cards.assert_called_once_with(min_salt=1.2, limit=100)

    def test_empty_cards_list(self, generator):
        """Should handle empty cards list gracefully."""
        ds = MagicMock()
        ds.get_salty_cards.return_value = []
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()
        assert batches == []

    def test_single_batch_when_under_8_cards(self, generator, sample_salty_cards):
        """Should return a single batch when there are fewer than 8 cards."""
        ds = MagicMock()
        ds.get_salty_cards.return_value = sample_salty_cards[:3]
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()

        assert len(batches) == 1
        assert len(batches[0]) == 3


# =============================================================================
# BUILD_PROMPT
# =============================================================================


class TestBuildPrompt:
    def test_includes_salt_and_controversial_theme(self, generator, template):
        """Should mention salt or controversial themes in the prompt."""
        cards = [
            {"name": "Cyclonic Rift", "type": "Instant", "oracle_text": "Return all nonland permanents.", "mana_cost": "{1}{U}", "num_decks": 250000, "salt": 3.5},
            {"name": "Armageddon", "type": "Sorcery", "oracle_text": "Destroy all lands.", "mana_cost": "{3}{W}", "num_decks": 50000, "salt": 4.2},
        ]
        prompt = generator.build_prompt(template, cards)

        assert "<reference>test notation</reference>" in prompt
        assert "<task>" in prompt
        assert "</task>" in prompt
        assert "salt" in prompt.lower() or "controversial" in prompt.lower()
        assert "Cyclonic Rift" in prompt
        assert "Armageddon" in prompt

    def test_shows_oracle_text_and_salt_score(self, generator, template):
        """Each card should show oracle text and salt score."""
        cards = [
            {"name": "Test Card", "type": "Creature", "oracle_text": "Test ability text.", "mana_cost": "{2}", "num_decks": 100000, "salt": 2.5, "tags": [], "color_identity": []},
        ]
        prompt = generator.build_prompt(template, cards)

        assert "Test ability text" in prompt
        assert "2.50" in prompt or "2.5" in prompt

    def test_wraps_in_task_tags(self, generator, template):
        """Should wrap the prompt in <task> tags."""
        cards = [{"name": "Sol Ring", "type": "Artifact", "oracle_text": "Add {C}{C}.", "mana_cost": "{1}", "num_decks": 500000, "salt": 0.5}]
        prompt = generator.build_prompt(template, cards)

        assert "<task>" in prompt
        assert "</task>" in prompt


# =============================================================================
# BUILD_CONTEXT
# =============================================================================


class TestBuildContext:
    def test_returns_formatted_context(self, generator):
        """Should return context with category, card names, batch size, and avg salt."""
        cards = [
            {"name": "Card A", "salt": 2.0},
            {"name": "Card B", "salt": 4.0},
        ]
        context = generator.build_context(cards)

        assert context is not None
        assert "salt_questions" in context
        assert "Card A" in context
        assert "Card B" in context
        assert "Batch size: 2" in context
        # Average salt = (2.0 + 4.0) / 2 = 3.0
        assert "3.00" in context or "3.0" in context

    def test_handles_empty_batch(self, generator):
        """Should handle empty card list."""
        context = generator.build_context([])
        assert context is not None
        assert "salt_questions" in context
        assert "Batch size: 0" in context
