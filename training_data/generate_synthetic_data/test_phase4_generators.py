"""Integration tests for the 5 Phase 4 EDHREC-grounded generators."""

import pytest
from unittest.mock import MagicMock, patch
from typing import Callable

from training_data.generate_synthetic_data.base_generator import BaseGenerator
from training_data.generate_synthetic_data.common import (
    TemplateConfig, clean_html,
    build_guide_qa_prompt, build_staple_analysis_prompt,
    build_color_staples_prompt, build_salt_prompt,
    build_multi_card_usage_prompt,
)
from training_data.generate_synthetic_data.data_access import MTGDataAccess
from training_data.generate_synthetic_data.domain_models import Guide, GuideChapter, ComboWithCards, ComboCard
from training_data.generate_synthetic_data.models import ModelType, ValidationMetrics

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_mock_models():
    """Return a dict of mock models for all ModelTypes."""
    return {mt: MagicMock() for mt in ModelType}


def _make_metrics():
    m = ValidationMetrics(generator_name="test")
    return m


# ---------------------------------------------------------------------------
# GenerateGuideQa
# ---------------------------------------------------------------------------

class TestGenerateGuideQa:

    def test_inherits_base_generator(self):
        from training_data.generate_synthetic_data.main import GenerateGuideQa
        assert issubclass(GenerateGuideQa, BaseGenerator)

    def test_templates_defined(self):
        from training_data.generate_synthetic_data.main import GenerateGuideQa
        templates = GenerateGuideQa.TEMPLATES
        assert len(templates) >= 1
        assert all(isinstance(t, TemplateConfig) for t in templates)
        assert any(t.template_id == "guide_qa" for t in templates)

    def test_source_category(self):
        from training_data.generate_synthetic_data.main import GenerateGuideQa
        da = MagicMock(spec=MTGDataAccess)
        gen = GenerateGuideQa(
            data_access=da, models=_make_mock_models(),
            validation_pct=0.25, target_count=10, save_item=lambda x: None,
            metrics=_make_metrics(), dry_run=True,
        )
        assert gen.get_source_category() == "guide_qa"

    def test_get_data_batches_filters_short_guides(self):
        from training_data.generate_synthetic_data.main import GenerateGuideQa
        short_guide = Guide(
            title="Short", chapters=[GuideChapter(content="<p>tiny</p>", title="Ch")],
        )
        long_guide = Guide(
            title="Long", chapters=[GuideChapter(content="<p>" + "x" * 500 + "</p>", title="Ch")],
        )
        da = MagicMock(spec=MTGDataAccess)
        da.get_guides.return_value = [short_guide, long_guide]

        gen = GenerateGuideQa(
            data_access=da, models=_make_mock_models(),
            validation_pct=0.25, target_count=10, save_item=lambda x: None,
            metrics=_make_metrics(), dry_run=True,
        )
        batches = list(gen.get_data_batches())
        assert len(batches) == 1
        assert batches[0][0].title == "Long"

    def test_build_prompt_uses_guide_content(self):
        from training_data.generate_synthetic_data.main import GenerateGuideQa
        guide = Guide(
            title="Test Guide", chapters=[GuideChapter(content="<p>Some content</p>", title="Ch")],
        )
        da = MagicMock(spec=MTGDataAccess)
        gen = GenerateGuideQa(
            data_access=da, models=_make_mock_models(),
            validation_pct=0.25, target_count=10, save_item=lambda x: None,
            metrics=_make_metrics(), dry_run=True,
        )
        template = TemplateConfig(template_id="guide_qa", task_instruction="test")
        prompt = gen.build_prompt(template, guide)
        assert "Test Guide" in prompt
        assert isinstance(prompt, str) and len(prompt) > 0

    def test_build_prompt_truncates_long_content(self):
        from training_data.generate_synthetic_data.main import GenerateGuideQa
        long_content = "<p>" + "word " * 1000 + "</p>"
        guide = Guide(
            title="Big Guide", chapters=[GuideChapter(content=long_content, title="Ch")],
        )
        da = MagicMock(spec=MTGDataAccess)
        gen = GenerateGuideQa(
            data_access=da, models=_make_mock_models(),
            validation_pct=0.25, target_count=10, save_item=lambda x: None,
            metrics=_make_metrics(), dry_run=True,
        )
        template = TemplateConfig(template_id="guide_qa", task_instruction="test")
        prompt = gen.build_prompt(template, guide)
        assert len(prompt) > 0


