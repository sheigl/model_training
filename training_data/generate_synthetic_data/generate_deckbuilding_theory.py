"""Generate deckbuilding theory Q&A pairs using BaseGenerator."""

from typing import Iterator

from .base_generator import BaseGenerator
from .common import (
    MTG_NOTATION_LEGEND,
    OUTPUT_FORMAT,
    TemplateConfig,
)


# Validation criteria for deckbuilding theory templates
DECKBUILDING_GENERAL_VALIDATION = """
HARD REJECT RULES:
1. Answer does not provide actionable deckbuilding advice — vague platitudes are validation failures.
2. Answer contains markdown formatting (bold, italics, bullet points).
3. Answer references rule numbers directly — mechanics must be explained conversationally.
4. Answer is less than 80 characters.
5. JSON parsing fails.

VALIDATION CHECKLIST:
1. The answer provides specific, actionable deckbuilding advice for the given topic.
2. The answer explains the WHY behind the advice, not just WHAT to do.
3. At least one question comes from a practical perspective (e.g., "How do I...?" or "When should I...?").
"""

DECKBUILDING_EXAMPLE_VALIDATION = """
HARD REJECT RULES:
1. Answer does not include at least one concrete card example to illustrate the concept.
2. Answer contains markdown formatting (bold, italics, bullet points).
3. Answer references rule numbers directly — mechanics must be explained conversationally.
4. Answer is less than 80 characters.
5. JSON parsing fails.

VALIDATION CHECKLIST:
1. The answer includes at least one concrete card example that illustrates the concept.
2. The example is relevant to the topic and accurately described.
3. The answer explains WHY the example works in that context.
"""


class GenerateDeckbuildingTheory(BaseGenerator[str]):
    """Generate deckbuilding theory Q&A covering ratios, evaluation, and construction principles."""

    TEMPLATES = [
        TemplateConfig(
            template_id="general_advice",
            task_instruction="""You are an expert Magic: The Gathering deckbuilder. Generate exactly 3 Q&A pairs about this deckbuilding topic.

Topic: {topic}
Context: {context}

Questions should cover practical deckbuilding decisions, card evaluation, and construction theory.
Answers should be detailed, actionable, and explain the WHY behind the advice. Be specific — avoid vague platitudes.

Output JSON array with question/answer pairs. Keep answers 3-5 sentences with concrete reasoning.
{output_format}""",
            validation_rules=DECKBUILDING_GENERAL_VALIDATION.strip().split("\n"),
            weight=1.0,
        ),
        TemplateConfig(
            template_id="example_driven",
            task_instruction="""You are an expert Magic: The Gathering deckbuilder. Generate exactly 3 Q&A pairs about this deckbuilding topic using concrete card examples.

Topic: {topic}
Context: {context}

Each answer MUST include at least one specific card example that illustrates the concept. Explain WHY that card is a good example of the principle being discussed.

Output JSON array with question/answer pairs. Keep answers 3-5 sentences with concrete examples and reasoning.
{output_format}""",
            validation_rules=DECKBUILDING_EXAMPLE_VALIDATION.strip().split("\n"),
            weight=1.0,
        ),
    ]

    # All topics preserved from the original generator — order and content must not change
    TOPICS = [
        (
            "card evaluation and slot justification",
            "How to determine if a card belongs in your deck, evaluating cards on rate, role, and redundancy.",
        ),
        (
            "card advantage vs card selection",
            "The difference between drawing more cards (Rhystic Study) vs filtering cards (Ponder). When each matters.",
        ),
        (
            "mana curve and tempo",
            "How to build a mana curve, what tempo means, why you want to spend mana efficiently each turn.",
        ),
        (
            "redundancy and consistency",
            "Why you run multiple effects that do similar things, how to determine the right amount of redundancy.",
        ),
        (
            "synergy vs goodstuff",
            "The tradeoff between running powerful generic cards vs cards that specifically support your strategy.",
        ),
        (
            "win conditions and closing games",
            "How to identify your win conditions, ensure they're reachable, and have enough redundancy to close games.",
        ),
        (
            "deck tuning and iteration",
            "How to identify what's wrong with a deck after testing, what to cut, what to add, how to iterate.",
        ),
        (
            "threat density and role assignment",
            "Assigning cards roles (threat, answer, engine, accelerant) and ensuring the right density of each.",
        ),
        (
            "mana base construction",
            "How to build a mana base, dual lands vs basics, color ratios, when to run utility lands.",
        ),
        (
            "protection and resilience",
            "How to protect your key pieces, recover from board wipes, maintain card advantage after setbacks.",
        ),
        (
            "interaction and removal philosophy",
            "When to hold up interaction vs advance your game plan, reactive vs proactive playstyles.",
        ),
        (
            "tribal deck construction",
            "Special considerations for tribal decks: lord effects, creature density, tribal synergies, non-creature support.",
        ),
    ]

    def get_data_batches(self) -> Iterator[list[str]]:
        """Yield one topic string per batch."""
        while True:
            for topic_name, _ in self.TOPICS:
                yield [topic_name]

    def build_prompt(self, template: TemplateConfig, data_batch: str) -> str:
        """Build the LLM prompt for a deckbuilding theory topic."""
        topic = data_batch

        # Find context for this topic
        context = ""
        for tname, ctx in self.TOPICS:
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
        return "deckbuilding_theory"

    def build_context(self, template: TemplateConfig, data_batch: str) -> str:
        """Build validation context for the generated Q&A."""
        topic = data_batch
        context = ""
        for tname, ctx in self.TOPICS:
            if tname == topic:
                context = ctx
                break

        return f"Category: {self.get_source_category()}\nTemplate: {template.template_id}\nTopic: {topic}\nContext: {context}"
