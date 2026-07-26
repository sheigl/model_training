"""Generate synergy discovery Q&A pairs — cards that work well together.

Ports the old CLI synergy generator into the TrainForge BaseGenerator
framework.  Fetches high-rank cards, finds their synergy partners via
``get_synergy_partners()``, and generates Q&A about card interactions.
"""

from __future__ import annotations

import logging

from trainforge.domain import TemplateConfig
from trainforge.generator import BaseGenerator
from trainforge.domains.mtg.models import CardWithMetadata

logger = logging.getLogger(__name__)


# =============================================================================
# GENERATOR
# =============================================================================


class GenerateSynergyQuestions(BaseGenerator[CardWithMetadata]):
    """Generate synergy-discovery Q&A pairs from enriched card data.

    Each data batch is a single CardWithMetadata whose synergy partners
    are fetched and included in the prompt context.
    """

    def get_data_batches(self) -> list[CardWithMetadata]:
        """Fetch high-rank cards that have synergy partners.

        Gets top cards by EDHREC rank, then for each card finds synergy
        partners via the data source.  Only returns cards that have at
        least one synergy partner.

        Returns:
            List of CardWithMetadata that have synergy data.
        """
        ds = self.domain.get_data_source()

        # Fetch top cards by EDHREC rank
        cards = ds.get_cards_enriched(
            filters={"edhrecRank": {"$ne": None}},
            limit=100,
        )
        cards.sort(key=lambda c: c.edhrec_rank or 999999)

        results: list[CardWithMetadata] = []
        for card in cards:
            partners = ds.get_synergy_partners(card.name, limit=5)
            if partners:
                # Attach partner info for the build_prompt method
                _attach_synergy_partners(card, partners)
                results.append(card)

        logger.info(
            "Built %d synergy batches (from %d candidates)",
            len(results),
            len(cards),
        )
        return results

    def get_source_category(self) -> str:
        return "synergy"

    def build_prompt(
        self, template: TemplateConfig, data_batch: CardWithMetadata
    ) -> str:
        """Build the LLM prompt exploring card synergies.

        Args:
            template: TemplateConfig with task_instruction.
            data_batch: A CardWithMetadata with synergy partners attached.

        Returns:
            Full prompt string.
        """
        card = data_batch
        partners = _get_synergy_partners(card)

        detail = card.to_prompt_detail(include_prices=True)
        notation = self.domain.notation_legend

        # Format partner cards
        partner_lines: list[str] = []
        for i, partner in enumerate(partners, 1):
            partner_lines.append(
                f"Partner {i}: {partner.name}\n"
                f"  Mana Cost: {partner.mana_cost or 'N/A'}\n"
                f"  Type: {partner.type or 'N/A'}\n"
                f"  Oracle Text: {partner.text or partner.oracle_text or 'N/A'}"
            )
        partners_str = "\n\n".join(partner_lines) if partner_lines else "No synergy partners found."

        return (
            f"{notation}\n\n"
            f"<task>\n"
            f"{template.task_instruction}\n\n"
            f"Primary card:\n"
            f"{detail}\n\n"
            f"Synergy partner cards:\n"
            f"{partners_str}\n\n"
            f"Generate questions about:\n"
            f"- How these cards interact with {card.name}\n"
            f"- What combos or value engines they form\n"
            f"- Why they work well together mechanically\n"
            f"- What strategies benefit from this synergy\n"
            f"\n"
            f"Output JSON:\n"
            f'[\n'
            f'  {{"question": "...", "answer": "..."}},\n'
            f'  {{"question": "...", "answer": "..."}}\n'
            f"]\n"
            f"\n"
            f"Answers should be 3-5 sentences grounded in the cards' actual oracle text.\n"
            f"Output ONLY valid JSON.\n"
            f"</task>"
        )

    def build_context(self, data_batch: CardWithMetadata) -> str | None:
        """Build metadata context for the generated Q&A."""
        card = data_batch
        partners = _get_synergy_partners(card)
        partner_names = [p.name for p in partners]
        return (
            f"Category: {self.get_source_category()}\n"
            f"Primary Card: {card.name}\n"
            f"EDHREC Rank: {card.edhrec_rank or 'N/A'}\n"
            f"Color Identity: {', '.join(card.color_identity) if card.color_identity else 'Colorless'}\n"
            f"Synergy Partners ({len(partners)}): {', '.join(partner_names)}"
        )


# =============================================================================
# Private helpers — attach synergy partners to card objects
# =============================================================================

_SYNERGY_PARTNERS_ATTR = "_synergy_partners"


def _attach_synergy_partners(
    card: CardWithMetadata, partners: list[CardWithMetadata]
) -> None:
    """Store synergy partners on the card as a private attribute."""
    object.__setattr__(card, _SYNERGY_PARTNERS_ATTR, partners)


def _get_synergy_partners(card: CardWithMetadata) -> list[CardWithMetadata]:
    """Retrieve synergy partners from a card."""
    return getattr(card, _SYNERGY_PARTNERS_ATTR, [])
