"""Validation pipeline with regeneration loop — domain-agnostic."""

from __future__ import annotations

import logging
from typing import Any

from .models import GenerationTrace, Model, QuestionAnswerEnhanced

logger = logging.getLogger(__name__)

# Maximum number of fix attempts before giving up on a generated item
MAX_FIX_ATTEMPTS: int = 3


def validate_and_loop_with_suggested_fix(
    qa_enhanced: QuestionAnswerEnhanced,
    system_message: str,
    notation_legend: str,
    validation_model: Model,
    generation_model: Model,
    trace: GenerationTrace,
    extra_validation_rules: list[str] | None = None,
    source_id: str = "",
) -> tuple[bool, QuestionAnswerEnhanced | None]:
    """Validate a generated Q&A pair and attempt regeneration on failure.

    Core validation + regeneration loop that is fully domain-agnostic.
    Domain-specific context (system message, notation legend, extra rules)
    is passed as parameters rather than imported from hardcoded constants.

    Flow:
        1. Validate the current Q&A via LLM validator
        2. If valid → return immediately with accepted status
        3. If invalid but has suggested fix → regenerate and retry (up to MAX_FIX_ATTEMPTS)
        4. If exhausted retries or no fix possible → mark as rejected

    Args:
        qa_enhanced: The generated Q&A pair with metadata.
        system_message: Domain-specific LLM system prompt/persona.
        notation_legend: Domain-specific reference material for the validator.
        validation_model: LLM model used for validation checks.
        generation_model: LLM model used for regeneration/fix attempts.
        trace: GenerationTrace to record validation rounds and outcomes.
        extra_validation_rules: Additional domain-specific rules injected into
            the validation prompt (e.g., from TemplateConfig.validation_rules).
        source_id: Human-readable identifier of the source record, included in
            error context for debugging.

    Returns:
        Tuple of (is_valid, validated_qa | None).
        is_valid=True means the Q&A passed validation and can be used.
    """
    extra_validation_rules = extra_validation_rules or []
    template_id = qa_enhanced.source_template

    # --- First validation attempt -------------------------------------------

    is_valid, doc = _validate_qa(
        qa=qa_enhanced,
        system_message=system_message,
        notation_legend=notation_legend,
        validation_model=validation_model,
        extra_rules=extra_validation_rules,
        source_id=source_id,
    )

    trace.total_rounds = 1
    _record_validation_round(trace, round_num=1, is_valid=is_valid, doc=doc)

    if is_valid and doc is not None:
        # First attempt passed — record outcome on trace for callback processing
        score = doc.validation_score
        trace.final_outcome = "accepted_first_attempt"
        trace.final_score = score
        return True, doc

    # --- Fix loop -----------------------------------------------------------

    suggested_fix = _extract_suggested_fix(doc) if doc else None

    if not suggested_fix:
        logger.warning(
            "Validation failed for source %s with no suggested fix — rejecting",
            source_id,
        )
        trace.final_outcome = "rejected"
        return False, None

    # Attempt regeneration up to MAX_FIX_ATTEMPTS times
    for attempt in range(1, MAX_FIX_ATTEMPTS + 1):
        logger.info(
            "Fix attempt %d/%d for source %s (template=%s)",
            attempt,
            MAX_FIX_ATTEMPTS,
            source_id,
            template_id or "unknown",
        )

        # Regenerate using the suggested fix
        fixed_qa = _regenerate_with_fix(
            original=qa_enhanced,
            suggested_fix=suggested_fix,
            system_message=system_message,
            notation_legend=notation_legend,
            generation_model=generation_model,
            source_id=source_id,
        )

        if fixed_qa is None:
            logger.warning(
                "Regeneration failed for source %s on attempt %d — rejecting",
                source_id,
                attempt,
            )
            break

        # Validate the regenerated Q&A
        round_num = 1 + attempt
        is_valid, doc = _validate_qa(
            qa=fixed_qa,
            system_message=system_message,
            notation_legend=notation_legend,
            validation_model=validation_model,
            extra_rules=extra_validation_rules,
            source_id=source_id,
        )

        trace.total_rounds = round_num
        _record_validation_round(trace, round_num=round_num, is_valid=is_valid, doc=doc)

        if is_valid and doc is not None:
            logger.info(
                "Source %s passed validation after fix attempt %d",
                source_id,
                attempt,
            )
            trace.final_outcome = "accepted_after_fix"
            trace.final_score = doc.validation_score
            return True, doc

        # Prepare for next iteration
        suggested_fix = _extract_suggested_fix(doc) if doc else None
        if not suggested_fix:
            logger.warning(
                "Fix attempt %d for source %s returned no further fix — rejecting",
                attempt,
                source_id,
            )
            break

    # Exhausted all attempts
    logger.warning(
        "Source %s failed validation after %d rounds — rejecting",
        source_id,
        trace.total_rounds,
    )
    trace.final_outcome = "rejected"
    return False, None


# =============================================================================
# INTERNAL HELPERS
# =============================================================================


