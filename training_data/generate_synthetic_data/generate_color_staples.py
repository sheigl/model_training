from typing import Callable, Iterator
from typing_extensions import ClassVar
from .base_generator import BaseGenerator
from .data_access import MTGDataAccess
from .common import TemplateConfig, build_color_staples_prompt
from .models import Model, ModelType, QuestionAnswerEnhanced, ValidationMetrics

class GenerateColorStaples(BaseGenerator[tuple[str, list[dict]]]):
    COLORS: ClassVar[list[str]] = ['black', 'blue', 'colorless', 'green', 'red', 'white']

    def __init__(self, data_access: MTGDataAccess, models: dict[ModelType, Model],
                 validation_pct: float, target_count: int, save_item: Callable[[QuestionAnswerEnhanced], None],
                 metrics: ValidationMetrics | None = None, dry_run: bool = False, **kwargs):
        super().__init__(models=models, validation_pct=validation_pct, target_count=target_count,
                         save_item=save_item, metrics=metrics, generator_name="GenerateColorStaples",
                         dry_run=dry_run, **kwargs)
        self.data_access = data_access
    
    def get_data_batches(self) -> Iterator[list[tuple[str, list[dict]]]]:
        for color in self.COLORS:
            top_cards = self.data_access.get_top_cards_by_color(color, limit=30)
            subsets = [top_cards[:10], top_cards[10:20], top_cards[20:30]]
            for subset in subsets:
                if subset:
                    yield [(color, subset)]
    
    def build_prompt(self, template: TemplateConfig, data_batch: tuple[str, list[dict]]) -> str:
        color, cards = data_batch
        return build_color_staples_prompt(color, cards)
    
    def get_source_category(self) -> str:
        return "color_staples"
