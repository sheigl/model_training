"""Generate Commander-specific deckbuilding Q&A pairs using BaseGenerator."""

from typing import Iterator

from .base_generator import BaseGenerator
from .common import (
    MTG_NOTATION_LEGEND,
    OUTPUT_FORMAT,
    TemplateConfig,
)


# Validation criteria for commander building templates
COMMANDER_GENERAL_VALIDATION = """
HARD REJECT RULES:
1. Answer does not provide Commander-specific deckbuilding advice — generic advice that applies to any format is a validation failure.
2. Answer contains markdown formatting (bold, italics, bullet points).
3. Answer references rule numbers directly — mechanics must be explained conversationally.
4. Answer is less than 80 characters.
5. JSON parsing fails.

VALIDATION CHECKLIST:
1. The answer provides specific advice for building the given Commander archetype.
2. The answer addresses Commander-specific challenges (100-card singleton, multiplayer dynamics, commander tax, etc.).
3. At least one question comes from a practical deckbuilding perspective (e.g., "How do I build around...?" or "What's the right approach to...?").
"""

COMMANDER_EXAMPLE_VALIDATION = """
HARD REJECT RULES:
1. Answer does not include at least one concrete card example relevant to the archetype.
2. Answer contains markdown formatting (bold, italics, bullet points).
3. Answer references rule numbers directly — mechanics must be explained conversationally.
4. Answer is less than 80 characters.
5. JSON parsing fails.

VALIDATION CHECKLIST:
1. The answer includes at least one specific card example that illustrates the archetype concept.
2. The example is relevant to the Commander archetype and accurately described.
3. The answer explains WHY that card fits the archetype in Commander specifically.
"""


class GenerateCommanderBuilding(BaseGenerator[str]):
    """Generate Commander-specific deckbuilding Q&A for various archetypes and strategies."""

    TEMPLATES = [
        TemplateConfig(
            template_id="general_advice",
            task_instruction="""You are an expert Commander deckbuilder. Generate exactly 3 Q&A pairs about building a {archetype} Commander deck.

Strategy context:
{context}

Questions should be specific to Commander format construction challenges.
Cover topics like: choosing a commander, building around themes, threat density, political considerations, power level calibration.
Answers must address Commander-specific constraints (100-card singleton, multiplayer dynamics).

Output JSON array with question/answer pairs. Keep answers 3-6 sentences with Commander-specific advice and reasoning.
{output_format}""",
            validation_rules=COMMANDER_GENERAL_VALIDATION.strip().split("\n"),
            weight=1.0,
        ),
        TemplateConfig(
            template_id="example_driven",
            task_instruction="""You are an expert Commander deckbuilder. Generate exactly 3 Q&A pairs about building a {archetype} Commander deck using concrete card examples.

Strategy context:
{context}

Each answer MUST include at least one specific commander or card example that illustrates the archetype. Explain WHY that card is a good fit for this strategy in Commander.

Output JSON array with question/answer pairs. Keep answers 3-6 sentences with Commander-specific advice and reasoning.
{output_format}""",
            validation_rules=COMMANDER_EXAMPLE_VALIDATION.strip().split("\n"),
            weight=1.0,
        ),
    ]

    # All archetypes preserved from the original generator — order and content must not change
    ARCHETYPES = [
        (
            "sacrifice/aristocrats",
            "Decks that sacrifice creatures for value, using Blood Artist-style effects, sac outlets, and token generators. Key challenge: balancing fodder, payoffs, and sac outlets.",
        ),
        (
            "spellslinger/magecraft",
            "Decks that cast lots of instants and sorceries, using magecraft triggers, prowess, and spell-based win conditions. Key challenge: protecting your win condition while staying low to the ground.",
        ),
        (
            "token swarm",
            "Decks that generate many creature tokens and win through wide attacks or combo. Key challenge: having enough anthems and ways to win through chump blockers.",
        ),
        (
            "reanimator",
            "Decks that put big creatures in the graveyard and reanimate them cheaply. Key challenge: filling the graveyard, protecting the reanimation target, winning with the reanimated creature.",
        ),
        (
            "combo",
            "Decks that assemble a specific combination of cards to win instantly or lock opponents out. Key challenge: finding the combo pieces, protecting the combo, having backup win conditions.",
        ),
        (
            "control",
            "Decks that answer every threat and win through superior card advantage in the late game. Key challenge: staying relevant in multiplayer, having a win condition that can close through disruption.",
        ),
        (
            "voltron",
            "Decks that buff one creature (usually the commander) with equipment and auras to win through commander damage. Key challenge: protecting your commander, rebuilding after removal, winning through 21 combat damage.",
        ),
        (
            "stax/prison",
            "Decks that use symmetrical or asymmetrical effects to slow opponents while you advance your own game plan. Key challenge: calibrating the lock pieces so you can still win, not making the game unfun.",
        ),
        (
            "landfall/lands matter",
            "Decks that trigger off lands entering the battlefield, using extra land effects and landfall payoffs. Key challenge: getting enough lands into play per turn, balancing consistency with power.",
        ),
        (
            "graveyard value",
            "Decks that use the graveyard as a resource without necessarily being reanimator — flashback, delve, threshold, cycling. Key challenge: filling the graveyard efficiently, playing around graveyard hate.",
        ),
        (
            "turbo draw/card advantage",
            "Decks built around drawing as many cards as possible to find combo pieces or assemble overwhelming card advantage. Key challenge: using the cards drawn effectively, not decking yourself.",
        ),
        (
            "midrange goodstuff",
            "Decks that play powerful cards at every part of the curve without a focused synergy strategy. Key challenge: distinguishing this from a tuned synergy deck, knowing when to choose goodstuff over theme.",
        ),
    ]

    def get_data_batches(self) -> Iterator[list[str]]:
        """Yield one archetype string per batch."""
        while True:
            for archetype_name, _ in self.ARCHETYPES:
                yield [archetype_name]

    def build_prompt(self, template: TemplateConfig, data_batch: str) -> str:
        """Build the LLM prompt for a Commander building archetype."""
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
        return "commander_building"

    def build_context(self, template: TemplateConfig, data_batch: str) -> str:
        """Build validation context for the generated Q&A."""
        archetype = data_batch
        context = ""
        for aname, ctx in self.ARCHETYPES:
            if aname == archetype:
                context = ctx
                break

        return f"Category: {self.get_source_category()}\nTemplate: {template.template_id}\nArchetype: {archetype}\nContext: {context}"
