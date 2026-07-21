"""Unit tests for GenerateReverseLookupQuestions generator."""

import json
from unittest.mock import MagicMock, Mock, patch
from typing import Iterator

import pytest

from training_data.generate_synthetic_data.base_generator import BaseGenerator, TemplateConfig
from training_data.generate_synthetic_data.generate_reverse_lookup_questions import (
    GenerateReverseLookupQuestions,
    KeywordContext,
    LOOKUP_CATEGORIES,
    RULE_SECTIONS,
)
from training_data.generate_synthetic_data.models import (
    Model,
    ModelType,
    ModelProvider,
    QuestionAnswer,
    QuestionAnswerEnhanced,
    ValidationMetrics,
)
from training_data.generate_synthetic_data.domain_models import CardWithMetadata, CardFace
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
            {"question": "Test question?", "answer": "Test answer with sufficient length to pass validation."}
        ])

    def validate_qa(self, validation_model: Model, question: str, answer: str, context: str = "", category: str = "", enable_extra_validation: bool = True):
        self.validate_call_count += 1
        if self.validate_responses:
            return self.validate_responses.pop(0)
        return True, "OK", 8.0

    def regenerate_answer(self, generation_model: Model, question: str, old_answer: str, reason: str, score: float | None, context: str = "", category: str = "") -> str | None:
        self.regenerate_call_count += 1
        if self.regenerate_responses:
            return self.regenerate_responses.pop(0)
        return "Regenerated answer with sufficient length to pass validation."


class MockDataAccess:
    """Mock MTGDataAccess for testing."""
    def __init__(self):
        self.keyword_taxonomy = {
            "flying": ["Creatures with flying can't be blocked except by creatures with flying or reach."],
            "landfall": ["Whenever a land enters the battlefield under your control, trigger an ability."],
            "elf": ["Creature type elf."],
            "protect commander": ["Cards that protect your commander."],
        }
        self.cards_by_keyword = {}
        self.cards_by_text = {}

    def get_keyword_taxonomy(self) -> dict[str, list[str]]:
        return self.keyword_taxonomy

    def get_cards_by_keyword_mechanic(self, keyword: str, limit: int = 100):
        return self.cards_by_keyword.get(keyword, [])

    def search_cards_text(self, regex: str, filters: dict | None = None, limit: int = 100):
        # Handle tribe searches (word boundary patterns)
        for pattern, cards in self.cards_by_text.items():
            if pattern in regex or regex in pattern:
                return cards
        # Handle utility searches
        if "protect.*commander" in regex or "commander.*protect" in regex:
            return self.cards_by_text.get(r"protect.*commander|commander.*protect", [])
        # Return empty for unknown searches
        return []

    def connect(self):
        pass

    def close(self):
        pass


def create_mock_card(name: str, edhrec_rank: int = 100, keywords: list[str] = None, **kwargs) -> CardWithMetadata:
    """Create a mock CardWithMetadata for testing."""
    face = CardFace(
        name=name,
        manaCost=kwargs.get("mana_cost", "{1}{G}"),
        type=kwargs.get("type", "Creature — Bird"),
        text=kwargs.get("text", "Flying"),
        power=kwargs.get("power", "1"),
        toughness=kwargs.get("toughness", "1"),
        colors=kwargs.get("colors", ["G"]),
        colorIdentity=kwargs.get("color_identity", ["G"]),
        keywords=keywords or [],
    )
    card = CardWithMetadata(
        name=name,
        uuid=kwargs.get("uuid", f"uuid-{name}"),
        faces=[face],
        mana_cost=kwargs.get("mana_cost", "{1}{G}"),
        type=kwargs.get("type", "Creature — Bird"),
        text=kwargs.get("text", "Flying"),
        oracle_text=kwargs.get("text", "Flying"),
        color_identity=kwargs.get("color_identity", ["G"]),
        keywords=keywords or [],
        edhrec_rank=edhrec_rank,
        edhrec_salt=kwargs.get("salt", 0.0),
        edhrec_tags=kwargs.get("tags", []),
    )
    return card


