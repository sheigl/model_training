"""Abstract base generator class for synthetic data generation.

Provides shared generation loop, template selection, validation integration,
metrics tracking, and MongoDB saving for all synthetic data generators.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, ClassVar, Generic, Iterator, TypeVar
import random
import time
import json

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn

from .common import (
    TemplateConfig,
    validate_and_loop_with_suggested_fix,
    QuestionAnswer,
    QuestionAnswerEnhanced,
)
from .models import ValidationMetrics, ModelType, Model
from .query_model import QueryModel


T = TypeVar("T")  # Data batch type


console = Console()


class BaseGenerator(ABC, Generic[T]):
    """Abstract base class for all synthetic data generators.

    Uses Template Method pattern: subclasses implement abstract hooks,
    base class provides the invariant generation loop.

    Subclasses must implement:
        - get_data_batches(): Yield data batches for generation
        - build_prompt(template, data_batch): Build LLM prompt
        - get_source_category(): Return category string for metrics

    Subclasses should define:
        - TEMPLATES: ClassVar[list[TemplateConfig]] - Available templates with weights
    """

    # Subclasses override with their templates
    TEMPLATES: ClassVar[list[TemplateConfig]] = []

    # Universal HARD REJECT rules (enforced by base class validation)
    UNIVERSAL_HARD_REJECT_RULES: ClassVar[list[str]] = [
        "Answer is not a single string (must not be array)",
        "Answer contains markdown formatting (bold, italics, bullet points)",
        "Answer references rule numbers directly (must explain conversationally)",
        "Answer is less than 80 characters (insufficient detail)",
        "Question or answer is missing or empty",
        "JSON parsing fails",
        "Validation score < 7/10 after 3 regeneration attempts",
    ]

    def __init__(
        self,
        models: dict[ModelType, Model],
        validation_pct: float,
        target_count: int,
        save_item: Callable[[QuestionAnswerEnhanced], None],
        metrics: ValidationMetrics | None = None,
        generator_name: str | None = None,
        dry_run: bool = False,
        max_regeneration_attempts: int = 3,
        batch_size: int = 1,
        templates_per_item: int = 1,
        enable_extra_validation: bool = True,
    ):
        """Initialize the base generator.

        Args:
            models: Dict with ModelType.GENERATION and ModelType.VALIDATION keys
            validation_pct: Percentage of items to validate (0.0-1.0)
            target_count: Target number of items to generate
            save_item: Callback to save a validated QuestionAnswerEnhanced
            metrics: Optional ValidationMetrics instance for tracking
            generator_name: Name for metrics tracking (defaults to class name)
            dry_run: If True, don't call save_item (for testing)
            max_regeneration_attempts: Max retries after validation failure (default 3)
            batch_size: Items per generation batch (default 1)
            templates_per_item: Number of templates to apply per data item (default 1)
            enable_extra_validation: Enable detailed verification checklist
        """
        self.models = models
        self.validation_pct = validation_pct
        self.target_count = target_count
        self.save_item = save_item
        self.metrics = metrics
        self.dry_run = dry_run
        self.max_regeneration_attempts = max_regeneration_attempts
        self.batch_size = batch_size
        self.templates_per_item = templates_per_item
        self.enable_extra_validation = enable_extra_validation

        self._query_model = QueryModel()
        self.generated_count = 0
        self._start_time = time.time()
        self._generator_name = generator_name or self.__class__.__name__

        # Set generator name on metrics if provided
        if self.metrics and self.metrics.generator_name == "unknown":
            self.metrics.generator_name = self._generator_name
            self.metrics.generation_model = self.models[ModelType.GENERATION].name
            self.metrics.validation_model = self.models[ModelType.VALIDATION].name

    @property
    def generation_model(self) -> Model:
        """Get the generation model."""
        return self.models[ModelType.GENERATION]

    @property
    def validation_model(self) -> Model:
        """Get the validation model."""
        return self.models[ModelType.VALIDATION]

    @property
    def query_model(self) -> QueryModel:
        """Get the query model instance."""
        return self._query_model

    @query_model.setter
    def query_model(self, value: QueryModel):
        self._query_model = value

    @abstractmethod
    def get_data_batches(self) -> Iterator[list[T]]:
        """Fetch and yield data batches for generation.

        Each yielded batch is a list of data items. Each item will have
        `templates_per_item` templates applied to it.

        Returns:
            Iterator yielding lists of data items
        """
        ...

    @abstractmethod
    def build_prompt(self, template: TemplateConfig, data_batch: T) -> str:
        """Build the LLM prompt for a specific template and data batch.

        Args:
            template: The selected TemplateConfig
            data_batch: One item from get_data_batches()

        Returns:
            Complete prompt string for the generation model
        """
        ...

    @abstractmethod
    def get_source_category(self) -> str:
        """Return the source category string for metrics and tracking.

        Returns:
            Category string (e.g., "combo_query", "article_qa", "card_search")
        """
        ...

    def get_source_data(self, data_batch: T) -> list[Any]:
        """Extract source data references for the generated document.

        Override if source data structure differs from data_batch.

        Args:
            data_batch: One item from get_data_batches()

        Returns:
            List of source data references
        """
        return [data_batch] if data_batch else []

    def build_context(self, template: TemplateConfig, data_batch: T) -> str:
        """Build validation context for the generated Q&A.

        Override to provide rich, domain-specific context for validation.

        Args:
            template: The selected TemplateConfig
            data_batch: One item from get_data_batches()

        Returns:
            Context string for validation
        """
        return f"Category: {self.get_source_category()}\nTemplate: {template.template_id}"

    def select_templates(self, k: int = 1) -> list[TemplateConfig]:
        """Weighted random template selection from TEMPLATES.

        Args:
            k: Number of templates to select

        Returns:
            List of selected TemplateConfig instances

        Raises:
            ValueError: If TEMPLATES is empty
        """
        if not self.TEMPLATES:
            raise ValueError(f"{self.__class__.__name__} must define TEMPLATES class variable")

        weights = [t.weight for t in self.TEMPLATES]
        return random.choices(self.TEMPLATES, weights=weights, k=k)

    def select_template(self) -> TemplateConfig:
        """Select a single template using weighted random selection.

        Returns:
            Selected TemplateConfig
        """
        return self.select_templates(k=1)[0]

    def validate_answer(
        self,
        qa: QuestionAnswer,
        template: TemplateConfig,
        data_batch: T,
        source_data: list[Any],
    ) -> tuple[bool, QuestionAnswerEnhanced | None]:
        """Run validation pipeline with regeneration loop.

        Args:
            qa: QuestionAnswer to validate
            template: TemplateConfig used for generation
            data_batch: Source data batch
            source_data: Source data references

        Returns:
            Tuple of (is_valid, enhanced_document_or_none)
        """
        qa_pairs = [qa]

        is_valid, doc = validate_and_loop_with_suggested_fix(
            query_model=self.query_model,
            models=self.models,
            qa_pairs=qa_pairs,
            validation_pct=self.validation_pct,
            enable_extra_validation=self.enable_extra_validation,
            build_context=lambda: self.build_context(template, data_batch),
            source_category=self.get_source_category(),
            source_data=source_data,
            source_template=template.template_id,
            metrics=self.metrics,
        )

        return is_valid, doc

    def _parse_generation_response(self, response: str) -> list[QuestionAnswer]:
        """Parse JSON response from generation model into QuestionAnswer list.

        Args:
            response: Raw response string from generation model

        Returns:
            List of QuestionAnswer objects

        Raises:
            json.JSONDecodeError: If response is not valid JSON
        """
        # Clean up common formatting issues
        response = response.replace("```json", "").replace("```", "").strip()

        # Try to extract JSON if wrapped in extra text
        if not response.startswith("["):
            start = response.find("[")
            end = response.rfind("]")
            if start != -1 and end != -1:
                response = response[start:end + 1]

        qa_data = json.loads(response)
        return [QuestionAnswer(qa["question"], qa["answer"]) for qa in qa_data]

    def _process_item(self, data_batch: T) -> None:
        """Process a single data batch with all selected templates.

        Args:
            data_batch: One item from get_data_batches()
        """
        # Select templates for this data batch
        selected_templates = self.select_templates(k=self.templates_per_item)

        for template in selected_templates:
            if self.generated_count >= self.target_count:
                break

            try:
                # Build prompt and generate
                prompt = self.build_prompt(template, data_batch)
                response = self.query_model.query(
                    self.generation_model,
                    prompt,
                    max_tokens=8192,
                    purpose="GENERATION",
                )

                # Parse JSON response
                qa_pairs = self._parse_generation_response(response)

                # Validate each Q&A pair
                source_data = self.get_source_data(data_batch)

                for qa in qa_pairs:
                    if self.generated_count >= self.target_count:
                        break

                    is_valid, doc = self.validate_answer(
                        qa, template, data_batch, source_data
                    )

                    if is_valid and doc:
                        if not self.dry_run:
                            self.save_item(doc)
                        self.generated_count += 1

            except json.JSONDecodeError as e:
                console.print(f"[red]  ✗ JSON parse error: {e}[/red]")
                if self.metrics:
                    self.metrics.record_candidate(self.get_source_category(), template.template_id)
            except Exception as e:
                console.print(f"[red]  ✗ Error generating: {type(e).__name__}: {e}[/red]")
                if self.metrics:
                    self.metrics.record_candidate(self.get_source_category(), template.template_id)
                continue

    def generate(self) -> None:
        """Main generation loop - Template Method pattern.

        Orchestrates: fetch data → select template → build prompt → generate → validate → save
        """
        if not self.TEMPLATES:
            raise ValueError(f"{self.__class__.__name__} must define TEMPLATES class variable")

        console.print(f"\n[bold cyan]=== GENERATING {self.target_count:,} {self.get_source_category().upper()} ===[/bold cyan]")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"Generating {self.get_source_category()}",
                total=self.target_count,
            )

            for data_batch in self.get_data_batches():
                if self.generated_count >= self.target_count:
                    break

                self._process_item(data_batch)
                progress.advance(task, 0)  # Update progress bar

        elapsed = time.time() - self._start_time
        console.print(f"\n[green]✓ Completed {self.generated_count:,} {self.get_source_category()} in {elapsed:.1f}s[/green]")

        if self.metrics:
            self.metrics.flush()
            self.metrics.print_rolling_summary(interval=1)