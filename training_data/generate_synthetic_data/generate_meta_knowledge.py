"""Generate meta knowledge Q&A pairs using BaseGenerator."""

from typing import Iterator

from .base_generator import BaseGenerator
from .common import (
    MTG_NOTATION_LEGEND,
    OUTPUT_FORMAT,
    TemplateConfig,
)


# Validation criteria for meta knowledge templates
META_KNOWLEDGE_GENERAL_VALIDATION = """
HARD REJECT RULES:
1. Answer does not provide actionable meta knowledge advice — vague platitudes are validation failures.
2. Answer contains markdown formatting (bold, italics, bullet points).
3. Answer references rule numbers directly — mechanics must be explained conversationally.
4. Answer is less than 80 characters.
5. JSON parsing fails.

VALIDATION CHECKLIST:
1. The answer provides specific, accurate meta knowledge for the given topic.
2. The answer explains power levels, competitive considerations, or format-specific knowledge.
3. At least one question comes from a practical perspective (e.g., "How do I assess...?" or "What separates...?").
"""

META_KNOWLEDGE_DEEP_DIVE_VALIDATION = """
HARD REJECT RULES:
1. Answer does not include specific card names, strategy references, or competitive analysis.
2. Answer contains markdown formatting (bold, italics, bullet points).
3. Answer references rule numbers directly — mechanics must be explained conversationally.
4. Answer is less than 80 characters.
5. JSON parsing fails.

VALIDATION CHECKLIST:
1. The answer includes specific card names or strategy references relevant to the topic.
2. The answer provides deep competitive analysis with power level reasoning.
3. The answer explains WHY specific cards or strategies are meta-relevant.
"""


class GenerateMetaKnowledge(BaseGenerator[str]):
    """Generate meta and power level Q&A covering cEDH, pod dynamics, and format knowledge."""

    TEMPLATES = [
        TemplateConfig(
            template_id="general_advice",
            task_instruction="""You are an expert in Magic: The Gathering Commander meta and competitive play. Generate exactly 3 Q&A pairs about:

Topic: {topic}
Context: {context}

Questions should cover power levels, meta considerations, format-specific knowledge, and competitive vs casual play. Be specific — avoid vague platitudes.

Output JSON array with question/answer pairs. Keep answers 3-5 sentences with specific, accurate meta knowledge.
{output_format}""",
            validation_rules=META_KNOWLEDGE_GENERAL_VALIDATION.strip().split("\n"),
            weight=1.0,
        ),
        TemplateConfig(
            template_id="meta_deep_dive",
            task_instruction="""You are an expert in Magic: The Gathering Commander meta and competitive play. Generate exactly 3 Q&A pairs about:

Topic: {topic}
Context: {context}

Each answer MUST include specific card names, strategy references, or competitive analysis. Explain WHY specific cards or strategies are meta-relevant and how they shape the competitive landscape.

Output JSON array with question/answer pairs. Keep answers 3-5 sentences with specific card/strategy references and power level reasoning.
{output_format}""",
            validation_rules=META_KNOWLEDGE_DEEP_DIVE_VALIDATION.strip().split("\n"),
            weight=1.0,
        ),
    ]

    # All topics preserved from the original generator — order and content must not change
    TOPICS = [
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

    def get_data_batches(self) -> Iterator[list[str]]:
        """Yield one topic name per batch."""
        while True:
            for topic_name, _ in self.TOPICS:
                yield [topic_name]

    def build_prompt(self, template: TemplateConfig, data_batch: str) -> str:
        """Build the LLM prompt for a meta knowledge topic."""
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
        return "meta_knowledge"

    def build_context(self, template: TemplateConfig, data_batch: str) -> str:
        """Build validation context for the generated Q&A."""
        topic = data_batch
        context = ""
        for tname, ctx in self.TOPICS:
            if tname == topic:
                context = ctx
                break

        return f"Category: {self.get_source_category()}\nTemplate: {template.template_id}\nTopic: {topic}\nContext: {context}"