class TestGenerateReverseLookupQuestions:
    """Tests for GenerateReverseLookupQuestions generator."""

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

        # Set up mock cards
        self.data_access.cards_by_keyword["flying"] = [
            create_mock_card("Birds of Paradise", edhrec_rank=50, keywords=["Flying", "Mana"]),
            create_mock_card("Serra Angel", edhrec_rank=200, keywords=["Flying", "Vigilance"]),
            create_mock_card("Stormfront Pegasus", edhrec_rank=500, keywords=["Flying"]),
        ]
        self.data_access.cards_by_keyword["landfall"] = [
            create_mock_card("Lotus Cobra", edhrec_rank=100, keywords=["Landfall"]),
            create_mock_card("Scute Swarm", edhrec_rank=150, keywords=["Landfall"]),
        ]
        self.data_access.cards_by_keyword["elf"] = [
            create_mock_card("Llanowar Elves", edhrec_rank=80, keywords=["Mana"], type="Creature — Elf Druid"),
            create_mock_card("Elvish Archdruid", edhrec_rank=120, keywords=["Mana"], type="Creature — Elf Druid"),
        ]
        self.data_access.cards_by_text = {
            r"protect.*commander|commander.*protect": [
                create_mock_card("Swiftfoot Boots", edhrec_rank=30, keywords=["Equip"], type="Artifact — Equipment"),
                create_mock_card("Lightning Greaves", edhrec_rank=25, keywords=["Equip", "Haste"], type="Artifact — Equipment"),
            ],
            r"\belf\b": [
                create_mock_card("Llanowar Elves", edhrec_rank=80, keywords=["Mana"], type="Creature — Elf Druid"),
                create_mock_card("Elvish Archdruid", edhrec_rank=120, keywords=["Mana"], type="Creature — Elf Druid"),
                create_mock_card("Ezuri, Renegade Leader", edhrec_rank=200, keywords=["Regenerate"], type="Legendary Creature — Elf Warrior"),
            ],
        }

    def test_templates_defined(self):
        """Test that all four templates are defined."""
        generator = GenerateReverseLookupQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        template_ids = [t.template_id for t in generator.TEMPLATES]
        assert "mechanic_search" in template_ids
        assert "tribal_search" in template_ids
        assert "utility_search" in template_ids
        assert "commander_search" in template_ids
        assert len(generator.TEMPLATES) == 4

    def test_get_source_category(self):
        """Test source category."""
        generator = GenerateReverseLookupQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )
        assert generator.get_source_category() == "reverse_lookup"

    def test_build_keyword_list(self):
        """Test keyword list building."""
        generator = GenerateReverseLookupQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        # Trigger keyword list building
        list(generator.get_data_batches())

        # Should have keywords from taxonomy and LOOKUP_CATEGORIES
        assert len(generator._all_keywords) > 0

        # Check categorization
        keyword_names = [k[0] for k in generator._all_keywords]
        assert "flying" in keyword_names
        assert "landfall" in keyword_names
        assert "elf" in keyword_names

    def test_categorize_keyword(self):
        """Test keyword categorization."""
        generator = GenerateReverseLookupQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        assert generator._categorize_keyword("flying") == "keywords"
        assert generator._categorize_keyword("landfall") == "mechanics"
        assert generator._categorize_keyword("elf") == "tribes"
        assert generator._categorize_keyword("protect commander") == "utility"
        assert generator._categorize_keyword("unknown_keyword") == "keywords"  # default

    def test_build_keyword_context_mechanic(self):
        """Test building context for a mechanic."""
        generator = GenerateReverseLookupQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        context = generator._build_keyword_context("landfall", "mechanics")

        assert context is not None
        assert context.name == "landfall"
        assert context.category == "mechanics"
        assert "land enters" in context.description.lower()
        assert context.rule_section == "702.144"
        assert len(context.example_cards) == 2
        assert context.example_cards[0].name == "Lotus Cobra"  # Sorted by EDHREC rank

    def test_build_keyword_context_keyword(self):
        """Test building context for a keyword."""
        generator = GenerateReverseLookupQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        context = generator._build_keyword_context("flying", "keywords")

        assert context is not None
        assert context.name == "flying"
        assert context.category == "keywords"
        assert "flying" in context.description.lower()
        assert context.rule_section == "702.9"
        assert len(context.example_cards) == 3

    def test_build_keyword_context_tribe(self):
        """Test building context for a tribe."""
        generator = GenerateReverseLookupQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        context = generator._build_keyword_context("elf", "tribes")

        assert context is not None
        assert context.name == "elf"
        assert context.category == "tribes"
        assert len(context.example_cards) == 3

    def test_build_keyword_context_utility(self):
        """Test building context for utility."""
        generator = GenerateReverseLookupQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        context = generator._build_keyword_context("protect commander", "utility")

        assert context is not None
        assert context.name == "protect commander"
        assert context.category == "utility"
        assert len(context.example_cards) == 2

    def test_build_keyword_context_no_cards(self):
        """Test building context when no cards found."""
        generator = GenerateReverseLookupQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        context = generator._build_keyword_context("nonexistent", "mechanics")
        assert context is None

    def test_format_cards_for_prompt(self):
        """Test card formatting for prompt."""
        generator = GenerateReverseLookupQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        cards = [
            create_mock_card("Test Card", edhrec_rank=100, keywords=["Flying"]),
        ]
        formatted = generator._format_cards_for_prompt(cards)

        assert "Test Card" in formatted
        assert "EDHREC Rank: 100" in formatted
        assert "Flying" in formatted

    def test_build_prompt_mechanic_search(self):
        """Test prompt building for mechanic_search template."""
        generator = GenerateReverseLookupQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        context = generator._build_keyword_context("landfall", "mechanics")
        template = next(t for t in generator.TEMPLATES if t.template_id == "mechanic_search")

        prompt = generator.build_prompt(template, context)

        assert "landfall" in prompt.lower()
        assert "Lotus Cobra" in prompt
        assert "Scute Swarm" in prompt
        assert "702.144" in prompt
        assert "What cards have" in prompt
        assert "MTG NOTATION" in prompt

    def test_build_prompt_tribal_search(self):
        """Test prompt building for tribal_search template."""
        generator = GenerateReverseLookupQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        context = generator._build_keyword_context("elf", "tribes")
        template = next(t for t in generator.TEMPLATES if t.template_id == "tribal_search")

        prompt = generator.build_prompt(template, context)

        assert "elf" in prompt.lower()
        assert "Llanowar Elves" in prompt
        assert "Elvish Archdruid" in prompt
        assert "best" in prompt.lower()
        assert "commander" in prompt.lower()

    def test_build_prompt_utility_search(self):
        """Test prompt building for utility_search template."""
        generator = GenerateReverseLookupQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        context = generator._build_keyword_context("protect commander", "utility")
        template = next(t for t in generator.TEMPLATES if t.template_id == "utility_search")

        prompt = generator.build_prompt(template, context)

        assert "protect commander" in prompt.lower()
        assert "Swiftfoot Boots" in prompt
        assert "Lightning Greaves" in prompt

    def test_build_prompt_commander_search(self):
        """Test prompt building for commander_search template."""
        generator = GenerateReverseLookupQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        context = generator._build_keyword_context("landfall", "mechanics")
        template = next(t for t in generator.TEMPLATES if t.template_id == "commander_search")

        prompt = generator.build_prompt(template, context)

        assert "commander" in prompt.lower()
        assert "landfall" in prompt.lower()
        assert "color identity" in prompt.lower()

    def test_build_context(self):
        """Test validation context building."""
        generator = GenerateReverseLookupQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        context = generator._build_keyword_context("flying", "keywords")
        template = generator.TEMPLATES[0]

        val_context = generator.build_context(template, context)

        assert "Category: reverse_lookup" in val_context
        assert "Template: mechanic_search" in val_context
        assert "Keyword/Mechanic: flying" in val_context
        assert "Category: keywords" in val_context
        assert "Rule Section: 702.9" in val_context

    def test_get_source_data(self):
        """Test source data extraction."""
        generator = GenerateReverseLookupQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        context = generator._build_keyword_context("flying", "keywords")
        source_data = generator.get_source_data(context)

        assert len(source_data) == 3  # Top 3 cards (limited to 5)
        assert "Birds of Paradise" in source_data
        assert "Serra Angel" in source_data

    def test_generation_loop_dry_run(self):
        """Test full generation loop in dry run mode."""
        generator = GenerateReverseLookupQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=3,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        # Mock query model
        generator.query_model = MockQueryModel()
        generator.query_model.query_responses = [
            json.dumps([
                {"question": "Q1?", "answer": "A1 with sufficient length to pass validation."},
                {"question": "Q2?", "answer": "A2 with sufficient length to pass validation."},
                {"question": "Q3?", "answer": "A3 with sufficient length to pass validation."},
            ])
        ] * 10  # Enough for multiple templates
        generator.query_model.validate_responses = [
            (True, "OK", 8.0)
        ] * 30

        generator.generate()

        assert generator.generated_count == 3
        assert generator.query_model.query_call_count >= 1
        self.save_item.assert_not_called()  # dry_run=True

    def test_generation_loop_normal_mode(self):
        """Test full generation loop in normal mode."""
        generator = GenerateReverseLookupQuestions(
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
                {"question": "Q1?", "answer": "A1 with sufficient length to pass validation."},
                {"question": "Q2?", "answer": "A2 with sufficient length to pass validation."},
                {"question": "Q3?", "answer": "A3 with sufficient length to pass validation."},
            ])
        ] * 10
        generator.query_model.validate_responses = [
            (True, "OK", 8.0)
        ] * 30

        generator.generate()

        assert generator.generated_count == 2
        assert self.save_item.call_count == 2

    def test_validation_rules_mechanic_search(self):
        """Test validation rules for mechanic_search template."""
        generator = GenerateReverseLookupQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        template = next(t for t in generator.TEMPLATES if t.template_id == "mechanic_search")
        assert "Answer lists 3-5 specific cards from the provided examples" in template.validation_rules
        assert "Answer explains how EACH card uses the mechanic with oracle text quotes" in template.validation_rules
        assert "Answer cites rule section when provided" in template.validation_rules

    def test_validation_rules_tribal_search(self):
        """Test validation rules for tribal_search template."""
        generator = GenerateReverseLookupQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        template = next(t for t in generator.TEMPLATES if t.template_id == "tribal_search")
        assert "Answer mentions tribal synergies (lords, payoffs, kindred)" in template.validation_rules
        assert "Answer includes at least one lord effect" in template.validation_rules
        assert "Answer includes at least one tribal support card" in template.validation_rules

    def test_validation_rules_utility_search(self):
        """Test validation rules for utility_search template."""
        generator = GenerateReverseLookupQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        template = next(t for t in generator.TEMPLATES if t.template_id == "utility_search")
        assert "Answer solves the specific utility problem stated" in template.validation_rules
        assert "Answer explains how EACH card solves the problem mechanically" in template.validation_rules

    def test_validation_rules_commander_search(self):
        """Test validation rules for commander_search template."""
        generator = GenerateReverseLookupQuestions(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        template = next(t for t in generator.TEMPLATES if t.template_id == "commander_search")
        assert "Answer checks color identity of each commander" in template.validation_rules
        assert "Answer explains commander's synergy with theme/mechanic" in template.validation_rules
        assert "Answer includes EDHREC deck count and salt score" in template.validation_rules

    def test_lookup_categories_defined(self):
        """Test that LOOKUP_CATEGORIES has all required categories."""
        assert "mechanics" in LOOKUP_CATEGORIES
        assert "keywords" in LOOKUP_CATEGORIES
        assert "tribes" in LOOKUP_CATEGORIES
        assert "utility" in LOOKUP_CATEGORIES

        # Check some expected keywords
        assert "landfall" in LOOKUP_CATEGORIES["mechanics"]
        assert "flying" in LOOKUP_CATEGORIES["keywords"]
        assert "elf" in LOOKUP_CATEGORIES["tribes"]
        assert "protect commander" in LOOKUP_CATEGORIES["utility"]

    def test_rule_sections_defined(self):
        """Test that RULE_SECTIONS has mappings for key mechanics/keywords."""
        assert "landfall" in RULE_SECTIONS
        assert "flying" in RULE_SECTIONS
        assert "proliferate" in RULE_SECTIONS
        assert "partner" in RULE_SECTIONS


class TestKeywordContext:
    """Tests for KeywordContext dataclass."""

    def test_keyword_context_creation(self):
        """Test KeywordContext creation."""
        cards = [create_mock_card("Test Card")]
        context = KeywordContext(
            name="flying",
            category="keywords",
            description="Creatures with flying can't be blocked...",
            rule_section="702.9",
            example_cards=cards,
        )

        assert context.name == "flying"
        assert context.category == "keywords"
        assert context.description == "Creatures with flying can't be blocked..."
        assert context.rule_section == "702.9"
        assert len(context.example_cards) == 1

    def test_keyword_context_frozen(self):
        """Test that KeywordContext is frozen (immutable)."""
        cards = [create_mock_card("Test Card")]
        context = KeywordContext(
            name="flying",
            category="keywords",
            description="Test",
            rule_section="702.9",
            example_cards=cards,
        )

        with pytest.raises(AttributeError):
            context.name = "modified"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])