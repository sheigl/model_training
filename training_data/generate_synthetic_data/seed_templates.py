"""Seed/import script for the MongoDB template store (Story 041).

Extracts every hardcoded generation/validator template from the legacy
synthetic-data generators and populates the MongoDB template store via
:class:`TemplateStore.seed`.

Run via::

    # Generate YAML files (preferred — see Story 006)
    python -m training_data.generate_synthetic_data.seed_templates --to-yaml
    python -m training_data.generate_synthetic_data.seed_templates \
        --to-yaml --output-dir /tmp/my_templates

    # Seed MongoDB (deprecated — use --to-yaml instead)
    python -m training_data.generate_synthetic_data.seed_templates
    python -m training_data.generate_synthetic_data.seed_templates --dry-run
    python -m training_data.generate_synthetic_data.seed_templates \
        --mongo-uri mongodb://localhost:27017/ --mongo-user root --mongo-pass whatever

The script is idempotent — ``TemplateStore.seed`` skips docs whose
 ``(generator, template_id, template_type, version=1)`` key already exists.
"""

from __future__ import annotations

import argparse
import importlib
import logging
import os
import sys
from pathlib import Path
from typing import Any

import yaml

from .constants import (
    CARD_COMPARISON_INSTRUCTIONS,
    MTG_NOTATION_LEGEND,
    OUTPUT_FORMAT,
    REQUIREMENTS_BASE,
    SYSTEM_MESSAGE,
    VALIDATION_CHECKLIST,
    VALIDATION_SCORING_GUIDE,
)
from .query_model import build_card_validation_prompt_template, build_qa_validation_prompt_template
from .template_store import TemplateStore

logger = logging.getLogger("seed_templates")


# =============================================================================
# Generator registry — (module_name, class_name, category)
# =============================================================================
# ``category`` is the string returned by the generator's ``get_source_category()``.
# Values were confirmed by reading each generator file (some differ from the
# original spec — e.g. ``budget_alternative`` not ``budget``,
# ``commander_rules`` not ``commander_knowledge``).
GENERATOR_REGISTRY: list[tuple[str, str, str]] = [
    ("generate_combo_queries", "GenerateComboQueries", "combo_query"),
    ("generate_article_qa", "GenerateArticleQa", "article_qa"),
    ("generate_card_search_queries", "GenerateCardSearchQueries", "card_search"),
    ("generate_comparison_questions", "GenerateComparisonQuestions", "comparison"),
    ("generate_reverse_lookup_questions", "GenerateReverseLookupQuestions", "reverse_lookup"),
    ("generate_synergy_questions", "GenerateSynergyQuestions", "synergy"),
    ("generate_budget_alternatives", "GenerateBudgetAlternatives", "budget_alternative"),
    ("generate_color_identity_questions", "GenerateColorIdentityQuestions", "color_identity"),
    ("generate_quick_guidelines", "GenerateQuickGuidelines", "quick_guideline"),
    ("generate_terminology_questions", "GenerateTerminologyQuestions", "terminology"),
    ("generate_deckbuilding_theory", "GenerateDeckbuildingTheory", "deckbuilding_theory"),
    ("generate_commander_building", "GenerateCommanderBuilding", "commander_building"),
    ("generate_rules_scenarios", "GenerateRulesScenarios", "rules_scenario"),
    ("generate_archetypes", "GenerateArchetypes", "archetype"),
    ("generate_game_theory", "GenerateGameTheory", "game_theory"),
    ("generate_meta_knowledge", "GenerateMetaKnowledge", "meta_knowledge"),
    ("generate_commander_knowledge", "GenerateCommanderKnowledge", "commander_rules"),
    ("generate_rule_explanations", "GenerateRuleExplanations", "rule_explanation"),
    ("generate_rule_interactions", "GenerateRuleInteractions", "rule_interaction"),
    ("generate_glossary_with_examples", "GenerateGlossaryWithExamples", "glossary_with_examples"),
    ("generate_rule_edge_cases", "GenerateRuleEdgeCases", "rule_edge_case"),
    ("generate_rule_why_questions", "GenerateRuleWhyQuestions", "rule_why"),
    ("generate_guide_qa", "GenerateGuideQa", "guide_qa"),
    ("generate_staple_analysis", "GenerateStapleAnalysis", "staple_analysis"),
    ("generate_color_staples", "GenerateColorStaples", "color_staples"),
    ("generate_salt_questions", "GenerateSaltQuestions", "salt_analysis"),
    ("generate_multi_card_usage", "GenerateMultiCardUsage", "multi_card_usage"),
]


