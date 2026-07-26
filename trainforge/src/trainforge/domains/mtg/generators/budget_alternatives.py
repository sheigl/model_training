"""Generate budget alternative Q&A pairs for expensive MTG cards.

Category: budget
Templates: cheaper_alternative (from templates.yaml)
"""

from __future__ import annotations

import logging

from trainforge.domain import TemplateConfig
from trainforge.generator import BaseGenerator
from trainforge.domains.mtg.models import CardWithMetadata

logger = logging.getLogger(__name__)


class BudgetAlternativesGenerator(
    BaseGenerator[tuple[CardWithMetadata, list[CardWithMetadata]]]
):
    """Generate budget alternative Q&A pairs for expensive MTG cards.

    Each data batch is a (expensive_card, list_of_budget_alternatives) tuple.
    The prompt includes full card details for both the expensive card and its
    budget alternatives, with price comparisons.
    """

    def get_data_batches(
        self,
    ) -> list[tuple[CardWithMetadata, list[CardWithMetadata]]]:
        """Fetch expensive cards and find budget alternatives for each.

        Fetches popular cards (EDHREC rank < 500) that cost > $20, then
        finds budget alternatives using ds.get_budget_alternatives().

        Returns:
            List of (expensive_card, [budget_alternatives]) tuples.
        """
        ds = self.domain.get_data_source()

        # Get popular cards with EDHREC rank
        expensive = ds.get_cards_enriched(
            filters={"edhrecRank": {"$lt": 500}},
            limit=50,
        )

        # Filter for cards with price > $20
        expensive = [
            c
            for c in expensive
            if c.prices and c.prices.usd is not None and c.prices.usd > 20
        ]

        batches: list[tuple[CardWithMetadata, list[CardWithMetadata]]] = []
        for card in expensive[:20]:
            alternatives = ds.get_budget_alternatives(
                expensive_card=card.name,
                max_price=10.0,
                limit=5,
            )
            if alternatives:
                batches.append((card, alternatives))

        logger.info(
            "Found %d expensive cards with budget alternatives",
            len(batches),
        )
        return batches

    def get_source_category(self) -> str:
        return "budget"

    def build_prompt(
        self,
        template: TemplateConfig,
        data_batch: tuple[CardWithMetadata, list[CardWithMetadata]],
    ) -> str:
        """Build the LLM prompt for a budget alternative template.

        Args:
            template: TemplateConfig with task_instruction (may contain
                      {expensive_card_name}, {expensive_card_details},
                      {expensive_card_price}, {budget_details} placeholders).
            data_batch: (expensive_card, [budget_alternatives]) tuple.

        Returns:
            Complete prompt string with notation legend and <task> wrapping.
        """
        expensive_card, alternatives = data_batch

        # Format expensive card details
        exp_details = expensive_card.to_prompt_detail()

        def _price_str(card: CardWithMetadata) -> str:
            if card.prices and card.prices.usd is not None:
                return f"${card.prices.usd:.2f}"
            return "N/A"

        # Format budget alternatives
        budget_lines: list[str] = []
        for i, c in enumerate(alternatives, 1):
            budget_lines.append(
                f"{i}. {c.name} ({c.rarity or 'Unknown'}) - {_price_str(c)} - "
                f"EDHREC Rank: {c.edhrec_rank or 'N/A'}\n"
                f"   Oracle Text: {(c.text or '')[:200]}..."
            )
        budget_details = "\n".join(budget_lines)

        exp_price = _price_str(expensive_card)
        notation = self.domain.notation_legend

        # Fill template placeholders if present
        task = template.task_instruction.format(
            expensive_card_name=expensive_card.name,
            expensive_card_details=exp_details,
            expensive_card_price=exp_price,
            budget_details=budget_details,
        )

        return (
            f"{notation}\n\n"
            f"<task>\n"
            f"{task}\n\n"
            f"<expensive_card>\n"
            f"{exp_details}\n"
            f"Price: {exp_price}\n"
            f"EDHREC Rank: {expensive_card.edhrec_rank or 'N/A'}\n"
            f"Salt Score: {expensive_card.edhrec_salt or 'N/A'}\n"
            f"</expensive_card>\n\n"
            f"<budget_alternatives>\n"
            f"{budget_details}\n"
            f"Price range: {', '.join(_price_str(c) for c in alternatives)}\n"
            f"</budget_alternatives>\n"
            f"</task>"
        )

    def build_context(
        self,
        data_batch: tuple[CardWithMetadata, list[CardWithMetadata]],
    ) -> str | None:
        """Build metadata context for the generated Q&A."""
        expensive_card, alternatives = data_batch
        alt_names = [c.name for c in alternatives]
        return (
            f"Category: {self.get_source_category()}\n"
            f"Expensive card: {expensive_card.name}\n"
            f"Price: ${expensive_card.prices.usd if expensive_card.prices and expensive_card.prices.usd else 'N/A'}\n"
            f"Alternatives: {', '.join(alt_names)}\n"
            f"Alternative count: {len(alternatives)}"
        )
