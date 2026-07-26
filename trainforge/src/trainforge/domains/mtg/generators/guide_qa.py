"""Generate guide Q&A pairs — questions derived from EDHREC strategy guides."""

from __future__ import annotations

import logging

from trainforge.domain import TemplateConfig
from trainforge.generator import BaseGenerator
from trainforge.domains.mtg.models import Guide

logger = logging.getLogger(__name__)


class GuideQAGenerator(BaseGenerator[Guide]):
    """Generate Q&A pairs derived from EDHREC strategy guides.

    Category: guide_qa
    Data batches: Guide objects with chapters containing >300 chars total content.
    Templates: guide_question (from templates.yaml)
    """

    MIN_CONTENT_LENGTH = 300

    def get_data_batches(self) -> list[Guide]:
        """Fetch guides with substantial content.

        Returns:
            List of Guide objects where total chapter content > 300 chars.
        """
        ds = self.domain.get_data_source()
        guides = ds.get_guides(limit=50)

        # Filter guides with sufficient content
        result: list[Guide] = []
        for guide in guides:
            total_content = sum(
                len(ch.content or "") for ch in (guide.chapters or [])
            )
            if total_content > self.MIN_CONTENT_LENGTH:
                result.append(guide)

        return result

    def get_source_category(self) -> str:
        return "guide_qa"

    def build_prompt(self, template: TemplateConfig, data_batch: Guide) -> str:
        """Build the LLM prompt for a guide-based Q&A.

        Args:
            template: TemplateConfig with task_instruction.
            data_batch: Guide object with title, chapters, and tags.

        Returns:
            Prompt with notation legend and <task> wrapping.
        """
        guide = data_batch

        # Build chapter summaries (first 500 chars per chapter)
        chapter_lines: list[str] = []
        for i, chapter in enumerate(guide.chapters or [], 1):
            content = (chapter.content or "")[:500]
            chapter_lines.append(f"Chapter {i}: {chapter.title}\n{content}")

        chapters_str = "\n\n".join(chapter_lines)

        tags_str = ", ".join(guide.tags) if guide.tags else "none"

        notation = self.domain.notation_legend

        task_instruction = template.task_instruction.format(
            guide_title=guide.title,
            chapters=chapters_str,
        )

        return (
            f"{notation}\n\n"
            f"<task>\n"
            f"{task_instruction}\n\n"
            f"Guide: {guide.title}\n"
            f"Tags: {tags_str}\n"
            f"Chapters: {len(guide.chapters or [])}\n\n"
            f"Guide content:\n"
            f"{chapters_str}\n\n"
            f"Generate questions that a player might ask based on this guide's "
            f"content. Focus on practical takeaways, strategy advice, and key "
            f"insights.\n"
            f"\n"
            f"Output JSON:\n"
            f'[\n'
            f'  {{"question": "...", "answer": "..."}},\n'
            f'  {{"question": "...", "answer": "..."}}\n'
            f"]\n"
            f"\n"
            f"Answers should be 3-5 sentences grounded in the guide content. "
            f"Output ONLY valid JSON.\n"
            f"</task>"
        )

    def build_context(self, data_batch: Guide) -> str | None:
        """Build metadata context for the generated Q&A."""
        guide = data_batch
        total_content = sum(
            len(ch.content or "") for ch in (guide.chapters or [])
        )
        return (
            f"Category: {self.get_source_category()}\n"
            f"Guide: {guide.title}\n"
            f"Chapters: {len(guide.chapters or [])}\n"
            f"Total content length: {total_content}"
        )
