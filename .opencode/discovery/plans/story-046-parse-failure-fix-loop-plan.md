# Story 046 Technical Plan — Filter Validator Transport Failures Out of the Fix Loop

## Goal
Stop validator transport failures (unparseable/truncated/errored responses) from
being treated as answer-quality rejections: they must not burn regeneration
attempts, inflate fix metrics, permanently reject good answers, flood sibling
feedback, or drive observer template changes. Also reconcile the drifted
`VALIDATION_MODEL` default in the run scripts.

## Changes

### 1. Reconcile validator config — all 27 `run_*.sh`
Replace `deepseek-v4-flash` → `glm-5.2` in every
`VALIDATION_MODEL=${3:-https://server.tailc63ae8.ts.net:4444/v1,openai,deepseek-v4-flash,$LITELLM_API_KEY}`
line. Update the stale `glm-5.1` usage comment in `run_combos.sh` (line 3).
Do not touch `MODEL` / `OBSERVER_MODEL` defaults.

### 2. `query_model.py` — transport-failure predicate
Add near the top (after `logger`):
```python
VALIDATION_PARSE_FAILURE_PREFIX = "Validation parse failed"
VALIDATION_TRANSPORT_ERROR_PREFIX = "Validation error"

def is_transport_failure_reason(reason: str | None) -> bool:
    """True when the rejection came from the validator itself (unparseable,
    truncated, or errored response), not from a content-quality verdict."""
    if not reason:
        return False
    return reason.startswith(VALIDATION_PARSE_FAILURE_PREFIX) or reason.startswith(VALIDATION_TRANSPORT_ERROR_PREFIX)
```
Both `validate_qa` (lines ~291, ~301) and `validate_with_model` (lines ~226,
~231) already return reasons with exactly these prefixes.

### 3. `common.py` — `validate_and_loop_with_suggested_fix`
- Import `is_transport_failure_reason` from `.query_model`.
- Module constant `_MAX_VALIDATION_PARSE_RETRIES = 2`.
- Helper:
```python
def _upsert_sibling_correction(sibling_corrections: list[str], q_index: int, reason: str) -> None:
    prefix = f"Q{q_index + 1} was rejected for: "
    correction = (f"{prefix}{reason}. The corrected answer now fixes that issue. "
                  f"Apply the same fix to any similar errors in your answer.")
    for i, existing in enumerate(sibling_corrections):
        if existing.startswith(prefix):
            sibling_corrections[i] = correction
            return
    sibling_corrections.append(correction)
```
- In the loop, initialize `parse_retries_left = _MAX_VALIDATION_PARSE_RETRIES`.
- At the top of the `if not is_valid:` branch, handle transport failures BEFORE
  the regeneration path:
```python
if is_transport_failure_reason(reason):
    if parse_retries_left > 0:
        parse_retries_left -= 1
        print(f"    ⚠️  Validator unparseable — re-validating same answer (retries left {parse_retries_left})")
        round_num += 1
        if trace is not None:
            trace.validation_rounds.append(round_data)
        continue
    print(f"    ✗ REJECTED — validator produced no parseable response after retries: {qa.question[:80]}")
    if trace is not None:
        trace.validation_rounds.append(round_data)
    break
```
- In the successful-regeneration branch, replace the plain `sibling_corrections.append(...)`
  with `_upsert_sibling_correction(sibling_corrections, enumerated_i, reason)`
  (only reachable for non-transport rejections, but keep a
  `not is_transport_failure_reason(reason)` guard for safety).

### 4. `observer.py`
Import `is_transport_failure_reason`. In `_analyze`'s reason-counting loop
(around line 339), `continue` when
`is_transport_failure_reason(reason)` so the LLM stats exclude transport noise.

### 5. `batch_validate.py`
Line 165: unpack the 3-tuple —
```python
is_valid, reason, score = query_model.validate_qa(...)
suggested_fix = None
```

### 6. Tests — `test_generation_trace.py`
Extend `MockQueryModel.regenerate_answer` to record
`self.sibling_feedbacks.append(sibling_feedback)`. Add to the
validate-and-loop test class:
- `test_parse_failure_revalidates_same_answer` — responses
  `[(False, "Validation parse failed: Expecting value: line 1 column 1 (char 0)", 0), (True, "OK", 8.0)]` →
  accepted, `regenerate_call_count == 0`, `validate_call_count == 2`,
  `metrics.record_fix_attempt` not called, passed-in `sibling_corrections` unchanged.
- `test_parse_failure_exhausted_retries_rejects_without_regeneration` — 3
  consecutive parse failures → rejected, `regenerate_call_count == 0`,
  `record_fix_attempt` not called, `record_failed_first_attempt` called,
  `final_outcome == "rejected"`.
- `test_parse_failure_not_in_sibling_feedback` — QA1: parse fail → genuine
  reject → fix → pass; QA2: genuine reject → fix → pass; assert the
  `sibling_feedback` received for QA2's regeneration contains no
  `"Validation parse failed"`.
- `test_sibling_corrections_dedupe_per_qa` — single QA rejected twice with
  different genuine reasons then fixed; assert `sibling_corrections` length 1
  and it contains the latest reason.
- `test_is_transport_failure_reason` — unit tests for the predicate
  (parse prefix, error prefix, content reasons, None, empty).

## Verification
`pytest training_data/generate_synthetic_data/ -v` — baseline 368 passing /
20 pre-existing failures; no new failures.

## Risks / Notes
- The parse-retry adds up to 2 extra validation calls per transport failure;
  latency cost is acceptable and only hits when the validator is misbehaving.
- Trace round data for retries is recorded with incrementing `round_num`, so
  `total_rounds`/`final_outcome` stay correct.
- Content rejections behave exactly as before (regenerate loop, up to 3
  attempts) — no behavior change for genuine quality failures.
