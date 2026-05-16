import pymongo
from rich.console import Console
from rich.status import Status
from query_model import QueryModel
import json
from common import MTG_NOTATION_LEGEND, OUTPUT_FORMAT, REQUIREMENTS_BASE, SYSTEM_MESSAGE, NEW_LINE, build_rule_explanation_prompt, validate_and_loop_with_suggested_fix
from typing import Any, Callable
from models import Model, ModelType, QuestionAnswer, QuestionAnswerEnhanced
from logger import print
import random

from constants import RULE_EXPLANATION_TEMPLATES, RULE_EXPLANATION_VALIDATION

console = Console()

class GenerateRuleExplanations:
    def __init__(
        self,
        rules_collection: pymongo.collection.Collection, # type: ignore
        save_item: Callable[[QuestionAnswerEnhanced], None],
        models: dict[ModelType, Model],
        validation_pct: int,
        target_count=5000) -> None:

        self.rules_collection = rules_collection
        self.save_item = save_item
        self.models = models
        self.validation_pct = validation_pct
        self.target_count = target_count


    def generate_rule_explanations(self) -> None:
        """Generate rule explanation queries - returns MongoDB documents"""

        rules_collection = self.rules_collection
        save_item = self.save_item
        models = self.models
        validation_pct = self.validation_pct
        target_count = self.target_count

        print(f"\n=== GENERATING {target_count:,} RULE EXPLANATION QUERIES ===")

        rules = []

        with console.status("[bold green]Extracting rule data...") as status:
            rules = self.__extract_rule_data(rules_collection, target_count, status)

        print(f"  → Processing {len(rules):,} rules...")

        i: int = 0
        for rule in rules:
            if i >= target_count:
                break

            if (i + 1) % 100 == 0:
                print(f"    Generated {i:,}/{target_count:,}...")

            rule_num = rule['rule_number']
            rule_text = rule['rule_text']

            # Build prompt
            prompts: list[tuple[str, str, str, dict[str, str]]] = []

            selected_templates = random.sample(RULE_EXPLANATION_TEMPLATES, k=2)

            for template in selected_templates:
                prompts.append((
                    build_rule_explanation_prompt(rule_num, rule_text, template),
                    rule_num,
                    rule_text,
                    template
                ))

            query_model = QueryModel()

            for prompt, rule_num, rule_text, template in prompts:
                try:

                    response = query_model.query(models[ModelType.GENERATION], prompt)
                    qa_pairs = list(map(lambda qa: QuestionAnswer(qa["question"], qa["answer"]), json.loads(response)))

                    qa_context = f"""
For rule_explanation category ({template["type"]}): verify the following:
{RULE_EXPLANATION_VALIDATION[template["type"]]}

Rule {rule_num}: {rule_text}
"""

                    is_valid, doc = validate_and_loop_with_suggested_fix(
                        query_model=query_model,
                        models=models,
                        qa_pairs=qa_pairs,
                        validation_pct=validation_pct,
                        enable_extra_validation=True,
                        build_context=lambda: qa_context,
                        source_category="rule_explanation",
                        source_data=[f"rule_{rule_num}"],
                        source_template=template["type"]
                    )

                    if is_valid and doc:
                        save_item(doc)

                except Exception as e:
                    print(f"  ✗ Error generating for rule {rule_num}: {type(e).__name__}: {e}")
                    continue

            i = i + 1


    def __extract_rule_data(
        self,
        rules_collection: pymongo.collection.Collection, # type: ignore
        target_count: int,
        rich_status: Status) -> list[dict]:
        """Extract rule data from MongoDB and prepare for prompt generation."""
        all_rules = list(rules_collection.find(
            {'text': {'$exists': True, '$ne': '', '$not': {'$regex': r'^See rule \d'}}},
            {'rule_number': 1, 'text': 1}
        ))

        # Filter to rules with meaningful content (>50 chars) and shuffle for variety
        SKIP_SECTIONS = {
            "000",  # Preface/introduction
            "001",  # Players
            "002",  # Decks  
            "003",  # Sleeves/accessories
            "004",  # Tourneys/admin
            "005",  # Formats overview
            "900",  # Sanctioned formats overview
        }

        meaningful_rules = [
            r for r in all_rules 
            if len(r.get('text', '')) > 50
            and r.get('rule_number', '').split('.')[0] not in SKIP_SECTIONS
        ]
        
        random.shuffle(meaningful_rules)

        # Take more than needed to allow for some failures
        rules_to_process = meaningful_rules[:target_count + int(target_count * .25)]

        rules: list[dict] = []

        for i, rule in enumerate(rules_to_process):
            rich_status.update(f"[bold green]Extracting rule data... {i+1}/{len(rules_to_process)}")

            rule_num = rule.get('rule_number', '')
            rule_text = rule.get('text', '')

            if not rule_num or not rule_text:
                continue

            # Skip if we already have this rule
            if len(list(filter(lambda r: r['rule_number'] == rule_num, rules))) > 0:
                continue

            rules.append({
                'rule_number': rule_num,
                'rule_text': rule_text
            })

        random.shuffle(rules)
        return rules
