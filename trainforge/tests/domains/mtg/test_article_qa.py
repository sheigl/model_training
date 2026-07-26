"""Tests for ArticleQAGenerator."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from trainforge.domain import TemplateConfig
from trainforge.domains.mtg.generators.article_qa import ArticleQAGenerator
from trainforge.domains.mtg.models import Article
from trainforge.models import Model, ModelType


# =============================================================================
# FIXTURES
# =============================================================================


def _make_article(
    title: str,
    content: str,
    tags: list[str] | None = None,
) -> Article:
    """Create an Article with given fields."""
    return Article(
        title=title,
        content=content,
        tags=tags or [],
    )


@pytest.fixture
def mock_domain():
    """Create a mock domain."""
    domain = MagicMock()
    domain.name = "mtg"
    domain.notation_legend = "<reference>test notation</reference>"
    return domain


@pytest.fixture
def sample_article_dicts():
    """Return sample article dicts as they'd come from MongoDB.

    - Article 1: 500 chars of content (> 200, should be included)
    - Article 2: 300 chars of content (> 200, should be included)
    - Article 3: 50 chars of content (< 200, should be excluded)
    - Article 4: empty content (should be excluded)
    - Article 5: content with HTML tags (should be cleaned)
    """
    return [
        {
            "title": "Building the Best Commander Deck",
            "content": "A" * 500,
            "tags": ["deckbuilding", "commander"],
        },
        {
            "title": "Understanding Mana Bases",
            "content": "Mana is the foundation of every deck. "
            "You need to understand color fixing. "
            "Proper land count is critical for consistency." * 3,
            "tags": ["mana", "basics"],
        },
        {
            "title": "Short Article",
            "content": "Too short to include.",
            "tags": ["short"],
        },
        {
            "title": "Empty Article",
            "content": "",
            "tags": [],
        },
        {
            "title": "Article with HTML",
            "content": "<p>This is a <strong>test</strong> article with &amp; HTML entities.</p>"
            "<script>alert('xss')</script>"
            "<p>It has enough content to pass the filter after cleaning.</p>"
            "<p>Multiple paragraphs ensure the total is above 200 characters.</p>"
            "<p>Lorem ipsum dolor sit amet, consectetur adipiscing elit.</p>"
            "<p>More content here to reach the threshold easily.</p>",
            "tags": ["html"],
        },
    ]


@pytest.fixture
def generator(mock_domain):
    """Create an ArticleQAGenerator."""
    gen = ArticleQAGenerator(
        domain=mock_domain,
        generation_model=Model(name="test-gen", type=ModelType.GENERATION),
        validation_model=Model(name="test-val", type=ModelType.VALIDATION),
    )
    return gen


@pytest.fixture
def template():
    """Create a simple template for testing."""
    return TemplateConfig(
        template_id="key_takeaways",
        task_instruction=(
            "Generate a Q&A about the main points of this article."
        ),
    )


# =============================================================================
# GET_SOURCE_CATEGORY
# =============================================================================


class TestGetSourceCategory:
    def test_returns_correct_category(self, generator):
        """Should return 'article_qa'."""
        assert generator.get_source_category() == "article_qa"


# =============================================================================
# GET_DATA_BATCHES
# =============================================================================


class TestGetDataBatches:
    def test_filters_articles_by_content_length(
        self, generator, sample_article_dicts
    ):
        """Should only include articles with cleaned content > 200 chars."""
        ds = MagicMock()
        ds.get_articles.return_value = sample_article_dicts
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()

        assert len(batches) == 3
        assert all(isinstance(b, Article) for b in batches)
        titles = {b.title for b in batches}
        assert "Building the Best Commander Deck" in titles
        assert "Understanding Mana Bases" in titles
        assert "Article with HTML" in titles
        assert "Short Article" not in titles
        assert "Empty Article" not in titles

    def test_cleans_html_content(self, generator):
        """Should strip HTML tags from article content."""
        # Build content that is > 200 chars after HTML stripping
        clean_part = "Hello <b>World</b> &amp; stuff. "
        padding = "x" * 250  # ensures total > 200 after cleaning
        ds = MagicMock()
        ds.get_articles.return_value = [
            {
                "title": "HTML Article",
                "content": f"<p>{clean_part}{padding}</p>",
                "tags": [],
            },
        ]
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()
        assert len(batches) == 1
        article = batches[0]
        assert "<p>" not in article.content
        assert "<b>" not in article.content
        assert "&amp;" not in article.content
        assert "Hello World & stuff" in article.content
        assert len(article.content) > 200

    def test_call_get_articles_with_limit_100(self, generator):
        """Should call get_articles with limit=100."""
        ds = MagicMock()
        ds.get_articles.return_value = []
        generator.domain.get_data_source.return_value = ds

        generator.get_data_batches()
        ds.get_articles.assert_called_once_with(limit=100)

    def test_empty_articles_list(self, generator):
        """Should handle empty articles list."""
        ds = MagicMock()
        ds.get_articles.return_value = []
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()
        assert batches == []

    def test_all_articles_too_short(self, generator):
        """Should return empty list when all articles are too short."""
        short_articles = [
            {"title": "Short", "content": "Hi", "tags": []},
            {"title": "Also Short", "content": "Bye", "tags": []},
        ]
        ds = MagicMock()
        ds.get_articles.return_value = short_articles
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()
        assert batches == []

    def test_article_content_is_truncated_to_2000_chars(self, generator):
        """Content should be preserved as-is (truncation happens in build_prompt)."""
        long_content = "A" * 3000
        ds = MagicMock()
        ds.get_articles.return_value = [
            {"title": "Long", "content": long_content, "tags": []},
        ]
        generator.domain.get_data_source.return_value = ds

        batches = generator.get_data_batches()
        assert len(batches) == 1
        assert len(batches[0].content) == 3000  # Full content preserved


# =============================================================================
# BUILD_PROMPT
# =============================================================================


class TestBuildPrompt:
    def test_includes_article_title_and_content(self, generator, template):
        """Should include article title and content in the prompt."""
        article = _make_article(
            "Building the Best Commander Deck",
            "This article covers how to build a competitive Commander deck.",
            tags=["deckbuilding"],
        )
        prompt = generator.build_prompt(template, article)

        assert "<reference>test notation</reference>" in prompt
        assert "<task>" in prompt
        assert "</task>" in prompt
        assert "Building the Best Commander Deck" in prompt
        assert "competitive Commander deck" in prompt
        assert "deckbuilding" in prompt

    def test_content_truncated_to_2000_chars(self, generator, template):
        """Content should be truncated to 2000 chars in the prompt."""
        long_content = "A" * 3000
        article = _make_article("Long Article", long_content)
        prompt = generator.build_prompt(template, article)

        # The full content is in the article object, but truncated in prompt
        assert "A" * 2000 in prompt
        assert "A" * 2001 not in prompt

    def test_wraps_in_task_tags(self, generator, template):
        """Should wrap the prompt in <task> tags."""
        article = _make_article("Test", "Some content here.")
        prompt = generator.build_prompt(template, article)

        assert "<task>" in prompt
        assert "</task>" in prompt

    def test_output_json_format_included(self, generator, template):
        """Should include JSON output format in the prompt."""
        article = _make_article("Test", "Some content here.")
        prompt = generator.build_prompt(template, article)

        assert '"question"' in prompt
        assert '"answer"' in prompt
        assert "Output ONLY valid JSON" in prompt


# =============================================================================
# BUILD_CONTEXT
# =============================================================================


class TestBuildContext:
    def test_returns_formatted_context(self, generator):
        """Should return context with category, article title, and content length."""
        article = _make_article(
            "Building the Best Commander Deck",
            "A" * 500,
            tags=["deckbuilding"],
        )
        context = generator.build_context(article)

        assert context is not None
        assert "article_qa" in context
        assert "Building the Best Commander Deck" in context
        assert "Content length: 500" in context

    def test_handles_empty_content(self, generator):
        """Should handle article with empty content."""
        article = Article(title="Empty", content="", tags=[])
        context = generator.build_context(article)

        assert context is not None
        assert "article_qa" in context
        assert "Content length: 0" in context
