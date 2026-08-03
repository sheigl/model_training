"""Unit tests for :class:`YamlTemplateLoader`.

Covers: loading existing category files, missing files returning None, shared
scaffolding/validator loading, malformed YAML raising descriptive errors, the
``task_instruction`` alias, and ``list_versions`` returning an empty list.
"""

from __future__ import annotations

import pytest
import yaml

from training_data.generate_synthetic_data.yaml_template_loader import YamlTemplateLoader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_loader(templates_dir: str | None = None) -> YamlTemplateLoader:
    """Build a loader, using the real templates dir if no override given."""
    return YamlTemplateLoader(templates_dir=templates_dir)


def _make_temp_dir(tmp_path) -> str:
    """Create a temporary templates directory with a minimal category file."""
    templates_dir = str(tmp_path / "templates")
    import os
    os.makedirs(templates_dir, exist_ok=True)

    # Write a minimal category YAML
    entries = [
        {
            "template_id": "how_does_it_work",
            "instruction": "Generate exactly 3 Q&A pairs explaining how it works.",
            "weight": 1.0,
            "validation_rules": ["Rule 1", "Rule 2"],
            "min_answer_length": 80,
            "max_answer_length": 2000,
        },
        {
            "template_id": "what_do_i_need",
            "task_instruction": "Generate requirements-focused Q&A pairs.",
            "weight": 0.5,
            "validation_rules": [],
            "min_answer_length": 100,
            "max_answer_length": 3000,
        },
    ]
    with open(os.path.join(templates_dir, "test_category.yaml"), "w") as f:
        yaml.dump(entries, f, default_flow_style=False)

    # Write a minimal shared.yaml
    shared = {
        "scaffolding": {
            "system_message": "<system>You are an MTG expert.</system>",
            "notation_legend": "<reference>MTG notation legend</reference>",
            "output_format": "OUTPUT FORMAT: JSON array",
            "requirements_base": ["Req 1", "Req 2"],
            "card_comparison_instructions": "CRITICAL ANALYSIS REQUIREMENTS...",
        },
        "validators": {
            "qa_validation": "Category: {category}\nQuestion: {question}\nAnswer: {answer}",
            "validation_checklist": "Checklist content",
            "validation_scoring_guide": "Scoring guide content",
        },
    }
    with open(os.path.join(templates_dir, "shared.yaml"), "w") as f:
        yaml.dump(shared, f, default_flow_style=False)

    # Write a validator override file
    with open(os.path.join(templates_dir, "test_category_validator.yaml"), "w") as f:
        f.write("instruction: |\n  Card comparison prompt for {card1_name} vs {card2_name}\n")

    return templates_dir


# ---------------------------------------------------------------------------
# test_load_category_file_returns_list_of_dicts
# ---------------------------------------------------------------------------
class TestLoadCategoryFile:
    def test_load_existing_category(self, tmp_path):
        """Loading an existing category file returns a list of dicts."""
        loader = _make_loader(_make_temp_dir(tmp_path))
        entries = loader._load_yaml(
            __import__("pathlib").Path(
                str(tmp_path / "templates")
            ) / "test_category.yaml"
        )
        assert isinstance(entries, list)
        assert len(entries) == 2
        assert entries[0]["template_id"] == "how_does_it_work"
        assert entries[1]["template_id"] == "what_do_i_need"

    def test_load_real_combo_query(self):
        """Loading the real combo_query.yaml returns a list of dicts."""
        loader = _make_loader()
        path = loader._templates_dir / "combo_query.yaml"
        entries = loader._load_yaml(path)
        assert isinstance(entries, list)
        assert len(entries) == 4
        ids = [e["template_id"] for e in entries]
        assert "how_does_it_work" in ids
        assert "what_do_i_need" in ids

    def test_load_all_27_category_files(self):
        """All 27 generator category YAML files parse correctly."""
        loader = _make_loader()
        import os
        templates_dir = str(loader._templates_dir)
        yaml_files = sorted(
            f for f in os.listdir(templates_dir)
            if f.endswith(".yaml")
            and "_validator" not in f
            and f not in ("shared.yaml", "qa_validation.yaml", "comparison_validator.yaml")
        )
        assert len(yaml_files) == 27
        for fname in yaml_files:
            path = loader._templates_dir / fname
            entries = loader._load_yaml(path)
            assert isinstance(entries, list), f"{fname} did not produce a list"
            for entry in entries:
                assert "template_id" in entry, f"Entry missing template_id in {fname}"