# =============================================================================
# YAML serialization helper
# =============================================================================

def _dump_yaml(data: Any) -> str:
    """Serialize ``data`` to YAML with stable formatting."""
    return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)


# =============================================================================
# Extraction functions
# =============================================================================

def extract_shared_blocks() -> list[dict]:
    """Build the 8 cross-generator scaffolding docs (generator="__shared__").

    Returned docs (template_id → template_type):
      - system_message            → generation
      - notation_legend           → generation
      - requirements_base         → generation
      - output_format             → generation
      - card_comparison_instructions → generation
      - validation_checklist      → validator
      - validation_scoring_guide  → validator
      - qa_validation            → validator
    """
    shared = TemplateStore.SHARED_NAMESPACE
    docs: list[dict] = []

    # --- generation scaffolding (text blocks) ---
    docs.append({
        "generator": shared,
        "template_id": "system_message",
        "template_type": "generation",
        "yaml_content": _dump_yaml({"content": SYSTEM_MESSAGE}),
    })
    docs.append({
        "generator": shared,
        "template_id": "notation_legend",
        "template_type": "generation",
        "yaml_content": _dump_yaml({"content": MTG_NOTATION_LEGEND}),
    })
    # REQUIREMENTS_BASE is a list → YAML list
    docs.append({
        "generator": shared,
        "template_id": "requirements_base",
        "template_type": "generation",
        "yaml_content": _dump_yaml({"content": list(REQUIREMENTS_BASE)}),
    })
    docs.append({
        "generator": shared,
        "template_id": "output_format",
        "template_type": "generation",
        "yaml_content": _dump_yaml({"content": OUTPUT_FORMAT}),
    })
    docs.append({
        "generator": shared,
        "template_id": "card_comparison_instructions",
        "template_type": "generation",
        "yaml_content": _dump_yaml({"content": CARD_COMPARISON_INSTRUCTIONS}),
    })

    # --- validator scaffolding ---
    docs.append({
        "generator": shared,
        "template_id": "validation_checklist",
        "template_type": "validator",
        "yaml_content": _dump_yaml({"content": VALIDATION_CHECKLIST}),
    })
    docs.append({
        "generator": shared,
        "template_id": "validation_scoring_guide",
        "template_type": "validator",
        "yaml_content": _dump_yaml({"content": VALIDATION_SCORING_GUIDE}),
    })
    # qa_validation — the full Q&A validator prompt template with placeholders
    docs.append({
        "generator": shared,
        "template_id": "qa_validation",
        "template_type": "validator",
        "yaml_content": _dump_yaml({
            "instruction": build_qa_validation_prompt_template(),
            "verification_block": "",
            "scoring_guide": "",
        }),
    })

    assert len(docs) == 8, f"expected 8 shared docs, got {len(docs)}"
    return docs


def _load_generator_class(module_name: str, class_name: str):
    """Lazily import a generator class from this package."""
    mod = importlib.import_module(f".{module_name}", package=__package__)
    return getattr(mod, class_name)


