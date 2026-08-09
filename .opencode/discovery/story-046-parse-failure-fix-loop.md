# Story 046 — Filter Validator Transport Failures Out of the Fix Loop

## Status
🔄 In Progress (plan approved, implementation pending)

## Priority
High

## Problem
Trace analysis of run `7c58c422` exposed two compounding issues:

1. **Wrong validator was being used.** All 27 `run_*.sh` wrapper scripts default
   `VALIDATION_MODEL` to `deepseek-v4-flash`, while the generator dashboard's
   `config.py` declares `glm-5.2` as the default. Launches that invoke a
   `run_*.sh` script without an explicit 3rd arg (e.g. `nohup ./run_combos.sh 1000`)
   silently use `deepseek-v4-flash`, which returns empty/truncated JSON
   ("Validation parse failed: Expecting value...", "Unterminated string")
   at a very high rate — cratering first-attempt pass rate (10.7% vs 46.3% on the
   GLM-5.2 benchmark) and permanently rejecting mechanically-fine answers at
   score 0 (e.g. the Ashaya/Scryb Ranger batch).
2. **Parse failures flood sibling feedback.** Every rejection reason — including
   validator parse failures — is appended to `sibling_corrections` in
   `validate_and_loop_with_suggested_fix` with no cap or dedup, so by round 3 the
   regeneration prompt contains 5–8 repeated lines of
   "Q1 was rejected for: Validation parse failed…" — noise that doesn't help the
   generator. Parse failures also burn regeneration attempts and inflate
   `record_fix_attempt` / failure metrics.

## Acceptance Criteria
- [ ] All 27 `run_*.sh` scripts default `VALIDATION_MODEL` to `glm-5.2`
      (matching `generator-dashboard/config.py`); stale `glm-5.1` comment in
      `run_combos.sh` updated.
- [ ] `query_model.py` exposes `is_transport_failure_reason(reason)` that
      recognizes the `"Validation parse failed"` / `"Validation error"` reason
      prefixes returned by `validate_qa` / `validate_with_model`.
- [ ] In `validate_and_loop_with_suggested_fix`, a transport-failure rejection
      re-validates the SAME answer (bounded retries, e.g. 2) WITHOUT:
      regenerating, counting a fix attempt, or appending sibling feedback.
      After retries are exhausted the item is rejected without regeneration.
- [ ] Sibling corrections are deduped per QA (replacing the entry for the same
      QA index) so the accumulated list never grows unbounded, and
      transport-failure reasons never appear in it.
- [ ] `observer.py` excludes transport-failure reasons from the top-rejection
      stats fed to the observer LLM.
- [ ] `batch_validate.py` unpacks the 3-tuple returned by `validate_qa`
      (previously unpacked 4 values → crash).
- [ ] New unit tests cover: parse-failure retry (no regeneration, no fix-attempt
      accounting), exhausted-retry rejection, parse failures excluded from
      sibling feedback, and per-QA dedupe.
- [ ] Full pytest suite passes with no new failures
      (`pytest training_data/generate_synthetic_data/ -v`).

## Notes
- `main.py` never auto-selects a validator; it consumes `--validation-model`.
  The scripts' `VALIDATION_MODEL` default is the de-facto source of truth for
  both direct launches and the dashboard (dashboard reads script defaults via
  `config.script_model_defaults()`).
- Generation-model drift (`gemma4:31b-small` in scripts vs `gemma4:31b` in
  `config.py`) is tracked as a follow-up, not part of this story.
