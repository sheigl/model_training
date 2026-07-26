"""Generate game theory and decision-making Q&A pairs — ported from generate_game_theory.py."""

from __future__ import annotations

import logging

from trainforge.domain import TemplateConfig
from trainforge.generator import BaseGenerator

logger = logging.getLogger(__name__)


class GameTheoryGenerator(BaseGenerator[str]):
    """Generate game theory and decision-making Q&A covering sequencing, threat assessment, and politics."""

    # All 10 situations preserved from the original CLI generator — order and content must not change
    SITUATIONS: list[tuple[str, str]] = [
        (
            "threat assessment and removal sequencing",
            "Deciding which threats to answer immediately vs ignore, when to hold removal, opportunity cost of using removal early",
        ),
        (
            "opening hand evaluation and mulliganing",
            "What makes a hand keepable, when to mulligan, evaluating land count, curve, and role of each card in opening hand",
        ),
        (
            "sequencing spells for maximum efficiency",
            "Playing around counterspells, ordering your spells to maximize impact, sandbagging threats",
        ),
        (
            "mana efficiency and tempo",
            "Spending all your mana every turn, tempo advantage, knowing when to hold up mana vs spend it",
        ),
        (
            "multiplayer politics and deal-making",
            "When to make deals in Commander, how to evaluate political deals, threat perception, being the archenemy",
        ),
        (
            "threat perception and table dynamics",
            "Recognizing who is ahead, when to team up vs go it alone, threat ordering in multiplayer",
        ),
        (
            "when to go all-in vs play conservatively",
            "Assessing when it's correct to commit your hand to the board vs hold back, playing around sweepers",
        ),
        (
            "card advantage decisions",
            "When to use your card draw, whether to refill your hand or deploy threats, resource management",
        ),
        (
            "combat math and blocking decisions",
            "How to evaluate attack and block decisions, when to take damage vs trade creatures, alpha strikes",
        ),
        (
            "timing your win attempt",
            "Reading the table to know when to go for the win, when opponents are tapped out, winning through disruption",
        ),
    ]

    def get_data_batches(self) -> list[str]:
        """Return list of situation names."""
        return [name for name, _ in self.SITUATIONS]

    def get_source_category(self) -> str:
        return "game_theory"

    def build_prompt(self, template: TemplateConfig, data_batch: str) -> str:
        """Build the LLM prompt for a game theory situation.

        Args:
            template: TemplateConfig with task_instruction (may contain {situation}, {context}, {description}).
            data_batch: Situation name string.

        Returns:
            Prompt with notation legend and <task> wrapping.
        """
        situation = data_batch
        context = self._get_description(situation)

        task_instruction = template.task_instruction.format(
            situation=situation,
            context=context,
            description=context,
        )
        notation = self.domain.notation_legend

        return f"{notation}\n\n<task>\n{task_instruction}\n</task>"

    def build_context(self, data_batch: str) -> str | None:
        """Build optional context metadata for the generated Q&A.

        Args:
            data_batch: Situation name string.

        Returns:
            Formatted metadata string or None.
        """
        situation = data_batch
        context = self._get_description(situation)
        return f"Category: {self.get_source_category()}\nSituation: {situation}\nContext: {context}"

    def _get_description(self, name: str) -> str:
        """Look up the description for a situation by name."""
        for n, d in self.SITUATIONS:
            if n == name:
                return d
        return ""
