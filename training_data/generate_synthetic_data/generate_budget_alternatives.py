"""Generate Budget Alternative Questions using BaseGenerator and MTGDataAccess.

Generates Q&A pairs for budget alternatives across four categories:
1. pauper_budget - Pauper-legal alternatives to expensive cards
2. budget_optimized - Best budget replacements under $10
3. proxy_friendly - Cards that proxy well for expensive staples
4. upgrade_path - Progression from budget to premium versions
"""

from __future__ import annotations

import random
from typing import Any, Iterator
from dataclasses import dataclass

from .base_generator import BaseGenerator, TemplateConfig
from .data_access import MTGDataAccess
from .models import Model, ModelType, ValidationMetrics
from .domain_models import CardWithMetadata, CardLegalities
from .common import MTG_NOTATION_LEGEND, SYSTEM_MESSAGE, OUTPUT_FORMAT
from .query_model import QueryModel


# Budget alternative categories with search filters
BUDGET_CATEGORIES = [
    {
        "name": "Fast Mana",
        "expensive_filters": {"text_regex": "add.*mana|add {C}", "rarity": ["mythic", "rare"], "min_price_usd": 20},
        "budget_filters": {"text_regex": "add.*mana|add {C}", "rarity": ["common", "uncommon"], "max_price_usd": 10},
    },
    {
        "name": "Tutors",
        "expensive_filters": {"text_regex": "search.*library", "rarity": ["mythic", "rare"], "min_price_usd": 15},
        "budget_filters": {"text_regex": "search.*library", "rarity": ["common", "uncommon"], "max_price_usd": 10},
    },
    {
        "name": "Card Draw Engines",
        "expensive_filters": {"text_regex": "draw.*card", "rarity": ["mythic", "rare"], "min_price_usd": 15},
        "budget_filters": {"text_regex": "draw.*card", "rarity": ["common", "uncommon"], "max_price_usd": 10},
    },
    {
        "name": "Removal",
        "expensive_filters": {"text_regex": "destroy|exile", "rarity": ["mythic", "rare"], "min_price_usd": 10},
        "budget_filters": {"text_regex": "destroy|exile", "rarity": ["common", "uncommon"], "max_price_usd": 8},
    },
    {
        "name": "Protection",
        "expensive_filters": {"text_regex": "indestructible|hexproof|ward", "rarity": ["mythic", "rare"], "min_price_usd": 10},
        "budget_filters": {"text_regex": "indestructible|hexproof|ward", "rarity": ["common", "uncommon"], "max_price_usd": 8},
    },
    {
        "name": "Win Conditions",
        "expensive_filters": {"text_regex": "win the game|you win", "rarity": ["mythic", "rare"], "min_price_usd": 20},
        "budget_filters": {"text_regex": "win the game|you win", "rarity": ["common", "uncommon"], "max_price_usd": 10},
    },
    {
        "name": "Counterspells",
        "expensive_filters": {"text_regex": "counter target spell", "rarity": ["mythic", "rare"], "min_price_usd": 15},
        "budget_filters": {"text_regex": "counter target spell", "rarity": ["common", "uncommon"], "max_price_usd": 5},
    },
    {
        "name": "Board Wipes",
        "expensive_filters": {"text_regex": "destroy all|exile all", "rarity": ["mythic", "rare"], "min_price_usd": 15},
        "budget_filters": {"text_regex": "destroy all|exile all", "rarity": ["common", "uncommon"], "max_price_usd": 8},
    },
]


@dataclass(frozen=True)
class BudgetContext:
    """Context for budget alternative generation."""
    expensive_card: CardWithMetadata
    budget_cards: list[CardWithMetadata]
    category: str
    template_type: str


