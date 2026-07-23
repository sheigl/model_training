from typing import Callable, Iterator
from typing_extensions import ClassVar
from .base_generator import BaseGenerator
from .data_access import MTGDataAccess
from .common import TemplateConfig, build_salt_prompt
from .models import Model, ModelType, QuestionAnswerEnhanced, ValidationMetrics

class GenerateSaltQuestions(BaseGenerator[list[dict]]):
    TEMPLATES: ClassVar[list[TemplateConfig]] = [
        TemplateConfig(
            template_id="salt_analysis",
            task_instruction="""Generate 3 Q&A pairs about controversial/salty Commander cards.""",
        )
    ]

    BATCH_SIZE: ClassVar[int] = 8

    def __init__(self, data_access: MTGDataAccess, models: dict[ModelType, Model],
                 validation_pct: float, target_count: int, save_item: Callable[[QuestionAnswerEnhanced], None],
                 metrics: ValidationMetrics | None = None, dry_run: bool = False, **kwargs):
        super().__init__(models=models, validation_pct=validation_pct, target_count=target_count,
                         save_item=save_item, metrics=metrics, generator_name="GenerateSaltQuestions",
                         dry_run=dry_run, **kwargs)
        self.data_access = data_access
    
    def get_data_batches(self) -> Iterator[list[list[dict]]]:
        salty_cards = self.data_access.get_salty_cards(
            min_salt=1.2, limit=self.target_count * self.BATCH_SIZE)
        for i in range(0, len(salty_cards), self.BATCH_SIZE):
            batch = salty_cards[i:i + self.BATCH_SIZE]
            if batch:
                yield [batch]
    
    def build_prompt(self, template: TemplateConfig, data_batch: list[dict]) -> str:
        return build_salt_prompt(data_batch)
    
    def get_source_category(self) -> str:
        return "salt_analysis"
