"""Unit tests for YAML generation in seed_templates (Story 006).

Tests cover generate_yaml_files(), write_yaml_file(), and the --to-yaml CLI path.
Extraction function tests remain in test_seed_templates.py.
"""

from __future__ import annotations

import os
import warnings
from pathlib import Path
from unittest.mock import patch

import yaml

from training_data.generate_synthetic_data.seed_templates import (
    build_all_templates,
    generate_yaml_files,
    main,
    write_yaml_file,
)


# ---------------------------------------------------------------------------
# write_yaml_file
# ---------------------------------------------------------------------------

def test_write_yaml_file_creates_directory_and_serializes(tmp_path):
    """write_yaml_file creates parent dirs and writes valid YAML."""
    out = tmp_path / "sub" / "deep" / "file.yaml"
    data = {"key": "value", "nums": [1, 2, 3]}
    write_yaml_file(out, data)

    assert out.is_file()
    loaded = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert loaded == data


def test_write_yaml_file_overwrites_existing(tmp_path):
    """write_yaml_file overwrites an existing file."""
    out = tmp_path / "file.yaml"
    out.write_text("old: content\n", encoding="utf-8")
    write_yaml_file(out, {"new": "data"})

    loaded = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert loaded == {"new": "data"}


# ---------------------------------------------------------------------------
# generate_yaml_files
# ---------------------------------------------------------------------------

def test_generate_yaml_files_creates_expected_structure(tmp_path):
    """generate_yaml_files produces shared.yaml, qa_validation.yaml,
    comparison_validator.yaml, and one file per generator category."""
    templates = build_all_templates()
    output_dir = tmp_path / "templates"
    generate_yaml_files(templates, output_dir)

    # Core files always created
    assert (output_dir / "shared.yaml").is_file()
    assert (output_dir / "qa_validation.yaml").is_file()
    assert (output_dir / "comparison_validator.yaml").is_file()

    # One file per generator category (27 categories)
    yaml_files = sorted(
        f for f in os.listdir(output_dir) if f.endswith(".yaml")
    )
    assert len(yaml_files) == 30  # 27 generators + shared + qa_validation + comparison_validator

    # Each generator file is a list of dicts with template_id
    generator_files = [
        f for f in yaml_files
        if f not in ("shared.yaml", "qa_validation.yaml", "comparison_validator.yaml")
    ]
    assert len(generator_files) == 27
    for fname in generator_files:
        path = output_dir / fname
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(data, list), f"{fname} should be a list"
        for entry in data:
            assert "template_id" in entry, f"Entry missing template_id in {fname}"


def test_generate_yaml_files_shared_scaffolding_keys(tmp_path):
    """shared.yaml contains all 5 expected scaffolding blocks."""
    templates = build_all_templates()
    output_dir = tmp_path / "templates"
    generate_yaml_files(templates, output_dir)

    shared = yaml.safe_load((output_dir / "shared.yaml").read_text(encoding="utf-8"))
    scaffold = shared["scaffolding"]
    expected_keys = {
        "system_message",
        "notation_legend",
        "requirements_base",
        "output_format",
        "card_comparison_instructions",
    }
    assert set(scaffold.keys()) == expected_keys


def test_generate_yaml_files_shared_validators_keys(tmp_path):
    """shared.yaml validators section contains qa_validation, checklist, scoring."""
    templates = build_all_templates()
    output_dir = tmp_path / "templates"
    generate_yaml_files(templates, output_dir)

    shared = yaml.safe_load((output_dir / "shared.yaml").read_text(encoding="utf-8"))
    validators = shared["validators"]
    expected_keys = {"qa_validation", "validation_checklist", "validation_scoring_guide"}
    assert set(validators.keys()) == expected_keys


def test_generate_yaml_files_qa_validation_content(tmp_path):
    """qa_validation.yaml contains instruction with placeholders."""
    templates = build_all_templates()
    output_dir = tmp_path / "templates"
    generate_yaml_files(templates, output_dir)

    data = yaml.safe_load((output_dir / "qa_validation.yaml").read_text(encoding="utf-8"))
    assert "instruction" in data
    instruction = data["instruction"]
    assert "{question}" in instruction
    assert "{answer}" in instruction
    assert "{category}" in instruction


def test_generate_yaml_files_comparison_validator_content(tmp_path):
    """comparison_validator.yaml contains instruction with card placeholders."""
    templates = build_all_templates()
    output_dir = tmp_path / "templates"
    generate_yaml_files(templates, output_dir)

    data = yaml.safe_load((output_dir / "comparison_validator.yaml").read_text(encoding="utf-8"))
    assert "instruction" in data
    instruction = data["instruction"]
    assert "{card1_name}" in instruction
    assert "{card2_name}" in instruction