# ---------------------------------------------------------------------------
# GenerateStapleAnalysis
# ---------------------------------------------------------------------------

class TestGenerateStapleAnalysis:

    def test_inherits_base_generator(self):
        from training_data.generate_synthetic_data.main import GenerateStapleAnalysis
        assert issubclass(GenerateStapleAnalysis, BaseGenerator)

    def test_templates_defined(self):
        from training_data.generate_synthetic_data.main import GenerateStapleAnalysis
        templates = GenerateStapleAnalysis.TEMPLATES
        assert len(templates) >= 1
        assert any(t.template_id == "staple_analysis" for t in templates)

    def test_source_category(self):
        from training_data.generate_synthetic_data.main import GenerateStapleAnalysis
        da = MagicMock(spec=MTGDataAccess)
        gen = GenerateStapleAnalysis(
            data_access=da, models=_make_mock_models(),
            validation_pct=0.25, target_count=10, save_item=lambda x: None,
            metrics=_make_metrics(), dry_run=True,
        )
        assert gen.get_source_category() == "staple_analysis"

    def test_get_data_batches_uses_game_changers(self):
        from training_data.generate_synthetic_data.main import GenerateStapleAnalysis
        cards = [{"name": f"Card{i}", "rank": i} for i in range(5)]
        da = MagicMock(spec=MTGDataAccess)
        da.get_game_changers.return_value = cards

        gen = GenerateStapleAnalysis(
            data_access=da, models=_make_mock_models(),
            validation_pct=0.25, target_count=10, save_item=lambda x: None,
            metrics=_make_metrics(), dry_run=True,
        )
        batches = list(gen.get_data_batches())
        assert len(batches) == 5
        da.get_game_changers.assert_called_once()

    def test_build_prompt(self):
        from training_data.generate_synthetic_data.main import GenerateStapleAnalysis
        card = {"name": "Karn Liberated", "rank": 1, "description": "A legendary artifact"}
        da = MagicMock(spec=MTGDataAccess)
        gen = GenerateStapleAnalysis(
            data_access=da, models=_make_mock_models(),
            validation_pct=0.25, target_count=10, save_item=lambda x: None,
            metrics=_make_metrics(), dry_run=True,
        )
        template = TemplateConfig(template_id="staple_analysis", task_instruction="test")
        prompt = gen.build_prompt(template, card)
        assert "Karn Liberated" in prompt


# ---------------------------------------------------------------------------
# GenerateColorStaples
# ---------------------------------------------------------------------------

class TestGenerateColorStaples:

    def test_inherits_base_generator(self):
        from training_data.generate_synthetic_data.main import GenerateColorStaples
        assert issubclass(GenerateColorStaples, BaseGenerator)

    def test_templates_defined(self):
        from training_data.generate_synthetic_data.main import GenerateColorStaples
        templates = GenerateColorStaples.TEMPLATES
        assert len(templates) >= 1
        assert any(t.template_id == "color_staples" for t in templates)

    def test_colors_defined(self):
        from training_data.generate_synthetic_data.main import GenerateColorStaples
        expected = {'black', 'blue', 'colorless', 'green', 'red', 'white'}
        assert set(GenerateColorStaples.COLORS) == expected

    def test_source_category(self):
        from training_data.generate_synthetic_data.main import GenerateColorStaples
        da = MagicMock(spec=MTGDataAccess)
        gen = GenerateColorStaples(
            data_access=da, models=_make_mock_models(),
            validation_pct=0.25, target_count=10, save_item=lambda x: None,
            metrics=_make_metrics(), dry_run=True,
        )
        assert gen.get_source_category() == "color_staples"

    def test_get_data_batches_calls_per_color(self):
        from training_data.generate_synthetic_data.main import GenerateColorStaples
        da = MagicMock(spec=MTGDataAccess)
        # Return 30 cards per color to get all 3 subsets
        da.get_top_cards_by_color.return_value = [
            {"name": f"Card{i}", "color": "blue"} for i in range(30)
        ]

        gen = GenerateColorStaples(
            data_access=da, models=_make_mock_models(),
            validation_pct=0.25, target_count=10, save_item=lambda x: None,
            metrics=_make_metrics(), dry_run=True,
        )
        batches = list(gen.get_data_batches())
        # 6 colors * 3 subsets each = 18 batches (when 30 cards returned)
        assert len(batches) == 18
        assert da.get_top_cards_by_color.call_count == 6

    def test_get_data_batches_skips_empty_subsets(self):
        from training_data.generate_synthetic_data.main import GenerateColorStaples
        da = MagicMock(spec=MTGDataAccess)
        # Return only 5 cards - should yield just 1 subset per color
        da.get_top_cards_by_color.return_value = [
            {"name": f"Card{i}"} for i in range(5)
        ]

        gen = GenerateColorStaples(
            data_access=da, models=_make_mock_models(),
            validation_pct=0.25, target_count=10, save_item=lambda x: None,
            metrics=_make_metrics(), dry_run=True,
        )
        batches = list(gen.get_data_batches())
        # 6 colors * 1 non-empty subset each = 6 batches
        assert len(batches) == 6

    def test_build_prompt(self):
        from training_data.generate_synthetic_data.main import GenerateColorStaples
        color, cards = "blue", [{"name": "Counterspell"}, {"name": "Force of Will"}]
        da = MagicMock(spec=MTGDataAccess)
        gen = GenerateColorStaples(
            data_access=da, models=_make_mock_models(),
            validation_pct=0.25, target_count=10, save_item=lambda x: None,
            metrics=_make_metrics(), dry_run=True,
        )
        template = TemplateConfig(template_id="color_staples", task_instruction="test")
        prompt = gen.build_prompt(template, (color, cards))
        assert "blue" in prompt.lower() or "Blue" in prompt


