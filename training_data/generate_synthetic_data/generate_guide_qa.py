import random
from typing import Callable, Iterator
from typing_extensions import ClassVar
from .base_generator import BaseGenerator
from .data_access import MTGDataAccess
from .domain_models import Guide
from .common import TemplateConfig, build_guide_qa_prompt, clean_html
from .models import Model, ModelType, QuestionAnswerEnhanced, ValidationMetrics

class GenerateGuideQa(BaseGenerator[Guide]):
    TEMPLATES: ClassVar[list[TemplateConfig]] = [
        TemplateConfig(
            template_id="guide_qa",
            task_instruction="""Read this EDHREC guide and generate 4 Q&A pairs from it. Focus on instructional, how-to aspects.""",
        )
    ]

    def __init__(self, data_access: MTGDataAccess, models: dict[ModelType, Model],
                 validation_pct: float, target_count: int, save_item: Callable[[QuestionAnswerEnhanced], None],
                 metrics: ValidationMetrics | None = None, dry_run: bool = False, **kwargs):
        super().__init__(models=models, validation_pct=validation_pct, target_count=target_count,
                         save_item=save_item, metrics=metrics, generator_name="GenerateGuideQa",
                         dry_run=dry_run, **kwargs)
        self.data_access = data_access

    def get_data_batches(self) -> Iterator[list[Guide]]:
        guides = self.data_access.get_guides(limit=self.target_count + int(self.target_count * 0.25))
        good_guides = []
        for guide in guides:
            content = ""
            if guide.chapters:
                content = " ".join(ch.content for ch in guide.chapters)
            cleaned = clean_html(content) if content else ""
            if len(cleaned) > 300:
                good_guides.append(guide)
        random.shuffle(good_guides)
        for guide in good_guides:
            yield [guide]
    
    def build_prompt(self, template: TemplateConfig, data_batch: Guide) -> str:
        content = ""
        if data_batch.chapters:
            content = " ".join(ch.content for ch in data_batch.chapters)[:2000]
        return build_guide_qa_prompt(data_batch.title, clean_html(content))
    
    def get_source_category(self) -> str:
        return "guide_qa"
