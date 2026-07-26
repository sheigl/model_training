"""Generate card search query Q&A pairs — find cards by effect or property.

Ports the 20 search patterns and 5 template styles from the old CLI
into the TrainForge BaseGenerator framework using enriched MTGDataAccess.
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
# SEARCH PATTERNS — 20 effect categories for card discovery
# =============================================================================

SEARCH_PATTERNS: list[dict[str, Any]] = [
    {
        "name": "Green Ramp",
        "filters": {"text_regex": "search.*land", "colors": ["G"]},
    },
    {
        "name": "Zombie Tokens",
        "filters": {"text_regex": "zombie.*token"},
    },
    {
        "name": "Treasure Tokens",
        "filters": {"text_regex": "treasure"},
    },
    {
        "name": "White Removal",
        "filters": {"text_regex": "exile|destroy", "colors": ["W"]},
    },
    {
        "name": "Blue Card Draw",
        "filters": {"text_regex": "draw.*card", "colors": ["U"]},
    },
    {
        "name": "ETB Effects",
        "filters": {"text_regex": "enters the battlefield"},
    },
    {
        "name": "Black Removal",
        "filters": {"text_regex": "destroy.*creature", "colors": ["B"]},
    },
    {
        "name": "Red Burn",
        "filters": {"text_regex": "deals.*damage", "colors": ["R"]},
    },
    {
        "name": "Counterspells",
        "filters": {"text_regex": "counter target", "colors": ["U"]},
    },
    {
        "name": "Board Wipes",
        "filters": {"text_regex": "destroy all|exile all"},
    },
    {
        "name": "Tutors",
        "filters": {"text_regex": "search.*library"},
    },
    {
        "name": "Reanimation",
        "filters": {"text_regex": "return.*creature.*graveyard|graveyard.*battlefield"},
    },
    {
        "name": "Protection",
        "filters": {"text_regex": "protection from|hexproof|indestructible|ward"},
    },
    {
        "name": "Sacrifice Outlets",
        "filters": {"text_regex": "sacrifice.*creature|sacrifice.*permanent"},
    },
    {
        "name": "Artifact Ramp",
        "filters": {"text_regex": "add.*mana|tap.*add", "colors": []},
    },
    {
        "name": "Graveyard Hate",
        "filters": {"text_regex": "exile.*graveyard|graveyard.*exile"},
    },
    {
        "name": "Politics/Group Hug",
        "filters": {"text_regex": "each player|all players|each opponent"},
    },
    {
        "name": "Landfall",
        "filters": {"text_regex": "landfall|whenever.*land.*enters"},
    },
    {
        "name": "Proliferate",
        "filters": {"text_regex": "proliferate"},
    },
    {
        "name": "Blink/Flicker",
        "filters": {"text_regex": "exile.*return|blink|flicker"},
    },
]


# =============================================================================
# COMMANDER POOL for commander-specific advice
# =============================================================================

COMMON_COMMANDERS: list[dict[str, Any]] = [
    {"name": "Atraxa, Praetors' Voice", "colors": ["W", "U", "B", "G"]},
    {"name": "Edgar Markov", "colors": ["W", "B", "R"]},
    {"name": "The Ur-Dragon", "colors": ["W", "U", "B", "R", "G"]},
    {"name": "Krenko, Mob Boss", "colors": ["R"]},
    {"name": "Meren of Clan Nel Toth", "colors": ["B", "G"]},
    {"name": "Korvold, Fae-Cursed King", "colors": ["B", "R", "G"]},
    {"name": "Tatyova, Benthic Druid", "colors": ["G", "U"]},
    {"name": "Lathril, Blade of the Elves", "colors": ["B", "G"]},
    {"name": "Miirym, Sentinel Wyrm", "colors": ["R", "G", "U"]},
    {"name": "Prosper, Tome-Bound", "colors": ["B", "R"]},
    {"name": "Sissay, Weatherlight Captain", "colors": ["W", "U", "B", "R", "G"]},
    {"name": "Tymna the Weaver", "colors": ["W", "B"]},
    {"name": "Kinnan, Bonder Prodigy", "colors": ["G", "U"]},
    {"name": "Rograkh, Son of Rohgahh", "colors": ["R"]},
    {"name": "Tivit, Seller of Secrets", "colors": ["W", "U", "B"]},
]


# =============================================================================
# TAG — helper to attach metadata to a card for prompt/context
# =============================================================================

_SEARCH_PATTERN_ATTR = "_search_pattern_name"


def _attach_search_pattern(card: CardWithMetadata, pattern_name: str) -> CardWithMetadata:
    """Attach the search pattern name to a card (used in build_prompt/context)."""
    object.__setattr__(card, _SEARCH_PATTERN_ATTR, pattern_name)
    return card


def _get_search_pattern(card: CardWithMetadata) -> str:
    """Retrieve attached search pattern name."""
    return getattr(card, _SEARCH_PATTERN_ATTR, "Unknown")


# =============================================================================
# GENERATOR
# =============================================================================


class GenerateCardSearchQueries(BaseGenerator[CardWithMetadata]):
    """Generate card search query Q&A pairs via enriched card data.

    Each data batch is a single CardWithMetadata tagged with the search
    pattern name.  The prompt asks the LLM to explain why that card is
    a good fit for the given effect/theme.
    """

    def get_data_batches(self) -> list[CardWithMetadata]:
        """Fetch enriched cards for each search pattern.

        Returns:
            A flat list of CardWithMetadata, each tagged with its
            search pattern name via a private attribute.
        """
        ds = self.domain.get_data_source()
        batches: list[CardWithMetadata] = []

        for pattern in SEARCH_PATTERNS:
            filters = self._build_filters(pattern["filters"])
            cards = ds.get_cards_enriched(filters=filters, limit=10)
            for card in cards:
                _attach_search_pattern(card, pattern["name"])
            batches.extend(cards)

        return batches

    def get_source_category(self) -> str:
        return "card_search"

    def build_prompt(
        self, template: TemplateConfig, data_batch: CardWithMetadata
    ) -> str:
        """Build the LLM prompt for one card + search pattern.

        Args:
            template: TemplateConfig with task_instruction.
            data_batch: A CardWithMetadata tagged with its search pattern.

        Returns:
            Full prompt string.
        """
        card = data_batch
        effect_name = _get_search_pattern(card)

        detail = card.to_prompt_detail(include_prices=True)
        notation = self.domain.notation_legend

        # Randomly pick a commander for variety (used generically)
        commander = random.choice(COMMON_COMMANDERS)
        commander_colors = ", ".join(commander["colors"])

        return (
            f"{notation}\n\n"
            f"<task>\n"
            f"{template.task_instruction}\n\n"
            f"Search effect/theme: {effect_name}\n"
            f"Card: {card.name}\n\n"
            f"Card details:\n"
            f"{detail}\n\n"
            f"Example commander context: {commander['name']} ({commander_colors})\n"
            f"\n"
            f"Generate questions about:\n"
            f"- What makes {card.name} a good choice for {effect_name}\n"
            f"- How it fits into a Commander deck built around {effect_name}\n"
            f"- Its strengths and weaknesses compared to alternatives\n"
            f"\n"
            f"Output JSON:\n"
            f'[\n'
            f'  {{"question": "...", "answer": "..."}},\n'
            f'  {{"question": "...", "answer": "..."}}\n'
            f"]\n"
            f"\n"
            f"Answers should be 3-5 sentences grounded in the card's actual text and stats.\n"
            f"Output ONLY valid JSON.\n"
            f"</task>"
        )

    def build_context(self, data_batch: CardWithMetadata) -> str | None:
        """Build metadata context for the generated Q&A."""
        card = data_batch
        effect_name = _get_search_pattern(card)
        return (
            f"Category: {self.get_source_category()}\n"
            f"Card: {card.name}\n"
            f"Search Pattern: {effect_name}\n"
            f"Type: {card.type or 'N/A'}\n"
            f"EDHREC Rank: {card.edhrec_rank or 'N/A'}\n"
            f"Color Identity: {', '.join(card.color_identity) if card.color_identity else 'Colorless'}"
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_filters(pattern_filters: dict[str, Any]) -> dict[str, Any]:
        """Convert pattern filters to MongoDB query filters."""
        filters: dict[str, Any] = {}

        if "text_regex" in pattern_filters:
            filters["oracleText"] = {
                "$regex": pattern_filters["text_regex"],
                "$options": "i",
            }

        if "colors" in pattern_filters and pattern_filters["colors"]:
            filters["colorIdentity"] = {"$all": pattern_filters["colors"]}

        return filters
