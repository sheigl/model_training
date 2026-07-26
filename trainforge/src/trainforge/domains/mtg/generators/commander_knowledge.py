"""Commander knowledge Q&A generator — EDH/Commander format rules and conventions."""

from __future__ import annotations

import logging
from trainforge.domain import TemplateConfig
from trainforge.generator import BaseGenerator

logger = logging.getLogger(__name__)


class GenerateCommanderKnowledge(BaseGenerator[str]):
    """Generate Commander rules Q&A covering deck construction, tax, damage, and format rules.

    Category: commander_knowledge
    Data batches: 8 Commander sub-topics (topic name strings)
    Templates: edh_format_rules (from templates.yaml)
    """

    # Commander sub-topics broken from the original monolithic topic.
    # Covers all concepts from the original: singleton, command zone, tax,
    # damage, color identity, multiplayer, partner, companion.
    COMMANDER_SUBTOPICS: list[tuple[str, str]] = [
        (
            "deck construction rules",
            "100-card singleton, exactly 100 cards including commander, no sideboard, "
            "commander determines color identity, basics only from outside game.",
        ),
        (
            "commander tax",
            "Each time commander is cast from command zone, costs {2} more. "
            "Tax is cumulative. Applies to all spell-based commanders.",
        ),
        (
            "commander damage",
            "21 combat damage from a single commander to a player loses that game. "
            "Commander must be commanded by the player who dealt it. "
            "Resets if commander changes zones.",
        ),
        (
            "command zone",
            "Commander starts in command zone. Goes to command zone from any zone "
            "(owner's choice for graveyard/exile). Not cast from library, hand, or battlefield.",
        ),
        (
            "color identity restrictions",
            "Cards in deck must only use mana symbols in commander's color identity. "
            "Hybrid, Phyrexian, color indicators all count. Basic lands only from outside.",
        ),
        (
            "multiplayer rules",
            "Typically 4 players. Last player standing wins. Political deals, archenemy "
            "dynamics, kingmaking considerations. Turn order matters for threat assessment.",
        ),
        (
            "partner and background commanders",
            "Partner allows 2 commanders if both have 'Partner'. Background enchantment "
            "commanders pair with a creature that has 'Choose a Background'. "
            "Both count for color identity.",
        ),
        (
            "companion and wish effects",
            "Companion restrictions apply from outside the game. Wish effects can only "
            "get cards from outside in casual. Commander's Handbook / Rule 903.9 governs this.",
        ),
    ]

    def get_data_batches(self) -> list[str]:
        """Return flat list of all Commander sub-topic names."""
        return [topic for topic, _ in self.COMMANDER_SUBTOPICS]

    def build_prompt(self, template: TemplateConfig, data_batch: str) -> str:
        """Build the LLM prompt for a Commander knowledge sub-topic.

        Fills template instruction with topic and context, then wraps with
        the MTG notation legend and <task> tags.
        """
        topic = data_batch
        context = self._lookup_context(topic)

        task_instruction = template.task_instruction.format(
            topic=topic,
            context=context,
        )

        notation = self.domain.notation_legend

        return f"{notation}\n\n<task>\n{task_instruction}\n</task>"

    def get_source_category(self) -> str:
        return "commander_knowledge"

    def build_context(self, data_batch: str) -> str | None:
        """Build validation context with category, topic, and description."""
        topic = data_batch
        context = self._lookup_context(topic)
        return (
            f"Category: {self.get_source_category()}\n"
            f"Topic: {topic}\n"
            f"Context: {context}"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _lookup_context(self, topic: str) -> str:
        """Return the context description for a given sub-topic name."""
        for tname, ctx in self.COMMANDER_SUBTOPICS:
            if tname == topic:
                return ctx
        logger.warning("Unknown Commander sub-topic: %s", topic)
        return ""
