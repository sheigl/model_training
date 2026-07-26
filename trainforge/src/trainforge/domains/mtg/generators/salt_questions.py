"""Generate salt/controversial card Q&A pairs — why cards are salty or polarizing."""

from __future__ import annotations

import logging
from typing import Any

from trainforge.domain import TemplateConfig
from trainforge.generator import BaseGenerator

logger = logging.getLogger(__name__)


class SaltQuestionsGenerator(BaseGenerator[list[dict[str, Any]]]):
    """Generate Q&A explaining why certain cards are controversial or 'salty' in Commander.

    Category: salt_questions
    Data batches: Groups of 8 salty card dicts from EDHREC rankings.
    Templates: why_is_this_salty (from templates.yaml)
    """

    BATCH_SIZE = 8

    def get_data_batches(self) -> list[list[dict[str, Any]]]:
        """Fetch salty cards and group into batches of 8.

        Returns:
            List of batches, each batch being a list of up to 8 card dicts.
        """
        ds = self.domain.get_data_source()
        cards = ds.get_salty_cards(min_salt=1.2, limit=100)

        # Group into batches of BATCH_SIZE
        batches: list[list[dict[str, Any]]] = []
        for i in range(0, len(cards), self.BATCH_SIZE):
            batches.append(cards[i : i + self.BATCH_SIZE])

        return batches

    def get_source_category(self) -> str:
        return "salt_questions"

    def build_prompt(
        self, template: TemplateConfig, data_batch: list[dict[str, Any]]
    ) -> str:
        """Build the LLM prompt asking about salty/controversial cards.

        Args:
            template: TemplateConfig with task_instruction.
            data_batch: List of card dicts (up to 8).

        Returns:
            Prompt with notation legend and <task> wrapping.
        """
        # Build card list for the prompt
        card_lines: list[str] = []
        for i, card in enumerate(data_batch, 1):
            name = card.get("name", "Unknown")
            card_type = card.get("type", "")
            oracle_text = card.get("oracle_text", "") or card.get("text", "")
            salt = float(card.get("salt", 0) or 0)
            num_decks = card.get("num_decks", 0)

            card_lines.append(
                f"{i}. {name} ({card_type}) — Salt: {salt:.2f}, Decks: {num_decks:,}\n"
                f"   Oracle Text: {oracle_text[:200]}..."
            )

        cards_str = "\n".join(card_lines)

        notation = self.domain.notation_legend

        return (
            f"{notation}\n\n"
            f"<task>\n"
            f"{template.task_instruction}\n\n"
            f"Here are several cards that have high 'salt' scores in the Commander "
            f"community:\n\n"
            f"{cards_str}\n\n"
            f"Generate questions exploring:\n"
            f"- Why each card frustrates players\n"
            f"- The mechanical reasons for the controversy\n"
            f"- Whether the card is actually fair or overpowered\n"
            f"- How players can play around or against these cards\n"
            f"\n"
            f"Output JSON:\n"
            f'[\n'
            f'  {{"question": "...", "answer": "..."}},\n'
            f'  {{"question": "...", "answer": "..."}}\n'
            f"]\n"
            f"\n"
            f"Answers should be 3-5 sentences. Output ONLY valid JSON.\n"
            f"</task>"
        )

    def build_context(self, data_batch: list[dict[str, Any]]) -> str | None:
        """Build metadata context for the generated Q&A."""
        card_names = [c.get("name", "Unknown") for c in data_batch]
        avg_salt = sum(float(c.get("salt", 0) or 0) for c in data_batch) / max(
            len(data_batch), 1
        )
        return (
            f"Category: {self.get_source_category()}\n"
            f"Cards: {', '.join(card_names)}\n"
            f"Batch size: {len(data_batch)}\n"
            f"Average salt: {avg_salt:.2f}"
        )
