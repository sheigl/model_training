"""Unit tests for GenerateQuickGuidelines generator."""

import json
from unittest.mock import MagicMock, Mock, patch
from typing import Iterator

import pytest

from training_data.generate_synthetic_data.base_generator import BaseGenerator, TemplateConfig
from training_data.generate_synthetic_data.generate_quick_guidelines import (
    GenerateQuickGuidelines,
    ARCHETYPES,
    ARCHETYPE_STRATEGIES,
    ARCHETYPE_COMMANDERS,
)
from training_data.generate_synthetic_data.models import (
    Model,
    ModelType,
    ModelProvider,
    QuestionAnswer,
    QuestionAnswerEnhanced,
    ValidationMetrics,
)
from training_data.generate_synthetic_data.query_model import QueryModel
from training_data.generate_synthetic_data.domain_models import Archetype, CommanderWithTags, GameState


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
        return json.dumps([{"question": "Test question?", "answer": "Test answer with sufficient length to pass validation."}])

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
        self.archetype_data = [
            Archetype(
                name="Aristocrats",
                description="Sacrifice creatures for value",
                color_identities=[["B", "W"]],
                key_cards=["Teysa Karlov", "Krav, the Unredeemed", "Judith, the Scourge Diva"],
                strategy="Sacrifice creatures for value, drain life, and generate tokens.",
                win_conditions=["Infinite sacrifice loops", "Drain life"],
                weaknesses=["Graveyard hate", "Board wipes"],
                budget_options=["Budget sacrifice outlets"],
            ),
            Archetype(
                name="Spellslinger",
                description="Cast many spells",
                color_identities=[["U", "R"]],
                key_cards=["Mizzix of the Izmagnus", "Kalamax, the Stormsire"],
                strategy="Cast many instants/sorceries, copy spells, and generate value from spellcasting.",
                win_conditions=["Spell combos", "Burn"],
                weaknesses=["Counterspells", "Tax effects"],
                budget_options=["Budget spell copy effects"],
            ),
        ]
        self.commander_data = [
            CommanderWithTags(
                name="Teysa Karlov",
                color_identity=["W", "B"],
                tags=["aristocrats", "sacrifice", "tokens"],
                num_decks=5000,
                salt=0.5,
                avg_deck_rank=100.0,
                card_uuid="test-uuid-1",
                card_details=None,
            ),
            CommanderWithTags(
                name="Krav, the Unredeemed",
                color_identity=["W", "B"],
                tags=["aristocrats", "draw", "sacrifice"],
                num_decks=3000,
                salt=0.3,
                avg_deck_rank=150.0,
                card_uuid="test-uuid-2",
                card_details=None,
            ),
            CommanderWithTags(
                name="Mizzix of the Izmagnus",
                color_identity=["U", "R"],
                tags=["spellslinger", "experience", "cost reduction"],
                num_decks=4000,
                salt=1.2,
                avg_deck_rank=200.0,
                card_uuid="test-uuid-3",
                card_details=None,
            ),
        ]
        self.game_data = [
            GameState(
                turn=5,
                phase="main1",
                player_state={"life": 40, "hand": 7, "board": []},
                decision_point="play land",
                optimal_action="play land",
            )
        ]

    def get_archetype_data(self):
        return self.archetype_data

    def get_commanders_enriched(self, limit: int = 100):
        return self.commander_data

    def get_game_states(self, limit: int = 100):
        return self.game_data

    def get_top_cards_by_edhrec_rank(self, color_identity: list[str], limit: int = 15):
        # Return mock cards based on color identity
        if "W" in color_identity and "B" in color_identity:
            return [
                type('Card', (), {'name': 'Sol Ring'})(),
                type('Card', (), {'name': 'Arcane Signet'})(),
                type('Card', (), {'name': 'Phyrexian Arena'})(),
            ]
        elif "U" in color_identity and "R" in color_identity:
            return [
                type('Card', (), {'name': 'Sol Ring'})(),
                type('Card', (), {'name': 'Izzet Signet'})(),
                type('Card', (), {'name': 'Rhystic Study'})(),
            ]
        return [
            type('Card', (), {'name': 'Sol Ring'})(),
            type('Card', (), {'name': 'Arcane Signet'})(),
        ]


