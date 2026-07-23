"""Generate rule explanation Q&A pairs using BaseGenerator and MTGDataAccess."""

import random
from typing import Callable, Iterator

from .base_generator import BaseGenerator, TemplateConfig
from .common import build_rule_explanation_prompt
from .constants import RULE_EXPLANATION_TEMPLATES, RULE_EXPLANATION_VALIDATION
from .data_access import MTGDataAccess
from .domain_models import Rule
from .models import Model, ModelType, QuestionAnswerEnhanced, ValidationMetrics


class GenerateRuleExplanations(BaseGenerator[Rule]):
    """Generate natural Q&A from specific rule text using multiple templates."""

    TEMPLATES: list[TemplateConfig] = [
        TemplateConfig(
            template_id=t["type"],
            task_instruction=t["task_instruction"],
            validation_rules=[RULE_EXPLANATION_VALIDATION[t["type"]]],
        )
        for t in RULE_EXPLANATION_TEMPLATES
    ]

    SKIP_SECTIONS: set[str] = {
        "000",  # Preface/introduction
        "001",  # Players
        "002",  # Decks
        "003",  # Sleeves/accessories
        "004",  # Tourneys/admin
        "005",  # Formats overview
        "900",  # Sanctioned formats overview
    }

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
            generator_name="GenerateRuleExplanations",
            dry_run=dry_run,
            templates_per_item=2,
            **kwargs,
        )
        self.data_access = data_access

    def get_data_batches(self) -> Iterator[list[Rule]]:
        """Fetch rules from MongoDB via MTGDataAccess and yield filtered batches."""
        rules = self.data_access.get_rules({"text": {"$exists": True}})

        meaningful = [
            r for r in rules
            if len(r.text) > 50
            and r.rule_number.split(".")[0] not in self.SKIP_SECTIONS
        ]

        random.shuffle(meaningful)

        buffer = int(self.target_count * 1.25)
        for rule in meaningful[:buffer]:
            yield [rule]

    def build_prompt(self, template: TemplateConfig, data_batch: Rule) -> str:
        """Build prompt using the common.py builder."""
        return build_rule_explanation_prompt(
            data_batch.rule_number,
            data_batch.text,
            {"type": template.template_id, "task_instruction": template.task_instruction},
        )

    def get_source_category(self) -> str:
        return "rule_explanation"
