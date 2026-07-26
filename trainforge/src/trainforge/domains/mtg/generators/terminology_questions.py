"""Terminology Q&A generator — MTG-specific terms, slang, and jargon."""

from __future__ import annotations

import logging
from trainforge.domain import TemplateConfig
from trainforge.generator import BaseGenerator

logger = logging.getLogger(__name__)


class GenerateTerminologyQuestions(BaseGenerator[str]):
    """Generate MTG terminology Q&A covering slang, jargon, and format-specific terms.

    Category: terminology
    Data batches: 20 MTG terminology terms (term name strings)
    Templates: what_does_this_mean (from templates.yaml)
    """

    # All 20 terminology terms preserved from the original generator —
    # order and content must not change.
    TERMINOLOGY: list[tuple[str, str]] = [
        (
            "CEDH",
            "CEDH stands for Competitive EDH (Elder Dragon Highlander/Commander). "
            "It's Commander played at the highest power level with optimized decks, "
            "fast combos, and competitive mindset.",
        ),
        (
            "pillow fort",
            "A 'pillow fort' is a defensive strategy that uses enchantments and effects "
            "to discourage opponents from attacking you, like Ghostly Prison, Propaganda, "
            "and Sphere of Safety.",
        ),
        (
            "MLD",
            "MLD stands for Mass Land Destruction - effects that destroy all or most "
            "lands, like Armageddon. It's generally frowned upon in casual Commander.",
        ),
        (
            "staple",
            "A 'staple' is a card that's commonly played across many decks because it's "
            "powerful and generically useful, like Sol Ring, Arcane Signet, "
            "or Swords to Plowshares.",
        ),
        (
            "salt",
            "In Commander, 'salt' refers to cards or strategies that make opponents "
            "unhappy or frustrated, often because they're seen as unfun or oppressive.",
        ),
        (
            "aristocrats",
            "Aristocrats is a sacrifice-based strategy that generates value from creatures "
            "dying, using cards like Blood Artist, Zulaport Cutthroat, and sacrifice outlets.",
        ),
        (
            "voltron",
            "Voltron is a strategy focused on making one creature (usually your commander) "
            "extremely large and powerful with equipment, auras, and buffs to win through "
            "commander damage.",
        ),
        (
            "group hug",
            "Group hug is a political strategy that gives benefits to all players "
            "(card draw, mana, etc.) to make friends and avoid being targeted, "
            "sometimes hiding a secret win condition.",
        ),
        (
            "stax",
            "Stax (from 'The Stacks') is a prison strategy that uses tax effects and "
            "restrictions to slow down opponents while you build towards a win.",
        ),
        (
            "GY",
            "GY is shorthand for 'graveyard' - the zone where cards go when they die, "
            "are discarded, or milled.",
        ),
        (
            "ETB",
            "ETB stands for 'enters the battlefield' - refers to triggered abilities "
            "that happen when a permanent comes into play.",
        ),
        (
            "LTB",
            "LTB stands for 'leaves the battlefield' - refers to triggered abilities "
            "when a permanent is removed from play.",
        ),
        (
            "ramp",
            "Ramp refers to cards and strategies that accelerate your mana production, "
            "letting you cast bigger spells earlier than usual.",
        ),
        (
            "tutor",
            "A tutor is any card that lets you search your library for specific cards, "
            "named after the card Demonic Tutor.",
        ),
        (
            "wheel",
            "A wheel effect forces all players to discard their hand and draw a new hand "
            "of seven cards, named after Wheel of Fortune.",
        ),
        (
            "pod",
            "Pod refers to sacrifice-and-search effects like Birthing Pod, letting you "
            "sacrifice a creature to find one that costs more.",
        ),
        (
            "blink",
            "Blink effects temporarily exile a creature and return it immediately, "
            "retriggering ETB abilities. Named after the card Momentary Blink.",
        ),
        (
            "flicker",
            "Flicker is synonymous with blink - temporarily exiling and returning "
            "permanents to retrigger ETB effects.",
        ),
        (
            "bounce",
            "Bounce means returning permanents from the battlefield to hand, "
            "like with Cyclonic Rift or Unsummon.",
        ),
        (
            "hatedraft",
            "Hatedraft means drafting a card not for your deck, but to prevent opponents "
            "from getting it. Not relevant in Commander but part of MTG terminology.",
        ),
    ]

    def get_data_batches(self) -> list[str]:
        """Return flat list of all terminology term names."""
        return [term for term, _ in self.TERMINOLOGY]

    def build_prompt(self, template: TemplateConfig, data_batch: str) -> str:
        """Build the LLM prompt for a terminology term.

        Fills template instruction with term and definition, then wraps with
        the MTG notation legend and <task> tags.
        """
        term = data_batch
        definition = self._lookup_definition(term)

        task_instruction = template.task_instruction.format(
            term=term,
            definition=definition,
        )

        notation = self.domain.notation_legend

        return f"{notation}\n\n<task>\n{task_instruction}\n</task>"

    def get_source_category(self) -> str:
        return "terminology"

    def build_context(self, data_batch: str) -> str | None:
        """Build validation context with category, term, and definition."""
        term = data_batch
        definition = self._lookup_definition(term)
        return (
            f"Category: {self.get_source_category()}\n"
            f"Term: {term}\n"
            f"Definition: {definition}"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _lookup_definition(self, term: str) -> str:
        """Return the definition for a given term name."""
        for tname, tdef in self.TERMINOLOGY:
            if tname == term:
                return tdef
        logger.warning("Unknown terminology term: %s", term)
        return ""
