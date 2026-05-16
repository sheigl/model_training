import pymongo
from rich.console import Console
from rich.status import Status
from query_model import QueryModel
import json
from common import MTG_NOTATION_LEGEND, OUTPUT_FORMAT, SYSTEM_MESSAGE, NEW_LINE, build_rule_interaction_prompt, validate_and_loop_with_suggested_fix
import random
from typing import Any, Callable
from models import Model, ModelType, QuestionAnswer, QuestionAnswerEnhanced
from logger import print
from constants import RULE_INTERACTION_TEMPLATES, RULE_INTERACTION_VALIDATION

console = Console()


class ProjectedRulePair:
    def __init__(
        self,
        name: str,
        rule1_number: str,
        rule1_text: str,
        rule2_number: str,
        rule2_text: str,
        sections: list[str],
    ):
        self.name = name
        self.rule1_number = rule1_number
        self.rule1_text = rule1_text
        self.rule2_number = rule2_number
        self.rule2_text = rule2_text
        self.sections = sections


class GenerateRuleInteractions:
    def __init__(
        self,
        rules_collection: pymongo.collection.Collection,  # type: ignore
        save_item: Callable[[QuestionAnswerEnhanced], None],
        models: dict[ModelType, Model],
        validation_pct: int,
        target_count: int = 5000,
    ) -> None:
        self.rules_collection = rules_collection
        self.save_item = save_item
        self.models = models
        self.validation_pct = validation_pct
        self.target_count = target_count

    def generate_rule_interactions(self) -> None:
        """Generate rule interaction queries — returns MongoDB documents via save_item."""

        rules_collection = self.rules_collection
        save_item = self.save_item
        models = self.models
        validation_pct = self.validation_pct
        target_count = self.target_count

        print(f"\n=== GENERATING {target_count:,} RULE INTERACTION QUERIES ===")

        rule_pairs: list[ProjectedRulePair] = []

        with console.status("[bold green]Extracting rule data...") as status:
            rule_pairs = self.__extract_rule_data(rules_collection, target_count, status)

        print(f"  → Processing {len(rule_pairs):,} rule pairs...")

        i: int = 0
        for pair in rule_pairs:
            if i >= target_count:
                break

            if (i + 1) % 100 == 0:
                print(f"    Generated {i:,}/{target_count:,}...")

            pair_name = pair.name

            prompts: list[tuple[str, str, str, str, str, dict[str, str]]] = []

            selected_templates = random.sample(RULE_INTERACTION_TEMPLATES, k=2)

            for template in selected_templates:
                prompts.append((
                    self.__build_interaction_prompt(
                        pair.rule1_number, pair.rule1_text,
                        pair.rule2_number, pair.rule2_text,
                        template
                    ),
                    pair.rule1_number,
                    pair.rule1_text,
                    pair.rule2_number,
                    pair.rule2_text,
                    template
                ))

            query_model = QueryModel()

            for prompt, rule1_num, rule1_text, rule2_num, rule2_text, template in prompts:
                try:
                    response = query_model.query(models[ModelType.GENERATION], prompt)
                    qa_pairs = list(
                        map(
                            lambda qa: QuestionAnswer(qa["question"], qa["answer"]),
                            json.loads(response),
                        )
                    )

                    qa_context = f"""
For rule_interaction category ({template["type"]}): verify the following:
{RULE_INTERACTION_VALIDATION[template["type"]]}

Rule {rule1_num}: {rule1_text}
Rule {rule2_num}: {rule2_text}
"""

                    is_valid, doc = validate_and_loop_with_suggested_fix(
                        query_model=query_model,
                        models=models,
                        qa_pairs=qa_pairs,
                        validation_pct=validation_pct,
                        enable_extra_validation=True,
                        build_context=lambda: qa_context,
                        source_category="rule_interaction",
                        source_data=[f"rule_{rule1_num}", f"rule_{rule2_num}"],
                        source_template=template["type"]
                    )

                    if is_valid and doc:
                        save_item(doc)

                except Exception as e:
                    print(f"  ✗ Error generating for {pair_name}: {type(e).__name__}: {e}")
                    continue

            i = i + 1

    def __build_interaction_prompt(
        self,
        rule1_num: str,
        rule1_text: str,
        rule2_num: str,
        rule2_text: str,
        template: dict[str, str]
    ) -> str:
        prompt = f"""
    {SYSTEM_MESSAGE}

    {MTG_NOTATION_LEGEND}

    <rules>
    AUTHORITATIVE RULES — treat these as ground truth:

    Rule {rule1_num}: {rule1_text}

    Rule {rule2_num}: {rule2_text}
    </rules>

    <task>
    {template["task_instruction"]}

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
        return prompt

    def __extract_rule_data(
        self,
        rules_collection: pymongo.collection.Collection,  # type: ignore
        target_count: int,
        rich_status: Status,
    ) -> list[ProjectedRulePair]:
        """Extract rule pairs from the rules collection and prepare for prompt generation."""
        all_rules = list(
            rules_collection.find(
                {"text": {"$exists": True, "$not": {"$regex": r"^See rule \d"}}},
                {"rule_number": 1, "text": 1},
            )
        )

        meaningful_rules = [r for r in all_rules if len(r.get("text", "")) > 60]

        # Group rules by top-level section number
        rules_by_section: dict[str, list[dict]] = {}
        for rule in meaningful_rules:
            num = rule.get("rule_number", "")
            section = num.split(".")[0] if "." in num else num[:3]
            if section not in rules_by_section:
                rules_by_section[section] = []
            rules_by_section[section].append(rule)

        rich_status.update(
            f"[bold green]Grouped into {len(rules_by_section)} sections"
        )

        # Define section pairs that commonly interact in real games
        # Expanded section pairs covering more of the rules space
        interaction_pairs: list[tuple[str, str]] = [
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

        pairs: list[ProjectedRulePair] = []
        seen_names: set[str] = set()

        # Build enough pairs with buffer
        target_with_buffer = target_count + int(target_count * 0.25)
        max_attempts = target_with_buffer * 3
        attempts = 0

        while len(pairs) < target_with_buffer and attempts < max_attempts:
            attempts += 1
            rich_status.update(
                f"[bold green]Extracting rule pairs... {len(pairs)}/{target_with_buffer} (attempt {attempts})"
            )

            sec1, sec2 = random.choice(interaction_pairs)

            rules1 = rules_by_section.get(sec1, [])
            rules2 = rules_by_section.get(sec2, [])

            if not rules1 or not rules2:
                continue

            rule1 = random.choice(rules1)
            rule2 = random.choice(rules2)

            rule1_num = rule1.get("rule_number", "")
            rule1_text = rule1.get("text", "")
            rule2_num = rule2.get("rule_number", "")
            rule2_text = rule2.get("text", "")

            if not all([rule1_num, rule1_text, rule2_num, rule2_text]):
                continue

            pair_name = f"{rule1_num}+{rule2_num}"
            if pair_name in seen_names:
                continue
            seen_names.add(pair_name)

            projected_pair = ProjectedRulePair(
                name=pair_name,
                rule1_number=rule1_num,
                rule1_text=rule1_text,
                rule2_number=rule2_num,
                rule2_text=rule2_text,
                sections=[sec1, sec2],
            )

            pairs.append(projected_pair)

        random.shuffle(pairs)
        return pairs
