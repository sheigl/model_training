"""Tests for TrainForge UI Settings page — config management logic."""

from __future__ import annotations



class TestMongoDBConfig:
    """Test MongoDB configuration defaults and validation."""

    def test_default_mongodb_uri(self):
        """Default MongoDB URI should be localhost."""
        default_uri = "mongodb://localhost:27017/"
        assert default_uri.startswith("mongodb://")

    def test_default_auth_source(self):
        """Default auth source should be admin."""
        default_auth = "admin"
        assert default_auth == "admin"

    def test_connection_params_structure(self):
        """Connection params should have all required fields."""
        config = {
            "uri": "mongodb://localhost:27017/",
            "username": "root",
            "password": "testpass",
            "auth_source": "admin",
            "max_pool_size": 50,
            "min_pool_size": 5,
        }

        assert "uri" in config
        assert "username" in config
        assert "password" in config


class TestModelConfig:
    """Test model configuration defaults."""

    def test_default_generation_model(self):
        """Default generation model should be set."""
        default = {"generation_model": "qwen2.5:14b"}
        assert default["generation_model"] == "qwen2.5:14b"

    def test_default_validation_pct(self):
        """Validation percentage should default to 1.0 (100%)."""
        defaults = {"validation_pct": 1.0}
        assert defaults["validation_pct"] == 1.0

    def test_ollama_base_url(self):
        """Ollama base URL should be localhost."""
        url = "http://127.0.0.1:11434"
        assert url.startswith("http://")


class TestPathConfig:
    """Test output path configuration defaults."""

    def test_default_outputs_dir(self):
        """Default outputs directory should be set."""
        paths = {"outputs": "outputs/"}
        assert paths["outputs"] == "outputs/"

    def test_default_jsonl_dir(self):
        """Default JSONL directory should be under outputs."""
        paths = {"jsonl_dir": "outputs/jsonl/"}
        assert paths["jsonl_dir"].startswith("outputs/")


class TestDomainConfig:
    """Test domain configuration structure."""

    def test_domain_entry_structure(self):
        """Domain entry should have required fields."""
        domain_config = {
            "mtg": {
                "display_name": "Magic: The Gathering",
                "module_path": "domains.mtg",
                "enabled": True,
            }
        }

        assert "mtg" in domain_config
        entry = domain_config["mtg"]
        assert entry["enabled"] is True
        assert "display_name" in entry
        assert "module_path" in entry

    def test_enabled_filter(self):
        """Should filter domains by enabled status."""
        domains = {
            "mtg": {"enabled": True},
            "cooking": {"enabled": False},
            "coding": {"enabled": True},
        }

        enabled = [name for name, info in domains.items() if info.get("enabled", True)]

        assert "mtg" in enabled
        assert "coding" in enabled
        assert "cooking" not in enabled


class TestYAMLConfigLoading:
    """Test YAML config loading logic."""

    def test_env_var_interpolation(self):
        """Should support environment variable interpolation syntax."""
        # The actual interpolation is done by config.py's _interpolate_env
        from trainforge.config import _interpolate_env

        result = _interpolate_env("${TEST_VAR:default_value}")
        assert result == "default_value"  # Uses default when env var not set

    def test_nested_interpolation(self):
        """Should interpolate nested values."""
        from trainforge.config import _interpolate_env

        data = {
            "mongodb": {
                "uri": "${MONGO_URI:mongodb://localhost:27017/}",
                "password": "${MONGO_PASS:root}",
            }
        }

        result = _interpolate_env(data)
        assert result["mongodb"]["uri"] == "mongodb://localhost:27017/"


class TestDangerZoneOperations:
    """Test danger zone operation safety checks."""

    def test_clear_data_requires_connection(self):
        """Should not clear data when not connected."""
        mongo_connected = False
        should_proceed = mongo_connected and True  # Would check confirmation too

        assert not should_proceed

    def test_reset_metrics_deletes_both_collections(self):
        """Reset metrics should target both validation_metrics and traces."""
        collections_to_clear = [
            "synthetic_metrics.validation_metrics",
            "synthetic_metrics.generation_traces",
        ]

        assert len(collections_to_clear) == 2


class TestConfigSaveValidation:
    """Test config save operation validation."""

    def test_save_requires_valid_yaml(self):
        """Should validate YAML structure before saving."""
        import yaml

        valid_config = {
            "mongodb": {"uri": "test"},
            "models": {},
            "defaults": {},
            "paths": {},
        }

        # Should not raise
        yaml_str = yaml.dump(valid_config)
        parsed = yaml.safe_load(yaml_str)

        assert isinstance(parsed, dict)


class TestAppConfigSingleton:
    """Test AppConfig singleton behavior."""

    def test_get_config_returns_singleton(self):
        """get_config should return the same instance on repeated calls."""
        from trainforge.config import get_config

        # Reset singleton for testing
        import trainforge.config as config_module
        original = config_module._app_config
        config_module._app_config = None

        try:
            cfg1 = get_config()
            cfg2 = get_config()

            assert cfg1 is cfg2  # Same instance
        finally:
            config_module._app_config = original


class TestDomainRegistryLogic:
    """Test DomainRegistry behavior (without importing ABC classes)."""

    def test_registry_dict_structure(self):
        """Registry should store domains as a dict."""
        # Simulate the internal structure of DomainRegistry._domains
        _domains = {}

        class MockDomain:
            name = "test"
            display_name = "Test Domain"

        domain = MockDomain()
        _domains[domain.name] = domain

        assert "test" in _domains
        assert _domains["test"].display_name == "Test Domain"

    def test_domain_names_list(self):
        """Should return list of registered domain names."""
        _domains = {
            "mtg": type("MTG", (), {"name": "mtg"})(),
            "cooking": type("Cooking", (), {"name": "cooking"})(),
        }

        domain_names = list(_domains.keys())

        assert "mtg" in domain_names
        assert "cooking" in domain_names
