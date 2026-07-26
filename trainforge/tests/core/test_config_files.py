"""Config file validation tests - verify YAML structure and content."""

from __future__ import annotations

import yaml
from pathlib import Path

import pytest


# Project root for config paths (tests/core/ -> tests/ -> trainforge/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class TestAppYAML:
    """Verify config/app.yaml is valid YAML with expected structure."""

    def test_app_yaml_is_valid(self):
        """app.yaml should parse as valid YAML."""
        path = PROJECT_ROOT / "config" / "app.yaml"
        assert path.exists(), f"app.yaml not found at {path}"

        with open(path) as f:
            data = yaml.safe_load(f)

        assert isinstance(data, dict)

    def test_app_yaml_has_mongodb_section(self):
        """Should have mongodb configuration section."""
        path = PROJECT_ROOT / "config" / "app.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)

        assert "mongodb" in data
        mongo = data["mongodb"]
        assert "uri" in mongo
        assert "auth_source" in mongo

    def test_app_yaml_has_models_section(self):
        """Should have models configuration section."""
        path = PROJECT_ROOT / "config" / "app.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)

        assert "models" in data
        models = data["models"]
        assert "ollama_base_url" in models

    def test_app_yaml_has_defaults_section(self):
        """Should have defaults configuration section."""
        path = PROJECT_ROOT / "config" / "app.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)

        assert "defaults" in data
        defaults = data["defaults"]
        assert "generation_model" in defaults
        assert "validation_pct" in defaults

    def test_app_yaml_has_paths_section(self):
        """Should have paths configuration section."""
        path = PROJECT_ROOT / "config" / "app.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)

        assert "paths" in data
        paths = data["paths"]
        assert "outputs" in paths
        assert "jsonl_dir" in paths

    def test_app_yaml_env_var_syntax(self):
        """Should use ${VAR} or ${VAR:default} syntax for env vars."""
        path = PROJECT_ROOT / "config" / "app.yaml"
        content = path.read_text()
        # Should contain at least one env var reference
        assert "${MONGODB_URI:" in content


class TestDomainsYAML:
    """Verify config/domains.yaml is valid YAML with expected structure."""

    def test_domains_yaml_is_valid(self):
        """domains.yaml should parse as valid YAML."""
        path = PROJECT_ROOT / "config" / "domains.yaml"
        assert path.exists(), f"domains.yaml not found at {path}"

        with open(path) as f:
            data = yaml.safe_load(f)

        assert isinstance(data, dict)
        assert "domains" in data

    def test_domains_yaml_has_mtg_entry(self):
        """Should have MTG domain entry."""
        path = PROJECT_ROOT / "config" / "domains.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)

        mtg = data["domains"]["mtg"]
        assert mtg["display_name"] == "Magic: The Gathering"
        assert mtg["module_path"] == "domains.mtg"
        assert mtg["enabled"] is True


class TestMTGConfigYAML:
    """Verify domains/mtg/config.yaml is valid YAML."""

    def test_mtg_config_is_valid(self):
        """MTG config should parse as valid YAML."""
        path = PROJECT_ROOT / "domains" / "mtg" / "config.yaml"
        assert path.exists(), f"MTG config.yaml not found at {path}"

        with open(path) as f:
            data = yaml.safe_load(f)

        assert isinstance(data, dict)
        assert "domain" in data
        assert data["domain"]["name"] == "mtg"


class TestMTGTemplatesYAML:
    """Verify domains/mtg/templates.yaml has all 27 categories with templates."""

    def test_templates_yaml_is_valid(self):
        """templates.yaml should parse as valid YAML."""
        path = PROJECT_ROOT / "domains" / "mtg" / "templates.yaml"
        assert path.exists(), f"templates.yaml not found at {path}"

        with open(path) as f:
            data = yaml.safe_load(f)

        assert isinstance(data, dict)
        assert "categories" in data

    def test_has_system_message(self):
        """Should have a system_message field."""
        path = PROJECT_ROOT / "domains" / "mtg" / "templates.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)

        assert "system_message" in data
        assert len(data["system_message"].strip()) > 0

    def test_has_notation_legend(self):
        """Should have a notation_legend field."""
        path = PROJECT_ROOT / "domains" / "mtg" / "templates.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)

        assert "notation_legend" in data
        assert len(data["notation_legend"].strip()) > 0

    def test_has_27_categories(self):
        """Should have exactly 27 categories."""
        path = PROJECT_ROOT / "domains" / "mtg" / "templates.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)

        cats = data["categories"]
        assert len(cats) == 27, f"Expected 27 categories, got {len(cats)}: {list(cats.keys())}"

    def test_each_category_has_at_least_one_template(self):
        """Every category should have at least 1 template."""
        path = PROJECT_ROOT / "domains" / "mtg" / "templates.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)

        for cat_name, cat_data in data["categories"].items():
            templates = cat_data.get("templates", {})
            assert len(templates) >= 1, (
                f"Category '{cat_name}' has no templates"
            )

    def test_each_template_has_instruction(self):
        """Every template should have an instruction field."""
        path = PROJECT_ROOT / "domains" / "mtg" / "templates.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)

        for cat_name, cat_data in data["categories"].items():
            for tpl_name, tpl_data in cat_data.get("templates", {}).items():
                assert "instruction" in tpl_data, (
                    f"Template '{tpl_name}' in category '{cat_name}' missing 'instruction'"
                )

    def test_known_categories_present(self):
        """Should include all known MTG categories."""
        path = PROJECT_ROOT / "domains" / "mtg" / "templates.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)

        expected_cats = [
            "combo_query",
            "article_qa",
            "card_search",
            "comparison",
            "reverse_lookup",
            "synergy",
            "budget",
            "color_identity",
            "guidelines",
            "terminology",
            "deckbuilding_theory",
            "commander_building",
            "rules_scenarios",
            "archetypes",
            "game_theory",
            "meta_knowledge",
            "commander_knowledge",
            "rule_explanations",
            "rule_interactions",
            "glossary_with_examples",
            "rule_edge_cases",
            "rule_why_questions",
            "guide_qa",
            "staple_analysis",
            "color_staples",
            "salt_questions",
            "multi_card_usage",
        ]

        cats = set(data["categories"].keys())
        for expected in expected_cats:
            assert expected in cats, f"Missing category: {expected}"

    def test_combo_query_has_4_templates(self):
        """combo_query should have 4 templates."""
        path = PROJECT_ROOT / "domains" / "mtg" / "templates.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)

        combo_templates = data["categories"]["combo_query"]["templates"]
        assert len(combo_templates) == 4
        expected_ids = [
            "how_does_it_work",
            "what_do_i_need",
            "why_does_this_work",
            "what_is_the_result",
        ]
        for tpl_id in expected_ids:
            assert tpl_id in combo_templates
