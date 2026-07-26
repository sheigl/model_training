"""Unit tests for GenerateColorIdentityQuestions generator."""

import json
from unittest.mock import MagicMock, Mock, patch
from typing import Iterator

import pytest

from training_data.generate_synthetic_data.base_generator import BaseGenerator, TemplateConfig
from training_data.generate_synthetic_data.generate_color_identity_questions import (
    GenerateColorIdentityQuestions,
    ColorIdentityContext,
    COLOR_SYMBOL_MAP,
    COLOR_PAIR_NAMES,
    WEDGE_NAMES,
    SHARD_NAMES,
    RULE_903_4,
)
from training_data.generate_synthetic_data.models import (
    Model,
    ModelType,
    ModelProvider,
    QuestionAnswer,
    QuestionAnswerEnhanced,
    ValidationMetrics,
)
from training_data.generate_synthetic_data.domain_models import CardWithMetadata, CardFace, CommanderWithTags
from training_data.generate_synthetic_data.query_model import QueryModel


class MockModel(Model):
    """Mock model for testing."""
    def __init__(self, name: str = "test-model", model_type: ModelType = ModelType.GENERATION):
        self.name = name
        self.type = model_type
        self.provider = ModelProvider.OLLAMA
        self.provider_url = "http://localhost:11434"
        self.api_key = None


class MockQueryModel(QueryModel):
    """Mock QueryModel for testing."""
    def __init__(self):
        super().__init__()
        self.query_responses = []
        self.validate_responses = []
        self.regenerate_responses = []
        self.query_call_count = 0
        self.validate_call_count = 0
        self.regenerate_call_count = 0

    def query(self, model: Model, prompt: str, max_tokens: int = 8192) -> str:
        self.query_call_count += 1
        if self.query_responses:
            return self.query_responses.pop(0)
        return json.dumps([
            {"question": "Test question?", "answer": "Test answer with sufficient length to pass validation requirements."}
        ])

    def validate_qa(self, validation_model: Model, question: str, answer: str, context: str = "", category: str = "", enable_extra_validation: bool = True):
        self.validate_call_count += 1
        if self.validate_responses:
            return self.validate_responses.pop(0)
        return True, "OK", 8.0

    def regenerate_answer(self, generation_model: Model, question: str, old_answer: str, reason: str, score: float | None, context: str = "", category: str = "", sibling_feedback: str = "") -> str | None:
        self.regenerate_call_count += 1
        if self.regenerate_responses:
            return self.regenerate_responses.pop(0)
        return "Regenerated answer with sufficient length to pass validation."


class MockDataAccess:
    """Mock MTGDataAccess for testing."""
    def __init__(self):
        self.commanders = []
        self.cards = []

    def get_commanders_enriched(self, filters: dict | None = None, limit: int = 100) -> list[CommanderWithTags]:
        return self.commanders[:limit]

    def get_cards_enriched(self, filters: dict | None = None, limit: int = 100, skip: int = 0, lite: bool = False) -> list[CardWithMetadata]:
        return self.cards[skip:skip+limit]

    def connect(self):
        pass

    def close(self):
        pass


def create_mock_commander(name: str, color_identity: list[str], num_decks: int = 1000, tags: list[str] = None) -> CommanderWithTags:
    """Create a mock CommanderWithTags for testing."""
    face = CardFace(
        name=name,
        manaCost="{1}{W}{U}",
        type="Legendary Creature — Human Wizard",
        text="Test commander",
        colors=color_identity,
        colorIdentity=color_identity,
        keywords=[],
    )
    card_details = CardWithMetadata(
        name=name,
        uuid=f"uuid-{name}",
        faces=[face],
        mana_cost="{1}{W}{U}",
        type="Legendary Creature — Human Wizard",
        text="Test commander",
        oracle_text="Test commander",
        color_identity=color_identity,
        keywords=[],
        edhrec_rank=100,
        edhrec_salt=0.5,
        edhrec_tags=tags or [],
    )
    return CommanderWithTags(
        name=name,
        color_identity=color_identity,
        tags=tags or [],
        num_decks=num_decks,
        salt=0.5,
        card_uuid=f"uuid-{name}",
        card_details=card_details,
    )


