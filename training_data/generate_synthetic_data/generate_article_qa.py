"""Generate article Q&A pairs using BaseGenerator and MTGDataAccess."""

from typing import Iterator

from .base_generator import BaseGenerator, TemplateConfig
from .data_access import MTGDataAccess
from .domain_models import Article
from .models import Model, ModelType, ValidationMetrics
from .common import (
    MTG_NOTATION_LEGEND,
    OUTPUT_FORMAT,
    SYSTEM_MESSAGE,
    build_article_qa_prompt,
    clean_html,
    validate_and_loop_with_suggested_fix,
)
from .logger import print
from .query_model import QueryModel


# Validation criteria for article Q&A
ARTICLE_QA_VALIDATION = """
HARD REJECT RULES:
1. Answer is not grounded in the article content — inventing information not present in the source.
2. Answer does not synthesize the article's advice — merely quoting without explanation.
3. Answer contains markdown formatting (bold, italics, bullet points).
4. Answer references rule numbers directly — mechanics must be explained conversationally.
5. Answer is less than 80 characters.
6. JSON parsing fails.
7. Question is not something a Commander player would naturally ask.

VALIDATION CHECKLIST:
1. The question is something a Commander player would naturally ask that the article answers.
2. The answer synthesizes the article's advice rather than quoting directly.
3. The answer is practical and actionable (3-5 sentences).
4. The answer is grounded in the provided article content.
"""


class GenerateArticleQa(BaseGenerator[Article]):
    """Generate Q&A pairs from EDHREC articles."""

    TEMPLATES = [
        TemplateConfig(
            template_id="article_qa",
            task_instruction="""Generate exactly 4 Q&A pairs from this EDHREC article.
Questions should be what a Commander player would ask that this article answers.
Answers MUST be grounded in the article content — do not invent information not present.
Answers should synthesize the article's advice, not quote it directly.""",
            validation_rules=ARTICLE_QA_VALIDATION.strip().split("\n"),
            weight=1.0,
        ),
    ]

    def __init__(
        self,
        data_access: MTGDataAccess,
        models: dict[ModelType, Model],
        validation_pct: float,
        target_count: int = 2000,
        save_item: callable = None,
        metrics: ValidationMetrics | None = None,
        dry_run: bool = False,
        max_regeneration_attempts: int = 3,
        batch_size: int = 1,
        templates_per_item: int = 1,
        enable_extra_validation: bool = True,
    ):
        super().__init__(
            models=models,
            validation_pct=validation_pct,
            target_count=target_count,
            save_item=save_item,
            metrics=metrics,
            generator_name="GenerateArticleQa",
            dry_run=dry_run,
            max_regeneration_attempts=max_regeneration_attempts,
            batch_size=batch_size,
            templates_per_item=templates_per_item,
            enable_extra_validation=enable_extra_validation,
        )
        self.data_access = data_access

    def get_data_batches(self) -> Iterator[Article]:
        """Fetch article batches from MTGDataAccess."""
        # Fetch more than target to account for filtering/validation failures
        fetch_limit = self.target_count + int(self.target_count * 0.25)
        articles = self.data_access.get_articles(limit=fetch_limit)
        
        # Filter articles with sufficient content
        good_articles = [a for a in articles if len(clean_html(a.content or "")) > 300]
        
        # Yield one article at a time
        for article in good_articles:
            yield article

    def build_prompt(self, template: TemplateConfig, data_batch: Article) -> str:
        """Build the LLM prompt for an article."""
        article = data_batch
        content = clean_html(article.content or "")[:2000]
        return build_article_qa_prompt(article.title, content)

    def get_source_category(self) -> str:
        return "article_qa"

    def get_source_data(self, data_batch: Article) -> list:
        """Extract source data references for the generated document."""
        return [data_batch.title]

    def build_context(self, template: TemplateConfig, data_batch: Article) -> str:
        """Build validation context for the generated Q&A."""
        article = data_batch
        content = clean_html(article.content or "")[:500]
        return f"""Category: {self.get_source_category()}
Template: {template.template_id}

Article: {article.title}
Content preview: {content}"""