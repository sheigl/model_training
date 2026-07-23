from typing import Callable, Iterator
from typing_extensions import ClassVar
from .base_generator import BaseGenerator
from .data_access import MTGDataAccess
from .domain_models import ComboWithCards
from .common import TemplateConfig, build_multi_card_usage_prompt
from .models import Model, ModelType, QuestionAnswerEnhanced, ValidationMetrics

class GenerateMultiCardUsage(BaseGenerator[ComboWithCards]):
    TEMPLATES: ClassVar[list[TemplateConfig]] = [
        TemplateConfig(
            template_id="multi_card",
            task_instruction="""Generate 2 usage questions for these cards and how they work together.""",
        )
    ]

    def __init__(self, data_access: MTGDataAccess, models: dict[ModelType, Model],
                 validation_pct: float, target_count: int, save_item: Callable[[QuestionAnswerEnhanced], None],
                 metrics: ValidationMetrics | None = None, dry_run: bool = False, **kwargs):
        super().__init__(models=models, validation_pct=validation_pct, target_count=target_count,
                         save_item=save_item, metrics=metrics, generator_name="GenerateMultiCardUsage",
                         dry_run=dry_run, **kwargs)
        self.data_access = data_access
    
    def get_data_batches(self) -> Iterator[list[ComboWithCards]]:
        combos = self.data_access.get_combos_enriched(
            filters={"status": "OK"}, limit=self.target_count * 2)
        for combo in combos:
            card_names = [c.name for c in combo.uses if c.name]
            if len(card_names) < 2 or not combo.description:
                continue
            yield [combo]
    
    def build_prompt(self, template: TemplateConfig, data_batch: ComboWithCards) -> str:
        card_names = [c.name for c in data_batch.uses if c.name][:2]
        return build_multi_card_usage_prompt(card_names[0], card_names[1], data_batch.description)
    
    def get_source_category(self) -> str:
        return "multi_card_usage"
