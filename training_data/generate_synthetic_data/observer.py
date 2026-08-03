"""Observer — analyzes generation traces and improves templates via LLM.

After every N items per generator, the Observer:
  1. Reads buffered generation/validation traces for that category
  2. Computes first-pass rate and regeneration statistics
  3. If first-pass rate is below threshold AND items needed ≥1 regeneration:
     → sends trace summary to LLM for generation template improvement
     → writes a complete new versioned YAML to templates/
  4. If any items needed ≥1 regeneration (regardless of rate):
     → sends trace summary to LLM for validator prompt improvement
     → writes a complete new versioned validator YAML to templates/
  5. Updates _observer_manifest.json with version performance history

Template versions are persisted only to disk (no MongoDB writes). The manifest
tracks which version performed best across all runs, enabling automatic revert
to the historically-best template on subsequent runs.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .models import Model, ModelType
from .query_model import QueryModel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------

_DEFAULT_MANIFEST = {"categories": {}}


def _load_manifest(path: Path) -> dict:
    """Load the observer manifest JSON, returning a fresh default if missing."""
    if not path.is_file():
        return _fresh_manifest()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "categories" in data:
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return _fresh_manifest()


def _fresh_manifest() -> dict:
    """Return a deep-copied default manifest so mutations never leak between instances."""
    return json.loads(json.dumps(_DEFAULT_MANIFEST))


def _save_manifest(path: Path, manifest: dict) -> None:
    """Write the observer manifest JSON atomically."""
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(path)


def _ensure_category(
    manifest: dict,
    category: str,
    templates_dir: Path | None = None,
) -> dict:
    """Ensure *category* exists in the manifest; return its entry.

    Backward-compatible migration: a manifest written by older versions
    (single shared ``active_version`` / ``versions``) is migrated to the
    generation or validator namespace based on which versioned template file
    actually exists on disk (when *templates_dir* is provided). Without a
    templates directory the legacy counter defaults to the generation namespace.
    """
    cat = manifest.setdefault("categories", {}).setdefault(category, {})
    if "active_generation_version" not in cat:
        cat["active_generation_version"] = 1
    if "active_validator_version" not in cat:
        cat["active_validator_version"] = 1
    if "generation_versions" not in cat:
        if "versions" in cat:
            legacy = cat.get("active_version")
            target = "generation"
            if templates_dir is not None and legacy:
                from .yaml_template_loader import legacy_version_target

                target = legacy_version_target(templates_dir, category, int(legacy))
            if target == "validator":
                # Old single-counter schema → validator version improvement
                cat["validator_versions"] = cat.pop("versions")
                if "active_version" in cat:
                    cat["active_validator_version"] = cat.pop("active_version")
                cat["generation_versions"] = {}
            else:
                # Old single-counter schema → treat as generation versions
                cat["generation_versions"] = cat.pop("versions")
                if "active_version" in cat:
                    cat["active_generation_version"] = cat.pop("active_version")
        else:
            cat["generation_versions"] = {}
    if "validator_versions" not in cat:
        cat["validator_versions"] = {}
    return cat


def _best_version(cat_data: dict, key: str = "first_pass_rate") -> int:
    """Return the version with the highest recorded rate, or 1.

    Args:
        cat_data: A category entry from the manifest.
        key: Metric to rank by — ``"first_pass_rate"`` for generation
            templates, ``"regen_rate"`` for validator templates.
    """
    versions = cat_data.get("generation_versions", {})
    if key == "regen_rate":
        versions = cat_data.get("validator_versions", {})
    if not versions:
        return 1
    best = max(
        versions.items(),
        key=lambda kv: (kv[1].get(key) or 0.0, int(kv[0])),
    )
    return int(best[0])


# ---------------------------------------------------------------------------
# LLM prompt builders
# ---------------------------------------------------------------------------

_GENERATION_PROMPT_TEMPLATE = """\
You are an expert prompt engineer for Magic: The Gathering Q&A generation.

CURRENT TEMPLATE INSTRUCTION (template_id: {template_id}):
{current_instruction}

RECENT GENERATION RESULTS ({total_items} items analyzed):
- First-pass pass rate: {first_pass_rate:.1f}%
- Threshold for improvement: {threshold:.1f}%
- Items needing ≥1 regeneration: {regeneration_count}/{total_items}
- Items rejected after all attempts: {failed_after_fixes}/{total_items}

Top rejection reasons from first validation round (most frequent first):
{rejection_reasons}

SUGGEST an improved template instruction that would increase the first-pass \
pass rate. Focus on clarifying ambiguities, adding explicit constraints, or \
restructuring the prompt to prevent the most common failures. Keep the same \
style and format as the original — only change what is needed.

