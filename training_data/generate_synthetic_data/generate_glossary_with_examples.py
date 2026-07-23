"""Generate glossary Q&A pairs with examples using BaseGenerator and MTGDataAccess."""

import random
from typing import Callable, Iterator

from .base_generator import BaseGenerator, TemplateConfig
from .common import build_glossary_with_examples_prompt
from .data_access import MTGDataAccess
from .domain_models import GlossaryTerm
from .models import Model, ModelType, QuestionAnswerEnhanced, ValidationMetrics


class GenerateGlossaryWithExamples(BaseGenerator[GlossaryTerm]):
    """Generate Q&A from glossary terms with concrete in-game examples."""

    TEMPLATES: list[TemplateConfig] = [
        TemplateConfig(
            template_id="glossary_example",
            task_instruction=(
                "Generate 3 Q&A pairs about this MTG term. "
                "Include the definition AND a concrete in-game example."
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
            generator_name="GenerateGlossaryWithExamples",
            dry_run=dry_run,
            **kwargs,
        )
        self.data_access = data_access

    def get_data_batches(self) -> Iterator[list[GlossaryTerm]]:
        """Fetch glossary terms and yield filtered batches."""
        terms = self.data_access.get_glossary()
        meaningful = [t for t in terms if len(t.definition) > 30]
        random.shuffle(meaningful)

        buffer = int(self.target_count * 1.25)
        for term in meaningful[:buffer]:
            yield [term]

    def build_prompt(self, template: TemplateConfig, data_batch: GlossaryTerm) -> str:
        """Build prompt using the common.py builder."""
        return build_glossary_with_examples_prompt(
            data_batch.term, data_batch.definition
        )

    def get_source_category(self) -> str:
        return "glossary_with_examples"
