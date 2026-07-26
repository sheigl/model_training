"""Generic synthetic data generator — domain-agnostic template method pattern."""

from __future__ import annotations

import logging
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Callable, Generic, TypeVar

from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
)

from .domain import DomainPlugin, TemplateConfig
from .models import (
    GenerationTrace,
    Model,
    QuestionAnswer,
    QuestionAnswerEnhanced,
    ValidationMetrics,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")  # The type of a single data batch item (e.g., dict from MongoDB)


# =============================================================================
# TRACE CALLBACK TYPE
# =============================================================================

TraceCallback = Callable[[GenerationTrace], None]


# =============================================================================
# BASE GENERATOR
# =============================================================================


class BaseGenerator(ABC, Generic[T]):
    """Abstract base generator using the template method pattern.

    Subclasses implement domain-specific data fetching and prompt building.
    The base class handles: construction, generation loop, progress reporting,
    validation integration, trace callbacks, and metrics collection.

    Usage:
        class CardSearchGenerator(BaseGenerator[dict]):
            def get_data_batches(self) -> list[dict]: ...
            def build_prompt(self, template, batch): ...
            def get_source_category(self) -> str: return "card_search"
    """

    # -- Constructor (single consolidated __init__) --------------------------

    def __init__(
        self,
        domain: DomainPlugin,
        generation_model: Model,
        validation_model: Model,
        output_ds: Any | None = None,
        templates_yaml: dict[str, Any] | None = None,
        run_id: str | None = None,
        max_items: int = 0,
        trace_callback: TraceCallback | None = None,
        metrics: ValidationMetrics | None = None,
    ):
        """Initialize generator with shared configuration.

        Args:
            domain: The DomainPlugin providing context and data access.
            generation_model: LLM model for generating Q&A pairs.
            validation_model: LLM model for validating generated output.
            output_ds: Optional DataSource for saving results.
            templates_yaml: Pre-loaded YAML config; loaded from domain if None.
            run_id: Unique identifier for this generation run.
            max_items: Max items to generate (0 = unlimited).
            trace_callback: Called with each completed GenerationTrace.
            metrics: Shared ValidationMetrics accumulator.
        """
        self.domain = domain
        self.generation_model = generation_model
        self.validation_model = validation_model
        self.output_ds = output_ds
        self.run_id = run_id or str(uuid.uuid4())[:8]
        self.max_items = max_items
        self.trace_callback = trace_callback

        # Shared metrics — create default if not provided
        if metrics is None:
            metrics = ValidationMetrics(
                generator_name=self.__class__.__name__,
                generation_model=generation_model.name,
                validation_model=validation_model.name,
            )
        else:
            metrics.generator_name = self.__class__.__name__
            metrics.generation_model = generation_model.name
            metrics.validation_model = validation_model.name

        self.metrics = metrics

        # Load templates from YAML (domain-specific)
        if templates_yaml is None:
            templates_yaml = {}
        self._templates_yaml = templates_yaml

    # -- Abstract methods (subclasses MUST implement) ------------------------

    @abstractmethod
    def get_data_batches(self) -> list[T]:
        """Return the list of data batches to iterate over.

        Each batch is fed into build_prompt() along with a template.
        Subclasses typically fetch from domain's data source.
        """
        ...

    @abstractmethod
    def build_prompt(self, template: TemplateConfig, data_batch: T) -> str:
        """Build the full prompt string for one generation attempt.

        Args:
            template: The TemplateConfig with instruction and constraints.
            data_batch: A single item from get_data_batches().

        Returns:
            Complete prompt string ready for the LLM.
        """
        ...

    @abstractmethod
    def get_source_category(self) -> str:
        """Return the category identifier for this generator's output."""
        ...

    # -- Overridable hooks (subclasses MAY override) -------------------------

    def get_source_data(self, collection: str, limit: int = 1000) -> list[dict]:
        """Fetch raw records from domain's data source.

        Override for custom query logic or different backends.
        Default uses the domain's DataSource.get_records().
        """
        ds = self.domain.get_data_source()
        return ds.get_records(collection, limit=limit)

    def build_context(self, data_batch: T) -> str | None:
        """Build optional extra context to prepend to prompts.

        Override to add domain-specific context (e.g., card details,
        recipe ingredients). Returns None if no extra context needed.
        """
        return None

    # -- Template loading ----------------------------------------------------

    def get_templates(self) -> list[TemplateConfig]:
        """Load templates for this generator's category from YAML."""
        category = self.get_source_category()
        return self.domain.get_templates_for_category(
            self._templates_yaml, category
        )

    # -- Core generation loop (template method) ------------------------------

    def generate(self) -> list[QuestionAnswerEnhanced]:
        """Execute the full generation pipeline.

        1. Load templates for this generator's category
        2. Fetch data batches
        3. For each template + batch combination:
           a. Build prompt and call LLM
           b. Validate output (with regeneration loop)
           c. Record trace, metrics, save to output
        """
        from .validator import validate_and_loop_with_suggested_fix

        templates = self.get_templates()
        if not templates:
            logger.warning(
                "No templates found for category '%s' — skipping generator %s",
                self.get_source_category(),
                self.__class__.__name__,
            )
            return []

        data_batches = self.get_data_batches()
        total_items = len(data_batches) * len(templates)

        if self.max_items > 0:
            total_items = min(total_items, self.max_items)

        logger.info(
            "Generator %s: %d templates x %d batches = %d items (max=%s)",
            self.__class__.__name__,
            len(templates),
            len(data_batches),
            total_items,
            self.max_items or "unlimited",
        )

        results: list[QuestionAnswerEnhanced] = []
        completed = 0

        # Progress bar
        progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            transient=True,
        )

        with progress:
            task_id = progress.add_task(
                f"[cyan]Generating ({self.__class__.__name__})", total=total_items
            )

            for template in templates:
                for batch_idx, data_batch in enumerate(data_batches):
                    # Check max items limit
                    if self.max_items > 0 and completed >= self.max_items:
                        break

                    source_id = self._get_source_identifier(data_batch)
                    category = self.get_source_category()

                    # Build trace record
                    trace = GenerationTrace(
                        run_id=self.run_id,
                        category=category,
                        domain=self.domain.name,
                        source_template=template.template_id,
                        generator_name=self.__class__.__name__,
                        generation_model=self.generation_model.name,
                        validation_model=self.validation_model.name,
                    )

                    # Record candidate in metrics
                    self.metrics.record_candidate(category, template.template_id)

                    try:
                        # Build prompt
                        prompt = self.build_prompt(template, data_batch)
                        context = self.build_context(data_batch)
                        if context:
                            full_prompt = f"{context}\n\n{prompt}"
                        else:
                            full_prompt = prompt

                        trace.generation_prompt = full_prompt

                        # Generate via LLM
                        start_ms = time.time() * 1000
                        raw_response = self._call_generation_llm(full_prompt)
                        latency_ms = int(time.time() * 1000 - start_ms)

                        trace.generation_response = raw_response
                        trace.generation_latency_ms = latency_ms

                        # Parse response into QuestionAnswer
                        qa = self._parse_qa(raw_response)
                        if qa is None:
                            logger.warning(
                                "Failed to parse Q&A from LLM for source %s",
                                source_id,
                            )
                            trace.generation_parsed_ok = False
                            trace.final_outcome = "rejected"
                            self.metrics.record_failed_first_attempt(category, template.template_id)
                            if self.trace_callback:
                                self.trace_callback(trace)
                            completed += 1
                            progress.update(task_id, completed=completed)
                            continue

                        # Build enhanced Q&A with metadata
                        qa_enhanced = QuestionAnswerEnhanced(
                            **qa.model_dump(),
                            category=category,
                            domain=self.domain.name,
                            source_data=[data_batch] if not isinstance(data_batch, list) else data_batch,
                            source_template=template.template_id,
                            generation_model=self.generation_model.name,
                            run_id=self.run_id,
                        )

                        # Validate with regeneration loop
                        is_valid, validated_qa = validate_and_loop_with_suggested_fix(
                            qa_enhanced=qa_enhanced,
                            system_message=self.domain.system_message,
                            notation_legend=self.domain.notation_legend,
                            validation_model=self.validation_model,
                            generation_model=self.generation_model,
                            trace=trace,
                            extra_validation_rules=template.validation_rules or [],
                            source_id=source_id,
                        )

                        if is_valid and validated_qa is not None:
                            results.append(validated_qa)

                            # Save to output data source
                            if self.output_ds:
                                self._save_result(validated_qa)
                    except Exception as e:
                        logger.error(
                            "Error generating for source %s (template=%s): %s",
                            source_id,
                            template.template_id,
                            e,
                            exc_info=True,
                        )
                        trace.final_outcome = "rejected"

                    # Advance progress bar by actual completed count
                    completed += 1
                    progress.update(task_id, completed=completed)

        logger.info(
            "Generator %s complete: %d/%d items generated successfully",
            self.__class__.__name__,
            len(results),
            total_items,
        )

        return results

    # -- LLM interaction helpers ---------------------------------------------

    def _call_generation_llm(self, prompt: str) -> str:
        """Call the generation LLM and return raw text response.

        Override for custom LLM integration or caching behavior.
        Default uses QueryModel from .query_model.
        """
        from .query_model import QueryModel

        qm = QueryModel(
            model_name=self.generation_model.name,
            provider_url=self.generation_model.provider_url,
            api_key=self.generation_model.api_key,
        )
        return qm.query(self.domain.system_message, prompt)

    def _parse_qa(self, raw: str) -> QuestionAnswer | None:
        """Parse LLM response into a QuestionAnswer model.

        Expects JSON-like output with 'question' and 'answer' fields.
        Uses brace-depth tracking to handle nested JSON structures.
        Override for domain-specific parsing logic.
        """
        import json

        # Strip markdown fences
        cleaned = raw.replace("```json", "").replace("```", "").strip()

        # Find the outermost JSON object using brace-depth tracking
        start = cleaned.find("{")
        if start == -1:
            return None

        depth = 0
        end = start
        for i in range(start, len(cleaned)):
            if cleaned[i] == "{":
                depth += 1
            elif cleaned[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break

        if depth != 0:
            return None  # Unbalanced braces

        json_str = cleaned[start : end + 1]

        try:
            data = json.loads(json_str)
            question = str(data.get("question", "")).strip()
            answer = str(data.get("answer", "")).strip()
            if question and answer:
                return QuestionAnswer(question=question, answer=answer)
        except (json.JSONDecodeError, AttributeError):
            pass

        return None

    def _save_result(self, qa: QuestionAnswerEnhanced) -> None:
        """Save a validated Q&A to the output data source."""
        if self.output_ds is None:
            return

        record = qa.model_dump(exclude_none=True)
        dedup_key = "content_hash" if qa.content_hash else None
        self.output_ds.save_record("generated_qa", record, dedup_key=dedup_key)

    # -- Source identifier helper --------------------------------------------

    @staticmethod
    def _get_source_identifier(data_batch: T) -> str:
        """Extract a human-readable identifier from a data batch for traces.

        Handles dict batches (looks for 'id', '_id', 'name' keys).
        Falls back to index-based ID.
        """
        if isinstance(data_batch, dict):
            # Try common ID fields in order of preference
            for key in ("_id", "id", "name", "title"):
                val = data_batch.get(key)
                if val is not None:
                    return str(val)
            # Fallback: use first few chars of stringified dict
            return str(dict(list(data_batch.items())[:3]))[:80]

        if isinstance(data_batch, (str, int, float)):
            return str(data_batch)[:80]

        return str(type(data_batch).__name__)


# =============================================================================
# FACTORY FUNCTION
# =============================================================================


def create_generator(
    domain: DomainPlugin,
    generator_class: type[BaseGenerator[T]],
    generation_model: Model | None = None,
    validation_model: Model | None = None,
    output_ds: Any | None = None,
    templates_yaml: dict[str, Any] | None = None,
    run_id: str | None = None,
    max_items: int = 0,
    trace_callback: TraceCallback | None = None,
    metrics: ValidationMetrics | None = None,
) -> BaseGenerator[T]:
    """Factory function to instantiate generators with shared configuration.

    This is the recommended way to create generator instances — it ensures
    consistent initialization and allows sharing of metrics across multiple
    generators in a single run.

    Args:
        domain: The DomainPlugin for this generation run.
        generator_class: Concrete subclass of BaseGenerator.
        generation_model: LLM model for generation (required).
        validation_model: LLM model for validation (required).
        output_ds: Optional DataSource for saving results.
        templates_yaml: Pre-loaded YAML config; loaded from domain if None.
        run_id: Unique identifier for this generation run.
        max_items: Max items to generate per generator (0 = unlimited).
        trace_callback: Called with each completed GenerationTrace.
        metrics: Shared ValidationMetrics accumulator across generators.

    Returns:
        Instantiated generator ready to call .generate().
    """
    if generation_model is None or validation_model is None:
        raise ValueError("Both generation_model and validation_model are required")

    return generator_class(
        domain=domain,
        generation_model=generation_model,
        validation_model=validation_model,
        output_ds=output_ds,
        templates_yaml=templates_yaml,
        run_id=run_id,
        max_items=max_items,
        trace_callback=trace_callback,
        metrics=metrics,
    )
