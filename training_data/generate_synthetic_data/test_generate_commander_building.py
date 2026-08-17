"""Unit tests for card-aware validation context builders (Story 050).

The validation context must mirror the generation prompt's card data (Mana Cost,
Type, Oracle Text, Color Identity) so the validator can ground color-identity
legality and mana-cost claims instead of rejecting them as UNSUPPORTED.
"""

from pathlib import Path
import random
from unittest.mock import patch

import pytest

from training_data.generate_synthetic_data.base_generator import BaseGenerator, TemplateConfig
from training_data.generate_synthetic_data.common import NEW_LINE
from training_data.generate_synthetic_data.domain_models import CardFace, CardWithMetadata, CommanderWithTags, Article, Guide
from training_data.generate_synthetic_data.generate_commander_building import (
    ARCHETYPE_KEY_CARDS,
    ARTICLE_POOL_SIZE,
    COMMANDER_POOL_SIZE,
    COMMANDERS_PER_BATCH,
    CommanderBuildingBatch,
    GenerateCommanderBuilding,
    GUIDE_POOL_SIZE,
)
from training_data.generate_synthetic_data.generate_commander_knowledge import (
    CommanderKnowledgeBatch,
    GenerateCommanderKnowledge,
)
from training_data.generate_synthetic_data.generate_synergy_questions import (
    GenerateSynergyQuestions,
    SynergyDataBatch,
)


def create_mock_card(
    name: str,
    color_identity: list[str],
    mana_cost: str = "{1}{R}",
    text: str = "Test card text.",
    type_line: str = "Creature — Elemental",
    edhrec_rank: int = 100,
) -> CardWithMetadata:
    """Create a mock CardWithMetadata for testing."""
    face = CardFace(
        name=name,
        manaCost=mana_cost,
        type=type_line,
        text=text,
        colors=color_identity,
        colorIdentity=color_identity,
        keywords=[],
    )
    return CardWithMetadata(
        name=name,
        uuid=f"uuid-{name}",
        faces=[face],
        mana_cost=mana_cost,
        type=type_line,
        text=text,
        oracle_text=text,
        color_identity=color_identity,
        keywords=[],
        edhrec_rank=edhrec_rank,
        edhrec_salt=0.0,
        edhrec_tags=[],
    )


def create_mock_commander(
    name: str, color_identity: list[str], num_decks: int = 1000
) -> CommanderWithTags:
    card_details = create_mock_card(
        name=name,
        color_identity=color_identity,
        mana_cost="{2}{R}{R}",
        text="Legendary commander text.",
        type_line="Legendary Creature — Human Shaman",
    )
    return CommanderWithTags(
        name=name,
        color_identity=color_identity,
        tags=[],
        num_decks=num_decks,
        salt=0.0,
        card_uuid=f"uuid-{name}",
        card_details=card_details,
    )


class TestCommanderBuildingContext:
    """Validation context mirrors the generation card data for commander_building."""

    def _build(self):
        generator = GenerateCommanderBuilding(
            data_access=None, models={}, validation_pct=0.0, target_count=1
        )
        batch = CommanderBuildingBatch(
            archetype_name="spellslinger/magecraft",
            archetype_description="Cast instants and sorceries.",
            example_commanders=[create_mock_commander("Ashling the Pilgrim", ["R"])],
            key_cards=[create_mock_card("Guttersnipe", ["R"], mana_cost="{2}{R}")],
            win_conditions=["Burn"],
            weaknesses=["Board wipes"],
        )
        template = TemplateConfig(template_id="general_advice", task_instruction="Instruction")
        return generator, batch, template

    def test_context_includes_color_identity(self):
        generator, batch, template = self._build()
        context = generator.build_context(template, batch)
        assert "Color Identity: R" in context

    def test_context_includes_mana_cost(self):
        generator, batch, template = self._build()
        context = generator.build_context(template, batch)
        assert "Mana Cost: {2}{R}" in context
        assert "Mana Cost: {2}{R}{R}" in context

    def test_context_includes_type(self):
        generator, batch, template = self._build()
        context = generator.build_context(template, batch)
        assert "Type: Legendary Creature — Human Shaman" in context
        assert "Type: Creature — Elemental" in context

    def test_context_includes_oracle_text(self):
        generator, batch, template = self._build()
        context = generator.build_context(template, batch)
        assert "Test card text." in context
        assert "Legendary commander text." in context

    def test_context_grounds_legality_claims(self):
        """The exact claim that previously failed ('Guttersnipe is legal in
        Ashling's deck') must now be verifiable from the context alone."""
        generator, batch, template = self._build()
        context = generator.build_context(template, batch)
        ashling_idx = context.index("Ashling the Pilgrim")
        guttersnipe_idx = context.index("Guttersnipe")
        # Both cards expose their color identity so R ⊆ R is checkable.
        assert "Color Identity: R" in context
        assert ashling_idx < guttersnipe_idx