Output ONLY valid JSON (no markdown fences):
{{
  "new_instruction": "...",
  "rationale": "...",
  "expected_improvement": "..."
}}
"""


_VALIDATOR_PROMPT_TEMPLATE = """\
You are an expert prompt engineer for Magic: The Gathering Q&A validation.

RECENT VALIDATION RESULTS ({total_items} items analyzed):
- Items requiring ≥1 regeneration: {regeneration_count}/{total_items}
- Items rejected after all attempts: {failed_after_fixes}/{total_items}
- First-pass pass rate: {first_pass_rate:.1f}%

Top rejection reasons from first validation round (most frequent first):
{rejection_reasons}

CURRENT VALIDATOR PROMPT EXCERPT (relevant section):
{validator_excerpt}

SUGGEST additions or modifications to the validation prompt that would \
catch these issues earlier or provide clearer feedback for regeneration. \
Focus on what the validator should check MORE carefully or what explicit \
rules it should enforce. Keep changes minimal and targeted — do not rewrite \
the entire prompt.

Output ONLY valid JSON (no markdown fences):
{{
  "suggested_additions": "...",
  "rationale": "...",
  "target_round": "first_validation | regeneration_feedback"
}}
"""


# ---------------------------------------------------------------------------
# Observer
# ---------------------------------------------------------------------------

class Observer:
    """Analyzes generation traces and improves templates via LLM.

    Args:
        models: Dict with ModelType keys; OBSERVER model used for analysis.
        yaml_loader: :class:`YamlTemplateLoader` for reading current templates.
        templates_dir: Path to the ``templates/`` directory.
        first_pass_threshold: First-pass rate below which generation template \
            improvement is triggered (default 50.0).
        observation_interval: Number of items per generator before analysis \
            runs (default 10).
        run_id: Current run identifier for manifest tracking.
        observer_model: Model to use for LLM analysis; defaults to the \
            VALIDATION model if not provided.
    """

    def __init__(
        self,
        models: dict[ModelType, Model],
        yaml_loader,
        templates_dir: Path | str,
        first_pass_threshold: float = 50.0,
        observation_interval: int = 10,
        run_id: str = "",
        observer_model: Model | None = None,
    ):
        self._models = models
        self._yaml_loader = yaml_loader
        self._templates_dir = Path(templates_dir)
        self._first_pass_threshold = first_pass_threshold
        self._observation_interval = observation_interval
        self._run_id = run_id

        # Use the observer-specific model if provided, otherwise fall back to validation model
        self._observer_model = observer_model or models.get(ModelType.VALIDATION)

        self._query_model = QueryModel()
        self._query_model.yaml_loader = yaml_loader

        self._manifest_path = self._templates_dir / "_observer_manifest.json"
        self._manifest = _load_manifest(self._manifest_path)
        self._buffers: dict[str, list[dict]] = {}
        self._item_counts: dict[str, int] = {}
        self._analysis_done: set[str] = set()
        self._last_metrics: dict[str, dict | None] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_item_processed(
        self,
        category: str,
        trace_dict: dict,
        metrics_summary: dict | None = None,
    ) -> None:
        """Called after each item completes validation.

        Buffers the trace and triggers analysis when the interval is reached.
        """
        self._buffers.setdefault(category, []).append(trace_dict)
        self._item_counts[category] = self._item_counts.get(category, 0) + 1
        self._last_metrics[category] = metrics_summary

        if self._item_counts[category] >= self._observation_interval:
            self._analyze(category, metrics_summary)

    def flush(self) -> None:
        """Final analysis pass for any remaining buffered traces."""
        for category in list(self._buffers.keys()):
            if self._buffers[category]:
                self._analyze(category, None)

    def get_best_template_version(self, category: str) -> int:
        """Return the historically best *generation* template version."""
        cat_data = _ensure_category(self._manifest, category, self._templates_dir)
        return _best_version(cat_data, key="first_pass_rate")

    def get_best_validator_version(self, category: str) -> int:
        """Return the historically best *validator* template version."""
        cat_data = _ensure_category(self._manifest, category, self._templates_dir)
        return _best_version(cat_data, key="regen_rate")

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def _analyze(
        self,
        category: str,
        metrics_summary: dict | None = None,
    ) -> None:
        """Run observer analysis on buffered traces for *category*."""
        traces = self._buffers.get(category, [])
        if not traces:
            return

        # Prefer per-QA-pair stats from the metrics summary so observer decisions
        # match the printed metrics. Fall back to per-trace counts when no summary
        # is available (e.g. tests).
        metrics_summary = metrics_summary or self._last_metrics.get(category)
        by_cat = None
        if metrics_summary:
            by_cat = (metrics_summary.get("by_category") or {}).get(category)

        if by_cat:
            total_items = by_cat.get("candidates", 0) or len(traces)
            first_passes = by_cat.get("first_attempt_passes", 0) or 0
            passes_after_fix = by_cat.get("pass_after_fix", 0) or 0
            failed_after_fixes = by_cat.get("failed_after_fixes", 0) or 0
            validated = by_cat.get("validated", 0) or 0
        else:
            total_items = len(traces)
            first_passes = sum(
                1 for t in traces
                if t.get("final_outcome") == "accepted_first_attempt"
            )
            passes_after_fix = sum(
                1 for t in traces
                if t.get("final_outcome") == "accepted_after_fix"
            )
            failed_after_fixes = sum(
                1 for t in traces
                if t.get("final_outcome") == "rejected"
            )
            validated = total_items

        regeneration_count = passes_after_fix + failed_after_fixes
        first_pass_rate = (first_passes / validated * 100) if validated > 0 else 0.0

        # Collect top rejection reasons from round-0 validation rounds
        reason_counts: dict[str, int] = {}
        for t in traces:
            rounds = t.get("validation_rounds") or []
            if rounds:
                r0 = rounds[0]
                reason = r0.get("reason") or r0.get("errors") or ""
                if reason and reason.lower() not in ("none", "n/a", ""):
                    # Normalise short reasons for grouping
                    reason = self._normalise_reason(reason)
                    reason_counts[reason] = reason_counts.get(reason, 0) + 1

        top_reasons = sorted(reason_counts.items(), key=lambda x: -x[1])[:5]
        rejection_lines = "\n".join(
            f'  - "{reason}" — {count}×' for reason, count in top_reasons
        ) or "  (none recorded)"

        # Format validator excerpt from the first trace's round-0 prompt if available
        validator_excerpt = ""
        for t in traces:
            rounds = t.get("validation_rounds") or []
            if rounds and rounds[0].get("prompt"):
                validator_excerpt = rounds[0]["prompt"][:2000]
                break

        # Determine current template versions from metrics or trace
        current_gen_version = 1
        current_val_version = 1
        if metrics_summary:
            tv = metrics_summary.get("template_versions") or {}
            if tv:
                versions = [v for v in tv.values() if v is not None]
                if versions:
                    current_gen_version = max(int(v) for v in versions) or 1
            tvv = metrics_summary.get("validator_template_versions") or {}
            if tvv:
                versions = [v for v in tvv.values() if v is not None]
                if versions:
                    current_val_version = max(int(v) for v in versions) or 1

        print(
            f"[Observer] {category}: first_pass={first_pass_rate:.1f}% "
            f"regen={regeneration_count}/{total_items} "
            f"failed={failed_after_fixes} gen_ver={current_gen_version} val_ver={current_val_version}"
        )

        # --- Generation template improvement ---
        if first_pass_rate < self._first_pass_threshold and regeneration_count > 0:
            gen_improvement = self._llm_analyze_generation_template(
                category, current_gen_version,
                first_pass_rate, total_items, regeneration_count,
                failed_after_fixes, top_reasons,
            )
        else:
            gen_improvement = None

        # --- Validator template improvement ---
        if regeneration_count > 0:
            val_improvement = self._llm_analyze_validation_template(
                category, current_val_version,
                first_pass_rate, total_items, regeneration_count,
                failed_after_fixes, top_reasons, validator_excerpt,
            )
        else:
            val_improvement = None

        # --- Write improved templates and update manifest ---
        new_gen_version, new_val_version = self._write_improved_templates(
            category, current_gen_version, current_val_version,
            gen_improvement, val_improvement,
        )

        # Record performance for whichever template(s) actually improved
        if gen_improvement:
            self._record_version_performance(
                category, "generation", new_gen_version, first_pass_rate, total_items,
            )
        if val_improvement:
            regen_rate = (regeneration_count / total_items * 100) if total_items > 0 else 0.0
            self._record_version_performance(
                category, "validator", new_val_version, regen_rate, total_items,
            )

        # Clear buffers and mark analysis done for this run
        self._buffers[category] = []
        self._item_counts[category] = 0
        self._analysis_done.add(category)

    def _record_version_performance(
        self,
        category: str,
        template_type: str,
        version: int,
        rate: float,
        total_items: int,
    ) -> None:
        """Persist version performance to the manifest.

        Args:
            category: Generator category name.
            template_type: ``"generation"`` or ``"validator"`` — selects the
                version namespace and metric key to record.
            version: The new version number that was written.
            rate: First-pass rate (generation) or regen rate (validator).
            total_items: Number of items analyzed for this version.
        """
        cat_data = _ensure_category(self._manifest, category, self._templates_dir)
        ver_key = str(version)
        metric_key = "first_pass_rate" if template_type == "generation" else "regen_rate"
        versions = cat_data["generation_versions" if template_type == "generation" else "validator_versions"]
        run_ids = versions.setdefault(ver_key, {}).get("run_ids", [])
        if self._run_id and self._run_id not in run_ids:
            run_ids.append(self._run_id)

        # Compute running average across all runs for this version
        prev = versions.get(ver_key, {})
        prev_rate = prev.get(metric_key)
        prev_items = prev.get("total_items", 0)
        if prev_rate is not None and prev_items > 0:
            avg_rate = (prev_rate * prev_items + rate * total_items) / (prev_items + total_items)
        else:
            avg_rate = rate

        versions[ver_key] = {
            metric_key: round(avg_rate, 2),
            "total_items": prev_items + total_items,
            "run_ids": run_ids,
        }

        # Update the active version if this one is now the best
        best = _best_version(cat_data, key=metric_key)
        active_key = (
            "active_generation_version" if template_type == "generation"
            else "active_validator_version"
        )
        cat_data[active_key] = best

        _save_manifest(self._manifest_path, self._manifest)
        print(
            f"[Observer] Manifest updated: {category} {template_type} v{version} "
            f"{metric_key}={avg_rate:.1f}% active_{template_type}_version={best}"
        )

    # ------------------------------------------------------------------
    # LLM analysis
    # ------------------------------------------------------------------

    def _llm_analyze_generation_template(
        self,
        category: str,
        current_version: int,
        first_pass_rate: float,
        total_items: int,
        regeneration_count: int,
        failed_after_fixes: int,
        top_reasons: list[tuple[str, int]],
    ) -> dict | None:
        """Send trace summary to LLM and return {new_instruction, rationale}."""
        # Load current templates for the category
        current_templates = self._load_category_templates(category)
        if not current_templates:
            logger.warning("[Observer] No templates found for %s — skipping generation analysis", category)
            return None

        # Build rejection reasons text
        rejection_lines = "\n".join(
            f'  - "{reason}" — {count}×' for reason, count in top_reasons
        ) or "  (none recorded)"

        # Use the first template's instruction as representative
        sample_template = current_templates[0]
        template_id = sample_template.get("template_id", "unknown")
        current_instruction = sample_template.get("instruction", "")[:1500]

        prompt = _GENERATION_PROMPT_TEMPLATE.format(
            template_id=template_id,
            current_instruction=current_instruction,
            first_pass_rate=first_pass_rate,
            threshold=self._first_pass_threshold,
            total_items=total_items,
            regeneration_count=regeneration_count,
            failed_after_fixes=failed_after_fixes,
            rejection_reasons=rejection_lines,
        )

        return self._call_observer_llm(prompt, category, "generation")

    def _llm_analyze_validation_template(
        self,
        category: str,
        current_version: int,
        first_pass_rate: float,
        total_items: int,
        regeneration_count: int,
        failed_after_fixes: int,
        top_reasons: list[tuple[str, int]],
        validator_excerpt: str,
    ) -> dict | None:
        """Send trace summary to LLM and return {suggested_additions, rationale}."""
        rejection_lines = "\n".join(
            f'  - "{reason}" — {count}×' for reason, count in top_reasons
        ) or "  (none recorded)"

        prompt = _VALIDATOR_PROMPT_TEMPLATE.format(
            total_items=total_items,
            regeneration_count=regeneration_count,
            failed_after_fixes=failed_after_fixes,
            first_pass_rate=first_pass_rate,
            rejection_reasons=rejection_lines,
            validator_excerpt=validator_excerpt[:2000],
        )

        return self._call_observer_llm(prompt, category, "validator")

    def _call_observer_llm(
        self, prompt: str, category: str, template_type: str,
    ) -> dict | None:
        """Call the observer LLM and parse its JSON response."""
        if not self._observer_model:
            logger.warning("[Observer] No observer model configured — skipping %s analysis for %s", template_type, category)
            return None

        try:
            print(f"\n{'─'*60}")
            print(f"  → OBSERVER PROMPT ({len(prompt)} chars):")
            print(f"{'─'*60}")
            response = self._query_model.query(
                self._observer_model, prompt, max_tokens=2048, purpose="OBSERVER",
            )
            # Parse JSON from response
            response = response.replace("```json", "").replace("```", "").strip()
            if not response.startswith("{"):
                start = response.find("{")
                end = response.rfind("}")
                if start != -1 and end != -1:
                    response = response[start:end + 1]

            result = json.loads(response)
            print(f"[Observer] {template_type} analysis for {category}: OK")
            return result
        except (json.JSONDecodeError, Exception) as e:
            print(f"[Observer] ⚠️  {template_type} analysis failed for {category}: {e}")
            logger.warning("[Observer] %s analysis failed: %s", template_type, e)
            return None

    # ------------------------------------------------------------------
    # Template writing
    # ------------------------------------------------------------------

    def _write_improved_templates(
        self,
        category: str,
        current_gen_version: int,
        current_val_version: int,
        gen_improvement: dict | None,
        val_improvement: dict | None,
    ) -> tuple[int, int]:
        """Write improved YAML files and return ``(new_gen_version, new_val_version)``.

        Generation and validator versions are tracked independently, so an
        improvement to one never mislabels the other.
        """
        new_gen_version = current_gen_version
        new_val_version = current_val_version

        # Generation template improvement
        if gen_improvement and gen_improvement.get("new_instruction"):
            new_gen_version = current_gen_version + 1
            new_file = self._templates_dir / f"{category}_v{new_gen_version}.yaml"
            improved = self._apply_generation_improvement(category, gen_improvement["new_instruction"])
            if improved is not None:
                with open(new_file, "w", encoding="utf-8") as f:
                    yaml.dump(improved, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
                print(f"[Observer] Wrote {new_file}")
            else:
                logger.warning("[Observer] Could not apply generation improvement for %s", category)

        # Validator template improvement
        if val_improvement and val_improvement.get("suggested_additions"):
            new_val_version = current_val_version + 1
            new_file = self._templates_dir / f"{category}_validator_v{new_val_version}.yaml"
            improved_validator = self._apply_validator_improvement(category, val_improvement["suggested_additions"])
            if improved_validator is not None:
                with open(new_file, "w", encoding="utf-8") as f:
                    yaml.dump(improved_validator, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
                print(f"[Observer] Wrote {new_file}")
            else:
                logger.warning("[Observer] Could not apply validator improvement for %s", category)

        return new_gen_version, new_val_version

    def _load_category_templates(self, category: str) -> list[dict]:
        """Load all generation templates for a category from YAML."""
        if self._yaml_loader is None:
            return []
        template_ids = self._yaml_loader.list_templates(category)
        if not template_ids:
            return []
        result = []
        for tid in template_ids:
            doc = self._yaml_loader.get_latest(category, tid, "generation")
            if doc and isinstance(doc, dict):
                # Normalise: ensure instruction key exists
                entry = dict(doc)
                if "instruction" not in entry and "task_instruction" in entry:
                    entry["instruction"] = entry.pop("task_instruction")
                result.append(entry)
        return result

    def _apply_generation_improvement(
        self, category: str, new_instruction: str,
    ) -> list[dict] | None:
        """Return a copy of all templates for *category* with the improved instruction applied."""
        # Try to load from the latest versioned file or base file
        templates = self._load_category_templates(category)
        if not templates:
            return None

        result = []
        for entry in templates:
            new_entry = dict(entry)
            new_entry["instruction"] = new_instruction.strip()
            # Preserve other fields
            result.append(new_entry)
        return result

    def _apply_validator_improvement(
        self, category: str, suggested_additions: str,
    ) -> dict | None:
        """Return a copy of the validator template with additions appended."""
        if self._yaml_loader is None:
            return None

        # Try generator-specific validator override first, then shared
        doc = self._yaml_loader.get_latest(category, "validator", "validator")
        if not doc or not isinstance(doc, dict):
            # Fall back to shared qa_validation
            doc = self._yaml_loader.get_latest(
                self._yaml_loader.SHARED_NAMESPACE, "qa_validation", "validator",
            )

        if not doc:
            return None

        result = dict(doc)
        current_instruction = result.get("instruction", "")
        if current_instruction and suggested_additions.strip():
            # Append the suggestion to the existing instruction
            result["instruction"] = (
                current_instruction.rstrip() + "\n\nADDITIONAL CHECKS FROM OBSERVER:\n"
                + suggested_additions.strip()
            )
        else:
            result["instruction"] = suggested_additions.strip()
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_reason(reason: str) -> str:
        """Normalise a rejection reason for grouping similar reasons together."""
        if not reason:
            return ""
        # Lowercase and strip
        r = reason.strip().lower()
        # Truncate long reasons to key phrase
        if len(r) > 120:
            r = r[:120] + "…"
        return r