# ---------------------------------------------------------------------------
# test_load_missing_category_returns_none
# ---------------------------------------------------------------------------
class TestLoadMissingCategory:
    def test_missing_file_returns_none(self):
        """Loading a non-existent category returns None."""
        loader = _make_loader()
        result = loader.get_latest("nonexistent_category", "some_id", "generation")
        assert result is None

    def test_missing_template_id_returns_none(self):
        """Loading an existing file but missing template_id returns None."""
        loader = _make_loader()
        result = loader.get_latest("combo_query", "does_not_exist", "generation")
        assert result is None


# ---------------------------------------------------------------------------
# test_load_shared_scaffolding
# ---------------------------------------------------------------------------
class TestLoadSharedScaffolding:
    def test_all_five_scaffolding_keys_present(self):
        """shared.yaml contains all 5 expected scaffolding blocks."""
        loader = _make_loader()
        scaffold = loader.get_scaffolding()
        assert scaffold is not None
        expected_keys = {
            "system_message",
            "notation_legend",
            "output_format",
            "requirements_base",
            "card_comparison_instructions",
        }
        assert set(scaffold.keys()) == expected_keys

    def test_scaffolding_values_are_strings_or_lists(self):
        """Scaffolding values are str or list as expected."""
        loader = _make_loader()
        scaffold = loader.get_scaffolding()
        assert isinstance(scaffold["system_message"], str)
        assert isinstance(scaffold["notation_legend"], str)
        assert isinstance(scaffold["output_format"], str)
        assert isinstance(scaffold["requirements_base"], list)
        assert isinstance(scaffold["card_comparison_instructions"], str)

    def test_requirements_base_has_multiple_items(self):
        """requirements_base contains multiple items."""
        loader = _make_loader()
        scaffold = loader.get_scaffolding()
        assert len(scaffold["requirements_base"]) >= 8

    def test_system_message_contains_mtG_reference(self):
        """system_message contains MTG-related content."""
        loader = _make_loader()
        scaffold = loader.get_scaffolding()
        assert "Magic: The Gathering" in scaffold["system_message"] or "MTG" in scaffold["system_message"]

    def test_notation_legend_contains_braces(self):
        """notation_legend contains MTG brace notation like {T}."""
        loader = _make_loader()
        scaffold = loader.get_scaffolding()
        assert "{T}" in scaffold["notation_legend"]


# ---------------------------------------------------------------------------
# test_load_shared_validators
# ---------------------------------------------------------------------------
class TestLoadSharedValidators:
    def test_qa_validation_key_present_with_placeholders(self):
        """qa_validation validator contains expected placeholders."""
        loader = _make_loader()
        validator = loader.get_validator("qa_validation")
        assert validator is not None
        assert "{question}" in validator
        assert "{answer}" in validator
        assert "{context}" in validator
        assert "{category}" in validator

    def test_validation_checklist_key_present(self):
        """validation_checklist validator is loadable."""
        loader = _make_loader()
        validator = loader.get_validator("validation_checklist")
        assert validator is not None
        assert isinstance(validator, str)

    def test_validation_scoring_guide_key_present(self):
        """validation_scoring_guide validator is loadable."""
        loader = _make_loader()
        validator = loader.get_validator("validation_scoring_guide")
        assert validator is not None
        assert isinstance(validator, str)

    def test_missing_validator_returns_none(self):
        """Asking for a non-existent validator returns None."""
        loader = _make_loader()
        result = loader.get_validator("nonexistent_validator")
        assert result is None


