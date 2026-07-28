"""Generate archetype strategy Q&A pairs using BaseGenerator."""

from typing import Iterator

from .base_generator import BaseGenerator
from .common import (
    MTG_NOTATION_LEGEND,
    OUTPUT_FORMAT,
    TemplateConfig,
)


# Validation criteria for archetype templates
ARCHETYPE_GENERAL_VALIDATION = """
HARD REJECT RULES:
1. Answer does not provide actionable archetype strategy advice — vague platitudes are validation failures.
2. Answer contains markdown formatting (bold, italics, bullet points).
3. Answer references rule numbers directly — mechanics must be explained conversationally.
4. Answer is less than 80 characters.
5. JSON parsing fails.

VALIDATION CHECKLIST:
1. The answer provides specific strategic advice about the archetype.
2. The answer explains strengths, weaknesses, or key strategic concepts.
3. At least one question comes from a practical perspective (e.g., "How do I build...?" or "What are the weaknesses of...?").
"""

ARCHETYPE_EXAMPLE_VALIDATION = """
HARD REJECT RULES:
1. Answer does not include at least one concrete card example relevant to the archetype.
2. Answer contains markdown formatting (bold, italics, bullet points).
3. Answer references rule numbers directly — mechanics must be explained conversationally.
4. Answer is less than 80 characters.
5. JSON parsing fails.

VALIDATION CHECKLIST:
1. The answer includes at least one specific card example that illustrates the archetype.
2. The example is relevant to the archetype and accurately described.
3. The answer explains WHY the card is key to the archetype's strategy.
"""


class GenerateArchetypes(BaseGenerator[str]):
    """Generate deck archetype and strategy Q&A covering playstyles and strategic concepts."""

    # All 10 archetypes preserved from the original generator — order and content must not change
    ARCHETYPES = [
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

    def get_data_batches(self) -> Iterator[list[str]]:
        """Yield one archetype name per batch."""
        while True:
            for archetype_name, _ in self.ARCHETYPES:
                yield [archetype_name]

    def build_prompt(self, template: TemplateConfig, data_batch: str) -> str:
        """Build the LLM prompt for an archetype."""
        archetype = data_batch

        # Find context for this archetype
        context = ""
        for aname, ctx in self.ARCHETYPES:
            if aname == archetype:
                context = ctx
                break

        task_instruction = template.task_instruction.format(
            archetype=archetype,
            context=context,
            output_format=OUTPUT_FORMAT.strip(),
        )

        prompt = f"""{MTG_NOTATION_LEGEND}

<task>
{task_instruction}
</task>"""

        return prompt

    def get_source_category(self) -> str:
        return "archetype"

    def build_context(self, template: TemplateConfig, data_batch: str) -> str:
        """Build validation context for the generated Q&A."""
        archetype = data_batch
        context = ""
        for aname, ctx in self.ARCHETYPES:
            if aname == archetype:
                context = ctx
                break

        return f"Category: {self.get_source_category()}\nTemplate: {template.template_id}\nArchetype: {archetype}\nContext: {context}"
