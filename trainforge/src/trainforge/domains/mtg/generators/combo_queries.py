"""Generate combo query Q&A pairs from Commander Spellbook combos.

Category: combo_query
Templates: how_does_it_work, what_do_i_need, why_does_this_work, what_is_the_result
"""

from __future__ import annotations

import logging

from trainforge.domain import TemplateConfig
from trainforge.generator import BaseGenerator
from trainforge.domains.mtg.models import ComboWithCards

logger = logging.getLogger(__name__)


class ComboQueriesGenerator(BaseGenerator[ComboWithCards]):
    """Generate combo query Q&A pairs from Commander Spellbook combos.

    Each data batch is a single ComboWithCards with enriched card details.
    The prompt includes card details, combo description, and what the combo produces.
    """

    def get_data_batches(self) -> list[ComboWithCards]:
        """Fetch combos enriched with card data, filtering for 2+ card combos.

        Returns:
            List of ComboWithCards objects with at least 2 cards and a description.
        """
        ds = self.domain.get_data_source()
        combos = ds.get_combos_enriched(limit=100)

        # Filter for combos with 2 or more cards and a non-empty description
        return [c for c in combos if len(c.uses) >= 2 and c.description]

    def get_source_category(self) -> str:
        return "combo_query"

    def build_prompt(self, template: TemplateConfig, data_batch: ComboWithCards) -> str:
        """Build the LLM prompt for a combo and template.

        Args:
            template: TemplateConfig with task_instruction (may contain
                      {combo_name}, {card_details}, {combo_description}, {produces}
                      placeholders).
            data_batch: ComboWithCards with enriched card details.

        Returns:
            Complete prompt string with notation legend and <task> wrapping.
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
        card_details = "\n\n".join(card_lines)

        # Format description with numbered steps
        description = combo.description or ""
        steps = description.split("\n")
        numbered = (f"Step {i + 1}. {s}" for i, s in enumerate(steps))
        description_str = "\n".join(numbered)

        # What this combo produces
        produces_lines: list[str] = []
        for p in combo.produces or []:
            produces_lines.append(p.description + (" (infinite)" if p.infinite else ""))
        produces_str = "; ".join(produces_lines) if produces_lines else "Not specified"

        notation = self.domain.notation_legend

        # Fill template placeholders if present
        task = template.task_instruction.format(
            combo_name=combo.name or "Unnamed Combo",
            card_details=card_details,
            combo_description=description_str,
            produces=produces_str,
        )

        tags_str = ", ".join(combo.tags) if combo.tags else "none"

        return (
            f"{notation}\n\n"
            f"<task>\n"
            f"{task}\n\n"
            f"Combo: {combo.name or 'Unnamed Combo'}\n"
            f"Description: {combo.description or 'N/A'}\n"
            f"Tags: {tags_str}\n"
            f"Cards in combo: {len(combo.cards)}\n\n"
            f"Card details:\n"
            f"{card_details}\n\n"
            f"What this combo produces:\n"
            f"{produces_str}\n"
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
