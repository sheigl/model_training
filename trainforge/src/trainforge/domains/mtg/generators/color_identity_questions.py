"""Generate color identity legality Q&A pairs for Commander format.

Category: color_identity
Templates: what_color_does_this (from templates.yaml)
"""

from __future__ import annotations

import logging
import random
import re
from typing import Any

from trainforge.domain import TemplateConfig
from trainforge.generator import BaseGenerator
from trainforge.domains.mtg.models import CardWithMetadata, CommanderWithTags

logger = logging.getLogger(__name__)

# =============================================================================
# COLOR IDENTITY CONSTANTS
# =============================================================================

COLOR_SYMBOL_MAP: dict[str, str] = {
    "W": "White",
    "U": "Blue",
    "B": "Black",
    "R": "Red",
    "G": "Green",
}

COLOR_PAIR_NAMES: dict[frozenset[str], str] = {
    frozenset(["W", "U"]): "Azorius",
    frozenset(["U", "B"]): "Dimir",
    frozenset(["B", "R"]): "Rakdos",
    frozenset(["R", "G"]): "Gruul",
    frozenset(["G", "W"]): "Selesnya",
    frozenset(["W", "B"]): "Orzhov",
    frozenset(["U", "R"]): "Izzet",
    frozenset(["B", "G"]): "Golgari",
    frozenset(["R", "W"]): "Boros",
    frozenset(["G", "U"]): "Simic",
}

THREE_COLOR_NAMES: dict[frozenset[str], str] = {
    frozenset(["W", "U", "B"]): "Esper",
    frozenset(["U", "B", "R"]): "Grixis",
    frozenset(["B", "R", "G"]): "Jund",
    frozenset(["R", "G", "W"]): "Naya",
    frozenset(["G", "W", "U"]): "Bant",
    frozenset(["W", "B", "G"]): "Abzan",
    frozenset(["U", "R", "W"]): "Jeskai",
    frozenset(["B", "G", "U"]): "Sultai",
    frozenset(["R", "W", "B"]): "Mardu",
    frozenset(["G", "U", "R"]): "Temur",
}

# Commander Rule 903.4 — Color Identity
RULE_903_4 = (
    "903.4. The Commander variant uses color identity to determine what cards can be in a deck "
    "with a certain commander. The color identity of a card is the color or colors of any mana "
    "symbols in that card's mana cost or rules text, plus any colors defined by its "
    "characteristic-defining abilities (see rule 604.3) or color indicator (see rule 204)."
)

# Weighted distribution of commanders by color identity size
COMMANDER_DISTRIBUTION: dict[int, int] = {
    1: 10,  # mono-color
    2: 15,  # two-color
    3: 10,  # three-color
    5: 5,   # five-color
}


