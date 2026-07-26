"""Deckbuilding theory Q&A generator — ratios, evaluation, and construction principles."""

from __future__ import annotations

import logging
from trainforge.domain import TemplateConfig
from trainforge.generator import BaseGenerator

logger = logging.getLogger(__name__)


class GenerateDeckbuildingTheory(BaseGenerator[str]):
    """Generate deckbuilding theory Q&A covering ratios, evaluation, and construction principles.

    Category: deckbuilding_theory
    Data batches: 12 deckbuilding topics (topic name strings)
    Templates: deck_design_principle (from templates.yaml)
    """

    # All topics preserved from the original generator —
    # order and content must not change.
    TOPICS: list[tuple[str, str]] = [
        (
            "card evaluation and slot justification",
            "How to determine if a card belongs in your deck, evaluating cards "
            "on rate, role, and redundancy.",
        ),
        (
            "card advantage vs card selection",
            "The difference between drawing more cards (Rhystic Study) vs filtering "
            "cards (Ponder). When each matters.",
        ),
        (
            "mana curve and tempo",
            "How to build a mana curve, what tempo means, why you want to spend "
            "mana efficiently each turn.",
        ),
        (
            "redundancy and consistency",
            "Why you run multiple effects that do similar things, how to determine "
            "the right amount of redundancy.",
        ),
        (
            "synergy vs goodstuff",
            "The tradeoff between running powerful generic cards vs cards that "
            "specifically support your strategy.",
        ),
        (
            "win conditions and closing games",
            "How to identify your win conditions, ensure they're reachable, and have "
            "enough redundancy to close games.",
        ),
        (
            "deck tuning and iteration",
            "How to identify what's wrong with a deck after testing, what to cut, "
            "what to add, how to iterate.",
        ),
        (
            "threat density and role assignment",
            "Assigning cards roles (threat, answer, engine, accelerant) and ensuring "
            "the right density of each.",
        ),
        (
            "mana base construction",
            "How to build a mana base, dual lands vs basics, color ratios, "
            "when to run utility lands.",
        ),
        (
            "protection and resilience",
            "How to protect your key pieces, recover from board wipes, maintain "
            "card advantage after setbacks.",
        ),
        (
            "interaction and removal philosophy",
            "When to hold up interaction vs advance your game plan, reactive vs "
            "proactive playstyles.",
        ),
        (
            "tribal deck construction",
            "Special considerations for tribal decks: lord effects, creature density, "
            "tribal synergies, non-creature support.",
        ),
    ]

    def get_data_batches(self) -> list[str]:
        """Return flat list of all deckbuilding topic names."""
        return [topic for topic, _ in self.TOPICS]

    def build_prompt(self, template: TemplateConfig, data_batch: str) -> str:
        """Build the LLM prompt for a deckbuilding theory topic.

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
        return "deckbuilding_theory"

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
        """Return the context description for a given topic name."""
        for tname, ctx in self.TOPICS:
            if tname == topic:
                return ctx
        logger.warning("Unknown deckbuilding topic: %s", topic)
        return ""
