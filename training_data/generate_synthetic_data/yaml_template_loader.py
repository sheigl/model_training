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


def legacy_version_target(templates_dir: Path, generator: str, version: int) -> str:
    """Resolve which namespace a legacy single-counter version belongs to.

    Legacy manifests recorded only a shared ``active_version`` without
    distinguishing generation vs validator templates. The file that actually
    exists on disk disambiguates: ``{generator}_validator_v{N}.yaml``
    indicates a validator improvement, ``{generator}_v{N}.yaml`` a
    generation improvement. Defaults to ``"generation"`` when neither file
    exists.
    """
    if (templates_dir / f"{generator}_validator_v{version}.yaml").is_file():
        return "validator"
    return "generation"


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

    def get_version(
        self, generator: str, template_id: str, template_type: str, version: int
    ) -> dict | None:
        """Load a specific historical version from ``templates/{generator}_v{N}.yaml``.

        For generation templates, reads the versioned file and returns the entry
        matching *template_id*. Falls back to the base (unversioned) file if the
        versioned file does not exist.

        For non-generation types, delegates to :meth:`get_latest`.
        """
        if template_type == "validator":
            # Versioned per-generator validator override: {generator}_validator_v{N}.yaml
            versioned_file = self._templates_dir / f"{generator}_validator_v{version}.yaml"
            if versioned_file.is_file():
                data = self._load_yaml(versioned_file)
                if isinstance(data, dict) and "instruction" in data:
                    return {"template_id": template_id, **data}
                if isinstance(data, list):
                    for entry in data:
                        if entry.get("template_id") == template_id:
                            result = dict(entry)
                            result.setdefault("version", str(version))
                            return result
            # Fall through to latest validator resolution
            return self.get_latest(generator, template_id, template_type)

        if template_type != "generation":
            return self.get_latest(generator, template_id, template_type)

        filename = f"{generator}_v{version}.yaml"
        path = self._templates_dir / filename
        if not path.is_file():
            # Fall back to base file
            path = self._templates_dir / f"{generator}.yaml"
        if not path.is_file():
            return None

        entries = self._load_yaml(path)
        if not isinstance(entries, list):
            return None
        for entry in entries:
            if isinstance(entry, dict) and entry.get("template_id") == template_id:
                result = dict(entry)
                result.setdefault("version", version)
                # Normalise instruction key
                if "instruction" not in result and "task_instruction" in result:
                    result["instruction"] = result.pop("task_instruction")
                return result
        return None

    def list_versions(
        self, generator: str, template_id: str, template_type: str
    ) -> list:
        """Return an empty list — YAML has no versioning support."""
        return []

    def list_templates(self, generator: str) -> list[str]:
        """Return all template_ids defined for *generator* in its category file.

        Loads ``templates/{generator}.yaml`` and returns the list of
        ``template_id`` values found in the entries. Returns an empty list when
        the category file is missing or does not contain a list of entries.
        """
        category_file = self._templates_dir / f"{generator}.yaml"
        if not category_file.is_file():
            return []
        entries = self._load_yaml(category_file)
        if not isinstance(entries, list):
            return []
        return [e.get("template_id") for e in entries if isinstance(e, dict) and e.get("template_id")]

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
    # Observer manifest support
    # ------------------------------------------------------------------

    def _load_observer_manifest(self) -> dict:
        """Load ``_observer_manifest.json`` from the templates directory."""
        import json as _json
        manifest_path = self._templates_dir / "_observer_manifest.json"
        if not manifest_path.is_file():
            return {"categories": {}}
        try:
            with open(manifest_path, encoding="utf-8") as f:
                data = _json.load(f)
            if isinstance(data, dict) and "categories" in data:
                return data
        except (_json.JSONDecodeError, OSError):
            pass
        return {"categories": {}}

    def _legacy_version_target(
        self, generator: str, version: int
    ) -> str:
        """Resolve which namespace a legacy single-counter version belongs to.

        Legacy manifests recorded only a shared ``active_version`` without
        distinguishing generation vs validator templates. The file that actually
        exists on disk disambiguates: ``{generator}_validator_v{N}.yaml``
        indicates a validator improvement, ``{generator}_v{N}.yaml`` a
        generation improvement. Defaults to ``"generation"`` when neither file
        exists.
        """
        return legacy_version_target(self._templates_dir, generator, version)

    def _get_active_version(
        self, generator: str, version_type: str
    ) -> int | None:
        """Return the active (best historical) version for *generator*.

        Reads ``active_generation_version`` or ``active_validator_version``
        from the observer manifest, migrating the legacy single-counter
        ``active_version`` into the generation namespace.

        Args:
            generator: Category name.
            version_type: ``"generation"`` or ``"validator"``.

        Returns:
            Best version number (> 1 means an override exists), or ``None``
            when no manifest/entry is present.
        """
        manifest = self._load_observer_manifest()
        cat_data = manifest.get("categories", {}).get(generator, {})
        if version_type == "generation":
            version = cat_data.get("active_generation_version")
            if version is None:
                # Legacy single-counter schema — only treat it as a generation
                # version when the generation file actually exists.
                legacy = cat_data.get("active_version")
                if legacy and self._legacy_version_target(generator, int(legacy)) == "generation":
                    version = legacy
        else:
            version = cat_data.get("active_validator_version")
            if version is None:
                # Legacy single-counter schema — treat it as a validator version
                # only when the versioned validator file actually exists.
                legacy = cat_data.get("active_version")
                if legacy and self._legacy_version_target(generator, int(legacy)) == "validator":
                    version = legacy
        if not version:
            return None
        return int(version)

    def load_active_templates(self, generator: str) -> list[dict] | None:
        """Check the observer manifest for a historically-best version.

        If the manifest records a best generation version > 1 for *generator*,
        loads that specific historical version instead of the latest. Falls
        back to :meth:`get_latest` when no override is recorded or the best
        version is 1.

        Returns a list of template dicts (compatible with
        :func:`common._dict_to_template_config`), or ``None`` to fall through.
        """
        best_version = self._get_active_version(generator, "generation")
        if not best_version or best_version <= 1:
            return None

        template_ids = self.list_templates(generator)
        if not template_ids:
            return None

        result = []
        for tid in template_ids:
            doc = self.get_version(generator, tid, "generation", best_version)
            if doc:
                result.append(doc)
        return result if result else None

    def get_active_validator_version(self, generator: str) -> int | None:
        """Return the best historical validator version for *generator*, or ``None``."""
        return self._get_active_version(generator, "validator")

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
