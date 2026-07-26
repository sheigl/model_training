"""Generic models for TrainForge — domain-agnostic data structures."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


# =============================================================================
# LLM MODEL CONFIGURATION
# =============================================================================


class ModelType(str, Enum):
    GENERATION = "generation"
    VALIDATION = "validation"


class ModelProvider(str, Enum):
    OLLAMA = "ollama"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


class Model(BaseModel):
    """Configuration for an LLM endpoint."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    type: ModelType
    provider: ModelProvider | None = None
    provider_url: str | None = None
    api_key: str | None = None

    @model_validator(mode="after")
    def _set_provider_defaults(self) -> "Model":
        if self.provider is None:
            self.provider = self._parse_provider()
        return self

    def _parse_provider(self) -> ModelProvider:
        name_lower = (self.name or "").lower()
        if "anthropic" in name_lower:
            return ModelProvider.ANTHROPIC
        elif "openai" in name_lower:
            return ModelProvider.OPENAI
        else:
            return ModelProvider.OLLAMA


# =============================================================================
# QUESTION-ANSWER DATA
# =============================================================================


class QuestionAnswer(BaseModel):
    """A single Q&A pair."""

    question: str
    answer: str


class QuestionAnswerEnhanced(QuestionAnswer):
    """Q&A pair with metadata for storage and tracking."""

    category: str | None = None
    domain: str | None = None
    source_data: list[Any] | None = None
    validated: bool = False
    validation_score: float | None = None
    needs_review: bool = True
    suggested_fix: str | None = None
    content_hash: str | None = None
    generated_at: datetime | None = None
    version: int = 0
    source_template: str | None = None
    generation_model: str | None = None
    validation_model: str | None = None
    run_id: str | None = None


# =============================================================================
# GENERATION TRACE
# =============================================================================


class GenerationTrace(BaseModel):
    """Captures the full LLM interaction trace for a single Q&A item."""

    item_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str = ""
    category: str = ""
    domain: str = ""
    source_template: str | None = None
    generator_name: str = ""
    generation_model: str = ""
    validation_model: str = ""
    created_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat() + "Z"
    )

    # Generation
    generation_prompt: str = ""
    generation_response: str = ""
    generation_parsed_ok: bool = True
    generation_latency_ms: int = 0

    # Validation rounds — list of dicts per round
    validation_rounds: list[dict] = Field(default_factory=list)

    # Final outcome
    final_outcome: str = "pending"  # accepted_first_attempt | accepted_after_fix | rejected | skipped
    total_rounds: int = 0
    final_score: float | None = None


# =============================================================================
# VALIDATION METRICS
# =============================================================================


