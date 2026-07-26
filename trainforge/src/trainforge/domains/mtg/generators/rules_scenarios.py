"""Generate rules and scenarios Q&A pairs — ported from generate_rules_scenarios.py."""

from __future__ import annotations

import logging

from trainforge.domain import TemplateConfig
from trainforge.generator import BaseGenerator

logger = logging.getLogger(__name__)


class RulesScenariosGenerator(BaseGenerator[str]):
    """Generate rules and scenario Q&A covering stack, combat, triggers, SBAs, and more."""

    # All scenarios preserved from the original CLI generator — order and content must not change
    SCENARIOS: list[tuple[str, str]] = [
        (
            "spell resolution and the stack",
            "Last in first out stack resolution, responding to spells, fizzling spells, counterspells",
        ),
        (
            "combat damage and blocking",
            "Assigning combat damage, trample, first strike, double strike, deathtouch in combat, lifelink in combat",
        ),
        (
            "triggered abilities and timing",
            "When triggered abilities go on the stack, controlling the order of your own triggers, missed triggers",
        ),
        (
            "state-based actions",
            "Creatures dying from lethal damage or 0 toughness, legend rule, planeswalker uniqueness rule, poison counters",
        ),
        (
            "activated abilities and costs",
            "Paying costs for activated abilities, tapping as a cost, sacrifice as a cost, mana abilities",
        ),
        (
            "replacement effects and prevention effects",
            "How replacement effects modify events, prevention effects, damage prevention, redirection",
        ),
        (
            "keyword abilities interactions",
            "How keywords interact: hexproof vs targeting, shroud vs targeting, indestructible vs destroy vs exile, regenerate",
        ),
        (
            "Commander-specific rules",
            "Commander tax, commander damage, moving to command zone vs graveyard, color identity in deck building",
        ),
        (
            "planeswalker rules",
            "Activating planeswalker abilities, attacking planeswalkers, the planeswalker uniqueness rule, loyalty counters",
        ),
        (
            "token and copy rules",
            "Creating tokens, copying spells, copying permanents, token characteristics, copy effects on the stack",
        ),
        (
            "priority and passing priority",
            "When players receive priority, how to sequence actions, when you can and cannot respond",
        ),
        (
            "enters the battlefield and leaves the battlefield triggers",
            "ETB triggers, LTB triggers, flicker effects, blink, phasing, bouncing permanents",
        ),
        (
            "targeting and illegal targets",
            "Choosing targets on announcement, targets becoming illegal before resolution, fizzling",
        ),
        (
            "mana and casting",
            "Mana pool, emptying the mana pool, split second, flash, timing restrictions for casting spells",
        ),
        (
            "graveyard and exile interactions",
            "Cards going to graveyard, replacement effects for dying, exile vs graveyard, returning from exile",
        ),
    ]

    def get_data_batches(self) -> list[str]:
        """Return list of scenario names."""
        return [name for name, _ in self.SCENARIOS]

    def get_source_category(self) -> str:
        return "rules_scenarios"

    def build_prompt(self, template: TemplateConfig, data_batch: str) -> str:
        """Build the LLM prompt for a rules scenario topic.

        Args:
            template: TemplateConfig with task_instruction (may contain {scenario}, {context}, {description}).
            data_batch: Scenario name string.

        Returns:
            Prompt with notation legend and <task> wrapping.
        """
        scenario = data_batch
        context = self._get_description(scenario)

        task_instruction = template.task_instruction.format(
            scenario=scenario,
            context=context,
            description=context,
        )
        notation = self.domain.notation_legend

        return f"{notation}\n\n<task>\n{task_instruction}\n</task>"

    def build_context(self, data_batch: str) -> str | None:
        """Build optional context metadata for the generated Q&A.

        Args:
            data_batch: Scenario name string.

        Returns:
            Formatted metadata string or None.
        """
        scenario = data_batch
        context = self._get_description(scenario)
        return f"Category: {self.get_source_category()}\nScenario: {scenario}\nContext: {context}"

    def _get_description(self, name: str) -> str:
        """Look up the description for a scenario by name."""
        for n, d in self.SCENARIOS:
            if n == name:
                return d
        return ""