class GenerateBudgetAlternatives(BaseGenerator[BudgetContext]):
    """Generate budget alternative Q&A pairs using BaseGenerator."""

    TEMPLATES = [
        TemplateConfig(
            template_id="pauper_budget",
            task_instruction=(
                "Generate exactly 3 Q&A pairs for PAUPER-LEGAL budget alternatives.\n"
                "Focus on: cards legal in Pauper format (common rarity only) that provide similar functionality.\n"
                "At least one question must be phrased as 'What\'s a pauper-legal replacement for [card]?'"
            ),
            validation_rules=(
                "1. All suggested alternatives MUST be common rarity (Pauper legal)\n"
                "2. Answer explains functional similarity to expensive card\n"
                "3. Answer cites oracle text of BOTH expensive card and budget alternative\n"
                "4. Answer mentions actual price difference (use provided price data)\n"
                "5. HARD REJECT if any suggested card is not common rarity\n"
                "6. HARD REJECT if answer doesn't explain HOW the alternative works similarly\n"
                "7. HARD REJECT if answer contains markdown formatting (bold, bullets)\n"
                "8. Answer must be at least 100 characters"
            ),
            weight=1.0,
            min_answer_length=100,
        ),
        TemplateConfig(
            template_id="budget_optimized",
            task_instruction=(
                "Generate exactly 3 Q&A pairs for OPTIMIZED BUDGET replacements (under $10).\n"
                "Focus on: best value replacements that capture 80%+ of the expensive card's utility.\n"
                "At least one question must compare EDHREC inclusion percentages."
            ),
            validation_rules=(
                "1. All suggested alternatives MUST be under $10 (use provided price data)\n"
                "2. Answer compares EDHREC inclusion % of expensive vs budget cards\n"
                "3. Answer explains specific trade-offs (what you lose/gain)\n"
                "4. Answer cites oracle text for key abilities on both cards\n"
                "5. HARD REJECT if any suggested card is $10 or more\n"
                "6. HARD REJECT if answer doesn't mention inclusion percentage difference\n"
                "7. HARD REJECT if answer contains markdown formatting\n"
                "8. Answer must be at least 100 characters"
            ),
            weight=1.0,
            min_answer_length=100,
        ),
        TemplateConfig(
            template_id="proxy_friendly",
            task_instruction=(
                "Generate exactly 3 Q&A pairs for PROXY-FRIENDLY casual alternatives.\n"
                "Focus on: cards that are functionally similar enough for casual playgroups allowing proxies.\n"
                "At least one question must address 'Is it worth proxying [expensive card] or should I use [budget card]?'"
            ),
            validation_rules=(
                "1. Answer distinguishes between proxying vs. using budget alternative\n"
                "2. Answer explains functional equivalence for casual play\n"
                "3. Answer mentions power level difference honestly\n"
                "4. Answer cites oracle text showing key similarities\n"
                "5. HARD REJECT if answer recommends proxying without caveats\n"
                "6. HARD REJECT if answer doesn't mention playgroup communication\n"
                "7. HARD REJECT if answer contains markdown formatting\n"
                "8. Answer must be at least 100 characters"
            ),
            weight=1.0,
            min_answer_length=100,
        ),
        TemplateConfig(
            template_id="upgrade_path",
            task_instruction=(
                "Generate exactly 3 Q&A pairs for UPGRADE PATH analysis.\n"
                "Focus on: when and why to upgrade from budget to premium version, intermediate steps.\n"
                "At least one question must be phrased as 'When should I upgrade from [budget card] to [expensive card]?'"
            ),
            validation_rules=(
                "1. Answer identifies specific meta conditions warranting upgrade\n"
                "2. Answer mentions intermediate upgrade steps if they exist\n"
                "3. Answer compares competitive viability (cEDH vs casual)\n"
                "4. Answer cites oracle text showing what premium version adds\n"
                "5. HARD REJECT if answer says 'always upgrade immediately'\n"
                "6. HARD REJECT if answer doesn't mention budget constraints\n"
                "7. HARD REJECT if answer contains markdown formatting\n"
                "8. Answer must be at least 100 characters"
            ),
            weight=1.0,
            min_answer_length=100,
        ),
    ]

    def __init__(
        self,
        data_access: MTGDataAccess,
        models: dict[ModelType, Model],
        validation_pct: float,
        target_count: int,
        save_item: Any,
        metrics: ValidationMetrics | None = None,
        dry_run: bool = False,
    ) -> None:
        super().__init__(
            models=models,
            validation_pct=validation_pct,
            target_count=target_count,
            save_item=save_item,
            metrics=metrics,
            generator_name="GenerateBudgetAlternatives",
            dry_run=dry_run,
        )
        self.data_access = data_access

    def get_data_batches(self) -> Iterator[BudgetContext]:
        """Fetch expensive cards and their budget alternatives."""
        for category in BUDGET_CATEGORIES:
            if self.generated_count >= self.target_count:
                break

            # Fetch expensive cards
            expensive_cards = self.data_access.get_cards_enriched(
                filters=category["expensive_filters"],
                limit=10,
            )

            # Fetch budget alternatives
            budget_cards = self.data_access.get_cards_enriched(
                filters=category["budget_filters"],
                limit=15,
            )

            if not expensive_cards or not budget_cards:
                continue

            for exp_card in expensive_cards[:5]:
                if self.generated_count >= self.target_count:
                    break

                # Filter budget cards that are actually cheaper (or both have no price)
                exp_price = exp_card.prices.usd if exp_card.prices and exp_card.prices.usd else None
                cheaper_budget = []
                for c in budget_cards:
                    c_price = c.prices.usd if c.prices and c.prices.usd else None
                    if exp_price is not None and c_price is not None and c_price < exp_price:
                        cheaper_budget.append(c)
                    elif exp_price is None and c_price is None:
                        # Both have no price data — still useful for budget comparison by rarity
                        cheaper_budget.append(c)
                cheaper_budget = cheaper_budget[:5]

                if not cheaper_budget:
                    continue

                yield BudgetContext(
                    expensive_card=exp_card,
                    budget_cards=cheaper_budget,
                    category=category["name"],
                    template_type="budget_alternative",
                )

    def build_prompt(self, template: TemplateConfig, data_batch: BudgetContext) -> str:
        """Build the LLM prompt for a specific template and budget context."""
        context = data_batch
        exp_card = context.expensive_card
        budget_cards = context.budget_cards

        # Build expensive card details
        exp_details = exp_card.to_prompt_detail()

        # Build budget card details
        def _price_str(card):
            if card.prices and card.prices.usd is not None:
                return f"${card.prices.usd:.2f}"
            return "N/A"

        budget_details = "\n".join([
            f"  - {c.name} ({c.rarity or 'Unknown'}) - {_price_str(c)} - EDHREC Rank: {c.edhrec_rank or 'N/A'}\n    Text: {(c.text or '')[:200]}..."
            for c in budget_cards
        ])

        # Build price comparison
        exp_price = _price_str(exp_card) if (exp_card.prices and exp_card.prices.usd is not None) else "Unknown"
        budget_prices = ", ".join([_price_str(c) for c in budget_cards])

        prompt = f"""{SYSTEM_MESSAGE}

{MTG_NOTATION_LEGEND}

<expensive_card>
{exp_details}
Price: {exp_price}
EDHREC Rank: {exp_card.edhrec_rank or 'N/A'}
Saltiness: {exp_card.edhrec_salt or 'N/A'}
</expensive_card>

<budget_alternatives>
{budget_details}
Price range: {budget_prices}
</budget_alternatives>

<category>
{context.category}
</category>

<task>
{template.task_instruction}

REQUIREMENTS:
- Output ONLY valid JSON array of 3 objects: [{{"question": "...", "answer": "..."}}, ...]
- Each answer must be a single string (not array)
- Use natural, conversational question phrasing
- Cite specific oracle text and price data
- No markdown formatting

{OUTPUT_FORMAT}
</task>"""

        return prompt

    def get_source_category(self) -> str:
        return "budget_alternative"

    def get_source_data(self, data_batch: BudgetContext) -> list[Any]:
        names = [data_batch.expensive_card.name]
        names.extend([c.name for c in data_batch.budget_cards])
        return names

    def build_context(self, template: TemplateConfig, data_batch: BudgetContext) -> str:
        """Build validation context with full card details."""
        context = data_batch
        exp_card = context.expensive_card
        budget_cards = context.budget_cards

        budget_info = "\n".join([
            f"  - {c.name}: {_price_str(c)}, EDHREC: {c.edhrec_rank or 'N/A'}, Legalities: {c.legalities}"
            for c in budget_cards
        ])

        return f"""For budget_alternative category ({template.template_id}): verify the following:
{template.validation_rules}

Expensive Card: {exp_card.name}
   Price: {_price_str(exp_card)}
   EDHREC Rank: {exp_card.edhrec_rank or 'N/A'}
   Oracle Text: {(exp_card.text or '')[:300]}...
  Legalities: {exp_card.legalities}

Budget Alternatives:
{budget_info}

Category: {context.category}
Template: {template.template_id}
"""


# Backward compatibility wrapper
class GenerateBudgetAlternativesLegacy:
    """Legacy interface for backward compatibility with old main.py."""

    def __init__(
        self,
        cards_collection: Any,
        save_item: Any,
        models: dict[ModelType, Model],
        validation_pct: int,
        target_count: int = 2000,
        metrics: ValidationMetrics | None = None,
    ) -> None:
        self.cards_collection = cards_collection
        self.save_item = save_item
        self.models = models
        self.validation_pct = validation_pct
        self.target_count = target_count
        self.metrics = metrics

    def generate_budget_alternatives(self) -> None:
        """Legacy method - creates new generator with data_access."""
        from .data_access import MTGDataAccess
        data_access = MTGDataAccess()
        data_access.connect()
        try:
            generator = GenerateBudgetAlternatives(
                data_access=data_access,
                models=self.models,
                validation_pct=self.validation_pct,
                target_count=self.target_count,
                save_item=self.save_item,
                metrics=self.metrics,
            )
            generator.generate()
        finally:
            data_access.close()
