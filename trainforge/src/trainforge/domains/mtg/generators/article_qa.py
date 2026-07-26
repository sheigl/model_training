"""Article Q&A generator — generates Q&A pairs from EDHREC articles."""

from __future__ import annotations

import logging
import re
from trainforge.domain import TemplateConfig
from trainforge.generator import BaseGenerator
from trainforge.domains.mtg.models import Article

logger = logging.getLogger(__name__)


def _clean_html(raw: str) -> str:
    """Strip HTML tags and normalise whitespace from article content."""
    if not raw:
        return ""
    # Remove script and style blocks entirely
    raw = re.sub(
        r"<(script|style)[^>]*>.*?</\1>",
        " ",
        raw,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # Remove all remaining tags
    raw = re.sub(r"<[^>]+>", " ", raw)
    # Decode common HTML entities
    raw = (
        raw.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&nbsp;", " ")
    )
    # Collapse whitespace
    return re.sub(r"\s+", " ", raw).strip()


class ArticleQAGenerator(BaseGenerator[Article]):
    """Generate Q&A pairs derived from EDHREC articles.

    Category: article_qa
    Data batches: Article objects with cleaned content > 200 chars.
    Templates: key_takeaways, strategy_insights (from templates.yaml)
    """

    MIN_CONTENT_LENGTH = 200

    def get_data_batches(self) -> list[Article]:
        """Fetch articles from the domain data source.

        Returns:
            List of Article objects with cleaned content > MIN_CONTENT_LENGTH
            characters. Content is stripped of HTML tags.
        """
        ds = self.domain.get_data_source()
        raw = ds.get_articles(limit=100)

        batches: list[Article] = []
        for doc in raw:
            article = Article(**doc)
            cleaned = _clean_html(article.content or "")
            if len(cleaned) > self.MIN_CONTENT_LENGTH:
                article.content = cleaned
                batches.append(article)

        logger.info(
            "Loaded %d articles (from %d raw, content > %d chars)",
            len(batches),
            len(raw),
            self.MIN_CONTENT_LENGTH,
        )
        return batches

    def build_prompt(self, template: TemplateConfig, data_batch: Article) -> str:
        """Build the LLM prompt for an article-based Q&A.

        Args:
            template: TemplateConfig with task_instruction. Supports
                      ``{title}``, ``{content}``, ``{tags}`` placeholders.
            data_batch: Article object with title, content, and tags.

        Returns:
            Full prompt string with notation legend and <task> wrapping.
        """
        article = data_batch
        content = (article.content or "")[:2000]
        tags_str = ", ".join(article.tags) if article.tags else ""

        notation = self.domain.notation_legend

        task_instruction = template.task_instruction.format(
            title=article.title,
            content=content,
            tags=tags_str,
        )

        return (
            f"{notation}\n\n"
            f"<task>\n"
            f"{task_instruction}\n\n"
            f"Article: {article.title}\n"
            f"Tags: {tags_str}\n\n"
            f"Article content:\n"
            f"{content}\n\n"
            f"Output JSON:\n"
            f'[\n'
            f'  {{"question": "...", "answer": "..."}},\n'
            f'  {{"question": "...", "answer": "..."}}\n'
            f"]\n"
            f"\n"
            f"Answers should be 3-5 sentences grounded in the article content. "
            f"Output ONLY valid JSON.\n"
            f"</task>"
        )

    def get_source_category(self) -> str:
        return "article_qa"

    def build_context(self, data_batch: Article) -> str | None:
        """Build metadata context for the generated Q&A."""
        article = data_batch
        content_len = len(article.content or "")
        return (
            f"Category: {self.get_source_category()}\n"
            f"Article: {article.title}\n"
            f"Content length: {content_len}"
        )
