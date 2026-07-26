"""Generate color staple Q&A pairs — top staple cards for each color identity."""

from __future__ import annotations

import logging
from typing import Any

from trainforge.domain import TemplateConfig
from trainforge.generator import BaseGenerator

logger = logging.getLogger(__name__)


class ColorStaplesGenerator(BaseGenerator[tuple[str, list[dict[str, Any]]]]):
    """Generate Q&A about staple cards organized by color identity.

    Category: color_staples
    Data batches: Tuples of (color_name, list_of_card_dicts).
    Templates: staples_for_color (from templates.yaml)
    """

    COLORS = ["white", "blue", "black", "red", "green", "colorless"]

    def get_data_batches(self) -> list[tuple[str, list[dict[str, Any]]]]:
        """Fetch top cards for each color identity, split into sub-batches of 10.

        Each color's cards are split into up to 3 sub-batches of 10 cards each
        to keep prompt sizes manageable.

        Returns:
            List of (color_name, cards) tuples.
        """
        ds = self.domain.get_data_source()
        batches: list[tuple[str, list[dict[str, Any]]]] = []

        for color in self.COLORS:
            cards = ds.get_top_cards_by_color(color, limit=30)
            if not cards:
                continue
            for i in range(0, min(len(cards), 30), 10):
                chunk = cards[i : i + 10]
                if chunk:
                    batches.append((color, list(chunk)))

        return batches

    def get_source_category(self) -> str:
        return "color_staples"

    def build_prompt(
        self,
        template: TemplateConfig,
        data_batch: tuple[str, list[dict[str, Any]]],
    ) -> str:
        """Build the LLM prompt about staple cards in a color.

        Args:
            template: TemplateConfig with task_instruction.
            data_batch: Tuple of (color_name, list_of_card_dicts).

        Returns:
            Prompt with notation legend and <task> wrapping.
        """
        color, cards = data_batch

        # Build card list (top 15 for readability)
        card_lines: list[str] = []
        for i, card in enumerate(cards[:15], 1):
            name = card.get("name", "Unknown")
            card_type = card.get("type", "")
            mana_cost = card.get("mana_cost", "")
            num_decks = card.get("num_decks", 0)
            edhrec_rank = card.get("edhrecRank") or card.get("edhrec_rank")

            rank_str = f" #{edhrec_rank}" if edhrec_rank else ""
            card_lines.append(
                f"{i}. {name}{rank_str} — {card_type} ({mana_cost}) — "
                f"{num_decks:,} decks"
            )

        cards_str = "\n".join(card_lines)

        notation = self.domain.notation_legend

        task_instruction = template.task_instruction.format(
            color=color,
            card_list=cards_str,
        )

        return (
            f"{notation}\n\n"
            f"<task>\n"
            f"{task_instruction}\n\n"
            f"The following are top staple cards for {color} in Commander:\n\n"
            f"{cards_str}\n\n"
            f"Generate questions about:\n"
            f"- Why these cards are essential in {color} decks\n"
            f"- What role each card fills (ramp, draw, removal, etc.)\n"
            f"- Alternatives to expensive staples\n"
            f"- How {color}'s identity shapes its staple choices\n"
            f"\n"
            f"Output JSON:\n"
            f'[\n'
            f'  {{"question": "...", "answer": "..."}},\n'
            f'  {{"question": "...", "answer": "..."}}\n'
            f"]\n"
            f"\n"
            f"Answers should be 3-5 sentences grounded in the card data. "
            f"Output ONLY valid JSON.\n"
            f"</task>"
        )

    def build_context(
        self, data_batch: tuple[str, list[dict[str, Any]]]
    ) -> str | None:
        """Build metadata context for the generated Q&A."""
        color, cards = data_batch
        card_names = [c.get("name", "Unknown") for c in cards[:10]]
        return (
            f"Category: {self.get_source_category()}\n"
            f"Color: {color}\n"
            f"Top cards: {', '.join(card_names)}\n"
            f"Total staples fetched: {len(cards)}"
        )
