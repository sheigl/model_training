"""Tests for GlossaryWithExamplesGenerator."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from trainforge.domain import TemplateConfig
from trainforge.domains.mtg.generators.glossary_with_examples import (
    GlossaryWithExamplesGenerator,
)
from trainforge.domains.mtg.models import GlossaryTerm
from trainforge.models import Model, ModelType


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_domain():
    """Create a mock domain with a data source returning glossary entries."""
    domain = MagicMock()
    domain.name = "mtg"
    domain.notation_legend = "<reference>test notation</reference>"
    return domain


@pytest.fixture
def raw_glossary_items():
    """Return sample raw glossary dicts as returned by get_glossary()."""
    return [
        {"term": "Flying", "definition": "Creatures with flying can only be blocked by creatures with flying or reach.", "relatedTerms": ["reach", "blocking"]},
        {"term": "Haste", "definition": "Creatures with haste can attack and use tap abilities the turn they enter the battlefield.", "relatedTerms": []},
        {"term": "Short", "definition": "Brief def", "relatedTerms": []},
        {"term": "Deathtouch", "definition": "Any amount of combat damage a creature with deathtouch deals to a creature is enough to destroy it.", "relatedTerms": ["trample", "blocking"]},
    ]


@pytest.fixture
def generator(mock_domain):
    """Create a GlossaryWithExamplesGenerator with a mock domain."""
    gen = GlossaryWithExamplesGenerator(
        domain=mock_domain,
        generation_model=Model(name="test-gen", type=ModelType.GENERATION),
        validation_model=Model(name="test-val", type=ModelType.VALIDATION),
    )
    return gen


@pytest.fixture
def template():
    """Create a simple template config for testing."""
    return TemplateConfig(
        template_id="term_with_example",
        task_instruction="Generate a Q&A about {term} with definition: {definition}",
    )


# =============================================================================
# GET_SOURCE_CATEGORY
# =============================================================================


class TestGetSourceCategory:
    def test_returns_correct_category(self, generator):
        """Should return 'glossary_with_examples'."""
        assert generator.get_source_category() == "glossary_with_examples"


# =============================================================================
# GET_DATA_BATCHES
# =============================================================================


class TestGetDataBatches:
    def test_filters_glossary_by_definition_length(self, generator, raw_glossary_items):
        """Should only include terms with definition > 30 chars."""
        ds = MagicMock()
        ds.get_glossary.return_value = raw_glossary_items
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()

        # "Short" should be filtered out (def = "Brief def" = 9 chars)
        # "Short" (def=9 chars) should be excluded
        assert len(batches) == 3
        assert all(isinstance(b, GlossaryTerm) for b in batches)
        term_names = [b.term for b in batches]
        assert "Flying" in term_names
        assert "Haste" in term_names
        assert "Deathtouch" in term_names
        assert "Short" not in term_names

    def test_converts_dicts_to_glossary_terms(self, generator, raw_glossary_items):
        """Should convert raw dicts to GlossaryTerm model instances."""
        ds = MagicMock()
        ds.get_glossary.return_value = raw_glossary_items
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()

        assert all(isinstance(b, GlossaryTerm) for b in batches)
        assert batches[0].term == "Flying"
        assert batches[1].term == "Haste"

    def test_empty_glossary(self, generator):
        """Should handle empty glossary gracefully."""
        ds = MagicMock()
        ds.get_glossary.return_value = []
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()
        assert batches == []

    def test_all_short_definitions(self, generator):
        """Should return empty list if all definitions are too short."""
        ds = MagicMock()
        ds.get_glossary.return_value = [
            {"term": "A", "definition": "Short"},
            {"term": "B", "definition": "Brief"},
        ]
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()
        assert batches == []

    def test_calls_get_glossary_with_limit_200(self, generator):
        """Should call get_glossary with limit=200."""
        ds = MagicMock()
        ds.get_glossary.return_value = []
        generator.domain.get_data_source.return_value = ds

        generator.get_data_batches()
        ds.get_glossary.assert_called_once_with(limit=200)


# =============================================================================
# BUILD_PROMPT
# =============================================================================


class TestBuildPrompt:
    def test_formats_task_instruction_with_term_and_definition(self, generator, template):
        """Should format template instruction with term and definition."""
        term = GlossaryTerm(
            term="Flying",
            definition="Creatures with flying can only be blocked by creatures with flying or reach.",
        )
        prompt = generator.build_prompt(template, term)

        assert "<reference>test notation</reference>" in prompt
        assert "<task>" in prompt
        assert "</task>" in prompt
        assert "Flying" in prompt
        assert "flying or reach" in prompt

    def test_includes_notation_legend(self, generator, template):
        """Should include the domain's notation legend."""
        term = GlossaryTerm(term="Haste", definition="Haste lets creatures attack immediately.")
        prompt = generator.build_prompt(template, term)

        assert "<reference>test notation</reference>" in prompt

    def test_empty_template_no_crash(self, generator):
        """Should handle template with no placeholders gracefully."""
        empty_template = TemplateConfig(
            template_id="term_with_example",
            task_instruction="Generate a Q&A about an MTG term.",
        )
        term = GlossaryTerm(term="Flying", definition="Flying is an evasion ability.")
        prompt = generator.build_prompt(empty_template, term)
        assert prompt


# =============================================================================
# BUILD_CONTEXT
# =============================================================================


class TestBuildContext:
    def test_returns_formatted_context(self, generator):
        """Should return context with category, term, and definition."""
        term = GlossaryTerm(term="Flying", definition="Flying is an evasion ability.")
        context = generator.build_context(term)

        assert context is not None
        assert "glossary_with_examples" in context
        assert "Flying" in context
        assert "Flying is an evasion ability" in context
