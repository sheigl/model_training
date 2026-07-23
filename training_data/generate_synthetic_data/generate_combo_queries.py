"""Generate combo query Q&A pairs using BaseGenerator and MTGDataAccess."""

import random
from typing import Iterator

from .base_generator import BaseGenerator, TemplateConfig
from .data_access import MTGDataAccess
from .domain_models import ComboWithCards
from .models import Model, ModelType, ValidationMetrics
from .common import (
    MTG_NOTATION_LEGEND,
    OUTPUT_FORMAT,
    REQUIREMENTS_BASE,
    SYSTEM_MESSAGE,
    NEW_LINE,
    build_card_detail,
    validate_and_loop_with_suggested_fix,
)
from .logger import print
from .query_model import QueryModel


# Validation criteria for each combo template type with HARD REJECT rules
COMBO_HOW_VALIDATION = """
HARD REJECT RULES:
1. Answer does not explain the sequence of steps in the correct order — a correct description of individual triggers in the wrong order is a factual error.
2. Answer does not explicitly name ALL required combo pieces and explain each one's role.
3. Answer does not state the concrete outcome matching the COMBO RESULT field — vague phrases like "very powerful" or "wins the game" are validation failures.
4. Answer does not cite or closely paraphrase oracle text when explaining why a trigger fires.
5. Answer contains markdown formatting (bold, italics, bullet points).
6. Answer references rule numbers directly — mechanics must be explained conversationally.
7. Answer is less than 80 characters.
8. JSON parsing fails.

VALIDATION CHECKLIST:
1. The sequence of triggers described matches the order in the provided combo steps.
2. The answer explicitly names ALL required combo pieces and explains each one's role.
3. The answer states the concrete outcome matching the COMBO RESULT field.
4. Oracle text is cited or closely paraphrased when explaining why a trigger fires.
5. At least one question comes from the perspective of a player who has never seen this combo before.
"""

COMBO_WHAT_VALIDATION = """
HARD REJECT RULES:
1. Answer does not list ALL required cards for the combo.
2. Answer does not specify what zone each piece needs to be in (battlefield, hand, command zone, etc.).
3. Answer does not state what mana or other resources are required.
4. Answer does not include at least one question phrased as "I have X, what else do I need to go infinite?"
5. Answer contains markdown formatting (bold, italics, bullet points).
6. Answer references rule numbers directly.
7. Answer is less than 80 characters.
8. JSON parsing fails.

VALIDATION CHECKLIST:
1. All required combo pieces are listed.
2. Zone requirements for each piece are specified.
3. Mana/resource requirements are stated.
4. At least one question is from the perspective of a player asking what else they need.
"""

COMBO_WHY_VALIDATION = """
HARD REJECT RULES:
1. Answer does not explain which specific abilities or rules interactions enable the combo.
2. Answer does not explain why removing any one piece breaks the combo.
3. Answer does not address at least one potential misconception about why the combo functions.
4. Answer contains markdown formatting (bold, italics, bullet points).
5. Answer references rule numbers directly.
6. Answer is less than 80 characters.
7. JSON parsing fails.

VALIDATION CHECKLIST:
1. Specific abilities/rules interactions enabling the combo are identified.
2. Why each piece is essential is explained.
3. At least one misconception is addressed and corrected.
"""

COMBO_RESULT_VALIDATION = """
HARD REJECT RULES:
1. Answer does not state the concrete outcome of the combo (what it produces).
2. Answer uses vague phrases like "very powerful" or "wins the game" instead of specific outcomes.
3. Answer does not explain how the combo wins the game or what the player should do once the loop is established.
4. Answer does not include at least one question from the opponent's perspective asking what happened.
5. Answer contains markdown formatting (bold, italics, bullet points).
6. Answer references rule numbers directly.
7. Answer is less than 80 characters.
8. JSON parsing fails.

VALIDATION CHECKLIST:
1. The concrete outcome is stated explicitly (e.g., "infinite damage", "infinite mana of any color", "infinite creature tokens").
2. How the combo wins the game is explained.
3. What the player should do once the loop is established is described.
4. At least one question is from the opponent's perspective.
"""