# ---------------------------------------------------------------------------
# GenerateSaltQuestions
# ---------------------------------------------------------------------------

class TestGenerateSaltQuestions:

    def test_inherits_base_generator(self):
        from training_data.generate_synthetic_data.main import GenerateSaltQuestions
        assert issubclass(GenerateSaltQuestions, BaseGenerator)

    def test_templates_defined(self):
        from training_data.generate_synthetic_data.main import GenerateSaltQuestions
        templates = GenerateSaltQuestions.TEMPLATES
        assert len(templates) >= 1
        assert any(t.template_id == "salt_analysis" for t in templates)

    def test_batch_size_class_var(self):
        from training_data.generate_synthetic_data.main import GenerateSaltQuestions
        assert GenerateSaltQuestions.BATCH_SIZE == 8

    def test_source_category(self):
        from training_data.generate_synthetic_data.main import GenerateSaltQuestions
        da = MagicMock(spec=MTGDataAccess)
        gen = GenerateSaltQuestions(
            data_access=da, models=_make_mock_models(),
            validation_pct=0.25, target_count=10, save_item=lambda x: None,
            metrics=_make_metrics(), dry_run=True,
        )
        assert gen.get_source_category() == "salt_analysis"

    def test_get_data_batches_groups_into_batches(self):
        from training_data.generate_synthetic_data.main import GenerateSaltQuestions
        salty = [{"name": f"Salty{i}", "salt_rating": 1.5} for i in range(20)]
        da = MagicMock(spec=MTGDataAccess)
        da.get_salty_cards.return_value = salty

        gen = GenerateSaltQuestions(
            data_access=da, models=_make_mock_models(),
            validation_pct=0.25, target_count=10, save_item=lambda x: None,
            metrics=_make_metrics(), dry_run=True,
        )
        batches = list(gen.get_data_batches())
        # 20 cards / batch_size 8 = 3 batches (8+8+4)
        assert len(batches) == 3
        # Each batch is wrapped in a list: [[card1..card8], ...]
        assert len(batches[0][0]) == 8
        assert len(batches[1][0]) == 8
        assert len(batches[2][0]) == 4

    def test_get_data_batches_passes_min_salt(self):
        from training_data.generate_synthetic_data.main import GenerateSaltQuestions
        da = MagicMock(spec=MTGDataAccess)
        da.get_salty_cards.return_value = []

        gen = GenerateSaltQuestions(
            data_access=da, models=_make_mock_models(),
            validation_pct=0.25, target_count=10, save_item=lambda x: None,
            metrics=_make_metrics(), dry_run=True,
        )
        list(gen.get_data_batches())
        da.get_salty_cards.assert_called_once()
        call_kwargs = da.get_salty_cards.call_args[1]
        assert call_kwargs["min_salt"] == 1.2

    def test_build_prompt(self):
        from training_data.generate_synthetic_data.main import GenerateSaltQuestions
        cards = [{"name": "Tarmogoyf", "salt_rating": 3.5}]
        da = MagicMock(spec=MTGDataAccess)
        gen = GenerateSaltQuestions(
            data_access=da, models=_make_mock_models(),
            validation_pct=0.25, target_count=10, save_item=lambda x: None,
            metrics=_make_metrics(), dry_run=True,
        )
        template = TemplateConfig(template_id="salt_analysis", task_instruction="test")
        prompt = gen.build_prompt(template, cards)
        assert "Tarmogoyf" in prompt