# ---------------------------------------------------------------------------
# test_get_latest_generation_template
# ---------------------------------------------------------------------------
class TestGetLatestGenerationTemplate:
    def test_fields_correct(self, tmp_path):
        """get_latest for a generation template returns correct fields."""
        loader = _make_loader(_make_temp_dir(tmp_path))
        result = loader.get_latest("test_category", "how_does_it_work", "generation")
        assert result is not None
        assert result["template_id"] == "how_does_it_work"
        assert "instruction" in result
        assert result["weight"] == 1.0
        assert result["validation_rules"] == ["Rule 1", "Rule 2"]
        assert result["min_answer_length"] == 80
        assert result["max_answer_length"] == 2000

    def test_real_combo_query_template(self):
        """get_latest for a real combo_query template returns correct data."""
        loader = _make_loader()
        result = loader.get_latest("combo_query", "how_does_it_work", "generation")
        assert result is not None
        assert result["template_id"] == "how_does_it_work"
        assert "Generate exactly 3 Q&A pairs" in result["instruction"]
        assert isinstance(result["validation_rules"], list)
        assert len(result["validation_rules"]) > 0

    def test_get_latest_shared_scaffolding(self):
        """get_latest for shared scaffolding returns instruction content."""
        loader = _make_loader()
        result = loader.get_latest(
            YamlTemplateLoader.SHARED_NAMESPACE, "system_message", "generation"
        )
        assert result is not None
        assert result["template_id"] == "system_message"
        assert isinstance(result["instruction"], str)

    def test_get_latest_shared_validator(self):
        """get_latest for shared validator returns instruction text."""
        loader = _make_loader()
        result = loader.get_latest(
            YamlTemplateLoader.SHARED_NAMESPACE, "qa_validation", "validator"
        )
        assert result is not None
        assert result["template_id"] == "qa_validation"
        assert "{question}" in result["instruction"]


# ---------------------------------------------------------------------------
# test_get_latest_missing_returns_none
# ---------------------------------------------------------------------------
class TestGetLatestMissing:
    def test_missing_generator(self):
        loader = _make_loader()
        assert loader.get_latest("no_such_gen", "x", "generation") is None

    def test_missing_template_id_in_existing_file(self):
        loader = _make_loader()
        assert loader.get_latest("combo_query", "nonexistent", "generation") is None


# ---------------------------------------------------------------------------
# test_malformed_yaml_raises_descriptive_error
# ---------------------------------------------------------------------------
class TestMalformedYaml:
    def test_syntax_error_raises_valueerror(self, tmp_path):
        """Malformed YAML raises ValueError with a descriptive message."""
        import os
        templates_dir = str(tmp_path / "templates")
        os.makedirs(templates_dir, exist_ok=True)
        bad_yaml = os.path.join(templates_dir, "broken.yaml")
        with open(bad_yaml, "w") as f:
            f.write("invalid: yaml: [missing bracket\n  - unterminated")

        loader = _make_loader(templates_dir)
        from pathlib import Path
        with pytest.raises(ValueError, match="Malformed YAML"):
            loader._load_yaml(Path(bad_yaml))

    def test_error_message_includes_filename(self, tmp_path):
        """The ValueError message includes the file path."""
        import os
        templates_dir = str(tmp_path / "templates")
        os.makedirs(templates_dir, exist_ok=True)
        bad_yaml = os.path.join(templates_dir, "broken.yaml")
        with open(bad_yaml, "w") as f:
            f.write("key: [value\n  bad indent: x")

        loader = _make_loader(templates_dir)
        from pathlib import Path
        with pytest.raises(ValueError, match="broken.yaml"):
            loader._load_yaml(Path(bad_yaml))


# ---------------------------------------------------------------------------
# test_task_instruction_alias
# ---------------------------------------------------------------------------
class TestTaskInstructionAlias:
    def test_entry_with_task_instruction_instead_of_instruction(self, tmp_path):
        """An entry using 'task_instruction' instead of 'instruction' works."""
        loader = _make_loader(_make_temp_dir(tmp_path))
        result = loader.get_latest("test_category", "what_do_i_need", "generation")
        assert result is not None
        # Should have been normalized to 'instruction'
        assert "instruction" in result
        assert result["instruction"] == "Generate requirements-focused Q&A pairs."

    def test_entry_with_instruction_key_works_normally(self, tmp_path):
        """An entry with the standard 'instruction' key works as expected."""
        loader = _make_loader(_make_temp_dir(tmp_path))
        result = loader.get_latest("test_category", "how_does_it_work", "generation")
        assert result is not None
        assert result["instruction"] == "Generate exactly 3 Q&A pairs explaining how it works."


# ---------------------------------------------------------------------------
# test_list_versions_returns_empty
# ---------------------------------------------------------------------------
class TestListVersions:
    def test_list_versions_always_empty(self):
        """list_versions returns [] — no versioning support."""
        loader = _make_loader()
        assert loader.list_versions("combo_query", "how_does_it_work", "generation") == []
        assert loader.list_versions(
            YamlTemplateLoader.SHARED_NAMESPACE, "system_message", "generation"
        ) == []
        assert loader.list_versions("comparison", "card_validation", "validator") == []