class ColorIdentityQuestionsGenerator(BaseGenerator[dict[str, Any]]):
    """Generate color identity legality Q&A pairs for Commander format.

    Fetches commanders weighted by popularity and cards with color identity data.
    Creates pairs that test understanding of Commander Rule 903.4 including:
    - Mono-color restrictions
    - Two-color hybrid mana rules
    - Three-color wedge/shard identity
    - Five-color freedom (no restrictions)
    """

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._commanders: list[CommanderWithTags] = []
        self._cards: list[CardWithMetadata] = []
        self._commanders_by_color_count: dict[int, list[CommanderWithTags]] = {}
        self._cards_by_color_identity: dict[frozenset[str], list[CardWithMetadata]] = {}

    # =========================================================================
    # BASE GENERATOR INTERFACE
    # =========================================================================

    def get_data_batches(self) -> list[dict[str, Any]]:
        """Fetch commanders and cards, build card + commander context dicts.

        Returns:
            List of dicts with keys: card, commander, is_legal,
            card_color_identity, commander_color_identity,
            template_type, color_identity_explanation.
        """
        self._load_data()

        commander_pool = self._build_commander_pool()
        random.shuffle(commander_pool)

        batches: list[dict[str, Any]] = []
        for commander in commander_pool:
            suitable_cards = self._find_suitable_cards(commander)
            if not suitable_cards:
                continue

            card = random.choice(suitable_cards)

            card_ci = set(card.color_identity or [])
            commander_ci = set(commander.color_identity or [])
            is_legal = card_ci.issubset(commander_ci)
            template_type = self._get_template_type(commander)
            explanation = self._build_color_identity_explanation(
                card, commander, is_legal
            )

            batches.append({
                "card": card,
                "commander": commander,
                "is_legal": is_legal,
                "card_color_identity": sorted(card_ci),
                "commander_color_identity": sorted(commander_ci),
                "template_type": template_type,
                "color_identity_explanation": explanation,
            })

        return batches

    def get_source_category(self) -> str:
        return "color_identity"

    def build_prompt(self, template: TemplateConfig, data_batch: dict[str, Any]) -> str:
        """Build the LLM prompt for a color identity question.

        Args:
            template: TemplateConfig with task_instruction (may contain
                      {card_name}, {commander_name}, {card_detail},
                      {commander_detail}, {color_identity_explanation}
                      placeholders).
            data_batch: Dict with card, commander, and legality context.

        Returns:
            Complete prompt string with notation legend and <task> wrapping.
        """
        card: CardWithMetadata = data_batch["card"]
        commander: CommanderWithTags = data_batch["commander"]
        is_legal: bool = data_batch["is_legal"]
        card_ci: list[str] = data_batch["card_color_identity"]
        commander_ci: list[str] = data_batch["commander_color_identity"]
        template_type: str = data_batch["template_type"]
        explanation: str = data_batch["color_identity_explanation"]

        face = card.primary_face
        card_detail = (
            f"Card: {card.name}\n"
            f"Mana Cost: {face.mana_cost or card.mana_cost or 'N/A'}\n"
            f"Type: {face.type_line or card.type or 'N/A'}\n"
            f"Oracle Text: {face.oracle_text or card.text or 'N/A'}\n"
            f"Color Identity: {', '.join(card_ci) if card_ci else 'Colorless'}\n"
        )

        commander_detail = (
            f"Commander: {commander.name}\n"
            f"Color Identity: {', '.join(commander_ci) if commander_ci else 'Colorless'}\n"
            f"EDHREC Decks: {commander.num_decks:,}\n"
            f"Tags: {', '.join(commander.tags[:5]) if commander.tags else 'none'}\n"
        )

        legality = "LEGAL" if is_legal else "ILLEGAL"
        template_context = self._get_template_specific_context(
            template_type, commander_ci
        )

        notation = self.domain.notation_legend

        task = template.task_instruction.format(
            card_name=card.name,
            commander_name=commander.name,
            card_detail=card_detail,
            commander_detail=commander_detail,
            color_identity_explanation=explanation,
        )

        return (
            f"{notation}\n\n"
            f"<task>\n"
            f"{task}\n\n"
            f"{card_detail}\n"
            f"{commander_detail}\n"
            f"Can this card be played: {legality}\n\n"
            f"{explanation}\n\n"
            f"Commander Rule 903.4:\n"
            f"{RULE_903_4}\n\n"
            f"{template_context}\n"
            f"</task>"
        )

    def build_context(self, data_batch: dict[str, Any]) -> str | None:
        """Build metadata context for the generated Q&A."""
        card: CardWithMetadata = data_batch["card"]
        commander: CommanderWithTags = data_batch["commander"]
        is_legal: bool = data_batch["is_legal"]
        card_ci: list[str] = data_batch["card_color_identity"]
        commander_ci: list[str] = data_batch["commander_color_identity"]
        explanation: str = data_batch["color_identity_explanation"]

        return (
            f"Category: {self.get_source_category()}\n"
            f"Card: {card.name}\n"
            f"Card Color Identity: {', '.join(card_ci) if card_ci else 'Colorless'}\n"
            f"Card Mana Cost: {card.mana_cost or 'N/A'}\n"
            f"Card Oracle Text: {(card.text or '')[:200]}\n"
            f"Commander: {commander.name}\n"
            f"Commander Color Identity: {', '.join(commander_ci) if commander_ci else 'Colorless'}\n"
            f"Commander EDHREC Decks: {commander.num_decks:,}\n"
            f"Legality: {'LEGAL' if is_legal else 'ILLEGAL'}\n"
            f"Color Identity Explanation: {explanation}\n"
            f"Rule 903.4: {RULE_903_4[:200]}..."
        )

    # =========================================================================
    # DATA LOADING & SELECTION
    # =========================================================================

    def _load_data(self) -> None:
        """Load commanders and cards from database on first access."""
        if self._commanders:
            return

        ds = self.domain.get_data_source()

        self._commanders = ds.get_commanders_enriched(limit=500)
        self._cards = ds.get_cards_enriched(
            filters={"colorIdentity": {"$exists": True, "$ne": []}},
            limit=2000,
            lite=True,
        )

        # Group commanders by color identity size
        self._commanders_by_color_count = {1: [], 2: [], 3: [], 5: []}
        for cmd in self._commanders:
            ci_size = len(cmd.color_identity or [])
            if ci_size in self._commanders_by_color_count:
                self._commanders_by_color_count[ci_size].append(cmd)

        # Group cards by color identity for efficient lookup
        self._cards_by_color_identity = {}
        for card in self._cards:
            ci = frozenset(card.color_identity or [])
            if ci not in self._cards_by_color_identity:
                self._cards_by_color_identity[ci] = []
            self._cards_by_color_identity[ci].append(card)

    def _build_commander_pool(self) -> list[CommanderWithTags]:
        """Build weighted commander pool based on distribution and popularity.

        Uses weighted random selection where commanders with more decks
        (higher num_decks) are more likely to be chosen.
        """
        pool: list[CommanderWithTags] = []
        for ci_size, count in COMMANDER_DISTRIBUTION.items():
            commanders = self._commanders_by_color_count.get(ci_size, [])
            if not commanders:
                continue

            commanders_sorted = sorted(
                commanders, key=lambda c: c.num_decks or 0, reverse=True
            )
            weights = [c.num_decks or 1 for c in commanders_sorted[: count * 3]]
            selected = random.choices(
                commanders_sorted[: count * 3],
                weights=weights,
                k=min(count, len(commanders_sorted)),
            )
            pool.extend(selected)
        return pool

    def _find_suitable_cards(
        self, commander: CommanderWithTags
    ) -> list[CardWithMetadata]:
        """Find cards interesting for color identity questions with this commander.

        Includes:
        - Cards that ARE legal (subset of commander's identity)
        - Cards that are NOT legal (off-color, test boundary understanding)
        - Colorless cards (always legal)
        - Cards with hybrid mana symbols
        """
        commander_ci = set(commander.color_identity or [])
        ci_size = len(commander_ci)
        suitable: list[CardWithMetadata] = []

        if ci_size == 5:
            # 5-color: any card is legal — pick complex ones
            for ci_set, cards in self._cards_by_color_identity.items():
                if len(ci_set) >= 3 or len(ci_set) == 0:
                    suitable.extend(cards[:5])
        else:
            # Legal cards (subset)
            for ci_set, cards in self._cards_by_color_identity.items():
                if ci_set.issubset(commander_ci):
                    suitable.extend(cards[:3])

            # Illegal cards (off-color boundary)
            for ci_set, cards in self._cards_by_color_identity.items():
                if not ci_set.issubset(commander_ci) and ci_set:
                    suitable.extend(cards[:2])

            # Colorless cards (always legal)
            colorless = self._cards_by_color_identity.get(frozenset(), [])
            suitable.extend(colorless[:3])

            # Cards with hybrid mana
            for card in self._cards:
                if card.mana_cost and "/" in card.mana_cost:
                    card_set = set(card.color_identity or [])
                    if card_set.issubset(commander_ci) or (
                        ci_size >= 2 and len(card_set) <= 2
                    ):
                        suitable.append(card)

        # Deduplicate by name
        seen: set[str] = set()
        unique: list[CardWithMetadata] = []
        for card in suitable:
            if card.name not in seen:
                seen.add(card.name)
                unique.append(card)

        return unique[:50]

    @staticmethod
    def _get_template_type(commander: CommanderWithTags) -> str:
        """Determine template type based on commander color identity size."""
        ci_size = len(commander.color_identity or [])
        if ci_size == 1:
            return "mono_color"
        elif ci_size == 2:
            return "two_color"
        elif ci_size == 3:
            return "three_color"
        elif ci_size == 5:
            return "five_color"
        return "mono_color"

    # =========================================================================
    # PROMPT BUILDING HELPERS
    # =========================================================================

    def _build_color_identity_explanation(
        self,
        card: CardWithMetadata,
        commander: CommanderWithTags,
        is_legal: bool,
    ) -> str:
        """Build detailed explanation of color identity calculation."""
        card_ci = set(card.color_identity or [])
        commander_ci = set(commander.color_identity or [])

        parts: list[str] = []

        if card_ci:
            ci_names = [COLOR_SYMBOL_MAP.get(c, c) for c in sorted(card_ci)]
            parts.append(f"Card '{card.name}' has color identity: {', '.join(ci_names)}")
        else:
            parts.append(f"Card '{card.name}' is colorless (no color identity)")

        if commander_ci:
            ci_names = [COLOR_SYMBOL_MAP.get(c, c) for c in sorted(commander_ci)]
            parts.append(
                f"Commander '{commander.name}' has color identity: {', '.join(ci_names)}"
            )
        else:
            parts.append(f"Commander '{commander.name}' is colorless")

        if is_legal:
            parts.append(
                f"LEGAL: {card_ci} ⊆ {commander_ci} "
                f"(card's colors are subset of commander's)"
            )
        else:
            extra = card_ci - commander_ci
            extra_names = [COLOR_SYMBOL_MAP.get(c, c) for c in sorted(extra)]
            parts.append(
                f"ILLEGAL: Card has {', '.join(extra_names)} "
                f"not in commander's identity"
            )

        if card.mana_cost:
            parts.append(f"Mana cost: {card.mana_cost}")
            if "/" in card.mana_cost:
                parts.append(
                    "Contains hybrid mana symbols "
                    "(count as BOTH colors for color identity)"
                )

        # Color indicator / CDA check
        mana_colors = self._extract_mana_colors(card.mana_cost or "")
        if card.color_identity and set(card.color_identity) != set(mana_colors):
            parts.append(
                "Color identity includes colors from rules text/color indicator "
                "beyond mana cost"
            )

        return " | ".join(parts)

    @staticmethod
    def _extract_mana_colors(mana_cost: str) -> list[str]:
        """Extract color symbols from a mana cost string."""
        colors: set[str] = set()
        symbols = re.findall(r"\{([^}]+)\}", mana_cost)
        for sym in symbols:
            if sym in COLOR_SYMBOL_MAP:
                colors.add(sym)
            elif "/" in sym:
                for part in sym.split("/"):
                    if part in COLOR_SYMBOL_MAP:
                        colors.add(part)
        return sorted(colors)

    def _get_template_specific_context(
        self,
        template_type: str,
        commander_ci: list[str],
    ) -> str:
        """Add template-specific context for mono/two/three/five-color prompts."""
        if template_type == "mono_color" and commander_ci:
            color = commander_ci[0]
            color_name = COLOR_SYMBOL_MAP.get(color, color)
            return (
                f"\nMONO-COLOR CONTEXT:\n"
                f"- Commander is mono-{color_name.lower()} ({color})\n"
                f"- Only {color_name} and colorless cards are legal\n"
                f"- Hybrid mana with {color} counts as {color_name} "
                f"for color identity\n"
            )

        if template_type == "two_color" and len(commander_ci) == 2:
            pair_name = COLOR_PAIR_NAMES.get(
                frozenset(commander_ci),
                f"{commander_ci[0]}/{commander_ci[1]}",
            )
            color_names = [COLOR_SYMBOL_MAP.get(c, c) for c in commander_ci]
            return (
                f"\nTWO-COLOR CONTEXT:\n"
                f"- Commander is {pair_name} "
                f"({commander_ci[0]}/{commander_ci[1]})\n"
                f"- Legal colors: {', '.join(color_names)} and colorless\n"
                f"- Hybrid mana counts as BOTH colors for color identity\n"
                f"- Color (mana cost) ≠ Color Identity "
                f"(mana cost + rules text + color indicator)\n"
            )

        if template_type == "three_color" and len(commander_ci) == 3:
            color_set = frozenset(commander_ci)
            wedge_shard = THREE_COLOR_NAMES.get(color_set, "Three-color")
            color_names = [COLOR_SYMBOL_MAP.get(c, c) for c in commander_ci]
            return (
                f"\nTHREE-COLOR CONTEXT:\n"
                f"- Commander is {wedge_shard} "
                f"({'/'.join(commander_ci)})\n"
                f"- Legal colors: {', '.join(color_names)} and colorless\n"
                f"- Off-color fetch lands have color identity "
                f"of colors they CAN fetch\n"
                f"- Check ALL mana symbols in cost, text, "
                f"AND color indicator\n"
            )

        if template_type == "five_color":
            return (
                "\nFIVE-COLOR CONTEXT:\n"
                "- Commander is 5-color (WUBRG) — "
                "NO color identity restrictions\n"
                "- ANY card with ANY color identity is legal "
                "(subject to banlist)\n"
                "- The World Tree, Domain, Converge, Sunburst, "
                "Bring to Light are 5-color enablers\n"
                "- Notable 5-color commanders: Niv-Mizzet Reborn, "
                "Jodah, Kenrith, Golos, Morophon\n"
                "- Colorless cards are always legal\n"
                "- Only restrictions: Commander banlist + format legality\n"
            )

        return ""
