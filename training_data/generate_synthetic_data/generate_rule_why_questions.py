"""Generate 'why does this work' Q&A pairs using BaseGenerator and MTGDataAccess."""

import random
from typing import Callable, Iterator

from .base_generator import BaseGenerator, TemplateConfig
from .common import build_rule_why_prompt
from .data_access import MTGDataAccess
from .domain_models import Rule
from .models import Model, ModelType, QuestionAnswerEnhanced, ValidationMetrics


class GenerateRuleWhyQuestions(BaseGenerator[Rule]):
    """Generate backward-reasoning 'why does this work' questions from rule text."""

    TEMPLATES: list[TemplateConfig] = [
        TemplateConfig(
            template_id="why",
            task_instruction=(
                "Generate 2 Q&A pairs that ask WHY a ruling works the way it does. "
                "Start from a known outcome and ask why."
            ),
        )
    ]

    PRINCIPLE_SECTIONS: list[str] = [
        "116", "117", "118", "120",
        "601", "602", "603", "604", "608",
        "700", "701", "702", "704", "706",
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
            generator_name="GenerateRuleWhyQuestions",
            dry_run=dry_run,
            **kwargs,
        )
        self.data_access = data_access

    def get_data_batches(self) -> Iterator[list[Rule]]:
        """Fetch rules from principle sections and yield filtered batches."""
        rules = self.data_access.get_rules({"text": {"$exists": True}})

        principle_rules: list[Rule] = []
        for rule in rules:
            if len(rule.text) < 100:
                continue
            num = rule.rule_number
            for prefix in self.PRINCIPLE_SECTIONS:
                if num.startswith(prefix):
                    principle_rules.append(rule)
                    break

        random.shuffle(principle_rules)

        buffer = int(self.target_count * 1.25)
        for rule in principle_rules[:buffer]:
            yield [rule]

    def build_prompt(self, template: TemplateConfig, data_batch: Rule) -> str:
        """Build prompt using the common.py builder."""
        return build_rule_why_prompt(
            data_batch.rule_number, data_batch.text
        )

    def get_source_category(self) -> str:
        return "rule_why"
