"""Generate rules and scenarios Q&A pairs using BaseGenerator."""

from typing import Iterator

from .base_generator import BaseGenerator
from .common import (
    MTG_NOTATION_LEGEND,
    OUTPUT_FORMAT,
    TemplateConfig,
)


# Validation criteria for rules scenario templates
RULES_GENERAL_VALIDATION = """
HARD REJECT RULES:
1. Answer does not explain the relevant game rule — vague or incorrect rules are validation failures.
2. Answer contains markdown formatting (bold, italics, bullet points).
3. Answer references specific rule numbers directly (e.g., "Rule 608.2b") — mechanics must be explained conversationally.
4. Answer is less than 80 characters.
5. JSON parsing fails.

VALIDATION CHECKLIST:
1. The answer correctly explains the relevant Magic game rule for the scenario described.
2. The answer explains WHY the rule works that way, not just WHAT happens.
3. At least one question comes from a practical in-game perspective (e.g., "What happens when...?" or "Can I...?").
"""

RULES_EXAMPLE_VALIDATION = """
HARD REJECT RULES:
1. Answer does not include at least one concrete card example to illustrate the rule interaction.
2. Answer contains markdown formatting (bold, italics, bullet points).
3. Answer references specific rule numbers directly (e.g., "Rule 608.2b") — mechanics must be explained conversationally.
4. Answer is less than 80 characters.
5. JSON parsing fails.

VALIDATION CHECKLIST:
1. The answer includes at least one concrete card example that illustrates the rule interaction.
2. The example accurately demonstrates the rule being discussed.
3. The answer explains WHY the rule applies in this context.
"""


class GenerateRulesScenarios(BaseGenerator[str]):
    """Generate rules and scenario Q&A covering stack, combat, triggers, SBAs, and more."""

    TEMPLATES = [
        TemplateConfig(
            template_id="general_advice",
            task_instruction="""You are an expert Magic: The Gathering rules judge. Generate exactly 3 Q&A pairs about this rules topic.

Scenario category: {scenario}
Relevant rules context: {context}

Questions should cover practical in-game situations that players encounter at the table.
Answers must correctly explain the relevant game rule — explain WHY it works that way, not just WHAT happens. Do NOT reference specific rule numbers (e.g., "Rule 608.2b"). Explain mechanics conversationally.

Output JSON array with question/answer pairs. Keep answers 3-5 sentences with clear rules explanations.
{output_format}""",
            validation_rules=RULES_GENERAL_VALIDATION.strip().split("\n"),
            weight=1.0,
        ),
        TemplateConfig(
            template_id="example_driven",
            task_instruction="""You are an expert Magic: The Gathering rules judge. Generate exactly 3 Q&A pairs about this rules topic using concrete card examples.

Scenario category: {scenario}
Relevant rules context: {context}

Each answer MUST include at least one specific card example that illustrates the rule interaction. Explain WHY the rule applies in this context. Do NOT reference specific rule numbers (e.g., "Rule 608.2b").

Output JSON array with question/answer pairs. Keep answers 3-5 sentences with clear rules explanations.
{output_format}""",
            validation_rules=RULES_EXAMPLE_VALIDATION.strip().split("\n"),
            weight=1.0,
        ),
    ]

    # All scenarios preserved from the original generator — order and content must not change
    SCENARIOS = [
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

    def get_data_batches(self) -> Iterator[list[str]]:
        """Yield one scenario string per batch."""
        while True:
            for scenario_name, _ in self.SCENARIOS:
                yield [scenario_name]

    def build_prompt(self, template: TemplateConfig, data_batch: str) -> str:
        """Build the LLM prompt for a rules scenario topic."""
        scenario = data_batch

        # Find context for this scenario
        context = ""
        for sname, ctx in self.SCENARIOS:
            if sname == scenario:
                context = ctx
                break

        task_instruction = template.task_instruction.format(
            scenario=scenario,
            context=context,
            output_format=OUTPUT_FORMAT.strip(),
        )

        prompt = f"""{MTG_NOTATION_LEGEND}

<task>
{task_instruction}
</task>"""

        return prompt

    def get_source_category(self) -> str:
        return "rules_scenario"

    def build_context(self, template: TemplateConfig, data_batch: str) -> str:
        """Build validation context for the generated Q&A."""
        scenario = data_batch
        context = ""
        for sname, ctx in self.SCENARIOS:
            if sname == scenario:
                context = ctx
                break

        return f"Category: {self.get_source_category()}\nTemplate: {template.template_id}\nScenario: {scenario}\nContext: {context}"