def create_mock_card(name: str, color_identity: list[str], mana_cost: str = "{1}{W}", text: str = "Test card", type_line: str = "Creature — Human") -> CardWithMetadata:
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
        edhrec_rank=100,
        edhrec_salt=0.0,
        edhrec_tags=[],
    )


class TestGenerateColorIdentityQuestions:
    """Tests for GenerateColorIdentityQuestions generator."""

    def setup_method(self):
        """Set up test fixtures."""
        self.models = {
            ModelType.GENERATION: MockModel("gen-model", ModelType.GENERATION),
            ModelType.VALIDATION: MockModel("val-model", ModelType.VALIDATION),
        }
        self.save_item = Mock()
        self.metrics = Mock()
        self.metrics.generator_name = "unknown"
        self.metrics.generation_model = "unknown"
        self.metrics.validation_model = "unknown"
        self.metrics.run_id = "test-run-id"
        self.metrics.flush = Mock()
        self.metrics.print_rolling_summary = Mock()
        self.metrics.record_candidate = Mock()
        self.metrics.record_validation_attempt = Mock()
        self.metrics.record_skip = Mock()
        self.metrics.record_first_attempt_pass = Mock()
        self.metrics.record_pass_after_fix = Mock()
        self.metrics.record_failed_first_attempt = Mock()
        self.metrics.record_failed_after_fixes = Mock()
        self.metrics.record_fix_attempt = Mock()

        self.data_access = MockDataAccess()

        # Set up mock commanders (various color identities)
        self.data_access.commanders = [
            create_mock_commander("Krenko, Mob Boss", ["R"], num_decks=5000, tags=["aggro", "goblin"]),
            create_mock_commander("Elesh Norn, Grand Cenobite", ["W"], num_decks=3000, tags=["control", "stax"]),
            create_mock_commander("Niv-Mizzet, Parun", ["U", "R"], num_decks=4000, tags=["combo", "draw"]),
            create_mock_commander("Korvold, Fae-Cursed King", ["B", "R", "G"], num_decks=3500, tags=["sacrifice", "aristocrats"]),
            create_mock_commander("Kenrith, the Returned King", ["W", "U", "B", "R", "G"], num_decks=6000, tags=["goodstuff", "politics"]),
            create_mock_commander("Atraxa, Praetors' Voice", ["W", "U", "B", "G"], num_decks=5500, tags=["proliferate", "superfriends"]),
            create_mock_commander("Tymna the Weaver", ["W", "B"], num_decks=4500, tags=["card draw", "lifegain"]),
            create_mock_commander("The Gitrog Monster", ["B", "G"], num_decks=3000, tags=["lands", "graveyard"]),
        ]

        # Set up mock cards with various color identities
        self.data_access.cards = [
            create_mock_card("Lightning Bolt", ["R"], "{R}", "Deal 3 damage to any target.", "Instant"),
            create_mock_card("Counterspell", ["U"], "{U}{U}", "Counter target spell.", "Instant"),
            create_mock_card("Swords to Plowshares", ["W"], "{W}", "Exile target creature. Its controller gains life equal to its power.", "Instant"),
            create_mock_card("Dark Ritual", ["B"], "{B}", "Add {B}{B}{B}.", "Instant"),
            create_mock_card("Llanowar Elves", ["G"], "{G}", "{T}: Add {G}.", "Creature — Elf Druid"),
            create_mock_card("Lightning Helix", ["R", "W"], "{R}{W}", "Deal 3 damage to any target and you gain 3 life.", "Instant"),
            create_mock_card("Assassin's Trophy", ["B", "G"], "{B}{G}", "Destroy target permanent. Its controller may search for a basic land.", "Instant"),
            create_mock_card("Abrupt Decay", ["B", "G"], "{B}{G}", "Can't be countered. Destroy target nonland permanent with mana value 3 or less.", "Instant"),
            create_mock_card("Supreme Verdict", ["W", "U"], "{W}{W}{U}{U}", "Can't be countered. Destroy all creatures.", "Sorcery"),
            create_mock_card("Rhystic Study", ["U"], "{2}{U}", "Whenever an opponent casts a spell, you may draw a card unless they pay {1}.", "Enchantment"),
            create_mock_card("Sol Ring", [], "{1}", "{T}: Add {C}{C}.", "Artifact"),
            create_mock_card("Arcane Signet", [], "{2}", "{T}: Add one mana of any color in your commander's color identity.", "Artifact"),
            create_mock_card("Command Tower", [], "", "{T}: Add one mana of any color in your commander's color identity.", "Land"),
            create_mock_card("Fabled Passage", [], "", "{T}, Sacrifice Fabled Passage: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.", "Land"),
            create_mock_card("Niv-Mizzet Reborn", ["W", "U", "B", "R", "G"], "{W}{U}{B}{R}{G}", "When Niv-Mizzet Reborn enters, reveal the top ten cards of your library. For each color pair, choose a card that's exactly those colors. Put the chosen cards into your hand and the rest on the bottom.", "Legendary Creature — Dragon Avatar"),
            create_mock_card("Bring to Light", ["W", "U", "B", "R", "G"], "{W}{U}{B}{R}{G}", "Converge — Search your library for a card with mana value less than or equal to the number of colors of mana spent to cast this spell, exile that card, then shuffle. You may cast that card without paying its mana cost.", "Sorcery"),
        ]

    def test_templates_defined(self):
        """Test that all four templates are defined."""
        generator = GenerateColorIdentityQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        template_ids = [t.template_id for t in generator.TEMPLATES]
        assert "mono_color" in template_ids
        assert "two_color" in template_ids
        assert "three_color" in template_ids
        assert "five_color" in template_ids
        assert len(generator.TEMPLATES) == 4

    def test_get_source_category(self):
        """Test source category."""
        generator = GenerateColorIdentityQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )
        assert generator.get_source_category() == "color_identity"

    def test_commander_distribution(self):
        """Test commander distribution constants."""
        assert GenerateColorIdentityQuestions.COMMANDER_DISTRIBUTION[1] == 10  # mono
        assert GenerateColorIdentityQuestions.COMMANDER_DISTRIBUTION[2] == 15  # two-color
        assert GenerateColorIdentityQuestions.COMMANDER_DISTRIBUTION[3] == 10  # three-color
        assert GenerateColorIdentityQuestions.COMMANDER_DISTRIBUTION[5] == 5   # five-color

    def test_color_symbol_map(self):
        """Test color symbol mapping."""
        assert COLOR_SYMBOL_MAP["W"] == "White"
        assert COLOR_SYMBOL_MAP["U"] == "Blue"
        assert COLOR_SYMBOL_MAP["B"] == "Black"
        assert COLOR_SYMBOL_MAP["R"] == "Red"
        assert COLOR_SYMBOL_MAP["G"] == "Green"

    def test_color_pair_names(self):
        """Test color pair name mapping."""
        assert COLOR_PAIR_NAMES[frozenset(["W", "U"])] == "Azorius"
        assert COLOR_PAIR_NAMES[frozenset(["U", "B"])] == "Dimir"
        assert COLOR_PAIR_NAMES[frozenset(["B", "R"])] == "Rakdos"
        assert COLOR_PAIR_NAMES[frozenset(["R", "G"])] == "Gruul"
        assert COLOR_PAIR_NAMES[frozenset(["G", "W"])] == "Selesnya"
        assert COLOR_PAIR_NAMES[frozenset(["W", "B"])] == "Orzhov"
        assert COLOR_PAIR_NAMES[frozenset(["U", "R"])] == "Izzet"
        assert COLOR_PAIR_NAMES[frozenset(["B", "G"])] == "Golgari"
        assert COLOR_PAIR_NAMES[frozenset(["R", "W"])] == "Boros"
        assert COLOR_PAIR_NAMES[frozenset(["G", "U"])] == "Simic"

    def test_wedge_shard_names(self):
        """Test wedge/shard name mappings."""
        assert WEDGE_NAMES[frozenset(["W", "U", "B"])] == "Esper"
        assert WEDGE_NAMES[frozenset(["U", "B", "R"])] == "Grixis"
        assert WEDGE_NAMES[frozenset(["B", "R", "G"])] == "Jund"
        assert WEDGE_NAMES[frozenset(["R", "G", "W"])] == "Naya"
        assert WEDGE_NAMES[frozenset(["G", "W", "U"])] == "Bant"

    def test_rule_903_4_defined(self):
        """Test that rule 903.4 is defined."""
        assert "903.4" in RULE_903_4
        assert "color identity" in RULE_903_4.lower()

    def test_load_data(self):
        """Test data loading and grouping."""
        generator = GenerateColorIdentityQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        # Trigger data loading
        list(generator.get_data_batches())

        # Check commanders grouped by color identity size
        assert 1 in generator._commanders_by_color_count
        assert 2 in generator._commanders_by_color_count
        assert 3 in generator._commanders_by_color_count
        assert 5 in generator._commanders_by_color_count

        # Check cards grouped by color identity
        assert len(generator._cards_by_color_identity) > 0

    def test_get_template_type(self):
        """Test template type determination."""
        generator = GenerateColorIdentityQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        mono_cmd = create_mock_commander("Test", ["R"])
        two_cmd = create_mock_commander("Test", ["W", "U"])
        three_cmd = create_mock_commander("Test", ["W", "U", "B"])
        five_cmd = create_mock_commander("Test", ["W", "U", "B", "R", "G"])

        assert generator._get_template_type(mono_cmd) == "mono_color"
        assert generator._get_template_type(two_cmd) == "two_color"
        assert generator._get_template_type(three_cmd) == "three_color"
        assert generator._get_template_type(five_cmd) == "five_color"

    def test_build_color_identity_explanation_legal(self):
        """Test explanation building for legal card."""
        generator = GenerateColorIdentityQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        card = create_mock_card("Lightning Bolt", ["R"], "{R}")
        commander = create_mock_commander("Krenko", ["R"])

        explanation = generator._build_color_identity_explanation(card, commander, True)

        assert "LEGAL" in explanation
        assert "Lightning Bolt" in explanation
        assert "Krenko" in explanation
        assert "R" in explanation

    def test_build_color_identity_explanation_illegal(self):
        """Test explanation building for illegal card."""
        generator = GenerateColorIdentityQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        card = create_mock_card("Counterspell", ["U"], "{U}{U}")
        commander = create_mock_commander("Krenko", ["R"])

        explanation = generator._build_color_identity_explanation(card, commander, False)

        assert "ILLEGAL" in explanation
        assert "Counterspell" in explanation
        assert "Krenko" in explanation
        assert "U" in explanation

    def test_build_color_identity_explanation_hybrid(self):
        """Test explanation mentions hybrid mana."""
        generator = GenerateColorIdentityQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        card = create_mock_card("Lightning Helix", ["R", "W"], "{R/W}{R/W}")
        commander = create_mock_commander("Test", ["R", "W"])

        explanation = generator._build_color_identity_explanation(card, commander, True)

        assert "hybrid" in explanation.lower()

    def test_extract_mana_colors(self):
        """Test mana color extraction."""
        generator = GenerateColorIdentityQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        assert generator._extract_mana_colors("{R}") == ["R"]
        assert generator._extract_mana_colors("{W}{U}") == ["U", "W"]
        assert generator._extract_mana_colors("{R/W}{R/W}") == ["R", "W"]
        assert generator._extract_mana_colors("{2}{G}") == ["G"]
        assert generator._extract_mana_colors("") == []

    def test_find_suitable_cards_mono(self):
        """Test finding suitable cards for mono-color commander."""
        generator = GenerateColorIdentityQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )
        list(generator.get_data_batches())  # Load data

        mono_cmd = create_mock_commander("Krenko", ["R"])
        cards = generator._find_suitable_cards(mono_cmd)

        # Should include red cards, colorless cards, and some off-color for testing
        card_names = [c.name for c in cards]
        assert "Lightning Bolt" in card_names  # Red - legal
        assert "Sol Ring" in card_names  # Colorless - legal
        assert "Counterspell" in card_names or "Dark Ritual" in card_names  # Off-color - illegal

    def test_find_suitable_cards_five_color(self):
        """Test finding suitable cards for 5-color commander."""
        generator = GenerateColorIdentityQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )
        list(generator.get_data_batches())  # Load data

        five_cmd = create_mock_commander("Kenrith", ["W", "U", "B", "R", "G"])
        cards = generator._find_suitable_cards(five_cmd)

        # For 5-color, should include complex color identity cards
        card_names = [c.name for c in cards]
        assert "Niv-Mizzet Reborn" in card_names  # 5-color card
        assert "Bring to Light" in card_names  # 5-color card
        assert "Sol Ring" in card_names  # Colorless

    def test_build_prompt_mono_color(self):
        """Test prompt building for mono_color template."""
        generator = GenerateColorIdentityQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )
        list(generator.get_data_batches())  # Load data

        card = create_mock_card("Lightning Bolt", ["R"], "{R}")
        commander = create_mock_commander("Krenko, Mob Boss", ["R"], num_decks=5000)

        context = ColorIdentityContext(
            card=card,
            commander=commander,
            is_legal=True,
            card_color_identity=["R"],
            commander_color_identity=["R"],
            template_type="mono_color",
            color_identity_explanation="Test explanation",
        )

        template = next(t for t in generator.TEMPLATES if t.template_id == "mono_color")
        prompt = generator.build_prompt(template, context)

        assert "mono_color" in prompt or "mono-" in prompt.lower()
        assert "Lightning Bolt" in prompt
        assert "Krenko" in prompt
        assert "R" in prompt
        assert "903.4" in prompt
        assert "MTG NOTATION" in prompt

    def test_build_prompt_two_color(self):
        """Test prompt building for two_color template."""
        generator = GenerateColorIdentityQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )
        list(generator.get_data_batches())

        card = create_mock_card("Lightning Helix", ["R", "W"], "{R}{W}")
        commander = create_mock_commander("Test", ["R", "W"])

        context = ColorIdentityContext(
            card=card,
            commander=commander,
            is_legal=True,
            card_color_identity=["R", "W"],
            commander_color_identity=["R", "W"],
            template_type="two_color",
            color_identity_explanation="Test explanation",
        )

        template = next(t for t in generator.TEMPLATES if t.template_id == "two_color")
        prompt = generator.build_prompt(template, context)

        assert "two_color" in prompt or "color pair" in prompt.lower()
        assert "Lightning Helix" in prompt
        assert "Azorius" in prompt or "R/W" in prompt or "R" in prompt
        assert "hybrid" in prompt.lower()
        assert "903.4" in prompt

    def test_build_prompt_three_color(self):
        """Test prompt building for three_color template."""
        generator = GenerateColorIdentityQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )
        list(generator.get_data_batches())

        card = create_mock_card("Test Card", ["W", "U", "B"], "{W}{U}{B}")
        commander = create_mock_commander("Atraxa", ["W", "U", "B", "G"])

        context = ColorIdentityContext(
            card=card,
            commander=commander,
            is_legal=True,
            card_color_identity=["W", "U", "B"],
            commander_color_identity=["W", "U", "B", "G"],
            template_type="three_color",
            color_identity_explanation="Test explanation",
        )

        template = next(t for t in generator.TEMPLATES if t.template_id == "three_color")
        prompt = generator.build_prompt(template, context)

        assert "three_color" in prompt or "wedge" in prompt.lower() or "shard" in prompt.lower()
        assert "fetch" in prompt.lower()
        assert "903.4" in prompt

    def test_build_prompt_five_color(self):
        """Test prompt building for five_color template."""
        generator = GenerateColorIdentityQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )
        list(generator.get_data_batches())

        card = create_mock_card("Bring to Light", ["W", "U", "B", "R", "G"], "{W}{U}{B}{R}{G}")
        commander = create_mock_commander("Kenrith", ["W", "U", "B", "R", "G"])

        context = ColorIdentityContext(
            card=card,
            commander=commander,
            is_legal=True,
            card_color_identity=["W", "U", "B", "R", "G"],
            commander_color_identity=["W", "U", "B", "R", "G"],
            template_type="five_color",
            color_identity_explanation="Test explanation",
        )

        template = next(t for t in generator.TEMPLATES if t.template_id == "five_color")
        prompt = generator.build_prompt(template, context)

        assert "five_color" in prompt or "5-color" in prompt or "five color" in prompt.lower()
        assert "World Tree" in prompt or "Domain" in prompt
        assert "Niv-Mizzet" in prompt or "Kenrith" in prompt or "Golos" in prompt
        assert "banlist" in prompt.lower()
        assert "903.4" in prompt

    def test_build_context(self):
        """Test validation context building."""
        generator = GenerateColorIdentityQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )
        list(generator.get_data_batches())

        card = create_mock_card("Lightning Bolt", ["R"], "{R}")
        commander = create_mock_commander("Krenko", ["R"])

        context = ColorIdentityContext(
            card=card,
            commander=commander,
            is_legal=True,
            card_color_identity=["R"],
            commander_color_identity=["R"],
            template_type="mono_color",
            color_identity_explanation="Test explanation",
        )

        template = generator.TEMPLATES[0]
        val_context = generator.build_context(template, context)

        assert "Category: color_identity" in val_context
        assert "Template: mono_color" in val_context
        assert "Card: Lightning Bolt" in val_context
        assert "Commander: Krenko" in val_context
        assert "LEGAL" in val_context
        assert "903.4" in val_context

    def test_get_source_data(self):
        """Test source data extraction."""
        generator = GenerateColorIdentityQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )
        list(generator.get_data_batches())

        card = create_mock_card("Lightning Bolt", ["R"], "{R}")
        commander = create_mock_commander("Krenko", ["R"])

        context = ColorIdentityContext(
            card=card,
            commander=commander,
            is_legal=True,
            card_color_identity=["R"],
            commander_color_identity=["R"],
            template_type="mono_color",
            color_identity_explanation="Test",
        )

        source_data = generator.get_source_data(context)

        assert "Lightning Bolt" in source_data
        assert "Krenko" in source_data
        assert "card_ci:R" in source_data
        assert "cmd_ci:R" in source_data
        assert "legal:True" in source_data
        assert "template:mono_color" in source_data

    def test_validation_rules_mono_color(self):
        """Test validation rules for mono_color template."""
        generator = GenerateColorIdentityQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        template = next(t for t in generator.TEMPLATES if t.template_id == "mono_color")
        rules = template.validation_rules

        assert "Answer states YES or NO clearly" in rules
        assert "Answer explains rule 903.4 / color identity rule" in rules
        assert "Answer checks mana cost symbols AND color indicator" in rules
        assert "Answer explains subset relationship (card colors" in " ".join(rules)
        assert "Answer mentions hybrid mana counts as both colors" in rules

    def test_validation_rules_two_color(self):
        """Test validation rules for two_color template."""
        generator = GenerateColorIdentityQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        template = next(t for t in generator.TEMPLATES if t.template_id == "two_color")
        rules = template.validation_rules

        assert "Answer states YES or NO clearly" in rules
        assert "Answer explains both colors in commander's identity" in rules
        assert "Answer addresses hybrid mana counting as both colors" in rules
        assert "Answer distinguishes color vs color identity" in rules
        assert "Answer explains subset rule (card identity" in " ".join(rules)

    def test_validation_rules_three_color(self):
        """Test validation rules for three_color template."""
        generator = GenerateColorIdentityQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        template = next(t for t in generator.TEMPLATES if t.template_id == "three_color")
        rules = template.validation_rules

        assert "Answer states YES or NO clearly" in rules
        assert "Answer identifies wedge vs shard for 3-color commander" in rules
        assert "Answer explains off-color fetch land color identity" in rules
        assert "Answer checks all mana symbols (cost, text, color indicator)" in rules
        assert "Answer explains subset rule for three colors" in rules

    def test_validation_rules_five_color(self):
        """Test validation rules for five_color template."""
        generator = GenerateColorIdentityQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        template = next(t for t in generator.TEMPLATES if t.template_id == "five_color")
        rules = template.validation_rules

        assert "Answer explains 5-color commanders have no color identity restrictions" in rules
        assert "Answer mentions The World Tree and/or Domain mechanics" in rules
        assert "Answer mentions Commander banlist as only restriction" in rules
        assert "Answer mentions 5-color enablers (Converge, Sunburst, Bring to Light)" in rules
        assert "Answer mentions notable 5-color commanders" in rules
        assert "Answer clarifies colorless cards are always legal" in rules

    def test_generation_loop_dry_run(self):
        """Test full generation loop in dry run mode."""
        generator = GenerateColorIdentityQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=3,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        generator.query_model = MockQueryModel()
        generator.query_model.query_responses = [
            json.dumps([
                {"question": "Q1?", "answer": "A1 with sufficient length to pass validation requirements."},
                {"question": "Q2?", "answer": "A2 with sufficient length to pass validation requirements."},
            ])
        ] * 10
        generator.query_model.validate_responses = [
            (True, "OK", 8.0)
        ] * 30

        generator.generate()

        assert generator.generated_count == 3
        assert generator.query_model.query_call_count >= 2  # 2 batches needed for 3 items (2 per batch)
        self.save_item.assert_not_called()  # dry_run=True

    def test_generation_loop_normal_mode(self):
        """Test full generation loop in normal mode."""
        generator = GenerateColorIdentityQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=2,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=False,
        )

        generator.query_model = MockQueryModel()
        generator.query_model.query_responses = [
            json.dumps([
                {"question": "Q1?", "answer": "A1 with sufficient length to pass validation requirements."},
                {"question": "Q2?", "answer": "A2 with sufficient length to pass validation requirements."},
            ])
        ] * 10
        generator.query_model.validate_responses = [
            (True, "OK", 8.0)
        ] * 30

        generator.generate()

        assert generator.generated_count == 2
        assert self.save_item.call_count == 2

    def test_color_identity_context_frozen(self):
        """Test that ColorIdentityContext is frozen (immutable)."""
        card = create_mock_card("Test", ["R"], "{R}")
        commander = create_mock_commander("Test", ["R"])

        context = ColorIdentityContext(
            card=card,
            commander=commander,
            is_legal=True,
            card_color_identity=["R"],
            commander_color_identity=["R"],
            template_type="mono_color",
            color_identity_explanation="Test",
        )

        with pytest.raises(AttributeError):
            context.card = None

    def test_template_weights(self):
        """Test that all templates have equal weight."""
        generator = GenerateColorIdentityQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        for template in generator.TEMPLATES:
            assert template.weight == 1.0

    def test_min_answer_length(self):
        """Test minimum answer length for all templates."""
        generator = GenerateColorIdentityQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        for template in generator.TEMPLATES:
            assert template.min_answer_length == 150


if __name__ == "__main__":
    pytest.main([__file__, "-v"])