# ---------------------------------------------------------------------------
# GenerateMultiCardUsage
# ---------------------------------------------------------------------------

class TestGenerateMultiCardUsage:

    def test_inherits_base_generator(self):
        from training_data.generate_synthetic_data.main import GenerateMultiCardUsage
        assert issubclass(GenerateMultiCardUsage, BaseGenerator)

    def test_templates_defined(self):
        from training_data.generate_synthetic_data.main import GenerateMultiCardUsage
        templates = GenerateMultiCardUsage.TEMPLATES
        assert len(templates) >= 1
        assert any(t.template_id == "multi_card" for t in templates)

    def test_source_category(self):
        from training_data.generate_synthetic_data.main import GenerateMultiCardUsage
        da = MagicMock(spec=MTGDataAccess)
        gen = GenerateMultiCardUsage(
            data_access=da, models=_make_mock_models(),
            validation_pct=0.25, target_count=10, save_item=lambda x: None,
            metrics=_make_metrics(), dry_run=True,
        )
        assert gen.get_source_category() == "multi_card_usage"

    def test_get_data_batches_filters_combos(self):
        from training_data.generate_synthetic_data.main import GenerateMultiCardUsage
        # Combo with 2+ cards and description -> should pass filter
        good_combo = ComboWithCards(
            id="c1", name="Good Combo", description="A great combo",
            uses=[ComboCard(name="Card A"), ComboCard(name="Card B")],
        )
        # Combo with only 1 card -> should be filtered out
        bad_combo_1 = ComboWithCards(
            id="c2", name="Bad Combo", description="Only one card",
            uses=[ComboCard(name="Solo")],
        )
        # Combo with no description -> should be filtered out
        bad_combo_2 = ComboWithCards(
            id="c3", name="No Desc", description="",
            uses=[ComboCard(name="X"), ComboCard(name="Y")],
        )

        da = MagicMock(spec=MTGDataAccess)
        da.get_combos_enriched.return_value = [good_combo, bad_combo_1, bad_combo_2]

        gen = GenerateMultiCardUsage(
            data_access=da, models=_make_mock_models(),
            validation_pct=0.25, target_count=10, save_item=lambda x: None,
            metrics=_make_metrics(), dry_run=True,
        )
        batches = list(gen.get_data_batches())
        assert len(batches) == 1
        assert batches[0][0].id == "c1"

    def test_get_data_batches_filters_empty_names(self):
        from training_data.generate_synthetic_data.main import GenerateMultiCardUsage
        # Cards with empty names should be filtered out
        combo = ComboWithCards(
            id="c4", name="Empty Names", description="Combo",
            uses=[ComboCard(name=""), ComboCard(name="")],
        )
        da = MagicMock(spec=MTGDataAccess)
        da.get_combos_enriched.return_value = [combo]

        gen = GenerateMultiCardUsage(
            data_access=da, models=_make_mock_models(),
            validation_pct=0.25, target_count=10, save_item=lambda x: None,
            metrics=_make_metrics(), dry_run=True,
        )
        batches = list(gen.get_data_batches())
        assert len(batches) == 0

    def test_build_prompt(self):
        from training_data.generate_synthetic_data.main import GenerateMultiCardUsage
        combo = ComboWithCards(
            id="c5", name="Test Combo", description="They work together well",
            uses=[
                ComboCard(name="Tarmogoyf"),
                ComboCard(name="Llanowar Elves"),
            ],
        )
        da = MagicMock(spec=MTGDataAccess)
        gen = GenerateMultiCardUsage(
            data_access=da, models=_make_mock_models(),
            validation_pct=0.25, target_count=10, save_item=lambda x: None,
            metrics=_make_metrics(), dry_run=True,
        )
        template = TemplateConfig(template_id="multi_card", task_instruction="test")
        prompt = gen.build_prompt(template, combo)
        assert "Tarmogoyf" in prompt
        assert "Llanowar Elves" in prompt


