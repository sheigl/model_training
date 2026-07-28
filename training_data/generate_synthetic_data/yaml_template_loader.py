"""YAML-based template loader for the legacy synthetic-data CLI.

This module provides a :class:`YamlTemplateLoader` that reads generation
templates, scaffolding blocks, and validator prompts from local YAML files
instead of MongoDB documents. It mirrors the read surface of
:class:`template_store.TemplateStore` so downstream code can swap it in with
minimal changes.

File layout::

    templates/
        shared.yaml              # scaffolding blocks + shared validators
        comparison_validator.yaml  # per-generator validator override
        combo_query.yaml         # generation templates for combo queries
        card_search.yaml         # ...etc (one file per generator category)
        ...

The YAML schema intentionally mirrors the MongoDB ``yaml_content`` body shape
so that :meth:`template_store.TemplateStore.to_template_config` can be reused
with minimal changes.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class YamlTemplateLoader:
    """Load templates from local YAML files in the ``templates/`` directory."""

    SHARED_NAMESPACE = "__shared__"

    def __init__(self, templates_dir: str | None = None) -> None:
        """Construct a loader.

        * ``templates_dir`` — absolute or relative path to the templates root.
          If ``None``, resolves to ``<package_root>/templates/``.
        * The directory is validated to exist at construction time.
        """
        if templates_dir is None:
            self._templates_dir = Path(__file__).parent / "templates"
        else:
            self._templates_dir = Path(templates_dir)

        if not self._templates_dir.is_dir():
            raise ValueError(
                f"Templates directory does not exist: {self._templates_dir}"
            )

    # ------------------------------------------------------------------
    # Read paths — mirror TemplateStore surface
    # ------------------------------------------------------------------
    def get_latest(
        self, generator: str, template_id: str, template_type: str
    ) -> dict | None:
        """Return the matching entry as a dict compatible with
        :meth:`template_store.TemplateStore.to_template_config`, or ``None``.

        * For generation templates (``template_type == "generation"``): loads
          ``templates/{generator}.yaml``, finds the entry whose
          ``template_id`` matches, and returns it as-is.
        * For shared scaffolding/validators (``generator == SHARED_NAMESPACE``):
          loads ``templates/shared.yaml`` and looks up in the appropriate section.
        * For per-generator validator overrides: loads the corresponding
          ``templates/{generator}_validator.yaml`` file.
        """
        if generator == self.SHARED_NAMESPACE:
            return self._get_shared_entry(template_id, template_type)

        # Per-generator validator override (e.g. comparison_validator.yaml)
        if template_type == "validator":
            validator_file = self._templates_dir / f"{generator}_validator.yaml"
            if validator_file.is_file():
                data = self._load_yaml(validator_file)
                if isinstance(data, dict) and "instruction" in data:
                    return {"template_id": template_id, **data}
                if isinstance(data, list):
                    for entry in data:
                        if entry.get("template_id") == template_id:
                            result = dict(entry)
                            result.setdefault("version", "1")
                            return result
            # Fall through to shared validators
            return self._get_shared_entry(template_id, template_type)

        # Generation template — load category file
        category_file = self._templates_dir / f"{generator}.yaml"
        if not category_file.is_file():
            logger.debug("No category file found: %s", category_file)
            return None

        entries = self._load_yaml(category_file)
        if not isinstance(entries, list):
            logger.warning(
                "Category file %s did not produce a list; got %s",
                category_file, type(entries),
            )
            return None

        for entry in entries:
            if entry.get("template_id") == template_id:
                # Normalize: ensure 'instruction' key exists (support alias)
                if "instruction" not in entry and "task_instruction" in entry:
                    entry = dict(entry)
                    entry["instruction"] = entry.pop("task_instruction")
                # Set a stable version sentinel so trace recording works.
                result = dict(entry)
                result.setdefault("version", "1")
                return result

        return None

    def list_versions(
        self, generator: str, template_id: str, template_type: str
    ) -> list:
        """Return an empty list — YAML has no versioning support."""
        return []

    # ------------------------------------------------------------------
    # Convenience methods for shared content
    # ------------------------------------------------------------------
    def get_scaffolding(self) -> dict | None:
        """Load all scaffolding blocks from ``shared.yaml``.

        Returns a dict with keys matching the five expected scaffolding block
        IDs, or ``None`` if the file is missing or malformed.
        """
        shared = self._load_shared()
        if shared is None:
            return None
        return shared.get("scaffolding")

    def get_validator(self, validator_name: str) -> str | None:
        """Load a raw validator prompt template string from ``shared.yaml``.

        Returns the instruction text (with placeholders intact), or ``None``
        if not found.
        """
        shared = self._load_shared()
        if shared is None:
            return None
        validators = shared.get("validators")
        if not isinstance(validators, dict):
            return None
        instruction = validators.get(validator_name)
        if isinstance(instruction, str):
            return instruction
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_yaml(self, path: Path) -> Any:
        """Load and parse a YAML file, raising ``ValueError`` on syntax errors."""
        try:
            with open(path, encoding="utf-8") as f:
                return yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise ValueError(
                f"Malformed YAML in {path}: {exc}"
            ) from exc

    def _load_shared(self) -> dict | None:
        """Load ``shared.yaml`` and return its top-level dict, or ``None``."""
        shared_path = self._templates_dir / "shared.yaml"
        if not shared_path.is_file():
            logger.debug("No shared.yaml found at %s", shared_path)
            return None
        data = self._load_yaml(shared_path)
        if not isinstance(data, dict):
            logger.warning(
                "shared.yaml did not produce a dict; got %s", type(data)
            )
            return None
        return data

    def _get_shared_entry(
        self, template_id: str, template_type: str
    ) -> dict | None:
        """Look up an entry in ``shared.yaml`` by (template_id, template_type)."""
        shared = self._load_shared()
        if shared is None:
            return None

        # Scaffolding entries are under "scaffolding" with the template_id as key
        scaffolding = shared.get("scaffolding")
        if isinstance(scaffolding, dict) and template_id in scaffolding:
            content = scaffolding[template_id]
            result: dict[str, Any] = {
                "template_id": template_id,
                "instruction": content if isinstance(content, str) else "",
            }
            if template_type == "generation" and isinstance(content, list):
                # requirements_base is a list — wrap it appropriately
                result["content"] = content
            return result

        # Validator entries are under "validators"
        validators = shared.get("validators")
        if isinstance(validators, dict) and template_id in validators:
            instruction = validators[template_id]
            if isinstance(instruction, str):
                return {
                    "template_id": template_id,
                    "instruction": instruction,
                }

        return None
