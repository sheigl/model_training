"""Generate quick deckbuilding guideline Q&A pairs from EDHREC card data.

Category: guidelines
Templates: how_many_lands (from templates.yaml)
"""

from __future__ import annotations

import logging
from typing import Any

from trainforge.domain import TemplateConfig
from trainforge.generator import BaseGenerator

logger = logging.getLogger(__name__)


class QuickGuidelinesGenerator(BaseGenerator[dict[str, Any]]):
    """Generate quick deckbuilding guideline Q&A pairs from EDHREC card data.

    Each data batch is a dict with card metadata (type, text, rank, role).
    The prompt includes card details and derived role information to help
    the LLM generate contextually relevant deckbuilding advice.
    """

    def get_data_batches(self) -> list[dict[str, Any]]:
        """Fetch cards with EDHREC data and build guideline contexts.

        For each card, derives a deckbuilding role based on oracle text
        (e.g., removal, ramp, card_draw, tutor, counterspell).

        Returns:
            List of dicts with card metadata and derived role information.
        """
        ds = self.domain.get_data_source()

        cards = ds.get_cards_enriched(
            filters={"edhrecRank": {"$ne": None}},
            limit=100,
        )

        batches: list[dict[str, Any]] = []
        for card in cards:
            card_type = (card.type or "").lower()
            text_lower = (card.text or "").lower()

            # Determine card role based on oracle text patterns
            role = "utility"
            if "destroy" in text_lower or "exile" in text_lower:
                role = "removal"
            elif "draw" in text_lower:
                role = "card_draw"
            elif "search" in text_lower or "tutor" in text_lower:
                role = "tutor"
            elif "counter" in text_lower and "target" in text_lower:
                role = "counterspell"
            elif ("add" in text_lower and "mana" in text_lower) or any(
                kw in text_lower for kw in ["ramp", "land you control"]
            ):
                role = "ramp"

            batches.append({
                "card_name": card.name,
                "card_type": card.type or "Unknown",
                "oracle_text": card.text or "",
                "mana_cost": card.mana_cost or "N/A",
                "cmc": card.cmc,
                "color_identity": card.color_identity or [],
                "edhrec_rank": card.edhrec_rank,
                "edhrec_salt": card.edhrec_salt,
                "edhrec_tags": card.edhrec_tags or [],
                "rarity": card.rarity or "Unknown",
                "is_creature": "creature" in card_type,
                "is_land": "land" in card_type,
                "is_enchantment": "enchantment" in card_type,
                "is_artifact": "artifact" in card_type,
                "is_planeswalker": "planeswalker" in card_type,
                "is_instant_sorcery": any(
                    t in card_type for t in ["instant", "sorcery"]
                ),
                "role": role,
                "prices_usd": card.prices.usd if card.prices else None,
            })

        logger.info("Built %d guideline data batches from card data", len(batches))
        return batches

    def get_source_category(self) -> str:
        return "guidelines"

    def build_prompt(self, template: TemplateConfig, data_batch: dict[str, Any]) -> str:
        """Build the LLM prompt for a deckbuilding guidelines template.

        Args:
            template: TemplateConfig with task_instruction (may contain
                      {card_name}, {card_type}, {card_details}, {role}
                      placeholders).
            data_batch: Dict with card metadata and derived role.

        Returns:
            Complete prompt string with notation legend and <task> wrapping.
        """
        notation = self.domain.notation_legend

        # Build card description
        card_lines: list[str] = [
            f"Card: {data_batch['card_name']}",
            f"Type: {data_batch['card_type']}",
            f"Mana Cost: {data_batch['mana_cost']} (CMC: {data_batch['cmc']})",
            f"Color Identity: {', '.join(data_batch['color_identity']) if data_batch['color_identity'] else 'Colorless'}",
            f"Oracle Text: {data_batch['oracle_text'][:300]}",
            f"Rarity: {data_batch['rarity']}",
        ]
        if data_batch["edhrec_rank"] is not None:
            card_lines.append(f"EDHREC Rank: #{data_batch['edhrec_rank']}")
        if data_batch["edhrec_salt"] is not None:
            card_lines.append(f"S Salt Score: {data_batch['edhrec_salt']:.2f}")
        if data_batch["edhrec_tags"]:
            card_lines.append(
                f"Tags: {', '.join(data_batch['edhrec_tags'][:5])}"
            )
        if data_batch["prices_usd"] is not None:
            card_lines.append(f"Price: ${data_batch['prices_usd']:.2f}")

        card_str = "\n".join(card_lines)
        role = data_batch["role"]

        task = template.task_instruction.format(
            card_name=data_batch["card_name"],
            card_type=data_batch["card_type"],
            card_details=card_str,
            role=role,
        )

        # Build category tags
        category_parts: list[str] = []
        if data_batch["is_creature"]:
            category_parts.append("Creature")
        if data_batch["is_land"]:
            category_parts.append("Land")
        if data_batch["is_enchantment"]:
            category_parts.append("Enchantment")
        if data_batch["is_artifact"]:
            category_parts.append("Artifact")
        if data_batch["is_planeswalker"]:
            category_parts.append("Planeswalker")
        if data_batch["is_instant_sorcery"]:
            category_parts.append("Instant/Sorcery")

        return (
            f"{notation}\n\n"
            f"<task>\n"
            f"{task}\n\n"
            f"Card details:\n"
            f"{card_str}\n\n"
            f"Card role: {role}\n"
            f"Card categories: {' '.join(category_parts)}\n"
            f"</task>"
        )

    def build_context(self, data_batch: dict[str, Any]) -> str | None:
        """Build metadata context for the generated Q&A."""
        return (
            f"Category: {self.get_source_category()}\n"
            f"Card: {data_batch['card_name']}\n"
            f"Type: {data_batch['card_type']}\n"
            f"CMC: {data_batch['cmc']}\n"
            f"Role: {data_batch['role']}\n"
            f"EDHREC Rank: {data_batch['edhrec_rank'] or 'N/A'}\n"
            f"Price: ${data_batch['prices_usd'] or 'N/A'}"
        )
