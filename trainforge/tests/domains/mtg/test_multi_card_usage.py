"""Tests for MultiCardUsageGenerator."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from trainforge.domain import TemplateConfig
from trainforge.domains.mtg.generators.multi_card_usage import (
    MultiCardUsageGenerator,
)
from trainforge.domains.mtg.models import (
    CardWithMetadata,
    ComboCard,
    ComboProduces,
    ComboWithCards,
)
from trainforge.models import Model, ModelType


# =============================================================================
# FIXTURES
# =============================================================================


def _make_combo(
    combo_id: str,
    name: str,
    card_names: list[str],
    description: str = "A sample combo description.",
) -> ComboWithCards:
    """Create a ComboWithCards with specified cards."""
    return ComboWithCards(
        _id=combo_id,
        name=name,
        description=description,
        uses=[ComboCard(name=cn, zone="battlefield") for cn in card_names],
        cards=[CardWithMetadata(name=cn) for cn in card_names],
        produces=[ComboProduces(description="Infinite damage", infinite=True)],
        tags=["combo"],
    )


@pytest.fixture
def mock_domain():
    """Create a mock domain."""
    domain = MagicMock()
    domain.name = "mtg"
    domain.notation_legend = "<reference>test notation</reference>"
    return domain


@pytest.fixture
def sample_combos():
    """Return sample ComboWithCards objects.

    Includes:
    - Combos with 2+ cards and descriptions (should pass filter)
    - A combo with < 2 cards (should be filtered out)
    - A combo with empty description (should be filtered out)
    """
    return [
        _make_combo("combo-1", "Exquisite Blood + Sanguine Bond", ["Exquisite Blood", "Sanguine Bond"]),
        _make_combo("combo-2", "Mikaeus + Triskelion", ["Mikaeus, the Unhallowed", "Triskelion"], "Persist combo with undying."),
        _make_combo("combo-3", "Deadeye + Palinchron", ["Deadeye Navigator", "Palinchron", "Soulbond"], "Infinite mana combo."),
        # Combo with only 1 card — should be filtered out
        _make_combo("combo-4", "Single Card", ["Sol Ring"]),
        # Combo with empty description — should be filtered out
        _make_combo("combo-5", "No Description Combo", ["Card A", "Card B"], description=""),
    ]


@pytest.fixture
def generator(mock_domain):
    """Create a MultiCardUsageGenerator."""
    gen = MultiCardUsageGenerator(
        domain=mock_domain,
        generation_model=Model(name="test-gen", type=ModelType.GENERATION),
        validation_model=Model(name="test-val", type=ModelType.VALIDATION),
    )
    return gen


@pytest.fixture
def template():
    """Create a simple template for testing."""
    return TemplateConfig(
        template_id="how_to_use_these_together",
        task_instruction="Explain how these cards work together: {combo_name}",
    )


# =============================================================================
# GET_SOURCE_CATEGORY
# =============================================================================


class TestGetSourceCategory:
    def test_returns_correct_category(self, generator):
        """Should return 'multi_card_usage'."""
        assert generator.get_source_category() == "multi_card_usage"


# =============================================================================
# GET_DATA_BATCHES
# =============================================================================


class TestGetDataBatches:
    def test_filters_combos_with_2_plus_cards_and_description(self, generator, sample_combos):
        """Should only include combos with >= 2 cards and non-empty description."""
        ds = MagicMock()
        ds.get_combos_enriched.return_value = sample_combos
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()

        # combo-4 has only 1 card (filtered), combo-5 has empty description (filtered)
        assert len(batches) == 3
        assert all(isinstance(b, ComboWithCards) for b in batches)
        combo_names = {b.name for b in batches}
        assert "Exquisite Blood + Sanguine Bond" in combo_names
        assert "Mikaeus + Triskelion" in combo_names
        assert "Deadeye + Palinchron" in combo_names
        assert "Single Card" not in combo_names
        assert "No Description Combo" not in combo_names

    def test_all_combos_have_two_or_more_uses(self, generator, sample_combos):
        """Every returned combo should have at least 2 uses."""
        ds = MagicMock()
        ds.get_combos_enriched.return_value = sample_combos
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()

        for combo in batches:
            assert len(combo.uses) >= 2

    def test_calls_get_combos_enriched_with_limit_100(self, generator):
        """Should call get_combos_enriched with limit=100."""
        ds = MagicMock()
        ds.get_combos_enriched.return_value = []
        generator.domain.get_data_source.return_value = ds

        generator.get_data_batches()
        ds.get_combos_enriched.assert_called_once_with(limit=100)

    def test_empty_combos_list(self, generator):
        """Should handle empty combos list."""
        ds = MagicMock()
        ds.get_combos_enriched.return_value = []
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()
        assert batches == []

    def test_all_filtered_out(self, generator):
        """Should return empty list when no combos match criteria."""
        bad_combos = [
            _make_combo("c1", "Single", ["Card A"], description=""),
            _make_combo("c2", "Empty Desc", ["Card B", "Card C"], description=""),
        ]
        ds = MagicMock()
        ds.get_combos_enriched.return_value = bad_combos
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()
        assert batches == []


# =============================================================================
# BUILD_PROMPT
# =============================================================================


class TestBuildPrompt:
    def test_includes_combo_name_and_card_details(self, generator, template):
        """Should include combo name and all card names in the prompt."""
        combo = _make_combo(
            "combo-1",
            "Exquisite Blood + Sanguine Bond",
            ["Exquisite Blood", "Sanguine Bond"],
            "Infinite life drain combo when one triggers off the other.",
        )
        prompt = generator.build_prompt(template, combo)

        assert "<reference>test notation</reference>" in prompt
        assert "<task>" in prompt
        assert "</task>" in prompt
        assert "Exquisite Blood" in prompt
        assert "Sanguine Bond" in prompt
        assert "Infinite life drain combo" in prompt

    def test_shows_card_count_and_produces(self, generator, template):
        """Should indicate how many cards are in the combo and what it produces."""
        combo = _make_combo(
            "combo-2",
            "Mikaeus + Triskelion",
            ["Mikaeus, the Unhallowed", "Triskelion"],
            "Persist combo.",
        )
        prompt = generator.build_prompt(template, combo)

        assert "Cards in combo: 2" in prompt
        assert "Infinite damage" in prompt or "infinite" in prompt.lower()

    def test_wraps_in_task_tags(self, generator, template):
        """Should wrap the prompt in <task> tags."""
        combo = _make_combo("combo-3", "Test Combo", ["Card A", "Card B"], "Test description.")
        prompt = generator.build_prompt(template, combo)

        assert "<task>" in prompt
        assert "</task>" in prompt


# =============================================================================
# BUILD_CONTEXT
# =============================================================================


class TestBuildContext:
    def test_returns_formatted_context(self, generator):
        """Should return context with category, combo name, and card names."""
        combo = _make_combo(
            "combo-1",
            "Exquisite Blood + Sanguine Bond",
            ["Exquisite Blood", "Sanguine Bond"],
            "A combo description.",
        )
        context = generator.build_context(combo)

        assert context is not None
        assert "multi_card_usage" in context
        assert "Exquisite Blood + Sanguine Bond" in context or "Exquisite Blood" in context
        assert "Sanguine Bond" in context
        assert "Card count: 2" in context

    def test_handles_unnamed_combo(self, generator):
        """Should handle combo with no name."""
        combo = _make_combo("combo-no-name", "", ["Card A", "Card B"], "Test.")
        context = generator.build_context(combo)

        assert context is not None
        assert "multi_card_usage" in context
        assert "Unnamed" in context or "Card count: 2" in context
