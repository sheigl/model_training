"""Generate rule edge case Q&A pairs using BaseGenerator and MTGDataAccess."""

import random
from typing import Callable, Iterator

from .base_generator import BaseGenerator, TemplateConfig
from .common import build_rule_edge_case_prompt
from .constants import COMPLEX_RULE_SECTIONS
from .data_access import MTGDataAccess
from .domain_models import Rule
from .models import Model, ModelType, QuestionAnswerEnhanced, ValidationMetrics


class GenerateRuleEdgeCases(BaseGenerator[Rule]):
    """Generate tricky edge case questions from complex rule sections."""

    TEMPLATES: list[TemplateConfig] = [
        TemplateConfig(
            template_id="edge_case",
            task_instruction=(
                "Generate 2 tricky edge case Q&A pairs from this rule. "
                "Focus on non-obvious applications, common player mistakes, and edge cases."
            ),
        )
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
            generator_name="GenerateRuleEdgeCases",
            dry_run=dry_run,
            **kwargs,
        )
        self.data_access = data_access

    def get_data_batches(self) -> Iterator[list[Rule]]:
        """Fetch rules from complex sections and yield filtered batches."""
        rules = self.data_access.get_rules({"text": {"$exists": True}})
        complex_section_prefixes = list(COMPLEX_RULE_SECTIONS.keys())

        complex_rules: list[Rule] = []
        for rule in rules:
            if len(rule.text) < 80:
                continue
            num = rule.rule_number
            for prefix in complex_section_prefixes:
                if num.startswith(prefix):
                    complex_rules.append(rule)
                    break

        random.shuffle(complex_rules)

        buffer = int(self.target_count * 1.25)
        for rule in complex_rules[:buffer]:
            yield [rule]

    def build_prompt(self, template: TemplateConfig, data_batch: Rule) -> str:
        """Build prompt using the common.py builder with section name lookup."""
        num = data_batch.rule_number
        section_name = "General Rules"
        for prefix in COMPLEX_RULE_SECTIONS:
            if num.startswith(prefix):
                section_name = COMPLEX_RULE_SECTIONS[prefix]
                break

        return build_rule_edge_case_prompt(
            data_batch.rule_number, data_batch.text, section_name
        )

    def get_source_category(self) -> str:
        return "rule_edge_case"