def extract_legacy() -> list[dict]:
    """Extract one generation doc per template from each generator's YAML file.

    Each doc has ``template_type="generation"`` and ``yaml_content`` with keys:
    ``instruction``, ``weight``, ``validation_rules``, ``min_answer_length``,
    ``max_answer_length``.
    """
    docs: list[dict] = []
    templates_dir = Path(__file__).parent / "templates"

    for module_name, class_name, category in GENERATOR_REGISTRY:
        # Try class-level TEMPLATES first (backward compat)
        cls = _load_generator_class(module_name, class_name)
        templates = getattr(cls, "TEMPLATES", None)

        if templates:
            for tc in templates:
                yaml_content = _dump_yaml({
                    "instruction": tc.task_instruction,
                    "weight": tc.weight,
                    "validation_rules": list(tc.validation_rules or []),
                    "min_answer_length": tc.min_answer_length,
                    "max_answer_length": tc.max_answer_length,
                })
                docs.append({
                    "generator": category,
                    "template_id": tc.template_id,
                    "template_type": "generation",
                    "yaml_content": yaml_content,
                })
        else:
            # Fallback: read from YAML file on disk
            category_file = templates_dir / f"{category}.yaml"
            if not category_file.is_file():
                logger.warning("generator %s has no TEMPLATES and no YAML file — skipping", class_name)
                continue
            entries = yaml.safe_load(category_file.read_text(encoding="utf-8"))
            if not isinstance(entries, list):
                logger.warning("generator %s YAML file did not produce a list — skipping", class_name)
                continue
            for entry in entries:
                if not isinstance(entry, dict) or "template_id" not in entry:
                    continue
                yaml_content = _dump_yaml({
                    "instruction": entry.get("instruction", ""),
                    "weight": entry.get("weight", 1.0),
                    "validation_rules": list(entry.get("validation_rules") or []),
                    "min_answer_length": int(entry.get("min_answer_length", 80)),
                    "max_answer_length": int(entry.get("max_answer_length", 2000)),
                })
                docs.append({
                    "generator": category,
                    "template_id": entry["template_id"],
                    "template_type": "generation",
                    "yaml_content": yaml_content,
                })
    return docs


def extract_validators() -> list[dict]:
    """Return validator docs.

    ``qa_validation`` is already produced by :func:`extract_shared_blocks`
    (generator="__shared__"), so this function only needs to add the
    card-comparison validator (generator="comparison").
    """
    return [
        {
            "generator": "comparison",
            "template_id": "card_validation",
            "template_type": "validator",
            "yaml_content": _dump_yaml({
                "instruction": build_card_validation_prompt_template(),
                "verification_block": VALIDATION_CHECKLIST,
                "scoring_guide": VALIDATION_SCORING_GUIDE,
            }),
        }
    ]


# =============================================================================
# Reconciliation — legacy wins
# =============================================================================

def _doc_key(doc: dict) -> tuple[str, str, str]:
    """Return the ``(generator, template_id, template_type)`` key for a doc."""
    return (doc["generator"], doc["template_id"], doc["template_type"])


def build_all_templates() -> list[dict]:
    """Build the full template list.

    Order: shared blocks → legacy generators → validators.
    """
    shared = extract_shared_blocks()
    legacy = extract_legacy()
    validators = extract_validators()
    return shared + legacy + validators


# =============================================================================
# YAML file generation (Story 006)
# =============================================================================

