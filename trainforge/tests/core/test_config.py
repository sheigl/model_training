"""Tests for TrainForge config — YAML loading, env var interpolation, singleton."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from trainforge.config import AppConfig, _interpolate_env, get_config, load_yaml


# =============================================================================
# ENV VAR INTERPOLATION
# =============================================================================


class TestEnvVarInterpolation:
    """Test _interpolate_env() function."""

    def test_simple_var_replacement(self):
        """Should replace ${VAR} with environment variable value."""
        os.environ["TEST_VAR"] = "hello"
        result = _interpolate_env("${TEST_VAR}")
        assert result == "hello"
        del os.environ["TEST_VAR"]

    def test_var_with_default(self):
        """Should use default when var is not set: ${VAR:default}."""
        if "NONEXISTENT_VAR_XYZ" in os.environ:
            del os.environ["NONEXISTENT_VAR_XYZ"]
        result = _interpolate_env("${NONEXISTENT_VAR_XYZ:fallback}")
        assert result == "fallback"

    def test_var_with_empty_default(self):
        """Should use empty string when var is not set and no default: ${VAR}."""
        if "MISSING_VAR_ABC" in os.environ:
            del os.environ["MISSING_VAR_ABC"]
        result = _interpolate_env("${MISSING_VAR_ABC}")
        assert result == ""

    def test_var_with_default_empty_string(self):
        """Should use empty string default when explicitly set: ${VAR:}."""
        if "EMPTY_DEFAULT_VAR" in os.environ:
            del os.environ["EMPTY_DEFAULT_VAR"]
        result = _interpolate_env("${EMPTY_DEFAULT_VAR:}")
        assert result == ""

    def test_mixed_text_with_vars(self):
        """Should interpolate vars within surrounding text."""
        os.environ["HOST"] = "localhost"
        os.environ["PORT"] = "27017"
        result = _interpolate_env("mongodb://${HOST}:${PORT}/db")
        assert result == "mongodb://localhost:27017/db"

    def test_multiple_vars_in_string(self):
        """Should handle multiple vars in one string."""
        os.environ["A"] = "one"
        os.environ["B"] = "two"
        result = _interpolate_env("${A}-${B}")
        assert result == "one-two"

    def test_non_string_unchanged(self):
        """Non-string values should pass through unchanged."""
        assert _interpolate_env(42) == 42
        assert _interpolate_env(True) is True
        assert _interpolate_env(None) is None
        assert _interpolate_env(3.14) == 3.14

    def test_dict_interpolation(self):
        """Should recursively interpolate dict values."""
        os.environ["DB_HOST"] = "mongo.local"
        result = _interpolate_env({"host": "${DB_HOST}", "port": 27017})
        assert result == {"host": "mongo.local", "port": 27017}

    def test_list_interpolation(self):
        """Should recursively interpolate list items."""
        os.environ["ITEM"] = "replaced"
        result = _interpolate_env(["${ITEM}", "static"])
        assert result == ["replaced", "static"]


# =============================================================================
# YAML LOADING
# =============================================================================


class TestYAMLLoading:
    """Test load_yaml() function."""

    def test_load_valid_yaml(self):
        """Should parse valid YAML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("key: value\nnumber: 42\n")
            f.flush()
            result = load_yaml(f.name)
        Path(f.name).unlink()
        assert result["key"] == "value"
        assert result["number"] == 42

    def test_load_empty_file(self):
        """Should return empty dict for empty YAML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")
            f.flush()
            result = load_yaml(f.name)
        Path(f.name).unlink()
        assert result == {}

    def test_load_with_env_interpolation(self):
        """Should interpolate env vars in YAML content."""
        os.environ["TEST_DB_URI"] = "mongodb://test:27017"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("uri: ${TEST_DB_URI}\n")
            f.flush()
            result = load_yaml(f.name)
        Path(f.name).unlink()
        assert result["uri"] == "mongodb://test:27017"
        del os.environ["TEST_DB_URI"]

    def test_nested_interpolation(self):
        """Should interpolate env vars in nested structures."""
        os.environ["NESTED_VAL"] = "deep_value"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("level1:\n  level2:\n    val: ${NESTED_VAL}\n")
            f.flush()
            result = load_yaml(f.name)
        Path(f.name).unlink()
        assert result["level1"]["level2"]["val"] == "deep_value"
        del os.environ["NESTED_VAL"]


# =============================================================================
# APP CONFIG SINGLETON
# =============================================================================


class TestAppConfigSingleton:
    """Test AppConfig singleton behavior via get_config()."""

    def setup_method(self):
        """Reset the singleton before each test."""
        import trainforge.config as cfg_module
        cfg_module._app_config = None

    def teardown_method(self):
        """Clean up after each test."""
        import trainforge.config as cfg_module
        cfg_module._app_config = None

    def test_singleton_returns_same_instance(self):
        """get_config() should return the same instance on repeated calls."""
        config1 = get_config()
        config2 = get_config()
        assert config1 is config2

    def test_loads_app_yaml_by_default(self):
        """Should load app.yaml from default config directory."""
        cfg = get_config()
        # The project's app.yaml should be loaded
        assert "mongodb" in cfg.app_config or len(cfg.app_config) > 0

    def test_custom_config_dir(self):
        """Should accept custom config directory path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "app.yaml"
            config_path.write_text("mongodb:\n  uri: 'custom-uri'\n")
            domains_path = Path(tmpdir) / "domains.yaml"
            domains_path.write_text("domains: {}\n")

            cfg = get_config(config_dir=tmpdir)
            assert cfg.mongodb["uri"] == "custom-uri"

    def test_missing_app_yaml_is_handled(self):
        """Should handle missing app.yaml gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # No files in directory
            cfg = get_config(config_dir=tmpdir)
            assert cfg.app_config == {}


# =============================================================================
# NESTED CONFIG ACCESS
# =============================================================================


class TestNestedConfigAccess:
    """Test AppConfig property accessors."""

    def setup_method(self):
        import trainforge.config as cfg_module
        cfg_module._app_config = None

    def teardown_method(self):
        import trainforge.config as cfg_module
        cfg_module._app_config = None

    def test_mongodb_property(self):
        """Should return mongodb config section."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "app.yaml").write_text(
                "mongodb:\n  uri: 'test-uri'\n  max_pool_size: 10\n"
            )
            (Path(tmpdir) / "domains.yaml").write_text("domains: {}\n")
            cfg = get_config(config_dir=tmpdir)
            assert cfg.mongodb["uri"] == "test-uri"
            assert cfg.mongodb["max_pool_size"] == 10

    def test_models_property(self):
        """Should return models config section."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "app.yaml").write_text(
                "models:\n  ollama_base_url: 'http://test:11434'\n"
            )
            (Path(tmpdir) / "domains.yaml").write_text("domains: {}\n")
            cfg = get_config(config_dir=tmpdir)
            assert cfg.models["ollama_base_url"] == "http://test:11434"

    def test_defaults_property(self):
        """Should return defaults config section."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "app.yaml").write_text(
                "defaults:\n  generation_model: 'llama3'\n  validation_pct: 0.5\n"
            )
            (Path(tmpdir) / "domains.yaml").write_text("domains: {}\n")
            cfg = get_config(config_dir=tmpdir)
            assert cfg.defaults["generation_model"] == "llama3"

    def test_paths_property(self):
        """Should return paths config section."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "app.yaml").write_text(
                "paths:\n  outputs: '/custom/outputs'\n"
            )
            (Path(tmpdir) / "domains.yaml").write_text("domains: {}\n")
            cfg = get_config(config_dir=tmpdir)
            assert cfg.paths["outputs"] == "/custom/outputs"

    def test_empty_sections_return_empty_dict(self):
        """Missing sections should return empty dict, not raise."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "app.yaml").write_text("app:\n  name: 'test'\n")
            (Path(tmpdir) / "domains.yaml").write_text("domains: {}\n")
            cfg = get_config(config_dir=tmpdir)
            assert cfg.mongodb == {}
            assert cfg.models == {}
            assert cfg.defaults == {}

    def test_get_domain_list_enabled_only(self):
        """Should return only enabled domains."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "app.yaml").write_text("{}\n")
            (Path(tmpdir) / "domains.yaml").write_text(
                "domains:\n"
                "  mtg:\n    display_name: 'MTG'\n    enabled: true\n"
                "  cooking:\n    display_name: 'Cooking'\n    enabled: false\n"
            )
            cfg = get_config(config_dir=tmpdir)
            domains = cfg.get_domain_list()
            assert len(domains) == 1
            assert domains[0]["display_name"] == "MTG"