class GenerateComboQueries(BaseGenerator[ComboWithCards]):
    """Generate combo query Q&A pairs from Commander Spellbook combos."""

    TEMPLATES = [
        TemplateConfig(
            template_id="how_does_it_work",
            task_instruction="""Generate exactly 3 Q&A pairs explaining HOW this combo works.
Focus on: the sequence of steps, what triggers what, and why the loop is infinite (if applicable).
At least one question must come from the perspective of a player who has never seen this combo before.""",
            validation_rules=COMBO_HOW_VALIDATION.strip().split("\n"),
            weight=1.0,
        ),
        TemplateConfig(
            template_id="what_do_i_need",
            task_instruction="""Generate exactly 3 Q&A pairs focused on the REQUIREMENTS of this combo.
Focus on: what cards are needed, what zone each piece needs to be in, what mana or other resources are required.
At least one question must be phrased as a player asking 'I have X, what else do I need to go infinite?'""",
            validation_rules=COMBO_WHAT_VALIDATION.strip().split("\n"),
            weight=1.0,
        ),
        TemplateConfig(
            template_id="why_does_this_work",
            task_instruction="""Generate exactly 3 Q&A pairs explaining WHY this combo works from a rules perspective.
Focus on: which specific abilities or rules interactions enable the combo, and why removing any one piece breaks it.
At least one question must address a potential misconception about why the combo functions.""",
            validation_rules=COMBO_WHY_VALIDATION.strip().split("\n"),
            weight=1.0,
        ),
        TemplateConfig(
            template_id="what_is_the_result",
            task_instruction="""Generate exactly 3 Q&A pairs focused on the OUTCOME of this combo.
Focus on: what the combo produces, how it wins the game, and what a player should do once the loop is established.
At least one question must be from the perspective of the OPPONENT asking what just happened to them.""",
            validation_rules=COMBO_RESULT_VALIDATION.strip().split("\n"),
            weight=1.0,
        ),
    ]

    def __init__(
        self,
        data_access: MTGDataAccess,
        models: dict[ModelType, Model],
        validation_pct: float,
        target_count: int = 5000,
        save_item: callable = None,
        metrics: ValidationMetrics | None = None,
        dry_run: bool = False,
        max_regeneration_attempts: int = 3,
        batch_size: int = 1,
        templates_per_item: int = 2,
        enable_extra_validation: bool = True,
        **kwargs,
    ):
        super().__init__(
            models=models,
            validation_pct=validation_pct,
            target_count=target_count,
            save_item=save_item,
            metrics=metrics,
            generator_name="GenerateComboQueries",
            dry_run=dry_run,
            max_regeneration_attempts=max_regeneration_attempts,
            batch_size=batch_size,
            templates_per_item=templates_per_item,
            enable_extra_validation=enable_extra_validation,
            **kwargs,
        )
        self.data_access = data_access

    def get_data_batches(self) -> Iterator[ComboWithCards]:
        """Fetch combo batches from MTGDataAccess."""
        # Fetch more than target to account for filtering/validation failures
        fetch_limit = self.target_count + int(self.target_count * 0.5)
        combos = self.data_access.get_combos_enriched(limit=fetch_limit)
        
        # Yield one combo at a time
        for combo in combos:
            yield combo

    def build_prompt(self, template: TemplateConfig, data_batch: ComboWithCards) -> str:
        """Build the LLM prompt for a combo and template."""
        combo = data_batch
        
        # Build card details for prompt
        cards_in_combo = combo.cards
        card_details = NEW_LINE.join(
            map(lambda c: build_card_detail(card_number=None, card=c), cards_in_combo)
        )
        
        # Format combo description with numbered steps
        description = combo.description or ""
        numbered_descriptions = (f"Step {i + 1}. {desc}" for i, desc in enumerate(description.split('\n')))
        description = NEW_LINE.join(numbered_descriptions)
        
        # Handle notes field if present (may not be in domain model)
        notes = getattr(combo, 'notes', None)
        if notes:
            description = description + NEW_LINE + NEW_LINE + f"⚠️ WARNING: {notes}"
        
        # Get a random feature/result from the combo
        random_feature = ""
        if combo.produces:
            random_feature = random.choice(combo.produces).description
        
        # Build requirements list
        requirement_list = (f"{i + 1}. {desc}" for i, desc in enumerate(REQUIREMENTS_BASE))
        requirements = NEW_LINE.join(requirement_list)
        
        combo_result = f"\nCOMBO RESULT: {random_feature}" if random_feature else ""

        prompt = f"""
{SYSTEM_MESSAGE}

{MTG_NOTATION_LEGEND}

<cards>
{card_details}
</cards>

<combo>
AUTHORITATIVE COMBO — treat this as ground truth, overriding any inferences from card text alone:

{description}{combo_result}
</combo>

<task>
{template.task_instruction}

REQUIREMENTS:
{requirements}

{OUTPUT_FORMAT}
</task>"""

        return prompt

    def get_source_category(self) -> str:
        return "combo_query"

    def get_source_data(self, data_batch: ComboWithCards) -> list:
        """Extract source data references for the generated document."""
        combo = data_batch
        source_data = [card.to_dict() for card in combo.cards]
        source_data.append(combo.to_dict())
        return source_data

    def build_context(self, template: TemplateConfig, data_batch: ComboWithCards) -> str:
        """Build validation context for the generated Q&A."""
        combo = data_batch
        card_details = NEW_LINE.join(
            map(lambda c: build_card_detail(card_number=None, card=c), combo.cards)
        )
        
        return f"""Category: {self.get_source_category()}
Template: {template.template_id}

For combo_query category ({template.template_id}): verify the following:
1. The sequence of triggers described matches the order in the provided combo steps. A correct description of individual triggers in the wrong order is still a factual error.
2. The answer explicitly names ALL required combo pieces and explains each one's role.
3. The answer states the concrete outcome matching the COMBO RESULT field — vague phrases like "very powerful" or "wins the game" are validation failures.
4. Oracle text is cited or closely paraphrased when explaining why a trigger fires.

Don't get confused by the abilities on the cards below that have nothing to do with the combo.
The combo listed below should be considered more than anything else, and is 100% factually accurate and proven.

Cards:
{card_details}
Combo:
{combo.description or ''}"""