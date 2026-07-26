"""Tests for GuideQAGenerator."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from trainforge.domain import TemplateConfig
from trainforge.domains.mtg.generators.guide_qa import GuideQAGenerator
from trainforge.domains.mtg.models import Guide, GuideChapter
from trainforge.models import Model, ModelType


# =============================================================================
# FIXTURES
# =============================================================================


def _make_guide(
    title: str,
    chapter_contents: list[str],
    tags: list[str] | None = None,
) -> Guide:
    """Create a Guide with chapters from given content strings."""
    chapters = [GuideChapter(title=f"Chapter {i}", content=content) for i, content in enumerate(chapter_contents, 1)]
    return Guide(title=title, chapters=chapters, tags=tags or [])


@pytest.fixture
def mock_domain():
    """Create a mock domain."""
    domain = MagicMock()
    domain.name = "mtg"
    domain.notation_legend = "<reference>test notation</reference>"
    return domain


@pytest.fixture
def sample_guides():
    """Return sample Guide objects with varying content lengths.

    - Guide 1: 500 chars total (> 300, should be included)
    - Guide 2: 600 chars total (> 300, should be included)
    - Guide 3: 50 chars total (< 300, should be excluded)
    - Guide 4: 0 chars total (empty, should be excluded)
    """
    return [
        _make_guide(
            "Building a Budget Commander Deck",
            [
                "A" * 250,
                "B" * 250,
            ],
            tags=["budget", "deckbuilding"],
        ),
        _make_guide(
            "How to Play Control",
            [
                "Control decks focus on managing the board state through counterspells and removal. "
                "The key is to maintain card advantage while denying your opponent's threats. "
                "You need to know when to hold up mana and when to tap out for your own threats." * 2,
            ],
            tags=["control", "strategy"],
        ),
        _make_guide(
            "Short Guide",
            [
                "Too short to include.",
            ],
            tags=["short"],
        ),
        _make_guide(
            "Empty Guide",
            [
                "",
            ],
        ),
    ]


@pytest.fixture
def generator(mock_domain):
    """Create a GuideQAGenerator."""
    gen = GuideQAGenerator(
        domain=mock_domain,
        generation_model=Model(name="test-gen", type=ModelType.GENERATION),
        validation_model=Model(name="test-val", type=ModelType.VALIDATION),
    )
    return gen


@pytest.fixture
def template():
    """Create a simple template for testing."""
    return TemplateConfig(
        template_id="guide_question",
        task_instruction="Generate a Q&A based on the guide: {guide_title}",
    )


# =============================================================================
# GET_SOURCE_CATEGORY
# =============================================================================


class TestGetSourceCategory:
    def test_returns_correct_category(self, generator):
        """Should return 'guide_qa'."""
        assert generator.get_source_category() == "guide_qa"


# =============================================================================
# GET_DATA_BATCHES
# =============================================================================


class TestGetDataBatches:
    def test_filters_guides_by_content_length(self, generator, sample_guides):
        """Should only include guides with total content > 300 chars."""
        ds = MagicMock()
        ds.get_guides.return_value = sample_guides
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()

        assert len(batches) == 2
        assert all(isinstance(b, Guide) for b in batches)
        guide_titles = {b.title for b in batches}
        assert "Building a Budget Commander Deck" in guide_titles
        assert "How to Play Control" in guide_titles
        assert "Short Guide" not in guide_titles
        assert "Empty Guide" not in guide_titles

    def test_included_guides_have_content_over_300(self, generator, sample_guides):
        """Each included guide should have total chapter content > 300 chars."""
        ds = MagicMock()
        ds.get_guides.return_value = sample_guides
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()

        for guide in batches:
            total = sum(len(ch.content or "") for ch in (guide.chapters or []))
            assert total > 300

    def test_calls_get_guides_with_limit_50(self, generator):
        """Should call get_guides with limit=50."""
        ds = MagicMock()
        ds.get_guides.return_value = []
        generator.domain.get_data_source.return_value = ds

        generator.get_data_batches()
        ds.get_guides.assert_called_once_with(limit=50)

    def test_empty_guides_list(self, generator):
        """Should handle empty guides list."""
        ds = MagicMock()
        ds.get_guides.return_value = []
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()
        assert batches == []

    def test_all_guides_too_short(self, generator):
        """Should return empty list when all guides are too short."""
        short_guides = [
            _make_guide("Short 1", ["Hi"]),
            _make_guide("Short 2", ["Hello"]),
        ]
        ds = MagicMock()
        ds.get_guides.return_value = short_guides
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()
        assert batches == []

    def test_single_chapter_exceeds_threshold(self, generator):
        """Should include a guide with a single long chapter."""
        guide = _make_guide(
            "Long Guide",
            ["A" * 301],
            tags=["long"],
        )
        ds = MagicMock()
        ds.get_guides.return_value = [guide]
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()

        assert len(batches) == 1
        assert batches[0].title == "Long Guide"


# =============================================================================
# BUILD_PROMPT
# =============================================================================


class TestBuildPrompt:
    def test_includes_guide_title_and_chapter_content(self, generator, template):
        """Should include guide title and chapter content in the prompt."""
        guide = _make_guide(
            "Building a Budget Commander Deck",
            [
                "This chapter covers how to build a Commander deck on a budget of $50 or less.",
                "The second chapter discusses upgrading your deck over time.",
            ],
            tags=["budget"],
        )
        prompt = generator.build_prompt(template, guide)

        assert "<reference>test notation</reference>" in prompt
        assert "<task>" in prompt
        assert "</task>" in prompt
        assert "Building a Budget Commander Deck" in prompt
        assert "Chapter 1" in prompt
        assert "Chapter 2" in prompt
        assert "budget" in prompt

    def test_shows_chapter_count(self, generator, template):
        """Should show how many chapters are in the guide."""
        guide = _make_guide("Test Guide", ["Content one.", "Content two."])
        prompt = generator.build_prompt(template, guide)

        assert "Chapters: 2" in prompt

    def test_wraps_in_task_tags(self, generator, template):
        """Should wrap the prompt in <task> tags."""
        guide = _make_guide("Test", ["Some content here."])
        prompt = generator.build_prompt(template, guide)

        assert "<task>" in prompt
        assert "</task>" in prompt


# =============================================================================
# BUILD_CONTEXT
# =============================================================================


class TestBuildContext:
    def test_returns_formatted_context(self, generator):
        """Should return context with category, guide title, chapters, and content length."""
        guide = _make_guide(
            "Building a Budget Commander Deck",
            ["A" * 200, "B" * 200],
            tags=["budget"],
        )
        context = generator.build_context(guide)

        assert context is not None
        assert "guide_qa" in context
        assert "Building a Budget Commander Deck" in context
        assert "Chapters: 2" in context
        assert "Total content length: 400" in context

    def test_handles_no_chapters(self, generator):
        """Should handle guide with no chapters."""
        guide = Guide(title="Empty Guide", chapters=[], tags=[])
        context = generator.build_context(guide)

        assert context is not None
        assert "guide_qa" in context
        assert "Chapters: 0" in context
        assert "Total content length: 0" in context
