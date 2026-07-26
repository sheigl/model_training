"""Domain plugin abstraction — each knowledge domain implements this interface."""

from __future__ import annotations

import importlib
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, TypeVar

import yaml

from .data_source import DataSource
from .models import Model, ModelType

logger = logging.getLogger(__name__)

T = TypeVar("T")


# =============================================================================
# TEMPLATE CONFIG (loaded from YAML)
# =============================================================================


class TemplateConfig:
    """Configuration for a generation template, loaded from domain YAML."""

    def __init__(
        self,
        template_id: str,
        task_instruction: str,
        weight: float = 1.0,
        validation_rules: list[str] | None = None,
        min_answer_length: int = 80,
        max_answer_length: int = 2000,
    ):
        self.template_id = template_id
        self.task_instruction = task_instruction
        self.weight = weight
        self.validation_rules = validation_rules or []
        self.min_answer_length = min_answer_length
        self.max_answer_length = max_answer_length

    @classmethod
    def from_dict(cls, template_id: str, data: dict[str, Any]) -> "TemplateConfig":
        return cls(
            template_id=template_id,
            task_instruction=data.get("instruction", ""),
            weight=float(data.get("weight", 1.0)),
            validation_rules=data.get("validation_rules"),
            min_answer_length=int(data.get("min_answer_length", 80)),
            max_answer_length=int(data.get("max_answer_length", 2000)),
        )


# =============================================================================
# DOMAIN PLUGIN ABC
# =============================================================================


class DomainPlugin(ABC):
    """Abstract base class for domain plugins.

    Each domain (e.g., MTG, cooking, coding) implements this interface to provide:
    - Identity (name, display name)
    - LLM context (system message, notation/domain reference)
    - Data access (data source instance)
    - Generators (list of generator classes)
    - Template loading from YAML

    Usage:
        class MTGDomain(DomainPlugin):
            @property
            def name(self) -> str: return "mtg"
            ...
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short domain identifier (e.g., 'mtg', 'cooking')."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name for UI display."""
        ...

    @property
    @abstractmethod
    def system_message(self) -> str:
        """LLM system prompt / persona for this domain."""
        ...

    @property
    @abstractmethod
    def notation_legend(self) -> str:
        """Domain-specific reference material injected into prompts."""
        ...

    @abstractmethod
    def get_data_source(self, config: dict[str, Any] | None = None) -> DataSource:
        """Create and return a data source instance for this domain.

        Args:
            config: Optional connection config override (from app.yaml)
        """
        ...

    @abstractmethod
    def get_generators(self) -> list[type]:
        """Return list of generator classes available in this domain."""
        ...

    @abstractmethod
    def get_categories(self) -> list[str]:
        """Return list of category identifiers (e.g., ['combo_query', 'card_search'])."""
        ...

    # --- Template loading helpers ---

    def load_templates_yaml(self, templates_path: str | Path) -> dict[str, Any]:
        """Load domain templates from YAML file.

        Expected structure:
            system_message: "..."
            notation_legend: "..."
            categories:
              combo_query:
                description: "..."
                templates:
                  how_does_it_work:
                    instruction: "..."
                    validation_rules: [...]
                    weight: 1.0
        """
        with open(templates_path, "r") as f:
            return yaml.safe_load(f) or {}

    def get_templates_for_category(
        self, templates_yaml: dict[str, Any], category: str
    ) -> list[TemplateConfig]:
        """Extract TemplateConfig objects for a specific category from loaded YAML."""
        categories = templates_yaml.get("categories", {})
        cat_data = categories.get(category, {})
        raw_templates = cat_data.get("templates", {})

        return [
            TemplateConfig.from_dict(tid, tdata)
            for tid, tdata in raw_templates.items()
        ]


# =============================================================================
# DOMAIN REGISTRY
# =============================================================================


class DomainRegistry:
    """Discovers and manages domain plugins.

    Reads config/domains.yaml to find enabled domains, imports their modules,
    and instantiates plugin classes.
    """

    def __init__(self):
        self._domains: dict[str, DomainPlugin] = {}

    def register(self, domain: DomainPlugin) -> None:
        """Manually register a domain plugin instance."""
        self._domains[domain.name] = domain
        logger.info("Registered domain: %s (%s)", domain.name, domain.display_name)

    def discover_from_config(
        self, domains_config: dict[str, Any], src_dir: str | Path | None = None
    ) -> None:
        """Auto-discover domains from config/domains.yaml entries.

        For each enabled domain entry, imports the module and finds the
        DomainPlugin subclass (convention: class ending in 'Domain').
        """
        for name, info in domains_config.items():
            if not isinstance(info, dict):
                continue
            if not info.get("enabled", True):
                logger.info("Skipping disabled domain: %s", name)
                continue

            module_path = info.get("module_path")
            if not module_path:
                logger.warning("Domain '%s' has no module_path, skipping", name)
                continue

            try:
                module = importlib.import_module(f".{module_path}", package="domains")
                # Find the DomainPlugin subclass (convention: *Domain class)
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, DomainPlugin)
                        and attr is not DomainPlugin
                    ):
                        instance = attr()
                        self.register(instance)
                        logger.info(
                            "Discovered domain '%s' via %s.%s", name, module_path, attr_name
                        )
                        break
            except ImportError as e:
                logger.error("Failed to import domain '%s' from %s: %s", name, module_path, e)

    def get(self, name: str) -> DomainPlugin | None:
        """Get a registered domain by name."""
        return self._domains.get(name)

    def list_domains(self) -> list[DomainPlugin]:
        """Return all registered domains."""
        return list(self._domains.values())

    @property
    def domain_names(self) -> list[str]:
        """Return list of registered domain names."""
        return list(self._domains.keys())


# Singleton
_registry: DomainRegistry | None = None


def get_registry() -> DomainRegistry:
    global _registry
    if _registry is None:
        _registry = DomainRegistry()
    return _registry
