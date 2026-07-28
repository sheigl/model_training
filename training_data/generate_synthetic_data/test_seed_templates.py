"""Unit tests for the seed/import script (Story 041).

Tests cover the extraction functions, reconciliation logic, and the generator
registry. MongoDB seeding is deprecated; YAML generation is tested in
:mod:`test_seed_templates_yaml`.
"""

from __future__ import annotations

import inspect
import re

import yaml

from training_data.generate_synthetic_data.seed_templates import (
    GENERATOR_REGISTRY,
    _doc_key,
    build_all_templates,
    extract_legacy,
    extract_shared_blocks,
    extract_validators,
)
from training_data.generate_synthetic_data.template_store import TemplateStore


# ---------------------------------------------------------------------------
# extract_shared_blocks
# ---------------------------------------------------------------------------

def test_extract_shared_blocks_returns_8_docs_with_correct_template_ids():
    docs = extract_shared_blocks()
    assert len(docs) == 8

    template_ids = {d["template_id"] for d in docs}
    expected_ids = {
        "system_message",
        "notation_legend",
        "requirements_base",
        "output_format",
        "card_comparison_instructions",
        "validation_checklist",
        "validation_scoring_guide",
        "qa_validation",
    }
    assert template_ids == expected_ids

    # All shared docs use the shared namespace
    for doc in docs:
        assert doc["generator"] == TemplateStore.SHARED_NAMESPACE
        assert "yaml_content" in doc and doc["yaml_content"]

    # template_type split: 5 generation + 3 validator
    by_type = {}
    for d in docs:
        by_type[d["template_type"]] = by_type.get(d["template_type"], 0) + 1
    assert by_type == {"generation": 5, "validator": 3}

    # requirements_base is serialized as a YAML list
    req_doc = next(d for d in docs if d["template_id"] == "requirements_base")
    parsed = yaml.safe_load(req_doc["yaml_content"])
    assert isinstance(parsed["content"], list)
    assert len(parsed["content"]) >= 8

    # qa_validation has an instruction field with placeholders
    qa_doc = next(d for d in docs if d["template_id"] == "qa_validation")
    qa_parsed = yaml.safe_load(qa_doc["yaml_content"])
    assert "instruction" in qa_parsed
    assert "{question}" in qa_parsed["instruction"]
    assert "{answer}" in qa_parsed["instruction"]


# ---------------------------------------------------------------------------
# extract_legacy
# ---------------------------------------------------------------------------

def test_extract_legacy_covers_all_27_generators():
    docs = extract_legacy()

    # 27 distinct generators
    generators = {d["generator"] for d in docs}
    assert len(generators) == 27

    # No duplicate (generator, template_id) keys
    keys = [(d["generator"], d["template_id"]) for d in docs]
    assert len(keys) == len(set(keys)), f"duplicate keys: {keys}"

    # All docs are generation type
    for d in docs:
        assert d["template_type"] == "generation"
        assert d["yaml_content"]

    # Every registry category is represented
    registry_categories = {entry[2] for entry in GENERATOR_REGISTRY}
    assert registry_categories == generators


def test_extract_legacy_yaml_content_has_expected_keys():
    docs = extract_legacy()
    for d in docs:
        parsed = yaml.safe_load(d["yaml_content"])
        assert "instruction" in parsed
        assert "weight" in parsed
        assert "validation_rules" in parsed
        assert "min_answer_length" in parsed
        assert "max_answer_length" in parsed


# ---------------------------------------------------------------------------
# extract_validators
# ---------------------------------------------------------------------------

def test_extract_validators_returns_card_validation():
    docs = extract_validators()
    # qa_validation is in shared blocks, so extract_validators only adds card_validation
    assert len(docs) == 1
    doc = docs[0]
    assert doc["generator"] == "comparison"
    assert doc["template_id"] == "card_validation"
    assert doc["template_type"] == "validator"

    parsed = yaml.safe_load(doc["yaml_content"])
    assert "instruction" in parsed
    assert "{card1_name}" in parsed["instruction"]
    assert "{card2_name}" in parsed["instruction"]
    assert "{question}" in parsed["instruction"]
    assert "{answer}" in parsed["instruction"]


def test_qa_validation_is_in_shared_blocks_not_validators():
    """qa_validation should be in extract_shared_blocks, not extract_validators."""
    shared = extract_shared_blocks()
    shared_ids = {d["template_id"] for d in shared}
    assert "qa_validation" in shared_ids

    validators = extract_validators()
    validator_ids = {d["template_id"] for d in validators}
    assert "qa_validation" not in validator_ids  # no duplication


# ---------------------------------------------------------------------------
# Generator registry matches actual classes
# ---------------------------------------------------------------------------

def test_generator_registry_matches_classes():
    """For each registry entry, import the class, confirm it has TEMPLATES and
    the category matches ``get_source_category()`` (read from source).
    """
    assert len(GENERATOR_REGISTRY) == 27

    for module_name, class_name, category in GENERATOR_REGISTRY:
        # Import the class lazily
        from training_data.generate_synthetic_data.seed_templates import _load_generator_class
        cls = _load_generator_class(module_name, class_name)

        # Confirm class has TEMPLATES
        assert hasattr(cls, "TEMPLATES"), f"{class_name} has no TEMPLATES"
        assert len(cls.TEMPLATES) > 0, f"{class_name} has empty TEMPLATES"

        # Confirm category matches get_source_category() by reading the source.
        # (Construction is heavy due to data_access deps, so we inspect source.)
        source = inspect.getsource(cls.get_source_category)
        # Extract the returned string literal from the source
        match = re.search(r'return\s+"([^"]+)"', source)
        assert match, f"could not extract return string from {class_name}.get_source_category"
        actual_category = match.group(1)
        assert actual_category == category, (
            f"{class_name}: registry category={category!r} but "
            f"get_source_category() returns {actual_category!r}"
        )


def test_generator_registry_no_duplicate_categories():
    categories = [entry[2] for entry in GENERATOR_REGISTRY]
    assert len(categories) == len(set(categories)), "duplicate categories in registry"


def test_generator_registry_no_duplicate_modules():
    modules = [entry[0] for entry in GENERATOR_REGISTRY]
    assert len(modules) == len(set(modules)), "duplicate modules in registry"


# ---------------------------------------------------------------------------
# build_all_templates integration
# ---------------------------------------------------------------------------

def test_build_all_templates_includes_shared_legacy_validators():
    templates = build_all_templates()
    assert len(templates) > 0

    keys = {_doc_key(t) for t in templates}
    # Shared blocks present
    assert (TemplateStore.SHARED_NAMESPACE, "system_message", "generation") in keys
    assert (TemplateStore.SHARED_NAMESPACE, "qa_validation", "validator") in keys
    # A legacy generator present
    assert ("combo_query", "how_does_it_work", "generation") in keys
    # Card validation validator present
    assert ("comparison", "card_validation", "validator") in keys

    # No duplicate keys across the full set
    all_keys = [_doc_key(t) for t in templates]
    assert len(all_keys) == len(set(all_keys)), "duplicate keys in build_all_templates"
