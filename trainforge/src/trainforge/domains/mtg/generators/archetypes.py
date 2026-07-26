"""Generate archetype strategy Q&A pairs — ported from generate_archetypes.py."""

from __future__ import annotations

import logging

from trainforge.domain import TemplateConfig
from trainforge.generator import BaseGenerator

logger = logging.getLogger(__name__)


class ArchetypesGenerator(BaseGenerator[str]):
    """Generate deck archetype and strategy Q&A covering playstyles and strategic concepts."""

    # All 10 archetypes preserved from the original CLI generator — order and content must not change
    ARCHETYPES: list[tuple[str, str]] = [
        (
            "Aggro",
            "A strategy focused on dealing quick damage with low-cost creatures.",
        ),
        (
            "Control",
            "A strategy that counters threats and wins through card advantage.",
        ),
        (
            "Combo",
            "A strategy that assembles specific card combinations to win instantly.",
        ),
        ("Midrange", "A strategy that plays efficient threats and disrupts opponents."),
        ("Stax", "A control strategy using resource denial and lock pieces."),
        (
            "Voltron",
            "A strategy that equips one commander to deal lethal commander damage.",
        ),
        ("Tokens", "A strategy that swarms the board with creature tokens."),
        (
            "Reanimator",
            "A strategy that puts powerful creatures into play from the graveyard.",
        ),
        (
            "Storm",
            "A strategy that casts many spells in one turn to win with a storm payoff.",
        ),
        (
            "Pillow Fort",
            "A defensive strategy that prevents opponents from attacking you.",
        ),
    ]

    def get_data_batches(self) -> list[str]:
        """Return list of archetype names."""
        return [name for name, _ in self.ARCHETYPES]

    def get_source_category(self) -> str:
        return "archetypes"

    def build_prompt(self, template: TemplateConfig, data_batch: str) -> str:
        """Build the LLM prompt for an archetype topic.

        Args:
            template: TemplateConfig with task_instruction (may contain {archetype}, {context}, {description}).
            data_batch: Archetype name string.

        Returns:
            Prompt with notation legend and <task> wrapping.
        """
        archetype = data_batch
        context = self._get_description(archetype)

        task_instruction = template.task_instruction.format(
            archetype=archetype,
            context=context,
            description=context,
        )
        notation = self.domain.notation_legend

        return f"{notation}\n\n<task>\n{task_instruction}\n</task>"

    def build_context(self, data_batch: str) -> str | None:
        """Build optional context metadata for the generated Q&A.

        Args:
            data_batch: Archetype name string.

        Returns:
            Formatted metadata string or None.
        """
        archetype = data_batch
        context = self._get_description(archetype)
        return f"Category: {self.get_source_category()}\nArchetype: {archetype}\nContext: {context}"

    def _get_description(self, name: str) -> str:
        """Look up the description for an archetype by name."""
        for n, d in self.ARCHETYPES:
            if n == name:
                return d
        return ""
