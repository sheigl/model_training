from typing import Callable, Iterator
from typing_extensions import ClassVar
from .base_generator import BaseGenerator
from .data_access import MTGDataAccess
from .common import TemplateConfig, build_staple_analysis_prompt
from .models import Model, ModelType, QuestionAnswerEnhanced, ValidationMetrics

class GenerateStapleAnalysis(BaseGenerator[dict]):
    TEMPLATES: ClassVar[list[TemplateConfig]] = [
        TemplateConfig(
            template_id="staple_analysis",
            task_instruction="""Generate 3 Q&A pairs analyzing why this card is a Commander staple.""",
        )
    ]

    def __init__(self, data_access: MTGDataAccess, models: dict[ModelType, Model],
                 validation_pct: float, target_count: int, save_item: Callable[[QuestionAnswerEnhanced], None],
                 metrics: ValidationMetrics | None = None, dry_run: bool = False):
        super().__init__(models=models, validation_pct=validation_pct, target_count=target_count,
                         save_item=save_item, metrics=metrics, generator_name="GenerateStapleAnalysis",
                         dry_run=dry_run)
        self.data_access = data_access
    
    def get_data_batches(self) -> Iterator[list[dict]]:
        game_changers = self.data_access.get_game_changers(
            limit=self.target_count + int(self.target_count * 0.25))
        for card in game_changers:
            yield [card]
    
    def build_prompt(self, template: TemplateConfig, data_batch: dict) -> str:
        return build_staple_analysis_prompt(data_batch)
    
    def get_source_category(self) -> str:
        return "staple_analysis"
