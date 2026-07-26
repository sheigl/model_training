"""Generate meta knowledge Q&A pairs — ported from generate_meta_knowledge.py."""

from __future__ import annotations

import logging

from trainforge.domain import TemplateConfig
from trainforge.generator import BaseGenerator

logger = logging.getLogger(__name__)


class MetaKnowledgeGenerator(BaseGenerator[str]):
    """Generate meta and power level Q&A covering cEDH, pod dynamics, and format knowledge."""

    # All 9 topics preserved from the original CLI generator — order and content must not change
    TOPICS: list[tuple[str, str]] = [
        (
            "cEDH viability and what separates competitive from casual",
            "cEDH decks win on turns 3-5, use fast mana (Mana Crypt, Chrome Mox), run tutors, counterspells, and win through established combo lines. Power level 9-10.",
        ),
        (
            "Commander power level scale (1-10)",
            "The 1-10 power level scale: 1-3 precon/kitchen table, 4-6 focused casual, 7-8 optimized synergy, 9 high power, 10 cEDH. How to self-assess your deck.",
        ),
        (
            "pod communication and power level matching",
            "How to communicate your deck's power level to your pod, why mismatched power levels ruin games, asking before you sit down.",
        ),
        (
            "fast mana and why it's powerful",
            "Sol Ring, Mana Crypt, Chrome Mox — why fast mana is so format-warping, what separates high power from casual, the role of 0-cost acceleration.",
        ),
        (
            "tutors and deck consistency",
            "How tutors increase consistency, why tutors are stronger in Commander than other formats, the tradeoff between consistency and fun.",
        ),
        (
            "common cEDH win conditions and strategies",
            "Flash Hulk, Thassa's Oracle + Demonic Consultation, Underworld Breach loops, Dockside Extortionist combos — recognizing and playing against them.",
        ),
        (
            "evaluating commanders for power level",
            "What makes a commander powerful: built-in card advantage, low mana cost, combo enabler, resilience. Why some commanders are format staples.",
        ),
        (
            "meta reads and adapting your deck",
            "Reading your local meta, building hate for common strategies, adjusting your deck for the environment you play in.",
        ),
        (
            "banned list philosophy in Commander",
            "Why certain cards are banned in Commander (Flash, Primeval Titan, Braids), how the rules committee evaluates bans, why some powerful cards aren't banned.",
        ),
    ]

    def get_data_batches(self) -> list[str]:
        """Return list of topic names."""
        return [name for name, _ in self.TOPICS]

    def get_source_category(self) -> str:
        return "meta_knowledge"

    def build_prompt(self, template: TemplateConfig, data_batch: str) -> str:
        """Build the LLM prompt for a meta knowledge topic.

        Args:
            template: TemplateConfig with task_instruction (may contain {topic}, {context}, {description}).
            data_batch: Topic name string.

        Returns:
            Prompt with notation legend and <task> wrapping.
        """
        topic = data_batch
        context = self._get_description(topic)

        task_instruction = template.task_instruction.format(
            topic=topic,
            context=context,
            description=context,
        )
        notation = self.domain.notation_legend

        return f"{notation}\n\n<task>\n{task_instruction}\n</task>"

    def build_context(self, data_batch: str) -> str | None:
        """Build optional context metadata for the generated Q&A.

        Args:
            data_batch: Topic name string.

        Returns:
            Formatted metadata string or None.
        """
        topic = data_batch
        context = self._get_description(topic)
        return f"Category: {self.get_source_category()}\nTopic: {topic}\nContext: {context}"

    def _get_description(self, name: str) -> str:
        """Look up the description for a topic by name."""
        for n, d in self.TOPICS:
            if n == name:
                return d
        return ""
