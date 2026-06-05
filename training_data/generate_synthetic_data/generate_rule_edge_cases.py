import random
import pymongo
from rich.console import Console
from rich.status import Status
from query_model import QueryModel
import json
from common import COMPLEX_RULE_SECTIONS, build_rule_edge_case_prompt, validate_and_loop_with_suggested_fix
from typing import Any, Callable
from models import Model, ModelType, QuestionAnswer, QuestionAnswerEnhanced, ValidationMetrics
from logger import print

DEFAULT = 1500
console = Console()

class GenerateRuleEdgeCases:
    def __init__(
        self,
        rules_collection: pymongo.collection.Collection,  # type: ignore
        save_item: Callable[[QuestionAnswerEnhanced], None],
        models: dict[ModelType, Model],
        validation_pct: int,
        target_count: int = DEFAULT,
        metrics: ValidationMetrics | None = None,
    ) -> None:
        self.rules_collection = rules_collection
        self.save_item = save_item
        self.models = models
        self.validation_pct = validation_pct
        self.target_count = target_count
        self.metrics = metrics

    def generate_rule_edge_cases(self) -> None:
        print(f"\n=== GENERATING {self.target_count:,} RULE EDGE CASE QUESTIONS ===")

        rules: list[dict] = []
        with console.status("[bold green]Extracting rule data...") as status:
            complex_section_prefixes = list(COMPLEX_RULE_SECTIONS.keys())

            all_rules = list(
                self.rules_collection.find(
                    {"text": {"$exists": True, "$ne": "", "$not": {"$regex": r"^See rule \d"}}},
                    {"rule_number": 1, "text": 1},
                )
            )

            complex_rules: list[dict] = []
            for rule in all_rules:
                num = rule.get("rule_number", "")
                text = rule.get("text", "")
                if len(text) < 80:
                    continue
                for prefix in complex_section_prefixes:
                    if num.startswith(prefix):
                        rule["section_name"] = COMPLEX_RULE_SECTIONS[prefix]
                        complex_rules.append(rule)
                        break

            random.shuffle(complex_rules)
            rules = complex_rules[: self.target_count + int(self.target_count * 0.25)]
            status.update(f"[bold green]Extracted {len(rules):,} complex rules")

        print(f"  → Processing {len(rules):,} rules...")

        i: int = 0
        for rule in rules:
            if i >= self.target_count:
                break

            rule_num = rule.get("rule_number", "")
            rule_text = rule.get("text", "")
            section_name = rule.get("section_name", "General Rules")

            if (i + 1) % 100 == 0:
                print(f"    Generated {i:,}/{self.target_count:,}...")

            prompt = build_rule_edge_case_prompt(rule_num, rule_text, section_name)

            try:
                query_model = QueryModel()
                response = query_model.query(self.models[ModelType.GENERATION], prompt)
                qa_pairs = list(
                    map(
                        lambda qa: QuestionAnswer(qa["question"], qa["answer"]),
                        json.loads(response),
                    )
                )

                qa_context = f"Rule {rule_num} ({section_name}): {rule_text}"

                is_valid, doc = validate_and_loop_with_suggested_fix(
                    query_model=query_model,
                    models=self.models,
                    qa_pairs=qa_pairs,
                    validation_pct=self.validation_pct,
                    enable_extra_validation=True,
                    build_context=lambda: qa_context,
                    source_category="rule_edge_case",
                    source_data=[f"rule_{rule_num}"],
                    source_template=None,
                    metrics=self.metrics,
                )

                if is_valid and doc:
                    self.save_item(doc)

            except Exception as e:
                print(f"  ✗ Error for rule {rule_num}: {type(e).__name__}: {e}")
                continue

            i = i + 1
