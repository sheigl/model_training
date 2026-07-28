"""Generate game theory and decision-making Q&A pairs using BaseGenerator."""

from typing import Iterator

from .base_generator import BaseGenerator
from .common import (
    MTG_NOTATION_LEGEND,
    OUTPUT_FORMAT,
    TemplateConfig,
)


# Validation criteria for game theory templates
GAME_THEORY_GENERAL_VALIDATION = """
HARD REJECT RULES:
1. Answer does not provide actionable decision-making advice — vague platitudes are validation failures.
2. Answer contains markdown formatting (bold, italics, bullet points).
3. Answer references rule numbers directly — mechanics must be explained conversationally.
4. Answer is less than 80 characters.
5. JSON parsing fails.

VALIDATION CHECKLIST:
1. The answer provides a clear decision-making framework for the given situation.
2. The answer explains trade-offs and when to apply different approaches.
3. At least one question comes from an in-game perspective (e.g., "When should I...?" or "How do I decide...?").
"""

GAME_THEORY_SCENARIO_VALIDATION = """
HARD REJECT RULES:
1. Answer does not walk through a concrete scenario — abstract advice without examples is a validation failure.
2. Answer contains markdown formatting (bold, italics, bullet points).
3. Answer references rule numbers directly — mechanics must be explained conversationally.
4. Answer is less than 80 characters.
5. JSON parsing fails.

VALIDATION CHECKLIST:
1. The answer includes a concrete in-game scenario that illustrates the decision-making concept.
2. The scenario walks through the reasoning step by step.
3. The answer explains what information a player should look for to make the right call.
"""


class GenerateGameTheory(BaseGenerator[str]):
    """Generate game theory and decision-making Q&A covering sequencing, threat assessment, and politics."""

    # All situations preserved from the original generator — order and content must not change
    SITUATIONS = [
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

    def get_data_batches(self) -> Iterator[list[str]]:
        """Yield one situation string per batch."""
        while True:
            for situation_name, _ in self.SITUATIONS:
                yield [situation_name]

    def build_prompt(self, template: TemplateConfig, data_batch: str) -> str:
        """Build the LLM prompt for a game theory situation."""
        situation = data_batch

        # Find context for this situation
        context = ""
        for sname, ctx in self.SITUATIONS:
            if sname == situation:
                context = ctx
                break

        task_instruction = template.task_instruction.format(
            situation=situation,
            context=context,
            output_format=OUTPUT_FORMAT.strip(),
        )

        prompt = f"""{MTG_NOTATION_LEGEND}

<task>
{task_instruction}
</task>"""

        return prompt

    def get_source_category(self) -> str:
        return "game_theory"

    def build_context(self, template: TemplateConfig, data_batch: str) -> str:
        """Build validation context for the generated Q&A."""
        situation = data_batch
        context = ""
        for sname, ctx in self.SITUATIONS:
            if sname == situation:
                context = ctx
                break

        return f"Category: {self.get_source_category()}\nTemplate: {template.template_id}\nSituation: {situation}\nContext: {context}"