class TestCommanderKnowledgeContext:
    """Validation context mirrors the generation card data for commander_rules."""

    def _build(self):
        generator = GenerateCommanderKnowledge(
            data_access=None, models={}, validation_pct=0.0, target_count=1
        )
        batch = CommanderKnowledgeBatch(
            topic="deck construction rules",
            topic_context="Color identity determines deck legality.",
            example_commanders=[create_mock_card("Sisay, Weatherlight Captain", ["W", "U", "B", "R", "G"])],
            key_cards=[create_mock_card("Arcane Signet", [], mana_cost="{2}")],
        )
        template = TemplateConfig(template_id="rules", task_instruction="Instruction")
        return generator, batch, template

    def test_context_includes_color_identity(self):
        generator, batch, template = self._build()
        context = generator.build_context(template, batch)
        assert "Color Identity: W, U, B, R, G" in context

    def test_context_includes_mana_cost(self):
        generator, batch, template = self._build()
        context = generator.build_context(template, batch)
        assert "Mana Cost: {2}" in context

    def test_context_includes_type(self):
        generator, batch, template = self._build()
        context = generator.build_context(template, batch)
        assert "Type: Creature — Elemental" in context


class TestSynergyContext:
    """Validation context mirrors the generation card data for synergy."""

    def _build(self):
        generator = GenerateSynergyQuestions(
            data_access=None, models={}, validation_pct=0.0, target_count=1
        )
        primary = create_mock_card("Guttersnipe", ["R"], mana_cost="{2}{R}")
        partner = create_mock_card("Young Pyromancer", ["R"], mana_cost="{1}{R}")
        batch = SynergyDataBatch(
            primary_card=primary,
            combo_partners=[partner],
            tribal_partners=[],
            mechanic_partners=[],
            commander_partners=[],
            edhrec_tags=["burn"],
            combo_descriptions=[],
            shared_keywords=[],
            creature_types=["Human"],
        )
        template = TemplateConfig(template_id="generic", task_instruction="Instruction")
        return generator, batch, template

    def test_primary_card_includes_color_identity(self):
        generator, batch, template = self._build()
        context = generator.build_context(template, batch)
        assert "Color Identity: R" in context

    def test_primary_card_includes_mana_cost(self):
        generator, batch, template = self._build()
        context = generator.build_context(template, batch)
        assert "Mana Cost: {2}{R}" in context

    def test_partners_include_mana_cost_and_type(self):
        generator, batch, template = self._build()
        context = generator.build_context(template, batch)
        assert "Mana Cost: {1}{R}" in context
        assert "Type: Creature — Elemental" in context


class TestCommanderBuildingTemplateManaCostRule:
    """The generator task block must forbid stating mana costs not in source."""

    TEMPLATES_DIR = Path(__file__).parent / "templates"

    @pytest.mark.parametrize("template_id", ["general_advice", "example_driven"])
    def test_instruction_forbids_unverbatim_mana_costs(self, template_id):
        import yaml

        entries = yaml.safe_load((self.TEMPLATES_DIR / "commander_building.yaml").read_text(encoding="utf-8"))
        entry = next(e for e in entries if e["template_id"] == template_id)
        instruction = entry["instruction"]
        assert "mana cost" in instruction.lower()
        assert "verbatim" in instruction.lower()


def _make_commander(name: str, text: str, num_decks: int = 1000) -> CommanderWithTags:
    card = create_mock_card(name=name, color_identity=["R"], text=text)
    return CommanderWithTags(
        name=name,
        color_identity=["R"],
        tags=[],
        num_decks=num_decks,
        salt=0.0,
        card_uuid=f"uuid-{name}",
        card_details=card,
    )


class _FakeDataAccess:
    """Minimal stand-in exposing get_cards_enriched for key-card lookup."""

    def __init__(self, cards):
        self.cards = cards

    def get_cards_enriched(self, filters=None, limit=100, skip=0, lite=False):
        return self.cards


