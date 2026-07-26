"""Generate multi-card usage Q&A pairs — how combo cards work together effectively."""

from __future__ import annotations

import logging

from trainforge.domain import TemplateConfig
from trainforge.generator import BaseGenerator
from trainforge.domains.mtg.models import ComboWithCards

logger = logging.getLogger(__name__)


class MultiCardUsageGenerator(BaseGenerator[ComboWithCards]):
    """Generate Q&A explaining how multiple cards work together in combos.

    Category: multi_card_usage
    Data batches: ComboWithCards objects with 2+ cards.
    Templates: how_to_use_these_together (from templates.yaml)
    """

    def get_data_batches(self) -> list[ComboWithCards]:
        """Fetch combos enriched with card data, filtering for 2+ card combos.

        Returns:
            List of ComboWithCards where each combo has at least 2 cards.
        """
        ds = self.domain.get_data_source()
        combos = ds.get_combos_enriched(limit=100)

        # Filter for combos with 2 or more cards and a non-empty description
        return [c for c in combos if len(c.uses) >= 2 and c.description]

    def get_source_category(self) -> str:
        return "multi_card_usage"

    def build_prompt(
        self, template: TemplateConfig, data_batch: ComboWithCards
    ) -> str:
        """Build the LLM prompt explaining how combo cards work together.

        Args:
            template: TemplateConfig with task_instruction.
            data_batch: ComboWithCards with enriched card details.

        Returns:
            Prompt with notation legend and <task> wrapping.
        """
        combo = data_batch

        # Build card details
        card_lines: list[str] = []
        for i, card in enumerate(combo.cards, 1):
            oracle = card.text or card.oracle_text or "N/A"
            card_lines.append(
                f"Card {i}: {card.name}\n"
                f"  Mana Cost: {card.mana_cost or 'N/A'}\n"
                f"  Type: {card.type or 'N/A'}\n"
                f"  Oracle Text: {oracle[:300]}"
            )

        cards_str = "\n\n".join(card_lines)

        # Combo produces details
        produces_lines: list[str] = []
        for p in combo.produces or []:
            produces_lines.append(
                f"- {p.description}" + (" (infinite)" if p.infinite else "")
            )
        produces_str = "\n".join(produces_lines) if produces_lines else "Not specified"

        tags_str = ", ".join(combo.tags) if combo.tags else "none"

        notation = self.domain.notation_legend

        return (
            f"{notation}\n\n"
            f"<task>\n"
            f"{template.task_instruction}\n\n"
            f"Combo: {combo.name or 'Unnamed Combo'}\n"
            f"Description: {combo.description or 'N/A'}\n"
            f"Tags: {tags_str}\n"
            f"Cards in combo: {len(combo.cards)}\n\n"
            f"Card details:\n"
            f"{cards_str}\n\n"
            f"What this combo produces:\n"
            f"{produces_str}\n\n"
            f"Generate questions about:\n"
            f"- How these cards interact to create the combo\n"
            f"- The sequence of steps needed\n"
            f"- What each card contributes\n"
            f"- What happens if one piece is removed\n"
            f"- How to disrupt or counter this combo\n"
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

    def build_context(self, data_batch: ComboWithCards) -> str | None:
        """Build metadata context for the generated Q&A."""
        combo = data_batch
        card_names = [c.name for c in combo.cards]
        return (
            f"Category: {self.get_source_category()}\n"
            f"Combo: {combo.name or 'Unnamed'}\n"
            f"Cards: {', '.join(card_names)}\n"
            f"Card count: {len(combo.cards)}"
        )
