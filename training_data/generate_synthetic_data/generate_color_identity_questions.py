"""Generate Color Identity Questions using BaseGenerator and MTGDataAccess.

Generates Q&A pairs for Commander color identity legality questions across four templates:
1. mono_color - "Can I play [card] in my mono-[color] [commander] deck?"
2. two_color - "Is [card] legal in my [color pair] commander deck?"
3. three_color - "What's the color identity of [card]? Can it go in [3-color commander]?"
4. five_color - "Are there any color identity restrictions in 5-color commanders?"

Uses EDHREC commanders weighted by popularity (num_decks) and MTG card data with color identity.
"""

from __future__ import annotations

import random
from typing import Any, Iterator
from dataclasses import dataclass

from .base_generator import BaseGenerator, TemplateConfig
from .data_access import MTGDataAccess
from .models import Model, ModelType, ValidationMetrics
from .domain_models import CardWithMetadata, CommanderWithTags
from .common import MTG_NOTATION_LEGEND, SYSTEM_MESSAGE, OUTPUT_FORMAT


# Commander Rule 903.4 - Color Identity
RULE_903_4 = """903.4. The Commander variant uses color identity to determine what cards can be in a deck with a certain commander. The color identity of a card is the color or colors of any mana symbols in that card's mana cost or rules text, plus any colors defined by its characteristic-defining abilities (see rule 604.3) or color indicator (see rule 204)."""


# Color identity calculation helper
COLOR_SYMBOL_MAP = {
    "W": "White",
    "U": "Blue",
    "B": "Black",
    "R": "Red",
    "G": "Green",
}

