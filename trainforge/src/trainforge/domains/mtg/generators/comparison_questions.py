"""Generate card comparison Q&A pairs — compare two cards across various dimensions.

Ports the old CLI comparison generator into the TrainForge BaseGenerator
framework using enriched MTGDataAccess.  Pairs cards by similar mana value,
type, or color and generates Q&A comparing them.
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
# COMPARISON CATEGORIES — effect categories with query filters
# =============================================================================

COMPARISON_CATEGORIES: list[dict[str, Any]] = [
    {
        "effect": "Fast Mana",
        "filters": {
            "oracleText": {"$regex": "add.*mana|add {C}", "$options": "i"},
            "types": ["Artifact"],
        },
    },
    {
        "effect": "Green Ramp",
        "filters": {
            "oracleText": {"$regex": "search.*land", "$options": "i"},
            "colors": ["G"],
        },
    },
    {
        "effect": "Removal",
        "filters": {"oracleText": {"$regex": "destroy|exile", "$options": "i"}},
    },
    {
        "effect": "Card Draw",
        "filters": {"oracleText": {"$regex": "draw.*card", "$options": "i"}},
    },
    {
        "effect": "Counterspells",
        "filters": {
            "oracleText": {"$regex": "counter target", "$options": "i"},
            "types": ["Instant"],
        },
    },
    {
        "effect": "Board Wipes",
        "filters": {
            "oracleText": {"$regex": "destroy all|exile all", "$options": "i"},
        },
    },
    {
        "effect": "Tutors",
        "filters": {"oracleText": {"$regex": "search.*library", "$options": "i"}},
    },
    {
        "effect": "Reanimation",
        "filters": {
            "oracleText": {
                "$regex": "return.*creature.*graveyard",
                "$options": "i",
            }
        },
    },
    {
        "effect": "Protection",
        "filters": {
            "oracleText": {"$regex": "indestructible|hexproof|ward", "$options": "i"},
        },
    },
    {
        "effect": "Token Generation",
        "filters": {"oracleText": {"$regex": "create.*token", "$options": "i"}},
    },
]


# =============================================================================
# EXAMPLE COMMANDERS & SYNERGY THEMES
# =============================================================================

EXAMPLE_COMMANDERS: list[dict[str, Any]] = [
    {"name": "Atraxa, Praetors' Voice", "color_identity": ["W", "U", "B", "G"], "theme": "proliferate/superfriends"},
    {"name": "Krenko, Mob Boss", "color_identity": ["R"], "theme": "goblin tribal/token swarm"},
    {"name": "Meren of Clan Nel Toth", "color_identity": ["B", "G"], "theme": "reanimation"},
    {"name": "Korvold, Fae-Cursed King", "color_identity": ["B", "R", "G"], "theme": "sacrifice/aristocrats"},
    {"name": "The Gitrog Monster", "color_identity": ["B", "G"], "theme": "lands matter/graveyard"},
    {"name": "Niv-Mizzet, Parun", "color_identity": ["U", "R"], "theme": "spells matter/card draw"},
    {"name": "Edgar Markov", "color_identity": ["W", "B", "R"], "theme": "vampire tribal/tokens"},
    {"name": "Urza, Lord Protector", "color_identity": ["U"], "theme": "artifacts/constructs"},
    {"name": "Teshar, Ancestor's Apostle", "color_identity": ["W"], "theme": "historic/artifacts recursion"},
    {"name": "Tymna the Weaver + Thrasios, Triton Hero", "color_identity": ["W", "U", "B", "G"], "theme": "value/control"},
]

SYNERGY_THEMES: list[str] = [
    "artifacts matter", "graveyard recursion", "token doubling",
    "enter-the-battlefield triggers", "sacrifice outlets", "landfall",
    "spellslinger", "enchantress", "aristocrats", "superfriends/proliferate",
    "equipment/voltron", "wheel effects", "mana doubling",
    "counter manipulation", "tribal synergies",
]


# =============================================================================
# GENERATOR
# =============================================================================


class GenerateComparisonQuestions(BaseGenerator[tuple[CardWithMetadata, CardWithMetadata]]):
    """Generate card comparison Q&A pairs from enriched card data.

    Each data batch is a ``(card1, card2)`` tuple of two cards that
    serve a similar role but differ in cost, color, or rank.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._card_pairs: list[tuple[CardWithMetadata, CardWithMetadata]] = []

    def get_data_batches(self) -> list[tuple[CardWithMetadata, CardWithMetadata]]:
        """Build and return card pairs for comparison generation.

        Fetches enriched cards per comparison category, then applies
        three pairing strategies:
        1. Adjacent EDHREC rank (similar popularity)
        2. Same CMC, different color identity
        3. Same effect category, different colors

        Returns:
            List of (card1, card2) tuples.
        """
        if self._card_pairs:
            return self._card_pairs

        ds = self.domain.get_data_source()

        for category in COMPARISON_CATEGORIES:
            effect_name = category["effect"]
            filters = category["filters"]
            cards = ds.get_cards_enriched(filters=filters, limit=20)

            if len(cards) < 2:
                logger.debug("Fewer than 2 cards for %s, skipping", effect_name)
                continue

            cards_with_rank = [c for c in cards if c.edhrec_rank is not None]
            if len(cards_with_rank) < 2:
                cards_with_rank = cards

            pairs = self._create_pairs(cards_with_rank)
            self._card_pairs.extend(pairs)

        random.shuffle(self._card_pairs)
        logger.info("Built %d comparison card pairs", len(self._card_pairs))
        return self._card_pairs

    def get_source_category(self) -> str:
        return "comparison"

    def build_prompt(
        self,
        template: TemplateConfig,
        data_batch: tuple[CardWithMetadata, CardWithMetadata],
    ) -> str:
        """Build the LLM prompt comparing two cards.

        Args:
            template: TemplateConfig with task_instruction.
            data_batch: (card1, card2) tuple.

        Returns:
            Full prompt string.
        """
        card1, card2 = data_batch

        # Build context block with rich card details
        detail1 = card1.to_prompt_detail(include_prices=True, include_rulings=True)
        detail2 = card2.to_prompt_detail(include_prices=True, include_rulings=True)

        # Pick a random commander or theme for context variety
        commander = random.choice(EXAMPLE_COMMANDERS)
        theme = random.choice(SYNERGY_THEMES)

        notation = self.domain.notation_legend

        return (
            f"{notation}\n\n"
            f"<cards>\n"
            f"CARD 1:\n"
            f"{detail1}\n\n"
            f"CARD 2:\n"
            f"{detail2}\n"
            f"</cards>\n\n"
            f"<comparison_context>\n"
            f"Effect category: Both cards serve a similar role.\n"
            f"Example commander: {commander['name']} ({', '.join(commander['color_identity'])})\n"
            f"Example theme: {theme}\n"
            f"</comparison_context>\n\n"
            f"<task>\n"
            f"{template.task_instruction}\n\n"
            f"Cards to compare:\n"
            f"1. {card1.name} — CMC: {card1.cmc}, EDHREC Rank: {card1.edhrec_rank or 'N/A'}\n"
            f"2. {card2.name} — CMC: {card2.cmc}, EDHREC Rank: {card2.edhrec_rank or 'N/A'}\n\n"
            f"Generate questions comparing:\n"
            f"- Power level and EDHREC rank differences\n"
            f"- Mana efficiency (CMC vs effect)\n"
            f"- Suitability for a {commander['name']} deck\n"
            f"- Synergy with {theme}\n"
            f"\n"
            f"Output JSON:\n"
            f'[\n'
            f'  {{"question": "...", "answer": "..."}},\n'
            f'  {{"question": "...", "answer": "..."}}\n'
            f"]\n"
            f"\n"
            f"Answers should be 3-5 sentences grounded in the cards' actual text and stats.\n"
            f"Output ONLY valid JSON.\n"
            f"</task>"
        )

    def build_context(
        self, data_batch: tuple[CardWithMetadata, CardWithMetadata]
    ) -> str | None:
        """Build metadata context for the generated Q&A."""
        card1, card2 = data_batch
        return (
            f"Category: {self.get_source_category()}\n"
            f"Card 1: {card1.name} (EDHREC Rank: {card1.edhrec_rank or 'N/A'}, CMC: {card1.cmc})\n"
            f"Card 2: {card2.name} (EDHREC Rank: {card2.edhrec_rank or 'N/A'}, CMC: {card2.cmc})\n"
            f"Color IDs: {card1.color_identity or 'C'} vs {card2.color_identity or 'C'}"
        )

    # ------------------------------------------------------------------
    # Pair-building helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _create_pairs(
        cards: list[CardWithMetadata],
    ) -> list[tuple[CardWithMetadata, CardWithMetadata]]:
        """Create card pairs using three strategies."""
        pairs: list[tuple[CardWithMetadata, CardWithMetadata]] = []
        seen: set[tuple[str, str]] = set()

        def _add_pair(c1: CardWithMetadata, c2: CardWithMetadata) -> None:
            key = tuple(sorted([c1.uuid or c1.name, c2.uuid or c2.name]))
            if key not in seen:
                seen.add(key)
                pairs.append((c1, c2))

        if len(cards) < 2:
            return pairs

        # Strategy 1: Adjacent EDHREC rank
        sorted_by_rank = sorted(cards, key=lambda c: c.edhrec_rank or 999999)
        for i in range(len(sorted_by_rank) - 1):
            _add_pair(sorted_by_rank[i], sorted_by_rank[i + 1])

        # Strategy 2: Same CMC, different color identity
        by_cmc: dict[float, list[CardWithMetadata]] = {}
        for card in cards:
            by_cmc.setdefault(card.cmc, []).append(card)
        for cmc_val, cmc_cards in by_cmc.items():
            if len(cmc_cards) >= 2:
                for i in range(len(cmc_cards) - 1):
                    for j in range(i + 1, min(i + 3, len(cmc_cards))):
                        if set(cmc_cards[i].color_identity) != set(cmc_cards[j].color_identity):
                            _add_pair(cmc_cards[i], cmc_cards[j])

        # Strategy 3: Different colors within the same category
        by_color_id: dict[str, list[CardWithMetadata]] = {}
        for card in cards:
            key = "".join(sorted(card.color_identity)) or "C"
            by_color_id.setdefault(key, []).append(card)
        color_ids = list(by_color_id.keys())
        for i in range(len(color_ids)):
            for j in range(i + 1, len(color_ids)):
                if by_color_id[color_ids[i]] and by_color_id[color_ids[j]]:
                    _add_pair(
                        by_color_id[color_ids[i]][0],
                        by_color_id[color_ids[j]][0],
                    )

        return pairs[:10]  # Limit pairs per category