class TestCommanderBuildingRandomization:
    """Commander/key-card/article selection is randomized for batch variety."""

    SACRIFICE = "sacrifice/aristocrats"

    def _generator(self):
        return GenerateCommanderBuilding(
            data_access=None, models={}, validation_pct=0.0, target_count=1
        )

    def _populate_commander_cache(self, gen, count, text="You may sacrifice a creature"):
        cmds = [
            _make_commander(f"Commander{i}", text=text, num_decks=1000 - i)
            for i in range(count)
        ]
        gen._commander_cache = {"aristocrats": cmds}
        return cmds

    def test_commander_selection_samples_from_scored_pool(self):
        gen = self._generator()
        cmds = self._populate_commander_cache(gen, 40)
        with patch(
            "training_data.generate_synthetic_data.generate_commander_building.random.sample",
            wraps=random.sample,
        ) as mock_sample:
            result = gen._fetch_commanders_for_archetype(self.SACRIFICE)
            mock_sample.assert_called_once()
            pool, k = mock_sample.call_args[0][0], mock_sample.call_args.kwargs["k"]
        assert k == min(COMMANDERS_PER_BATCH, len(pool))
        assert len(pool) <= COMMANDER_POOL_SIZE
        assert len(result) <= COMMANDERS_PER_BATCH
        assert all(c.name in {c.name for c in cmds} for c in result)

    def test_commander_selection_varies_across_calls(self):
        gen = self._generator()
        self._populate_commander_cache(gen, 60)
        seen = set()
        for _ in range(10):
            seen.update(c.name for c in gen._fetch_commanders_for_archetype(self.SACRIFICE))
        assert len(seen) > COMMANDERS_PER_BATCH

    def test_fallback_archetype_samples_uniformly(self):
        gen = self._generator()
        cmds = self._populate_commander_cache(gen, 12)
        with patch(
            "training_data.generate_synthetic_data.generate_commander_building.random.sample",
            wraps=random.sample,
        ) as mock_sample:
            result = gen._fetch_commanders_for_archetype("midrange goodstuff")
            mock_sample.assert_called_once()
            pool, k = mock_sample.call_args[0][0], mock_sample.call_args.kwargs["k"]
        assert k == min(COMMANDERS_PER_BATCH, len(pool))
        assert len(pool) <= COMMANDER_POOL_SIZE
        assert len(result) == min(COMMANDERS_PER_BATCH, len(cmds))

    def test_key_cards_shuffled_across_calls(self):
        fallback_names = ARCHETYPE_KEY_CARDS[self.SACRIFICE]
        cards = [create_mock_card(name, ["B"]) for name in fallback_names]
        gen = self._generator()
        gen.data_access = _FakeDataAccess(cards)
        gen._archetypes_db = {}

        first = gen._fetch_key_cards_for_archetype(self.SACRIFICE)
        second = gen._fetch_key_cards_for_archetype(self.SACRIFICE)
        third = gen._fetch_key_cards_for_archetype(self.SACRIFICE)

        assert {c.name for c in first} == set(fallback_names)
        assert not (first == second == third)

    def test_articles_sampled_from_top_matches(self):
        gen = self._generator()
        gen._articles = [
            Article(title=f"Sacrifice guide {i}", content="x", tags=["sacrifice", "aristocrats"])
            for i in range(8)
        ]
        with patch(
            "training_data.generate_synthetic_data.generate_commander_building.random.sample",
            wraps=random.sample,
        ) as mock_sample:
            result = gen._fetch_articles_for_archetype(self.SACRIFICE)
            mock_sample.assert_called_once()
            pool, k = mock_sample.call_args[0][0], mock_sample.call_args.kwargs["k"]
        assert k == min(2, len(pool))
        assert len(pool) <= ARTICLE_POOL_SIZE
        assert len(result) == 2
        assert all(a.title.startswith("Sacrifice guide") for a in result)

    def test_guides_sampled_from_top_matches(self):
        gen = self._generator()
        gen._guides = [
            Guide(title=f"Aristocrats how-to {i}", chapters=[], tags=["sacrifice", "dies"])
            for i in range(8)
        ]
        with patch(
            "training_data.generate_synthetic_data.generate_commander_building.random.sample",
            wraps=random.sample,
        ) as mock_sample:
            result = gen._fetch_guides_for_archetype(self.SACRIFICE)
            mock_sample.assert_called_once()
            pool, k = mock_sample.call_args[0][0], mock_sample.call_args.kwargs["k"]
        assert k == min(2, len(pool))
        assert len(pool) <= GUIDE_POOL_SIZE
        assert len(result) == 2
        assert all(g.title.startswith("Aristocrats how-to") for g in result)
