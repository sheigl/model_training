"""Generate Commander knowledge Q&A pairs using BaseGenerator."""

from typing import Iterator

from .base_generator import BaseGenerator
from .common import (
    MTG_NOTATION_LEGEND,
    OUTPUT_FORMAT,
    TemplateConfig,
)


# Validation criteria for commander knowledge templates
COMMANDER_KNOWLEDGE_GENERAL_VALIDATION = """
HARD REJECT RULES:
1. Answer does not provide accurate Commander rules information — incorrect rules are validation failures.
2. Answer contains markdown formatting (bold, italics, bullet points).
3. Answer references rule numbers directly — rules must be explained conversationally.
4. Answer is less than 80 characters.
5. JSON parsing fails.

VALIDATION CHECKLIST:
1. The answer accurately explains the Commander rules topic.
2. The answer uses a conversational tone without citing rule numbers.
3. At least one question comes from a practical perspective (e.g., "How does...?" or "What happens when...?").
"""

COMMANDER_KNOWLEDGE_EXAMPLE_VALIDATION = """
HARD REJECT RULES:
1. Answer does not include at least one concrete scenario or card interaction example.
2. Answer contains markdown formatting (bold, italics, bullet points).
3. Answer references rule numbers directly — rules must be explained conversationally.
4. Answer is less than 80 characters.
5. JSON parsing fails.

VALIDATION CHECKLIST:
1. The answer includes at least one concrete scenario that illustrates the rules interaction.
2. The answer references specific card names or game situations.
3. The answer explains the rules interaction step by step.
"""


class GenerateCommanderKnowledge(BaseGenerator[str]):
    """Generate Commander rules Q&A covering deck construction, tax, damage, and format rules."""

    # Commander sub-topics broken from the original monolithic topic
    # Covers all concepts from the original: singleton, command zone, tax, damage, color identity, multiplayer, partner, companion
    COMMANDER_SUBTOPICS = [
        (
            "deck construction rules",
            "100-card singleton, exactly 100 cards including commander, no sideboard, commander determines color identity, basics only from outside game.",
        ),
        (
            "commander tax",
            "Each time commander is cast from command zone, costs {2} more. Tax is cumulative. Applies to all spell-based commanders.",
        ),
        (
            "commander damage",
            "21 combat damage from a single commander to a player loses that game. Commander must be commanded by the player who dealt it. Resets if commander changes zones.",
        ),
        (
            "command zone",
            "Commander starts in command zone. Goes to command zone from any zone (owner's choice for graveyard/exile). Not cast from library, hand, or battlefield.",
        ),
        (
            "color identity restrictions",
            "Cards in deck must only use mana symbols in commander's color identity. Hybrid, Phyrexian, color indicators all count. Basic lands only from outside.",
        ),
        (
            "multiplayer rules",
            "Typically 4 players. Last player standing wins. Political deals, archenemy dynamics, kingmaking considerations. Turn order matters for threat assessment.",
        ),
        (
            "partner and background commanders",
            "Partner allows 2 commanders if both have 'Partner'. Background enchantment commanders pair with a creature that has 'Choose a Background'. Both count for color identity.",
        ),
        (
            "companion and wish effects",
            "Companion restrictions apply from outside the game. Wish effects can only get cards from outside in casual. Commander's Handbook / Rule 903.9 governs this.",
        ),
    ]

    def get_data_batches(self) -> Iterator[list[str]]:
        """Yield one sub-topic name per batch."""
        while True:
            for subtopic_name, _ in self.COMMANDER_SUBTOPICS:
                yield [subtopic_name]

    def build_prompt(self, template: TemplateConfig, data_batch: str) -> str:
        """Build the LLM prompt for a Commander knowledge sub-topic."""
        topic = data_batch

        # Find context for this sub-topic
        context = ""
        for tname, ctx in self.COMMANDER_SUBTOPICS:
            if tname == topic:
                context = ctx
                break

        task_instruction = template.task_instruction.format(
            topic=topic,
            context=context,
            output_format=OUTPUT_FORMAT.strip(),
        )

        prompt = f"""{MTG_NOTATION_LEGEND}

<task>
{task_instruction}
</task>"""

        return prompt

    def get_source_category(self) -> str:
        return "commander_rules"

    def build_context(self, template: TemplateConfig, data_batch: str) -> str:
        """Build validation context for the generated Q&A."""
        topic = data_batch
        context = ""
        for tname, ctx in self.COMMANDER_SUBTOPICS:
            if tname == topic:
                context = ctx
                break

        return f"Category: {self.get_source_category()}\nTemplate: {template.template_id}\nTopic: {topic}\nContext: {context}"