def write_yaml_file(path: Path, data: Any) -> None:
    """Serialize *data* to a YAML file with stable formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = _dump_yaml(data)
    path.write_text(content, encoding="utf-8")
    logger.info("wrote %s", path)


def generate_yaml_files(templates: list[dict], output_dir: Path) -> None:
    """Write extracted template data as YAML files in *output_dir*.

    Produces::

        <output_dir>/shared.yaml              # scaffolding + shared validators
        <output_dir>/qa_validation.yaml       # Q&A validator prompt
        <output_dir>/comparison_validator.yaml# card-comparison validator prompt
        <output_dir>/{category}.yaml          # one file per generator category
    """
    # Group templates by (generator, template_type)
    scaffolding: dict[str, Any] = {}
    validators_section: dict[str, Any] = {}
    qa_validation_content: str | None = None
    comparison_validator_content: str | None = None
    per_generator: dict[str, list[dict]] = {}

    for doc in templates:
        gen = doc["generator"]
        tid = doc["template_id"]
        ttype = doc["template_type"]
        parsed = yaml.safe_load(doc["yaml_content"])

        if gen == TemplateStore.SHARED_NAMESPACE:
            if ttype == "generation":
                # Shared scaffolding docs wrap content in {"content": ...}
                value = parsed.get("content") if isinstance(parsed, dict) else parsed
                scaffolding[tid] = value
            elif ttype == "validator":
                if tid == "qa_validation":
                    qa_validation_content = (
                        parsed["instruction"]
                        if isinstance(parsed, dict) and "instruction" in parsed
                        else str(parsed)
                    )
                    # Also include in shared.yaml validators section
                    validators_section[tid] = qa_validation_content
                else:
                    # validation_checklist, validation_scoring_guide
                    value = parsed.get("content") if isinstance(parsed, dict) else parsed
                    validators_section[tid] = value

        elif ttype == "generation":
            entry: dict[str, Any] = {"template_id": tid}
            if isinstance(parsed, dict):
                entry.update(parsed)
            per_generator.setdefault(gen, []).append(entry)

        elif ttype == "validator" and gen == "comparison":
            comparison_validator_content = (
                parsed["instruction"]
                if isinstance(parsed, dict) and "instruction" in parsed
                else str(parsed)
            )

    # Write shared.yaml
    shared_data: dict[str, Any] = {}
    if scaffolding:
        shared_data["scaffolding"] = scaffolding
    if validators_section:
        shared_data["validators"] = validators_section
    write_yaml_file(output_dir / "shared.yaml", shared_data)

    # Write qa_validation.yaml (standalone validator file)
    if qa_validation_content is not None:
        write_yaml_file(output_dir / "qa_validation.yaml", {"instruction": qa_validation_content})

    # Write comparison_validator.yaml
    if comparison_validator_content is not None:
        write_yaml_file(
            output_dir / "comparison_validator.yaml",
            {"instruction": comparison_validator_content},
        )

    # Write per-generator YAML files
    for gen, entries in sorted(per_generator.items()):
        write_yaml_file(output_dir / f"{gen}.yaml", entries)

    total_files = 1 + (1 if qa_validation_content else 0) + (1 if comparison_validator_content else 0) + len(per_generator)
    logger.info("generated %d YAML files in %s", total_files, output_dir)


# =============================================================================
# CLI
# =============================================================================

def _print_summary(templates: list[dict], result: dict | None) -> None:
    """Print a human-readable summary of what would be / was inserted."""
    by_type: dict[str, int] = {}
    by_generator: dict[str, int] = {}
    for t in templates:
        by_type[t["template_type"]] = by_type.get(t["template_type"], 0) + 1
        by_generator[t["generator"]] = by_generator.get(t["generator"], 0) + 1

    print("\n" + "=" * 60)
    print("  SEED TEMPLATES SUMMARY")
    print("=" * 60)
    print(f"  Total templates: {len(templates)}")
    print(f"  By template_type: {by_type}")
    print(f"  Distinct generators: {len(by_generator)}")
    print("-" * 60)
    print("  By generator:")
    for gen in sorted(by_generator):
        print(f"    {gen}: {by_generator[gen]}")
    print("-" * 60)
    if result is not None:
        print(f"  Inserted: {result.get('inserted', 0)}")
        print(f"  Skipped:  {result.get('skipped', 0)}")
    else:
        print("  (dry-run — no MongoDB writes)")
    print("=" * 60)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Seed the MongoDB template store with all hardcoded templates.",
    )
    parser.add_argument(
        "--to-yaml",
        action="store_true",
        help="Generate YAML template files instead of seeding MongoDB",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory for YAML files (default: templates/ in package)",
    )
    parser.add_argument(
        "--mongo-uri",
        default=os.getenv("MONGO_URI", "mongodb://localhost:27017/"),
        help="MongoDB URI (default: $MONGO_URI or mongodb://localhost:27017/)",
    )
    parser.add_argument("--mongo-user", default="root", help="MongoDB username (default: root)")
    parser.add_argument("--mongo-pass", default="whatever", help="MongoDB password (default: whatever)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be inserted; do not write to MongoDB",
    )
    args = parser.parse_args(argv)

    templates = build_all_templates()

    if args.to_yaml:
        output_dir = args.output_dir or (Path(__file__).parent / "templates")
        generate_yaml_files(templates, output_dir)
        _print_summary(templates, None)
        print(f"\n  --to-yaml: wrote YAML files to {output_dir}")
        return 0

    # MongoDB seeding path — deprecated
    import warnings
    warnings.warn(
        "MongoDB seeding is deprecated; use --to-yaml instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    if args.dry_run:
        _print_summary(templates, None)
        print("\n  --dry-run: no MongoDB writes performed.")
        return 0

    store = TemplateStore.from_uri(
        uri=args.mongo_uri,
        username=args.mongo_user,
        password=args.mongo_pass,
    )
    result = store.seed(templates)
    _print_summary(templates, result)
    return 0


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    sys.exit(main())