class ValidationMetrics(BaseModel):
    """Collects success/failure metrics for Q&A pair validation."""

    model_config = ConfigDict(populate_by_name=True)

    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    generator_name: str = "unknown"
    generation_model: str = "unknown"
    validation_model: str = "unknown"
    doc_id: str = Field(default_factory=lambda: str(uuid.uuid4()), alias="_id")

    # Counters
    total_candidates: int = 0
    total_validated: int = 0
    total_skipped: int = 0
    total_passed: int = 0
    total_failed: int = 0
    total_fix_attempts: int = 0
    total_first_attempt_passes: int = 0
    total_pass_after_fix: int = 0
    total_failed_first_attempt: int = 0
    total_failed_after_fixes: int = 0

    # Per-category and per-template breakdowns
    category_stats: dict[str, dict] = Field(default_factory=dict)
    template_stats: dict[str, dict] = Field(default_factory=dict)

    def _ensure_bucket(self, stats: dict[str, dict], key: str) -> None:
        if key not in stats:
            stats[key] = {
                "candidates": 0,
                "validated": 0,
                "skipped": 0,
                "passed": 0,
                "failed": 0,
                "fix_attempts": 0,
                "first_attempt_passes": 0,
                "pass_after_fix": 0,
                "failed_first_attempt": 0,
                "failed_after_fixes": 0,
                "scores": [],
            }

    def record_candidate(self, category: str, template: str | None = None) -> None:
        self.total_candidates += 1
        self._ensure_bucket(self.category_stats, category)
        self.category_stats[category]["candidates"] += 1
        if template:
            self._ensure_bucket(self.template_stats, template)
            self.template_stats[template]["candidates"] += 1

    def record_validation_attempt(self, category: str, template: str | None = None) -> None:
        self.total_validated += 1
        self._ensure_bucket(self.category_stats, category)
        self.category_stats[category]["validated"] += 1
        if template:
            self._ensure_bucket(self.template_stats, template)
            self.template_stats[template]["validated"] += 1

    def record_skip(self, category: str, template: str | None = None) -> None:
        self.total_skipped += 1
        self._ensure_bucket(self.category_stats, category)
        self.category_stats[category]["skipped"] += 1
        if template:
            self._ensure_bucket(self.template_stats, template)
            self.template_stats[template]["skipped"] += 1

    def record_first_attempt_pass(
        self, score: float | None, category: str, template: str | None = None
    ) -> None:
        self.total_passed += 1
        self.total_first_attempt_passes += 1
        self._ensure_bucket(self.category_stats, category)
        self.category_stats[category]["passed"] += 1
        self.category_stats[category]["first_attempt_passes"] += 1
        if score is not None:
            self.category_stats[category]["scores"].append(score)
        if template:
            self._ensure_bucket(self.template_stats, template)
            self.template_stats[template]["passed"] += 1
            self.template_stats[template]["first_attempt_passes"] += 1
            if score is not None:
                self.template_stats[template]["scores"].append(score)

    def record_pass_after_fix(
        self, score: float | None, category: str, template: str | None = None
    ) -> None:
        self.total_passed += 1
        self.total_pass_after_fix += 1
        self._ensure_bucket(self.category_stats, category)
        self.category_stats[category]["passed"] += 1
        self.category_stats[category]["pass_after_fix"] += 1
        if score is not None:
            self.category_stats[category]["scores"].append(score)
        if template:
            self._ensure_bucket(self.template_stats, template)
            self.template_stats[template]["passed"] += 1
            self.template_stats[template]["pass_after_fix"] += 1
            if score is not None:
                self.template_stats[template]["scores"].append(score)

    def record_failed_first_attempt(
        self, category: str, template: str | None = None
    ) -> None:
        self.total_failed += 1
        self.total_failed_first_attempt += 1
        self._ensure_bucket(self.category_stats, category)
        self.category_stats[category]["failed"] += 1
        self.category_stats[category]["failed_first_attempt"] += 1
        if template:
            self._ensure_bucket(self.template_stats, template)
            self.template_stats[template]["failed"] += 1
            self.template_stats[template]["failed_first_attempt"] += 1

    def record_failed_after_fixes(
        self, category: str, template: str | None = None
    ) -> None:
        self.total_failed += 1
        self.total_failed_after_fixes += 1
        self._ensure_bucket(self.category_stats, category)
        self.category_stats[category]["failed"] += 1
        self.category_stats[category]["failed_after_fixes"] += 1
        if template:
            self._ensure_bucket(self.template_stats, template)
            self.template_stats[template]["failed"] += 1
            self.template_stats[template]["failed_after_fixes"] += 1

    def record_fix_attempt(self, category: str, template: str | None = None) -> None:
        self.total_fix_attempts += 1
        self._ensure_bucket(self.category_stats, category)
        self.category_stats[category]["fix_attempts"] += 1
        if template:
            self._ensure_bucket(self.template_stats, template)
            self.template_stats[template]["fix_attempts"] += 1

    def summary(self) -> dict[str, Any]:
        """Return a flat summary dict."""

        def _avg(scores: list[float]) -> float | None:
            return round(sum(scores) / len(scores), 2) if scores else None

        total_validated_or_skipped = self.total_validated + self.total_skipped
        total_with_fixes = self.total_pass_after_fix + self.total_failed_after_fixes

        def _substats(stats: dict[str, dict]) -> dict[str, dict]:
            return {
                k: {
                    "candidates": v["candidates"],
                    "validated": v["validated"],
                    "skipped": v["skipped"],
                    "passed": v["passed"],
                    "failed": v["failed"],
                    "fix_attempts": v["fix_attempts"],
                    "first_attempt_passes": v["first_attempt_passes"],
                    "pass_after_fix": v["pass_after_fix"],
                    "failed_first_attempt": v["failed_first_attempt"],
                    "failed_after_fixes": v["failed_after_fixes"],
                    "avg_score": _avg(v["scores"]),
                    "pass_rate": (
                        round(v["passed"] / v["validated"] * 100, 1)
                        if v["validated"] > 0
                        else 0
                    ),
                }
                for k, v in stats.items()
            }

        return {
            "generation_model": self.generation_model,
            "validation_model": self.validation_model,
            "total_candidates": self.total_candidates,
            "total_validated": self.total_validated,
            "total_skipped": self.total_skipped,
            "total_passed": self.total_passed,
            "total_failed": self.total_failed,
            "overall_pass_rate": (
                round(self.total_passed / self.total_validated * 100, 1)
                if self.total_validated > 0
                else 0
            ),
            "first_attempt_pass_rate": (
                round(self.total_first_attempt_passes / self.total_validated * 100, 1)
                if self.total_validated > 0
                else 0
            ),
            "fix_recovery_rate": (
                round(self.total_pass_after_fix / total_with_fixes * 100, 1)
                if total_with_fixes > 0
                else None
            ),
            "by_category": _substats(self.category_stats),
            "by_template": _substats(self.template_stats),
        }