def test_generate_yaml_files_per_generator_template_ids(tmp_path):
    """Each generator file contains the correct template_ids from extraction."""
    templates = build_all_templates()
    output_dir = tmp_path / "templates"
    generate_yaml_files(templates, output_dir)

    # combo_query should have 4 templates
    data = yaml.safe_load((output_dir / "combo_query.yaml").read_text(encoding="utf-8"))
    template_ids = [e["template_id"] for e in data]
    assert template_ids == ["how_does_it_work", "what_do_i_need", "why_does_this_work", "what_is_the_result"]

    # synergy should have 4 templates
    data = yaml.safe_load((output_dir / "synergy.yaml").read_text(encoding="utf-8"))
    template_ids = [e["template_id"] for e in data]
    assert "combo_piece" in template_ids
    assert "value_engine" in template_ids


def test_generate_yaml_files_default_output_dir():
    """When called with the default templates dir, files are written there."""
    # This is an integration-style check — we use a temp dir to avoid mutating repo state.
    templates = build_all_templates()
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        output_dir = Path(td)
        generate_yaml_files(templates, output_dir)
        assert (output_dir / "shared.yaml").is_file()
        assert (output_dir / "combo_query.yaml").is_file()


# ---------------------------------------------------------------------------
# --to-yaml CLI path
# ---------------------------------------------------------------------------

def test_to_yaml_cli_writes_files(tmp_path):
    """--to-yaml flag writes YAML files to the specified output dir."""
    output_dir = tmp_path / "out"
    rc = main(["--to-yaml", "--output-dir", str(output_dir)])

    assert rc == 0
    assert (output_dir / "shared.yaml").is_file()
    assert (output_dir / "combo_query.yaml").is_file()
    assert (output_dir / "qa_validation.yaml").is_file()
    assert (output_dir / "comparison_validator.yaml").is_file()

    yaml_files = [f for f in os.listdir(output_dir) if f.endswith(".yaml")]
    assert len(yaml_files) == 30


def test_to_yaml_cli_default_output_dir():
    """--to-yaml without --output-dir writes to package templates/ dir."""
    # We can't easily assert the path without side effects, but we verify
    # the command succeeds and prints the expected message.
    with patch("training_data.generate_synthetic_data.seed_templates.generate_yaml_files") as mock_gen:
        rc = main(["--to-yaml"])
        assert rc == 0
        # Should be called with default templates dir
        call_args = mock_gen.call_args
        assert call_args[0][1] == Path(__file__).parent / "templates"


def test_to_yaml_cli_creates_output_dir(tmp_path):
    """--to-yaml creates the output directory if it doesn't exist."""
    output_dir = tmp_path / "nonexistent" / "nested"
    rc = main(["--to-yaml", "--output-dir", str(output_dir)])

    assert rc == 0
    assert (output_dir / "shared.yaml").is_file()


def test_deprecated_mongodb_warning():
    """MongoDB seeding path emits a DeprecationWarning."""
    from unittest.mock import MagicMock

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        with patch(
            "training_data.generate_synthetic_data.seed_templates.TemplateStore.from_uri"
        ) as mock_from_uri:
            mock_store = MagicMock(name="store")
            mock_store.seed.return_value = {"inserted": 0, "skipped": 0}
            mock_from_uri.return_value = mock_store

            rc = main(["--mongo-uri", "mongodb://example/"])
            assert rc == 0

        deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(deprecation_warnings) >= 1
        assert "MongoDB seeding is deprecated" in str(deprecation_warnings[0].message)


# ---------------------------------------------------------------------------
# Round-trip: extraction → YAML → loader compatibility
# ---------------------------------------------------------------------------

def test_generated_yaml_loadable_by_yaml_template_loader(tmp_path):
    """YAML files generated by --to-yaml are loadable by YamlTemplateLoader."""
    from training_data.generate_synthetic_data.yaml_template_loader import YamlTemplateLoader

    templates = build_all_templates()
    output_dir = tmp_path / "templates"
    generate_yaml_files(templates, output_dir)

    loader = YamlTemplateLoader(templates_dir=str(output_dir))

    # Scaffolding loads correctly
    scaffold = loader.get_scaffolding()
    assert scaffold is not None
    assert "system_message" in scaffold
    assert "requirements_base" in scaffold

    # Shared validator loads
    qa = loader.get_validator("qa_validation")
    assert qa is not None
    assert "{question}" in qa

    # Per-generator templates load
    result = loader.get_latest("combo_query", "how_does_it_work", "generation")
    assert result is not None
    assert result["template_id"] == "how_does_it_work"
    assert "instruction" in result

    # Validator override loads
    result = loader.get_latest("comparison", "card_validation", "validator")
    assert result is not None
    assert "{card1_name}" in result["instruction"]