# ---------------------------------------------------------------------------
# test_get_validator_for_per_generator_override
# ---------------------------------------------------------------------------
class TestGetValidatorOverride:
    def test_per_generator_validator_loads(self, tmp_path):
        """Per-generator validator override file is loaded correctly."""
        loader = _make_loader(_make_temp_dir(tmp_path))
        result = loader.get_latest("test_category", "validator", "validator")
        assert result is not None
        assert "{card1_name}" in result["instruction"]
        assert "{card2_name}" in result["instruction"]


# ---------------------------------------------------------------------------
# test_shared_namespace_constant
# ---------------------------------------------------------------------------
class TestSharedNamespace:
    def test_shared_namespace_constant(self):
        assert YamlTemplateLoader.SHARED_NAMESPACE == "__shared__"


# ---------------------------------------------------------------------------
# test_invalid_templates_dir
# ---------------------------------------------------------------------------
class TestInvalidTemplatesDir:
    def test_nonexistent_dir_raises_valueerror(self):
        with pytest.raises(ValueError, match="Templates directory does not exist"):
            _make_loader("/nonexistent/path/that/does/not/exist")


# ---------------------------------------------------------------------------
# Legacy manifest version resolution
# ---------------------------------------------------------------------------
class TestLegacyManifestVersionResolution:
    def _write_manifest(self, templates_dir, data):
        import json
        with open(__import__("os").path.join(templates_dir, "_observer_manifest.json"), "w") as f:
            json.dump(data, f)

    def test_legacy_version_routes_to_validator_file(self, tmp_path):
        """A legacy active_version maps to the validator when only the
        versioned validator file exists."""
        templates_dir = _make_temp_dir(tmp_path)
        import os
        with open(os.path.join(templates_dir, "test_category_validator_v2.yaml"), "w") as f:
            f.write("instruction: improved validator\n")
        self._write_manifest(templates_dir, {
            "categories": {
                "test_category": {"active_version": 2, "versions": {"2": {}}},
            }
        })
        loader = _make_loader(templates_dir)

        assert loader.get_active_validator_version("test_category") == 2
        # Generation namespace must NOT claim the legacy version
        assert loader._get_active_version("test_category", "generation") is None
        assert loader.load_active_templates("test_category") is None

    def test_legacy_version_routes_to_generation_file(self, tmp_path):
        """A legacy active_version maps to generation when only the versioned
        generation file exists."""
        templates_dir = _make_temp_dir(tmp_path)
        import os
        with open(os.path.join(templates_dir, "test_category_v2.yaml"), "w") as f:
            yaml.dump([{
                "template_id": "how_does_it_work",
                "instruction": "v2 instruction",
                "weight": 1.0,
                "validation_rules": [],
                "min_answer_length": 80,
                "max_answer_length": 2000,
            }], f, default_flow_style=False)
        self._write_manifest(templates_dir, {
            "categories": {
                "test_category": {"active_version": 2, "versions": {"2": {}}},
            }
        })
        loader = _make_loader(templates_dir)

        assert loader._get_active_version("test_category", "generation") == 2
        assert loader.get_active_validator_version("test_category") is None
        active = loader.load_active_templates("test_category")
        assert active is not None
        assert active[0]["instruction"] == "v2 instruction"

    def test_legacy_version_without_files_defaults_generation(self, tmp_path):
        """No versioned file on disk → legacy counter defaults to generation."""
        templates_dir = _make_temp_dir(tmp_path)
        self._write_manifest(templates_dir, {
            "categories": {
                "test_category": {"active_version": 2, "versions": {"2": {}}},
            }
        })
        loader = _make_loader(templates_dir)

        assert loader._get_active_version("test_category", "generation") == 2
        assert loader.get_active_validator_version("test_category") is None

    def test_versioned_validator_file_is_loadable(self, tmp_path):
        """get_version for a validator version reads the versioned file."""
        templates_dir = _make_temp_dir(tmp_path)
        import os
        with open(os.path.join(templates_dir, "test_category_validator_v2.yaml"), "w") as f:
            f.write("instruction: improved validator\n")
        loader = _make_loader(templates_dir)

        doc = loader.get_version("test_category", "validator", "validator", 2)
        assert doc is not None
        assert doc["instruction"] == "improved validator"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