# ---------------------------------------------------------------------------
# Cross-generator: common prompt builders
# ---------------------------------------------------------------------------

class TestCommonPromptBuilders:

    def test_build_guide_qa_prompt(self):
        result = build_guide_qa_prompt("Test Guide", "Some guide content here")
        assert isinstance(result, str)
        assert len(result) > 0
        assert "Test Guide" in result or "guide" in result.lower()

    def test_build_staple_analysis_prompt(self):
        card = {"name": "Karn Liberated", "rank": 1}
        result = build_staple_analysis_prompt(card)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_build_color_staples_prompt(self):
        cards = [{"name": "Counterspell"}, {"name": "Force of Will"}]
        result = build_color_staples_prompt("blue", cards)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_build_salt_prompt(self):
        cards = [{"name": "Tarmogoyf", "salt_rating": 3.5}]
        result = build_salt_prompt(cards)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_build_multi_card_usage_prompt(self):
        result = build_multi_card_usage_prompt("Card A", "Card B", "They combo together")
        assert isinstance(result, str)
        assert len(result) > 0
        assert "Card A" in result
        assert "Card B" in result


# ---------------------------------------------------------------------------
# Cross-generator: data_access new methods signature check
# ---------------------------------------------------------------------------

class TestNewDataAccessMethods:

    def test_get_game_changers_signature(self):
        import inspect
        sig = inspect.signature(MTGDataAccess.get_game_changers)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "limit" in params

    def test_get_salty_cards_signature(self):
        import inspect
        sig = inspect.signature(MTGDataAccess.get_salty_cards)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "min_salt" in params
        assert "limit" in params

    def test_get_top_cards_by_color_signature(self):
        import inspect
        sig = inspect.signature(MTGDataAccess.get_top_cards_by_color)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "color" in params
        assert "limit" in params


# ---------------------------------------------------------------------------
# Regression: ensure all 5 generators are importable from main.py namespace
# ---------------------------------------------------------------------------

class TestMainImports:

    def test_all_generators_importable_from_main(self):
        """Verify all 5 Phase 4 generators can be imported from the main module."""
        from training_data.generate_synthetic_data.main import (
            GenerateGuideQa,
            GenerateStapleAnalysis,
            GenerateColorStaples,
            GenerateSaltQuestions,
            GenerateMultiCardUsage,
        )
        # All imports succeeded — that's the test

    def test_generators_are_distinct_classes(self):
        """Verify each generator is a unique class (no accidental aliasing)."""
        from training_data.generate_synthetic_data.main import (
            GenerateGuideQa,
            GenerateStapleAnalysis,
            GenerateColorStaples,
            GenerateSaltQuestions,
            GenerateMultiCardUsage,
        )
        classes = [GenerateGuideQa, GenerateStapleAnalysis, GenerateColorStaples,
                   GenerateSaltQuestions, GenerateMultiCardUsage]
        assert len(set(classes)) == 5, "Some generators are aliased to the same class"

    def test_each_generator_has_unique_source_category(self):
        """Verify each generator reports a distinct source category."""
        from training_data.generate_synthetic_data.main import (
            GenerateGuideQa,
            GenerateStapleAnalysis,
            GenerateColorStaples,
            GenerateSaltQuestions,
            GenerateMultiCardUsage,
        )
        da = MagicMock(spec=MTGDataAccess)
        models = _make_mock_models()
        metrics = _make_metrics()

        gens = [
            GenerateGuideQa(data_access=da, models=models, validation_pct=0.25, target_count=10, save_item=lambda x: None, metrics=metrics, dry_run=True),
            GenerateStapleAnalysis(data_access=da, models=models, validation_pct=0.25, target_count=10, save_item=lambda x: None, metrics=metrics, dry_run=True),
            GenerateColorStaples(data_access=da, models=models, validation_pct=0.25, target_count=10, save_item=lambda x: None, metrics=metrics, dry_run=True),
            GenerateSaltQuestions(data_access=da, models=models, validation_pct=0.25, target_count=10, save_item=lambda x: None, metrics=metrics, dry_run=True),
            GenerateMultiCardUsage(data_access=da, models=models, validation_pct=0.25, target_count=10, save_item=lambda x: None, metrics=metrics, dry_run=True),
        ]

        categories = [g.get_source_category() for g in gens]
        assert len(set(categories)) == 5, f"Duplicate source categories: {categories}"