def _validate_qa(
    qa: QuestionAnswerEnhanced,
    system_message: str,
    notation_legend: str,
    validation_model: Model,
    extra_rules: list[str] | None = None,
    source_id: str = "",
) -> tuple[bool, QuestionAnswerEnhanced | None]:
    """Send a Q&A pair to the validator LLM and parse the result.

    Returns (is_valid, updated_qa). If invalid, qa.suggested_fix may be set.
    """
    from .query_model import QueryModel

    extra_rules = extra_rules or []

    # Build validation prompt — fully domain-ized via parameters
    rules_text = ""
    if extra_rules:
        rules_text = "\n\nAdditional validation rules:\n" + "\n".join(
            f"  - {rule}" for rule in extra_rules
        )

    validation_prompt = (
        "You are a quality validator for training data. Review the following "
        "question-answer pair and determine if it meets all criteria.\n\n"
        f"{notation_legend}\n{rules_text}\n\n"
        "---\n\n"
        f"**Question:** {qa.question}\n\n"
        f"**Answer:** {qa.answer}\n\n"
        "---\n\n"
        "Respond with a JSON object:\n"
        '  {{\n'
        '    "is_valid": true/false,\n'
        '    "score": <0-100>,\n'
        '    "issues": ["issue1", ...],\n'
        '    "suggested_fix": "<how to fix the answer>",\n'
        '  }}\n\n'
        "If valid, set is_valid=true and suggested_fix can be empty.\n"
        "If invalid, list specific issues and provide a concrete suggested_fix."
    )

    try:
        qm = QueryModel(
            model_name=validation_model.name,
            provider_url=validation_model.provider_url,
            api_key=validation_model.api_key,
        )
        raw_response = qm.query(system_message, validation_prompt)
    except Exception as e:
        logger.error(
            "Validation LLM call failed for source %s: %s",
            source_id,
            e,
            exc_info=True,
        )
        return False, None

    # Parse response
    import json
    import re

    json_match = re.search(r"\{[^{}]*\}", raw_response, re.DOTALL)
    if not json_match:
        logger.warning(
            "Could not parse validation JSON for source %s",
            source_id,
        )
        return False, None

    try:
        result = json.loads(json_match.group())
    except json.JSONDecodeError as e:
        logger.warning(
            "Validation JSON decode error for source %s: %s",
            source_id,
            e,
        )
        return False, None

    is_valid = bool(result.get("is_valid", False))
    score = result.get("score")
    _issues = result.get("issues", [])  # available for future use in trace enrichment
    suggested_fix = result.get("suggested_fix", "")

    # Update the Q&A with validation results
    qa_copy = qa.model_copy()
    qa_copy.validated = is_valid
    qa_copy.validation_score = score
    qa_copy.needs_review = not is_valid
    qa_copy.suggested_fix = suggested_fix if not is_valid else None
    qa_copy.validation_model = validation_model.name

    return is_valid, qa_copy


def _regenerate_with_fix(
    original: QuestionAnswerEnhanced,
    suggested_fix: str,
    system_message: str,
    notation_legend: str,
    generation_model: Model,
    source_id: str = "",
) -> QuestionAnswerEnhanced | None:
    """Regenerate the answer using the validator's suggested fix.

    Preserves the original question but rewrites the answer based on feedback.
    """
    from .query_model import QueryModel

    regen_prompt = (
        "Rewrite the following answer to address the validation feedback.\n\n"
        f"{notation_legend}\n\n"
        "---\n\n"
        f"**Original Question:** {original.question}\n\n"
        f"**Original Answer:** {original.answer}\n\n"
        f"**Validation Feedback / Suggested Fix:**\n{suggested_fix}\n\n"
        "---\n\n"
        "Respond with a JSON object:\n"
        '  {{\n'
        '    "question": "<the question, unchanged>",\n'
        '    "answer": "<the improved answer that addresses the feedback>",\n'
        '  }}'
    )

    try:
        qm = QueryModel(
            model_name=generation_model.name,
            provider_url=generation_model.provider_url,
            api_key=generation_model.api_key,
        )
        raw_response = qm.query(system_message, regen_prompt)
    except Exception as e:
        logger.error(
            "Regeneration LLM call failed for source %s: %s",
            source_id,
            e,
            exc_info=True,
        )
        return None

    # Parse response
    import json
    import re

    json_match = re.search(r"\{[^{}]*\}", raw_response, re.DOTALL)
    if not json_match:
        logger.warning(
            "Could not parse regeneration JSON for source %s",
            source_id,
        )
        return None

    try:
        result = json.loads(json_match.group())
        question = result.get("question", "").strip()
        answer = result.get("answer", "").strip()
        if not question or not answer:
            return None
    except (json.JSONDecodeError, AttributeError) as e:
        logger.warning(
            "Regeneration JSON parse error for source %s: %s",
            source_id,
            e,
        )
        return None

    # Return enhanced Q&A with updated answer and incremented version
    fixed = original.model_copy()
    fixed.question = question
    fixed.answer = answer
    fixed.version += 1
    fixed.suggested_fix = None
    fixed.validated = False
    fixed.validation_score = None
    fixed.needs_review = True

    return fixed


def _extract_suggested_fix(doc: QuestionAnswerEnhanced | None) -> str | None:
    """Extract the suggested fix string from a validation result."""
    if doc is None:
        return None
    fix = doc.suggested_fix
    if fix and fix.strip():
        return fix.strip()
    return None


def _record_validation_round(
    trace: GenerationTrace, round_num: int, is_valid: bool, doc: QuestionAnswerEnhanced | None
) -> None:
    """Append a validation round record to the trace."""
    round_record: dict[str, Any] = {
        "round": round_num,
        "is_valid": is_valid,
    }

    if doc is not None:
        round_record["score"] = doc.validation_score
        round_record["suggested_fix"] = doc.suggested_fix

    trace.validation_rounds.append(round_record)