class TestGenerateQuickGuidelines:
    """Tests for GenerateQuickGuidelines generator."""

    def setup_method(self):
        """Set up test fixtures."""
        self.models = {
            ModelType.GENERATION: MockModel("gen-model", ModelType.GENERATION),
            ModelType.VALIDATION: MockModel("val-model", ModelType.VALIDATION),
        }
        self.data_access = MockDataAccess()
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

    def test_templates_defined(self):
        """Test that all 5 templates are defined."""
        generator = GenerateQuickGuidelines(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        assert len(generator.TEMPLATES) == 5
        template_ids = [t.template_id for t in generator.TEMPLATES]
        assert "land_count" in template_ids
        assert "ramp_package" in template_ids
        assert "removal_suite" in template_ids
        assert "card_advantage" in template_ids
        assert "win_con_density" in template_ids

    def test_template_validation_rules(self):
        """Test that each template has validation rules."""
        generator = GenerateQuickGuidelines(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        for template in generator.TEMPLATES:
            assert template.validation_rules is not None
            assert len(template.validation_rules) > 0
            assert template.min_answer_length >= 120
            assert template.max_answer_length <= 2000

    def test_get_data_batches_yields_archetypes(self):
        """Test that get_data_batches yields all archetypes."""
        generator = GenerateQuickGuidelines(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        batches = list(generator.get_data_batches())
        assert len(batches) == len(ARCHETYPES)

        # Each batch should be a list with one dict containing archetype context
        for batch in batches:
            assert isinstance(batch, list)
            assert len(batch) == 1
            context = batch[0]
            assert "archetype" in context
            assert "strategy" in context
            assert "commanders" in context
            assert "key_cards" in context
            assert "avg_cmc" in context
            assert "color_identity" in context
            assert "deck_stats" in context

    def test_archetype_context_contains_required_fields(self):
        """Test that archetype context has all required fields."""
        generator = GenerateQuickGuidelines(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        # Get first batch (aristocrats)
        batches = list(generator.get_data_batches())
        context = batches[0][0]

        assert context["archetype"] == "aristocrats"
        assert "Sacrifice creatures" in context["strategy"]
        assert "Teysa Karlov" in context["commanders"]
        assert "Krav, the Unredeemed" in context["commanders"]
        assert isinstance(context["key_cards"], list)
        assert isinstance(context["avg_cmc"], float)
        assert isinstance(context["color_identity"], list)
        assert isinstance(context["deck_stats"], dict)
        assert "avg_lands" in context["deck_stats"]
        assert "avg_ramp" in context["deck_stats"]
        assert "avg_removal" in context["deck_stats"]
        assert "avg_card_draw" in context["deck_stats"]
        assert "avg_win_cons" in context["deck_stats"]
        assert "sample_size" in context["deck_stats"]

    def test_build_prompt_includes_context(self):
        """Test that build_prompt includes archetype context."""
        generator = GenerateQuickGuidelines(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        template = generator.TEMPLATES[0]  # land_count
        batches = list(generator.get_data_batches())
        data_batch = batches[0]

        prompt = generator.build_prompt(template, data_batch)

        assert "aristocrats" in prompt
        assert "Sacrifice creatures" in prompt
        assert "Teysa Karlov" in prompt
        assert "How many lands should my" in prompt  # Check template instruction is included
        assert "MTG NOTATION" in prompt
        assert "Output ONLY valid JSON" in prompt

    def test_get_source_category(self):
        """Test source category."""
        generator = GenerateQuickGuidelines(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        assert generator.get_source_category() == "quick_guideline"

    def test_get_source_data(self):
        """Test source data extraction."""
        generator = GenerateQuickGuidelines(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        batches = list(generator.get_data_batches())
        data_batch = batches[0]
        source_data = generator.get_source_data(data_batch)

        assert isinstance(source_data, list)
        assert any("archetype:aristocrats" in s for s in source_data)
        assert any("commanders:" in s for s in source_data)
        assert any("key_cards:" in s for s in source_data)

    def test_build_context_includes_validation_rules(self):
        """Test that build_context includes template-specific validation context."""
        generator = GenerateQuickGuidelines(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        template = generator.TEMPLATES[0]  # land_count
        batches = list(generator.get_data_batches())
        data_batch = batches[0]

        context = generator.build_context(template, data_batch)

        assert "Category: quick_guideline" in context
        assert "Template: land_count" in context
        assert "Archetype: aristocrats" in context
        assert "VALIDATION:" in context
        assert "land count range" in context

    def test_all_archetypes_have_strategies(self):
        """Test that all archetypes have strategy definitions."""
        for archetype in ARCHETYPES:
            assert archetype in ARCHETYPE_STRATEGIES
            assert len(ARCHETYPE_STRATEGIES[archetype]) > 20

    def test_all_archetypes_have_commanders(self):
        """Test that all archetypes have commander examples."""
        for archetype in ARCHETYPES:
            assert archetype in ARCHETYPE_COMMANDERS
            assert len(ARCHETYPE_COMMANDERS[archetype]) >= 2

    def test_dry_run_generation(self):
        """Test dry run generation works."""
        generator = GenerateQuickGuidelines(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=5,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        generator.query_model = MockQueryModel()
        generator.query_model.query_responses = [
            json.dumps([{"question": "How many lands?", "answer": "Aristocrats decks typically run 36-38 lands because they have a low curve and lots of ramp. Teysa Karlov and Krav, the Unredeemed both benefit from hitting land drops early. With 8-10 ramp sources, you can afford fewer lands."}])
            for _ in range(5)
        ]
        generator.query_model.validate_responses = [
            (True, "OK", 8.0) for _ in range(5)
        ]

        generator.generate()

        assert generator.generated_count == 5
        self.save_item.assert_not_called()  # dry_run=True

    def test_template_weights_equal(self):
        """Test that all templates have equal weight by default."""
        generator = GenerateQuickGuidelines(
            data_access=self.data_access,
            models=self.models,
            validation_pct=1.0,
            target_count=10,
            save_item=self.save_item,
            metrics=self.metrics,
            dry_run=True,
        )

        weights = [t.weight for t in generator.TEMPLATES]
        assert all(w == 1.0 for w in weights)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])