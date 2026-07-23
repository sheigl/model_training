"""Generate rule interaction Q&A pairs using BaseGenerator and MTGDataAccess."""

import random
from dataclasses import dataclass
from typing import Callable, Iterator

from .base_generator import BaseGenerator, TemplateConfig
from .common import (
    MTG_NOTATION_LEGEND,
    OUTPUT_FORMAT,
    SYSTEM_MESSAGE,
)
from .constants import RULE_INTERACTION_TEMPLATES, RULE_INTERACTION_VALIDATION
from .data_access import MTGDataAccess
from .domain_models import Rule
from .models import Model, ModelType, QuestionAnswerEnhanced, ValidationMetrics


@dataclass
class ProjectedRulePair:
    """A pair of rules from interacting sections for generating interaction Q&A."""

    name: str
    rule1_number: str
    rule1_text: str
    rule2_number: str
    rule2_text: str
    sections: list[str]


class GenerateRuleInteractions(BaseGenerator[ProjectedRulePair]):
    """Generate scenario Q&A where two rules interact."""

    TEMPLATES: list[TemplateConfig] = [
        TemplateConfig(
            template_id=t["type"],
            task_instruction=t["task_instruction"],
            validation_rules=[RULE_INTERACTION_VALIDATION[t["type"]]],
        )
        for t in RULE_INTERACTION_TEMPLATES
    ]

    INTERACTION_PAIRS: list[tuple[str, str]] = [
        # Existing pairs
        ("601", "116"),  # Casting + Priority
        ("603", "116"),  # Triggered abilities + Priority
        ("603", "704"),  # Triggered abilities + SBAs
        ("608", "603"),  # Resolving spells + Triggered abilities
        ("702", "120"),  # Keywords + Damage
        ("702", "704"),  # Keywords + SBAs
        ("706", "603"),  # Copying + Triggered abilities
        ("601", "117"),  # Casting + Costs
        ("700", "116"),  # Additional rules + Priority
        ("800", "116"),  # Multiplayer + Priority
        ("903", "603"),  # Commander + Triggered abilities
        ("120", "704"),  # Damage + SBAs
        ("118", "117"),  # Paying costs + Costs
        ("604", "603"),  # Static abilities + Triggered abilities
        # Zone changes
        ("400", "603"),  # Zone changes + Triggered abilities
        ("404", "603"),  # Exile zone + Triggered abilities
        ("406", "603"),  # Stack + Triggered abilities
        ("400", "704"),  # Zone changes + SBAs
        # Replacement effects
        ("614", "603"),  # Replacement effects + Triggered abilities
        ("614", "704"),  # Replacement effects + SBAs
        ("614", "120"),  # Replacement effects + Damage
        ("614", "116"),  # Replacement effects + Priority
        # Layers
        ("613", "604"),  # Layers + Static abilities
        ("613", "702"),  # Layers + Keywords
        # Combat
        ("506", "116"),  # Combat + Priority
        ("506", "603"),  # Combat + Triggered abilities
        ("506", "704"),  # Combat + SBAs
        ("510", "120"),  # Combat damage + Damage rules
        ("510", "704"),  # Combat damage + SBAs
        # Counters
        ("121", "704"),  # Counters + SBAs
        ("121", "603"),  # Counters + Triggered abilities
        # Mana
        ("106", "117"),  # Mana + Costs
        ("106", "601"),  # Mana + Casting
        # Commander specific
        ("903", "116"),  # Commander + Priority
        ("903", "704"),  # Commander + SBAs
        ("903", "614"),  # Commander + Replacement effects
        ("903", "400"),  # Commander + Zone changes
    ]

    def __init__(
        self,
        data_access: MTGDataAccess,
        models: dict[ModelType, Model],
        validation_pct: float,
        target_count: int,
        save_item: Callable[[QuestionAnswerEnhanced], None],
        metrics: ValidationMetrics | None = None,
        dry_run: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(
            models=models,
            validation_pct=validation_pct,
            target_count=target_count,
            save_item=save_item,
            metrics=metrics,
            generator_name="GenerateRuleInteractions",
            dry_run=dry_run,
            templates_per_item=2,
            **kwargs,
        )
        self.data_access = data_access

    def get_data_batches(self) -> Iterator[list[ProjectedRulePair]]:
        """Build rule pairs from interacting sections and yield them."""
        rules = self.data_access.get_rules({"text": {"$exists": True}})
        meaningful = [r for r in rules if len(r.text) > 60]

        # Group by section
        rules_by_section: dict[str, list[Rule]] = {}
        for rule in meaningful:
            num = rule.rule_number
            section = num.split(".")[0] if "." in num else num[:3]
            rules_by_section.setdefault(section, []).append(rule)

        # Build pairs with buffer
        target_with_buffer = self.target_count + int(self.target_count * 0.25)
        seen_names: set[str] = set()
        pairs: list[ProjectedRulePair] = []

        max_attempts = target_with_buffer * 3
        for _ in range(max_attempts):
            if len(pairs) >= target_with_buffer:
                break

            sec1, sec2 = random.choice(self.INTERACTION_PAIRS)

            rules1 = rules_by_section.get(sec1, [])
            rules2 = rules_by_section.get(sec2, [])

            if not rules1 or not rules2:
                continue

            rule1 = random.choice(rules1)
            rule2 = random.choice(rules2)

            pair_name = f"{rule1.rule_number}+{rule2.rule_number}"
            if pair_name in seen_names:
                continue
            seen_names.add(pair_name)

            pairs.append(ProjectedRulePair(
                name=pair_name,
                rule1_number=rule1.rule_number,
                rule1_text=rule1.text,
                rule2_number=rule2.rule_number,
                rule2_text=rule2.text,
                sections=[sec1, sec2],
            ))

        random.shuffle(pairs)
        for pair in pairs:
            yield [pair]

    def build_prompt(self, template: TemplateConfig, data_batch: ProjectedRulePair) -> str:
        """Build custom interaction prompt (preserves original inline builder)."""
        return f"""{SYSTEM_MESSAGE}

{MTG_NOTATION_LEGEND}

<rules>
AUTHORITATIVE RULES — treat these as ground truth:

Rule {data_batch.rule1_number}: {data_batch.rule1_text}

Rule {data_batch.rule2_number}: {data_batch.rule2_text}
</rules>

<task>
{template.task_instruction}

REQUIREMENTS:
1. At least one question MUST come from the perspective of a player mid-game who doesn't know the rules terminology — someone describing what's happening at the table. Examples: "I just cast X and my opponent did Y, what happens?" or "We disagreed about what happens when..."
2. At least one question MUST address a common misconception or point of confusion where a player might incorrectly apply one rule without considering the other.
3. Questions must be varied and natural-sounding. Do not reference rule numbers in questions — players don't talk that way.
4. Answers must explain how both rules interact to produce the outcome, quoting or closely paraphrasing the relevant text from each rule to explain WHY.
5. Every answer MUST state the concrete final game outcome — vague answers like "it depends" without full elaboration are not acceptable.
6. Answers must explain which rule applies first or takes precedence when both are relevant.
7. Do NOT reference rule numbers in answers — explain mechanics conversationally as a rules expert would.
8. Answers must be plain text only. Do not use markdown formatting such as bold (**text**), italics, or bullet points.
9. The answer field MUST be a single string (not an array).

{OUTPUT_FORMAT}
</task>"""

    def get_source_category(self) -> str:
        return "rule_interaction"
