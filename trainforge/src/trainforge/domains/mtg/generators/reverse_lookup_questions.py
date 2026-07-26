"""Generate reverse-lookup Q&A pairs — "What card does [effect]?" questions.

Ports the old CLI reverse-lookup generator into the TrainForge
BaseGenerator framework.  Defines search patterns describing card
effects and uses ``search_cards_text()`` to find matching cards.
"""

from __future__ import annotations

import logging
import random
from typing import Any

from trainforge.domain import TemplateConfig
from trainforge.generator import BaseGenerator
from trainforge.domains.mtg.models import CardWithMetadata

logger = logging.getLogger(__name__)


# =============================================================================
# SEARCH PATTERNS — map effect descriptions to oracle-text regexes
# =============================================================================

LOOKUP_PATTERNS: list[dict[str, str]] = [
    # -- Card advantage & draw --
    {
        "effect": "draw cards when creatures die",
        "regex": "whenever.*creature.*dies.*draw|draw.*whenever.*creature.*dies",
    },
    {
        "effect": "draw cards equal to a creature's power",
        "regex": "draw.*card.*equal.*power|draw.*x.*cards.*x.*power",
    },
    {
        "effect": "discard and draw new cards (wheel effect)",
        "regex": "discard.*hand.*draw.*cards|discard.*draw.*equal.*cards",
    },
    # -- Burn & damage --
    {
        "effect": "deal damage to any target",
        "regex": "deal.*damage.*any target|lightning bolt|shock|pinger",
    },
    {
        "effect": "deal damage to each opponent",
        "regex": "deal.*damage.*each opponent|deal.*damage.*each.*enemy",
    },
    {
        "effect": "deal damage to each creature",
        "regex": "deal.*damage.*each creature|deal.*damage.*all creatures",
    },
    # -- Board control --
    {
        "effect": "destroy target nonland permanent",
        "regex": "destroy target.*nonland permanent|beast within|generous gift",
    },
    {
        "effect": "exile target creature",
        "regex": "exile target creature|exile.*creature.*permanent|path to exile|swords to plowshares",
    },
    {
        "effect": "return target permanent to its owner's hand",
        "regex": "return target.*to.*owner.*hand|unsummon|cyclonic rift",
    },
    # -- Tutor & fetch --
    {
        "effect": "search your library for a creature card and put it into your hand",
        "regex": "search.*library.*creature.*hand|worldly tutor|green sun",
    },
    {
        "effect": "search your library for an artifact card",
        "regex": "search.*library.*artifact|whir of invention|fabricate|tinker",
    },
    {
        "effect": "search your library for a basic land and put it onto the battlefield",
        "regex": "search.*library.*basic.*land.*battlefield|rampant growth|cultivate|kodama",
    },
    # -- Graveyard --
    {
        "effect": "return a creature from your graveyard to the battlefield",
        "regex": "return.*creature.*from.*graveyard.*battlefield|reanimate|animate dead|resurrection",
    },
    {
        "effect": "put cards from your graveyard back into your library",
        "regex": "put.*cards.*from.*graveyard.*library|regrowth|eternal witness|noxious revival",
    },
    {
        "effect": "exile all cards from all graveyards",
        "regex": "exile all cards from.*graveyard|rest in peace|leyline of the void|relic of progenitus",
    },
    # -- Protection --
    {
        "effect": "give a creature hexproof or indestructible until end of turn",
        "regex": "creature.*hexproof.*indestructible.*turn|hexproof.*indestructible until|shelter|blossoming defense",
    },
    {
        "effect": "counter target spell",
        "regex": "counter target spell|counterspell|mana drain|force of will",
    },
    {
        "effect": "phase out a permanent",
        "regex": "phase out|phasing|teferi.*protection|slip out",
    },
    # -- Mana & ramp --
    {
        "effect": "add mana of any color",
        "regex": "add.*mana of any color|add.*one mana of any color|farseek|birds of paradise|fellwar",
    },
    {
        "effect": "untap all lands you control",
        "regex": "untap.*all lands.*control|turnabout|seedborn muse|wilderness reclamation",
    },
    # -- Token generation --
    {
        "effect": "create X 1/1 creature tokens",
        "regex": "create.*x.*1/1.*creature.*token|create.*that many.*1/1|finale of glory|martial coup",
    },
    {
        "effect": "create a copy of target creature",
        "regex": "create.*copy.*target creature|copy.*creature|clone|spark double|phyrexian metamorph",
    },
]


# =============================================================================
# GENERATOR
# =============================================================================


class GenerateReverseLookupQuestions(BaseGenerator[dict[str, Any]]):
    """Generate reverse-lookup Q&A pairs ("What card does [effect]?").

    Each data batch is a dict with keys ``card`` (CardWithMetadata),
    ``effect`` (str — description of the effect), and ``regex`` (the
    oracle-text pattern that was used to find the card).
    """

    def get_data_batches(self) -> list[dict[str, Any]]:
        """Fetch matching cards for each lookup pattern.

        For each pattern in LOOKUP_PATTERNS, calls
        ``search_cards_text()`` and yields a batch dict per card.

        Returns:
            List of dicts with keys: card, effect, regex.
        """
        ds = self.domain.get_data_source()
        batches: list[dict[str, Any]] = []

        for pattern in LOOKUP_PATTERNS:
            effect = pattern["effect"]
            regex = pattern["regex"]
            cards = ds.search_cards_text(regex=regex, limit=5)
            for card in cards:
                batches.append({
                    "card": card,
                    "effect": effect,
                    "regex": regex,
                })

        random.shuffle(batches)
        logger.info("Built %d reverse-lookup batches", len(batches))
        return batches

    def get_source_category(self) -> str:
        return "reverse_lookup"

    def build_prompt(
        self, template: TemplateConfig, data_batch: dict[str, Any]
    ) -> str:
        """Build the LLM prompt for a reverse-lookup Q&A.

        Args:
            template: TemplateConfig with task_instruction.
            data_batch: Dict with ``card``, ``effect``, and ``regex``.

        Returns:
            Full prompt string.
        """
        card: CardWithMetadata = data_batch["card"]
        effect: str = data_batch["effect"]

        detail = card.to_prompt_detail(include_prices=True)
        notation = self.domain.notation_legend

        return (
            f"{notation}\n\n"
            f"<task>\n"
            f"{template.task_instruction}\n\n"
            f"Player is looking for: \"{effect}\"\n\n"
            f"Matching card:\n"
            f"{detail}\n\n"
            f"Generate questions where a player describes this effect without naming the card.\n"
            f'Example: "What card lets me {effect}?"\n\n'
            f"The answer should identify {card.name} and explain how its oracle text "
            f"matches the described effect.\n\n"
            f"Output JSON:\n"
            f'[\n'
            f'  {{"question": "...", "answer": "..."}},\n'
            f'  {{"question": "...", "answer": "..."}}\n'
            f"]\n"
            f"\n"
            f"Answers should be 2-4 sentences grounded in the card's actual text.\n"
            f"Output ONLY valid JSON.\n"
            f"</task>"
        )

    def build_context(self, data_batch: dict[str, Any]) -> str | None:
        """Build metadata context for the generated Q&A."""
        card: CardWithMetadata = data_batch["card"]
        effect: str = data_batch["effect"]
        return (
            f"Category: {self.get_source_category()}\n"
            f"Effect: {effect}\n"
            f"Card: {card.name}\n"
            f"EDHREC Rank: {card.edhrec_rank or 'N/A'}\n"
            f"Color Identity: {', '.join(card.color_identity) if card.color_identity else 'Colorless'}"
        )
