"""Abstract base generator class for synthetic data generation.

Provides shared generation loop, template selection, validation integration,
metrics tracking, and MongoDB saving for all synthetic data generators.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, ClassVar, Generic, Iterator, TypeVar
import logging
import random
import time
import json
import uuid

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn

from .common import (
    TemplateConfig,
    validate_and_loop_with_suggested_fix,
    QuestionAnswer,
    QuestionAnswerEnhanced,
)
from .models import ValidationMetrics, ModelType, Model, GenerationTrace
from .query_model import QueryModel
from .template_store import TemplateStore
from .yaml_template_loader import YamlTemplateLoader


logger = logging.getLogger(__name__)


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
        trace_callback: Callable[[GenerationTrace], None] | None = None,
        template_store: TemplateStore | None = None,
        yaml_loader: YamlTemplateLoader | None = None,
        template_version_override: int | None = None,
        validator_template_version_override: int | None = None,
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
            template_store: Optional MongoDB TemplateStore for loading templates.
                Deprecated — use ``yaml_loader`` instead. Kept for backward compat.
            yaml_loader: Optional :class:`YamlTemplateLoader` for loading templates
                from local YAML files. Takes precedence over ``template_store``.
                When both are ``None`` (the default) the class-level ``TEMPLATES``
                constant is used, preserving byte-identical backward compatibility.
            template_version_override: When set, ``select_templates`` requests this
                specific version from the store instead of the latest.
            validator_template_version_override: When set, the validator template
                lookup requests this specific version instead of the latest.
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
        self._trace_callback = trace_callback
        self._template_store = template_store
        self._yaml_loader = yaml_loader
        self._template_version_override = template_version_override
        self._validator_template_version_override = validator_template_version_override

        self._query_model = QueryModel()
        # Wire the store into the QueryModel so validator prompts can be loaded
        # from MongoDB when a store handle is provided.
        self._query_model.template_store = template_store
        self._query_model.yaml_loader = yaml_loader
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

        When a ``template_store`` is configured and contains docs for this
        generator's category, the store-loaded ``TemplateConfig`` objects are
        used instead of the class-level ``TEMPLATES`` constant. When the store
        is ``None`` or returns no docs, falls back to ``self.TEMPLATES``
        (current hardcoded behavior).

        Args:
            k: Number of templates to select

        Returns:
            List of selected TemplateConfig instances

        Raises:
            ValueError: If TEMPLATES is empty and the store yields nothing
        """
        store_templates = self._load_templates_from_source()
        templates = store_templates if store_templates else self.TEMPLATES
        if not templates:
            raise ValueError(f"{self.__class__.__name__} must define TEMPLATES class variable")

        weights = [t.weight for t in templates]
        return random.choices(templates, weights=weights, k=k)

    def _load_templates_from_source(self) -> list[TemplateConfig] | None:
        """Load templates from the configured source with a fallback chain.

        Returns ``None`` when no source is available or yields no docs, so
        callers fall back to the class-level ``TEMPLATES`` constant.

        Source priority (yaml_loader takes precedence over template_store):
          1. ``self._yaml_loader`` — read from local YAML files.
          2. ``self._template_store`` — read from MongoDB (deprecated path).
          3. Neither configured → return ``None``.

        Fallback chain (per template_id in ``self.TEMPLATES``):
          * For the store path:
            1. ``template_version_override`` set → ``store.get_version(...)``.
               If that version is missing, log a warning and try ``get_latest``.
            2. ``get_latest`` → if a doc exists, build a ``TemplateConfig`` from it.
          * For the YAML path:
            1. ``get_latest(category, tid, "generation")`` → if an entry exists,
               build a ``TemplateConfig`` from it (version is always ``"1"``).
          3. No doc/entry for this template_id → use the class-level ``TemplateConfig``.
        """
        # YAML loader path (preferred)
        if self._yaml_loader is not None:
            category = self.get_source_category()
            result: list[TemplateConfig] = []
            for class_template in self.TEMPLATES:
                doc = self._yaml_loader.get_latest(category, class_template.template_id, "generation")
                if doc:
                    from .common import _dict_to_template_config
                    result.append(_dict_to_template_config(doc))
                else:
                    # YAML has no entry for this template_id — use the class constant.
                    result.append(class_template)
            return result if result else None

        # MongoDB store path (deprecated)
        if self._template_store is None:
            return None
        category = self.get_source_category()
        result: list[TemplateConfig] = []
        for class_template in self.TEMPLATES:
            tid = class_template.template_id
            doc = None
            if self._template_version_override is not None:
                doc = self._template_store.get_version(
                    category, tid, "generation", self._template_version_override,
                )
                if doc is None:
                    logger.warning(
                        "Template version %s not found for %s/%s — falling back to latest",
                        self._template_version_override, category, tid,
                    )
            if doc is None:
                doc = self._template_store.get_latest(category, tid, "generation")
            if doc:
                result.append(TemplateStore.to_template_config(doc))
            else:
                # Store has no doc for this template_id — use the class constant.
                result.append(class_template)
        return result if result else None

    def _load_templates_from_store(self) -> list[TemplateConfig] | None:
        """Alias for :meth:`_load_templates_from_source` (backward compat)."""
        return self._load_templates_from_source()

    def select_template(self) -> TemplateConfig:
        """Select a single template using weighted random selection.

        Returns:
            Selected TemplateConfig
        """
        return self.select_templates(k=1)[0]

    def _resolve_validator_version(self, category: str) -> int | None:
        """Resolve the validator template version from the store.

        Since YAML has no versioning, this returns ``None`` when a YAML loader
        is configured (caller treats ``None`` as "no override"). When a MongoDB
        store is configured it mirrors the hybrid lookup logic in
        ``QueryModel._resolve_validator_template`` and returns the version number
        (or ``None`` when no validator doc exists).

        Lookup order:
          1. Generator-specific validator doc — ``(generator=category, …)``.
          2. Shared validator doc — ``(generator="__shared__", …)``.
          3. ``None`` — no store or no doc found.
        """
        if self._yaml_loader is not None:
            return None
        if self._template_store is None:
            return None
        store = self._template_store
        # 1. Generator-specific validator override
        doc = store.get_latest(category, "validator", "validator")
        if doc:
            return doc.get("version")
        # 2. Shared validator
        doc = store.get_latest(store.SHARED_NAMESPACE, "qa_validation", "validator")
        if doc:
            return doc.get("version")
        return None

    def validate_answer(
        self,
        qa: QuestionAnswer,
        template: TemplateConfig,
        data_batch: T,
        source_data: list[Any],
        trace: GenerationTrace | None = None,
        sibling_corrections: list[str] | None = None,
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
            trace=trace,
            sibling_corrections=sibling_corrections,
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

            # Resolve validator template version (Story 045)
            resolved_validator_version = self._resolve_validator_version(
                self.get_source_category()
            )

            trace = None
            if self._trace_callback:
                trace = GenerationTrace(
                    item_id=str(uuid.uuid4()),
                    run_id=self.metrics.run_id if self.metrics else "",
                    category=self.get_source_category(),
                    source_template=template.template_id,
                    generator_name=self._generator_name,
                    generation_model=self.generation_model.name,
                    validation_model=self.validation_model.name,
                    created_at=datetime.utcnow().isoformat() + "Z",
                    template_version=template.version,
                    validator_template_version=resolved_validator_version,
                )

            # Record template version in metrics (Story 045)
            if self.metrics:
                self.metrics.record_template_version(
                    template.template_id, template.version
                )
                if resolved_validator_version is not None:
                    self.metrics.record_template_version(
                        "shared", resolved_validator_version, is_validator=True
                    )

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
                try:
                    qa_pairs = self._parse_generation_response(response)
                    if trace:
                        trace.generation_parsed_ok = True
                except json.JSONDecodeError:
                    if trace:
                        trace.generation_prompt = prompt
                        trace.generation_response = response
                        trace.generation_latency_ms = self._query_model._last_elapsed_ms
                        trace.generation_parsed_ok = False
                    raise  # Re-raise to be caught by the outer handler

                if trace:
                    trace.generation_prompt = prompt
                    trace.generation_response = response
                    trace.generation_latency_ms = self._query_model._last_elapsed_ms

                # Validate each Q&A pair
                source_data = self.get_source_data(data_batch)

                sibling_corrections: list[str] = []

                for qa in qa_pairs:
                    if self.generated_count >= self.target_count:
                        break

                    is_valid, doc = self.validate_answer(
                        qa, template, data_batch, source_data, trace=trace,
                        sibling_corrections=sibling_corrections,
                    )

                    if is_valid and doc:
                        if not self.dry_run:
                            self.save_item(doc)
                        self.generated_count += 1

                # Fire trace callback after all QA pairs are processed
                # (regardless of pass/fail) so we always capture generation traces
                if trace and self._trace_callback:
                    self._trace_callback(trace)
                    trace = None  # Prevent callback from firing again for this template

            except json.JSONDecodeError as e:
                console.print(f"[red]  ✗ JSON parse error: {e}[/red]")
                if self.metrics:
                    self.metrics.record_candidate(self.get_source_category(), template.template_id)
                # Save trace for failed generation (JSON parse error)
                if trace and self._trace_callback:
                    trace.final_outcome = "generation_error"
                    self._trace_callback(trace)
                    trace = None
            except Exception as e:
                console.print(f"[red]  ✗ Error generating: {type(e).__name__}: {e}[/red]")
                if self.metrics:
                    self.metrics.record_candidate(self.get_source_category(), template.template_id)
                # Save trace for failed generation (other error)
                if trace and self._trace_callback:
                    trace.final_outcome = "generation_error"
                    self._trace_callback(trace)
                    trace = None
                continue

    def generate(self) -> None:
        """Main generation loop - Template Method pattern.

        Orchestrates: fetch data → select template → build prompt → generate → validate → save
        """
        # Use store templates if available, else class TEMPLATES. ``select_templates``
        # already performs the store lookup + fallback, so this guard only needs to
        # raise when neither source yields any templates.
        available = self._load_templates_from_source() or self.TEMPLATES
        if not available:
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