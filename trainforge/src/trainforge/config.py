"""YAML configuration loader with environment variable interpolation."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml


def _interpolate_env(obj: Any) -> Any:
    """Recursively replace ${VAR} and ${VAR:default} patterns in strings."""
    if isinstance(obj, str):
        return re.sub(
            r"\$\{([^}:]+)(?::([^}]*))?\}",
            lambda m: os.environ.get(m.group(1), m.group(2) or ""),
            obj,
        )
    elif isinstance(obj, dict):
        return {k: _interpolate_env(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_interpolate_env(item) for item in obj]
    return obj


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Load a YAML file with environment variable interpolation."""
    with open(path, "r") as f:
        data = yaml.safe_load(f) or {}
    return _interpolate_env(data)


class AppConfig:
    """Global application configuration loaded from config/app.yaml."""

    def __init__(self, config_dir: str | Path | None = None):
        if config_dir is None:
            # This file is at src/trainforge/config.py
            # Project root: config.py → trainforge(pkg) → src → trainforge(project) = 3 parents up
            candidates = [
                Path(__file__).resolve().parent.parent.parent / "config",  # project root/config/
                Path.cwd() / "config",                                     # current working directory
            ]
            for candidate in candidates:
                if (candidate / "app.yaml").exists():
                    config_dir = candidate
                    break
            else:
                config_dir = candidates[0]
        
        self._config_dir = Path(config_dir)
        self.app_config: dict[str, Any] = {}
        self.domains_config: dict[str, Any] = {}

    def load(self) -> None:
        """Load all configuration files."""
        app_path = self._config_dir / "app.yaml"
        if app_path.exists():
            self.app_config = load_yaml(app_path)

        domains_path = self._config_dir / "domains.yaml"
        if domains_path.exists():
            self.domains_config = load_yaml(domains_path)

    @property
    def mongodb(self) -> dict[str, Any]:
        return self.app_config.get("mongodb", {})

    @property
    def models(self) -> dict[str, Any]:
        return self.app_config.get("models", {})

    @property
    def defaults(self) -> dict[str, Any]:
        return self.app_config.get("defaults", {})

    @property
    def paths(self) -> dict[str, str]:
        return self.app_config.get("paths", {})

    def get_domain_list(self) -> list[dict[str, Any]]:
        """Return list of enabled domains from registry."""
        domains = self.domains_config.get("domains", {})
        return [d for d in domains.values() if isinstance(d, dict) and d.get("enabled", True)]


# Singleton instance
_app_config: AppConfig | None = None


def get_config(config_dir: str | Path | None = None) -> AppConfig:
    """Get or create the global app config singleton."""
    global _app_config
    if _app_config is None:
        _app_config = AppConfig(config_dir)
        _app_config.load()
    return _app_config