COLOR_PAIR_NAMES = {
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

WEDGE_NAMES = {
    frozenset(["W", "U", "B"]): "Esper",
    frozenset(["U", "B", "R"]): "Grixis",
    frozenset(["B", "R", "G"]): "Jund",
    frozenset(["R", "G", "W"]): "Naya",
    frozenset(["G", "W", "U"]): "Bant",
}

SHARD_NAMES = {
    frozenset(["W", "U", "B"]): "Esper",
    frozenset(["U", "B", "R"]): "Grixis",
    frozenset(["B", "R", "G"]): "Jund",
    frozenset(["R", "G", "W"]): "Naya",
    frozenset(["G", "W", "U"]): "Bant",
}

# Five-color commanders often have special rules
FIVE_COLOR_NOTABLE = [
    "The World Tree",
    "Domain",
    "Converge",
    "Sunburst",
    "Bring to Light",
    "Niv-Mizzet Reborn",
    "Jodah, Archmage Eternal",
    "Kenrith, the Returned King",
    "Golos, Tireless Pilgrim",
    "Morophon, the Boundless",
]


@dataclass(frozen=True)
class ColorIdentityContext:
    """Context for a card + commander pair with color identity analysis."""
    card: CardWithMetadata
    commander: CommanderWithTags
    is_legal: bool
    card_color_identity: list[str]
    commander_color_identity: list[str]
    template_type: str  # "mono_color", "two_color", "three_color", "five_color"
    color_identity_explanation: str


class GenerateColorIdentityQuestions(BaseGenerator[ColorIdentityContext]):
    """Generate color identity legality questions using BaseGenerator."""

    TEMPLATES: list[TemplateConfig] = [
        TemplateConfig(
            template_id="mono_color",
            task_instruction=(
                "Generate 2 Q&A pairs for: \"Can I play [card] in my mono-[color] [commander] deck?\"\n\n"
                "Questions should be natural variations like:\n"
                "- \"Can I play {card_name} in my mono-{color} {commander_name} deck?\"\n"
                "- \"Is {card_name} legal in a mono-{color} Commander deck with {commander_name}?\"\n"
                "- \"Does {card_name} fit in my {commander_name} deck?\"\n\n"
                "Answers MUST:\n"
                "1. State YES or NO clearly at the start\n"
                "2. Explain Commander rule 903.4 (color identity) in plain English\n"
                "3. Check BOTH mana symbols in mana cost AND color indicator/characteristic-defining abilities\n"
                "4. Explain why the card's color identity is or isn't a subset of the commander's\n"
                "5. Mention hybrid mana counts as both colors for color identity\n"
                "6. Be 3-5 sentences with clear reasoning\n"
                "7. Use MTG notation ({W}, {U}, {B}, {R}, {G}, {T}, etc.)"
            ),
            weight=1.0,
            validation_rules=[
                "Answer states YES or NO clearly",
                "Answer explains rule 903.4 / color identity rule",
                "Answer checks mana cost symbols AND color indicator",
                "Answer explains subset relationship (card colors ⊆ commander colors)",
                "Answer mentions hybrid mana counts as both colors",
                "Answer is at least 150 characters",
                "Answer contains no markdown formatting",
            ],
            min_answer_length=150,
        ),
        TemplateConfig(
            template_id="two_color",
            task_instruction=(
                "Generate 2 Q&A pairs for: \"Is [card] legal in my [color pair] commander deck?\"\n\n"
                "Questions should be natural variations like:\n"
                "- \"Is {card_name} legal in my {color_pair_name} Commander deck?\"\n"
                "- \"Can I run {card_name} in a {commander_name} deck?\"\n"
                "- \"What's the color identity of {card_name}? Legal in {color_pair}?\"\n\n"
                "Answers MUST:\n"
                "1. State YES or NO clearly at the start\n"
                "2. Explain BOTH colors in the commander's color identity\n"
                "3. Check hybrid mana symbols - they count as BOTH colors for color identity\n"
                "4. Distinguish between a card's COLOR (mana cost) vs COLOR IDENTITY (mana cost + rules text + color indicator)\n"
                "5. Explain the subset rule: card's color identity must be subset of commander's\n"
                "6. Be 3-5 sentences with clear reasoning\n"
                "7. Use MTG notation and color pair names (Azorius, Dimir, Rakdos, etc.)"
            ),
            weight=1.0,
            validation_rules=[
                "Answer states YES or NO clearly",
                "Answer explains both colors in commander's identity",
                "Answer addresses hybrid mana counting as both colors",
                "Answer distinguishes color vs color identity",
                "Answer explains subset rule (card identity ⊆ commander identity)",
                "Answer is at least 150 characters",
                "Answer contains no markdown formatting",
            ],
            min_answer_length=150,
        ),
        TemplateConfig(
            template_id="three_color",
            task_instruction=(
                "Generate 2 Q&A pairs for: \"What's the color identity of [card]? Can it go in [3-color commander]?\"\n\n"
                "Questions should be natural variations like:\n"
                "- \"What's the color identity of {card_name}? Can it go in {commander_name}?\"\n"
                "- \"Is {card_name} legal in my {wedge_or_shard_name} deck with {commander_name}?\"\n"
                "- \"Can I play {card_name} in a three-color Commander deck?\"\n\n"
                "Answers MUST:\n"
                "1. State YES or NO clearly at the start\n"
                "2. Identify if the commander is a WEDGE (enemy pair + ally) or SHARD (ally trio)\n"
                "3. Explain off-color fetch lands: they have color identity of the colors they CAN fetch, not just their mana cost\n"
                "4. Check ALL mana symbols in mana cost AND rules text AND color indicator\n"
                "5. Explain the subset rule for three colors\n"
                "6. Be 3-5 sentences with clear reasoning\n"
                "7. Use wedge/shard names (Esper, Grixis, Jund, Naya, Bant, Abzan, Jeskai, Sultai, Mardu, Temur)"
            ),
            weight=1.0,
            validation_rules=[
                "Answer states YES or NO clearly",
                "Answer identifies wedge vs shard for 3-color commander",
                "Answer explains off-color fetch land color identity",
                "Answer checks all mana symbols (cost, text, color indicator)",
                "Answer explains subset rule for three colors",
                "Answer is at least 150 characters",
                "Answer contains no markdown formatting",
            ],
            min_answer_length=150,
        ),
        TemplateConfig(
            template_id="five_color",
            task_instruction=(
                "Generate 2 Q&A pairs for: \"Are there any color identity restrictions in 5-color commanders?\"\n\n"
                "Questions should be natural variations like:\n"
                "- \"Are there any color identity restrictions in 5-color commanders?\"\n"
                "- \"Can I play any card in my {commander_name} deck?\"\n"
                "- \"What cards are banned in 5-color Commander?\"\n\n"
                "Answers MUST:\n"
                "1. Explain that 5-color commanders (WUBRG) have NO color identity restrictions - any card with any color identity is legal\n"
                "2. Mention The World Tree and Domain mechanics as examples of 5-color enablers\n"
                "3. Explain that the ONLY restrictions are the Commander banlist and format legality\n"
                "4. Note that cards like 'Bring to Light', 'Converge', 'Sunburst' work optimally in 5-color\n"
                "5. Mention notable 5-color commanders (Niv-Mizzet Reborn, Jodah, Kenrith, Golos, Morophon)\n"
                "6. Clarify that colorless cards are always legal\n"
                "7. Be 3-5 sentences with clear reasoning"
            ),
            weight=1.0,
            validation_rules=[
                "Answer explains 5-color commanders have no color identity restrictions",
                "Answer mentions The World Tree and/or Domain mechanics",
                "Answer mentions Commander banlist as only restriction",
                "Answer mentions 5-color enablers (Converge, Sunburst, Bring to Light)",
                "Answer mentions notable 5-color commanders",
                "Answer clarifies colorless cards are always legal",
                "Answer is at least 150 characters",
                "Answer contains no markdown formatting",
            ],
            min_answer_length=150,
        ),
    ]

    # Commander distribution by color identity size
    COMMANDER_DISTRIBUTION = {
        1: 10,   # mono-color
        2: 15,   # two-color
        3: 10,   # three-color
        5: 5,    # five-color
    }

    def __init__(
        self,
        data_access: MTGDataAccess,
        models: dict[ModelType, Model],
        validation_pct: float,
        target_count: int,
        save_item: callable,
        metrics: ValidationMetrics | None = None,
        generator_name: str | None = None,
        dry_run: bool = False,
        max_regeneration_attempts: int = 3,
        batch_size: int = 1,
        templates_per_item: int = 1,
        enable_extra_validation: bool = True,
    ):
        """Initialize the generator.

        Args:
            data_access: MTGDataAccess instance for querying cards and commanders
            models: Dict with ModelType.GENERATION and ModelType.VALIDATION keys
            validation_pct: Percentage of items to validate (0.0-1.0)
            target_count: Target number of items to generate
            save_item: Callback to save a validated QuestionAnswerEnhanced
            metrics: Optional ValidationMetrics instance
            generator_name: Name for metrics tracking
            dry_run: If True, don't call save_item
            max_regeneration_attempts: Max retries after validation failure
            batch_size: Items per generation batch
            templates_per_item: Number of templates to apply per data item
            enable_extra_validation: Enable detailed verification checklist
        """
        self.data_access = data_access
        self._commanders: list[CommanderWithTags] = []
        self._cards: list[CardWithMetadata] = []
        self._commanders_by_color_count: dict[int, list[CommanderWithTags]] = {}
        self._cards_by_color_identity: dict[frozenset[str], list[CardWithMetadata]] = {}

        super().__init__(
            models=models,
            validation_pct=validation_pct,
            target_count=target_count,
            save_item=save_item,
            metrics=metrics,
            generator_name=generator_name,
            dry_run=dry_run,
            max_regeneration_attempts=max_regeneration_attempts,
            batch_size=batch_size,
            templates_per_item=templates_per_item,
            enable_extra_validation=enable_extra_validation,
        )

    def get_source_category(self) -> str:
        """Return the source category for metrics."""
        return "color_identity"

    def get_data_batches(self) -> Iterator[ColorIdentityContext]:
        """Fetch and yield card + commander pairs for generation.

        Loads commanders weighted by num_decks (popularity) and cards with color identity.
        Creates pairs ensuring variety across color identity sizes.
        """
        # Load data on first call
        if not self._commanders:
            self._load_data()

        # Build weighted commander pool
        commander_pool = self._build_commander_pool()

        # Shuffle for variety
        random.shuffle(commander_pool)

        for commander in commander_pool:
            if self.generated_count >= self.target_count:
                break

            # Find suitable cards for this commander
            suitable_cards = self._find_suitable_cards(commander)
            if not suitable_cards:
                continue

            # Pick a random card
            card = random.choice(suitable_cards)

            # Calculate color identity legality
            card_ci = set(card.color_identity or [])
            commander_ci = set(commander.color_identity or [])
            is_legal = card_ci.issubset(commander_ci)

            # Determine template type based on commander color count
            template_type = self._get_template_type(commander)

            # Build explanation
            explanation = self._build_color_identity_explanation(card, commander, is_legal)

            context = ColorIdentityContext(
                card=card,
                commander=commander,
                is_legal=is_legal,
                card_color_identity=sorted(card_ci),
                commander_color_identity=sorted(commander_ci),
                template_type=template_type,
                color_identity_explanation=explanation,
            )

            yield context

    def _load_data(self) -> None:
        """Load commanders and cards from database."""
        # Load commanders with tags, weighted by num_decks
        self._commanders = self.data_access.get_commanders_enriched(limit=500)

        # Load cards with color identity data
        self._cards = self.data_access.get_cards_enriched(
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
        """Build weighted commander pool based on distribution and popularity."""
        pool = []

        for ci_size, count in self.COMMANDER_DISTRIBUTION.items():
            commanders = self._commanders_by_color_count.get(ci_size, [])
            if not commanders:
                continue

            # Sort by num_decks (popularity) descending
            commanders_sorted = sorted(commanders, key=lambda c: c.num_decks or 0, reverse=True)

            # Take top commanders, weighted by popularity
            # Use weighted random selection based on num_decks
            weights = [c.num_decks or 1 for c in commanders_sorted[:count * 3]]  # 3x pool for variety
            selected = random.choices(
                commanders_sorted[:count * 3],
                weights=weights,
                k=min(count, len(commanders_sorted))
            )
            pool.extend(selected)

        return pool

    def _find_suitable_cards(self, commander: CommanderWithTags) -> list[CardWithMetadata]:
        """Find cards that are interesting for color identity questions with this commander."""
        commander_ci = set(commander.color_identity or [])
        ci_size = len(commander_ci)

        suitable = []

        if ci_size == 5:
            # For 5-color, any card is legal - pick interesting ones
            # Include cards with complex color identities, hybrid, colorless, etc.
            for ci_set, cards in self._cards_by_color_identity.items():
                if len(ci_set) >= 3 or len(ci_set) == 0:  # 3+ colors or colorless
                    suitable.extend(cards[:5])  # Top 5 from each group
        else:
            # For mono/two/three color, find cards that test boundaries
            # 1. Cards that ARE legal (subset)
            for ci_set, cards in self._cards_by_color_identity.items():
                if ci_set.issubset(commander_ci):
                    suitable.extend(cards[:3])

            # 2. Cards that are NOT legal (test the boundary) - off-color cards
            for ci_set, cards in self._cards_by_color_identity.items():
                if not ci_set.issubset(commander_ci) and ci_set:
                    # Only add a few illegal cards to test "no" answers
                    suitable.extend(cards[:2])

            # 3. Colorless cards (always legal)
            colorless = self._cards_by_color_identity.get(frozenset(), [])
            suitable.extend(colorless[:3])

            # 4. Cards with hybrid mana that test understanding
            for card in self._cards:
                if card.mana_cost and "/" in card.mana_cost:
                    card_ci = set(card.color_identity or [])
                    if card_ci.issubset(commander_ci) or (ci_size >= 2 and len(card_ci) <= 2):
                        suitable.append(card)

        # Deduplicate by name
        seen = set()
        unique = []
        for card in suitable:
            if card.name not in seen:
                seen.add(card.name)
                unique.append(card)

        return unique[:50]  # Limit pool size

    def _get_template_type(self, commander: CommanderWithTags) -> str:
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
        else:
            return "mono_color"  # fallback

    def _build_color_identity_explanation(
        self,
        card: CardWithMetadata,
        commander: CommanderWithTags,
        is_legal: bool
    ) -> str:
        """Build detailed explanation of color identity calculation."""
        card_ci = set(card.color_identity or [])
        commander_ci = set(commander.color_identity or [])

        parts = []

        # Card color identity breakdown
        if card_ci:
            ci_names = [COLOR_SYMBOL_MAP.get(c, c) for c in sorted(card_ci)]
            parts.append(f"Card '{card.name}' has color identity: {', '.join(ci_names)}")
        else:
            parts.append(f"Card '{card.name}' is colorless (no color identity)")

        # Commander color identity
        if commander_ci:
            ci_names = [COLOR_SYMBOL_MAP.get(c, c) for c in sorted(commander_ci)]
            parts.append(f"Commander '{commander.name}' has color identity: {', '.join(ci_names)}")
        else:
            parts.append(f"Commander '{commander.name}' is colorless")

        # Legality
        if is_legal:
            parts.append(f"LEGAL: {card_ci} ⊆ {commander_ci} (card's colors are subset of commander's)")
        else:
            extra = card_ci - commander_ci
            extra_names = [COLOR_SYMBOL_MAP.get(c, c) for c in sorted(extra)]
            parts.append(f"ILLEGAL: Card has {', '.join(extra_names)} not in commander's identity")

        # Mana cost analysis
        if card.mana_cost:
            parts.append(f"Mana cost: {card.mana_cost}")
            # Check for hybrid
            if "/" in card.mana_cost:
                parts.append("Contains hybrid mana symbols (count as BOTH colors for color identity)")

        # Color indicator / CDA check
        if card.color_identity and (not card.mana_cost or set(card.color_identity) != set(self._extract_mana_colors(card.mana_cost))):
            parts.append("Color identity includes colors from rules text/color indicator beyond mana cost")

        return " | ".join(parts)

    def _extract_mana_colors(self, mana_cost: str) -> list[str]:
        """Extract color symbols from mana cost."""
        import re
        colors = set()
        symbols = re.findall(r"\{([^}]+)\}", mana_cost)
        for sym in symbols:
            if sym in COLOR_SYMBOL_MAP:
                colors.add(sym)
            elif "/" in sym:
                for part in sym.split("/"):
                    if part in COLOR_SYMBOL_MAP:
                        colors.add(part)
        return sorted(colors)

    def build_prompt(self, template: TemplateConfig, data_batch: ColorIdentityContext) -> str:
        """Build the LLM prompt for a specific template and context."""
        context = data_batch
        card = context.card
        commander = context.commander

        # Format card details
        face = card.primary_face
        card_detail = (
            f"Card: {card.name}\n"
            f"Mana Cost: {face.mana_cost or card.mana_cost or 'N/A'}\n"
            f"Type: {face.type_line or card.type or 'N/A'}\n"
            f"Oracle Text: {face.oracle_text or card.text or 'N/A'}\n"
            f"Color Identity: {', '.join(context.card_color_identity) if context.card_color_identity else 'Colorless'}\n"
        )

        # Format commander details
        commander_detail = (
            f"Commander: {commander.name}\n"
            f"Color Identity: {', '.join(context.commander_color_identity) if context.commander_color_identity else 'Colorless'}\n"
            f"EDHREC Decks: {commander.num_decks:,}\n"
            f"Tags: {', '.join(commander.tags[:5]) if commander.tags else 'none'}\n"
        )

        # Legality result
        legality = "LEGAL" if context.is_legal else "ILLEGAL"

        # Color identity explanation
        explanation = context.color_identity_explanation

        # Rule 903.4 reference
        rule_ref = f"\nCommander Rule 903.4:\n{RULE_903_4}\n"

        # Template-specific additions
        template_specific = self._get_template_specific_context(context)

        prompt = f"""{SYSTEM_MESSAGE}

{MTG_NOTATION_LEGEND}

{OUTPUT_FORMAT}

{template.task_instruction}

{card_detail}

{commander_detail}

Can this card be played: {legality}

{explanation}

{rule_ref}

{template_specific}

Generate 2 Q&A pairs in JSON format. The answer MUST be a single string, not an array.
"""
        return prompt

    def _get_template_specific_context(self, context: ColorIdentityContext) -> str:
        """Add template-specific context for the prompt."""

        if context.template_type == "mono_color":
            color = context.commander_color_identity[0] if context.commander_color_identity else "C"
            color_name = COLOR_SYMBOL_MAP.get(color, color)
            return (
                f"\nMONO-COLOR CONTEXT:\n"
                f"- Commander is mono-{color_name.lower()} ({color})\n"
                f"- Only {color_name} and colorless cards are legal\n"
                f"- Hybrid mana with {color} counts as {color_name} for color identity\n"
                f"- Check for color indicator or CDA adding other colors\n"
            )
        elif context.template_type == "two_color":
            colors = context.commander_color_identity
            if len(colors) == 2:
                pair_name = COLOR_PAIR_NAMES.get(frozenset(colors), f"{colors[0]}/{colors[1]}")
                color_names = [COLOR_SYMBOL_MAP.get(c, c) for c in colors]
                return (
                    f"\nTWO-COLOR CONTEXT:\n"
                    f"- Commander is {pair_name} ({colors[0]}/{colors[1]})\n"
                    f"- Legal colors: {', '.join(color_names)} and colorless\n"
                    f"- Hybrid mana counts as BOTH colors for color identity\n"
                    f"- Color (mana cost) ≠ Color Identity (mana cost + rules text + color indicator)\n"
                )
        elif context.template_type == "three_color":
            colors = context.commander_color_identity
            if len(colors) == 3:
                color_set = frozenset(colors)
                wedge_shard = WEDGE_NAMES.get(color_set) or SHARD_NAMES.get(color_set, "Three-color")
                color_names = [COLOR_SYMBOL_MAP.get(c, c) for c in colors]
                return (
                    f"\nTHREE-COLOR CONTEXT:\n"
                    f"- Commander is {wedge_shard} ({'/'.join(colors)})\n"
                    f"- Legal colors: {', '.join(color_names)} and colorless\n"
                    f"- Off-color fetch lands have color identity of colors they CAN fetch\n"
                    f"- Check ALL mana symbols in cost, text, AND color indicator\n"
                )
        elif context.template_type == "five_color":
            return (
                "\nFIVE-COLOR CONTEXT:\n"
                "- Commander is 5-color (WUBRG) - NO color identity restrictions\n"
                "- ANY card with ANY color identity is legal (subject to banlist)\n"
                "- The World Tree, Domain, Converge, Sunburst, Bring to Light are 5-color enablers\n"
                "- Notable 5-color commanders: Niv-Mizzet Reborn, Jodah, Kenrith, Golos, Morophon\n"
                "- Colorless cards are always legal\n"
                "- Only restrictions: Commander banlist + format legality\n"
            )

        return ""

    def build_context(self, template: TemplateConfig, data_batch: ColorIdentityContext) -> str:
        """Build validation context for the generated Q&A."""
        context = data_batch
        return (
            f"Category: {self.get_source_category()}\n"
            f"Template: {template.template_id}\n"
            f"Card: {context.card.name}\n"
            f"Card Color Identity: {', '.join(context.card_color_identity) if context.card_color_identity else 'Colorless'}\n"
            f"Card Mana Cost: {context.card.mana_cost or 'N/A'}\n"
            f"Card Oracle Text: {context.card.text or 'N/A'[:200]}\n"
            f"Commander: {context.commander.name}\n"
            f"Commander Color Identity: {', '.join(context.commander_color_identity) if context.commander_color_identity else 'Colorless'}\n"
            f"Commander EDHREC Decks: {context.commander.num_decks:,}\n"
            f"Legality: {'LEGAL' if context.is_legal else 'ILLEGAL'}\n"
            f"Color Identity Explanation: {context.color_identity_explanation}\n"
            f"Rule 903.4: {RULE_903_4[:200]}..."
        )

    def get_source_data(self, data_batch: ColorIdentityContext) -> list[Any]:
        """Extract source data references for the generated document."""
        return [
            data_batch.card.name,
            data_batch.commander.name,
            f"card_ci:{','.join(data_batch.card_color_identity)}",
            f"cmd_ci:{','.join(data_batch.commander_color_identity)}",
            f"legal:{data_batch.is_legal}",
            f"template:{data_batch.template_type}",
        ]


# Backward compatibility wrapper for old main.py interface
class GenerateColorIdentityQuestionsLegacy:
    """Legacy wrapper for backward compatibility with main.py."""

    def __init__(
        self,
        cards_collection,
        commanders_collection,
        save_item: callable,
        models: dict[ModelType, Model],
        validation_pct: float,
        target_count: int = 2000,
        metrics: ValidationMetrics | None = None,
    ):
        self.cards_collection = cards_collection
        self.commanders_collection = commanders_collection
        self.save_item = save_item
        self.models = models
        self.validation_pct = validation_pct
        self.target_count = target_count
        self.metrics = metrics

    def generate_color_identity_questions(self) -> None:
        """Legacy method - delegates to new BaseGenerator implementation."""
        data_access = MTGDataAccess()
        data_access.connect()

        try:
            generator = GenerateColorIdentityQuestions(
                data_access=data_access,
                models=self.models,
                validation_pct=self.validation_pct,
                target_count=self.target_count,
                save_item=self.save_item,
                metrics=self.metrics,
                generator_name="GenerateColorIdentityQuestions",
            )
            generator.generate()
        finally:
            data_access.close()