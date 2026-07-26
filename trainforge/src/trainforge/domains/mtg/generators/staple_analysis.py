"""Generate staple analysis Q&A pairs — why a card is a Commander staple."""

from __future__ import annotations

import logging
from typing import Any

from trainforge.domain import TemplateConfig
from trainforge.generator import BaseGenerator

logger = logging.getLogger(__name__)


class StapleAnalysisGenerator(BaseGenerator[dict[str, Any]]):
    """Generate Q&A explaining why game-changer cards are Commander staples.

    Category: staple_analysis
    Data batches: Game-changer card dicts from EDHREC rankings.
    Templates: staple_analysis (from templates.yaml)
    """

    def get_data_batches(self) -> list[dict[str, Any]]:
        """Fetch game-changer cards from EDHREC rankings.

        Returns:
            List of card dicts with name, type, oracle_text, salt, num_decks, etc.
        """
        ds = self.domain.get_data_source()
        cards = ds.get_game_changers(limit=self.max_items or 100)
        return list(cards)

    def get_source_category(self) -> str:
        return "staple_analysis"

    def build_prompt(self, template: TemplateConfig, data_batch: dict[str, Any]) -> str:
        """Build the LLM prompt analyzing why a card is a Commander staple.

        Args:
            template: TemplateConfig with task_instruction.
            data_batch: Card dict from get_game_changers().

        Returns:
            Prompt with notation legend and <task> wrapping.
        """
        name = data_batch.get("name", "")
        oracle_text = data_batch.get("oracle_text", "") or data_batch.get("text", "")
        card_type = data_batch.get("type", "")
        mana_cost = data_batch.get("mana_cost", "")
        num_decks = data_batch.get("num_decks", 0)
        salt = float(data_batch.get("salt", 0) or 0)
        tags = data_batch.get("tags", []) or []
        color_identity = data_batch.get("color_identity", []) or []

        color_str = ", ".join(color_identity) if color_identity else "Colorless"
        tags_str = ", ".join(tags) if tags else "none"
        if salt > 2.5:
            salt_label = "very controversial"
        elif salt > 1.5:
            salt_label = "controversial"
        elif salt > 0.8:
            salt_label = "mildly disliked"
        else:
            salt_label = "generally accepted"

        edhrec_rank = data_batch.get("edhrecRank")
        if edhrec_rank is None:
            edhrec_rank = data_batch.get("edhrec_rank")

        # Build card detail section
        card_lines = [
            f"Card: {name}",
            f"Type: {card_type}",
            f"Mana cost: {mana_cost}",
            f"Color identity: {color_str}",
            f"Oracle text: {oracle_text}",
            f"Number of Commander decks it appears in: {num_decks:,}",
            f"Salt score: {salt:.2f} ({salt_label})",
            f"Tags: {tags_str}",
        ]
        if edhrec_rank is not None:
            card_lines.append(f"EDHREC Rank: #{edhrec_rank}")
        card_detail = "\n".join(card_lines)

        card_instruction = template.task_instruction.format(
            card_name=name,
            card_detail=card_detail,
        )

        notation = self.domain.notation_legend

        return (
            f"{notation}\n\n"
            f"<task>\n"
            f"{card_instruction}"
            f"\n\n"
            f"Card details:\n"
            f"{card_detail}"
            f"\n\n"
            f"Generate questions about why this card is so widely played, "
            f"what makes it powerful, and when/how to use it.\n"
            f"Also address the salt score if it's above 1.5 — why do players dislike it?\n"
            f"\n"
            f"Question styles:\n"
            f'- "Why is {name} in so many Commander decks?"\n'
            f'- "What makes {name} a staple?"\n'
            f'- "Is {name} worth including in my deck?"\n'
            f'- "Why do people hate playing against {name}?" (if salty)\n'
            f'- "What kind of decks want {name}?"\n'
            f"\n"
            f"Output JSON:\n"
            f'[\n'
            f'  {{"question": "...", "answer": "..."}},\n'
            f'  {{"question": "...", "answer": "..."}},\n'
            f'  {{"question": "...", "answer": "..."}}\n'
            f"]\n"
            f"\n"
            f"Answers should be 3-5 sentences grounded in the card's actual text and statistics.\n"
            f"Output ONLY valid JSON. The answer MUST be a string and not an array of strings.\n"
            f"</task>"
        )

    def build_context(self, data_batch: dict[str, Any]) -> str | None:
        """Build metadata context for the generated Q&A."""
        name = data_batch.get("name", "Unknown")
        card_type = data_batch.get("type", "")
        salt = float(data_batch.get("salt", 0) or 0)
        num_decks = data_batch.get("num_decks", 0)
        return (
            f"Category: {self.get_source_category()}\n"
            f"Card: {name}\n"
            f"Type: {card_type}\n"
            f"Salt: {salt:.2f}\n"
            f"Decks: {num_decks}"
        )
