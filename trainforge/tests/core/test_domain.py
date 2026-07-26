"""Tests for TrainForge domain module — TemplateConfig, DomainRegistry."""

from __future__ import annotations

import pytest

from trainforge.domain import (
    DomainPlugin,
    DomainRegistry,
    TemplateConfig,
    get_registry,
)


# =============================================================================
# TEMPLATE CONFIG FROM DICT
# =============================================================================


class TestTemplateConfigFromDict:
    """Test TemplateConfig.from_dict() parsing."""

    def test_basic_from_dict(self):
        """Should parse minimal dict with instruction only."""
        tc = TemplateConfig.from_dict("test_template", {"instruction": "Do something"})
        assert tc.template_id == "test_template"
        assert tc.task_instruction == "Do something"
        assert tc.weight == 1.0
        assert tc.validation_rules == []

    def test_full_from_dict(self):
        """Should parse dict with all fields."""
        data = {
            "instruction": "Generate Q&A",
            "weight": 2.5,
            "validation_rules": ["rule1", "rule2"],
            "min_answer_length": 100,
            "max_answer_length": 3000,
        }
        tc = TemplateConfig.from_dict("full_template", data)
        assert tc.template_id == "full_template"
        assert tc.task_instruction == "Generate Q&A"
        assert tc.weight == 2.5
        assert tc.validation_rules == ["rule1", "rule2"]
        assert tc.min_answer_length == 100
        assert tc.max_answer_length == 3000

    def test_default_values_from_dict(self):
        """Should use defaults for missing fields."""
        tc = TemplateConfig.from_dict("minimal", {})
        assert tc.task_instruction == ""
        assert tc.weight == 1.0
        assert tc.validation_rules == []
        assert tc.min_answer_length == 80
        assert tc.max_answer_length == 2000

    def test_weight_type_coercion(self):
        """Should coerce weight to float."""
        data = {"instruction": "test", "weight": "3"}
        tc = TemplateConfig.from_dict("coerce_test", data)
        assert tc.weight == 3.0
        assert isinstance(tc.weight, float)

    def test_answer_length_type_coercion(self):
        """Should coerce answer lengths to int."""
        data = {"instruction": "test", "min_answer_length": "50", "max_answer_length": "1500"}
        tc = TemplateConfig.from_dict("coerce_len", data)
        assert tc.min_answer_length == 50
        assert tc.max_answer_length == 1500


# =============================================================================
# DOMAIN REGISTRY
# =============================================================================


class TestDomainRegistry:
    """Test DomainRegistry register/get/list_domains."""

    def _make_mock_domain(self, name: str) -> DomainPlugin:
        """Create a concrete mock domain for testing."""

        class MockDomain(DomainPlugin):
            @property
            def name(self) -> str:
                return name

            @property
            def display_name(self) -> str:
                return f"Mock {name}"

            @property
            def system_message(self) -> str:
                return "System message for mock"

            @property
            def notation_legend(self) -> str:
                return ""

            def get_data_source(self, config=None):
                raise NotImplementedError

            def get_generators(self):
                return []

            def get_categories(self):
                return ["cat1"]

        return MockDomain()

    def test_register_domain(self):
        """Should register a domain and make it retrievable."""
        reg = DomainRegistry()
        domain = self._make_mock_domain("test")
        reg.register(domain)
        assert reg.get("test") is domain

    def test_get_nonexistent_returns_none(self):
        """Should return None for unregistered domain name."""
        reg = DomainRegistry()
        assert reg.get("nonexistent") is None

    def test_list_domains_empty(self):
        """Empty registry should return empty list."""
        reg = DomainRegistry()
        assert reg.list_domains() == []

    def test_list_domains_multiple(self):
        """Should return all registered domains."""
        reg = DomainRegistry()
        d1 = self._make_mock_domain("alpha")
        d2 = self._make_mock_domain("beta")
        reg.register(d1)
        reg.register(d2)

        domains = reg.list_domains()
        assert len(domains) == 2
        names = {d.name for d in domains}
        assert "alpha" in names
        assert "beta" in names

    def test_domain_names_property(self):
        """Should return list of registered domain names."""
        reg = DomainRegistry()
        reg.register(self._make_mock_domain("x"))
        reg.register(self._make_mock_domain("y"))
        assert sorted(reg.domain_names) == ["x", "y"]

    def test_overwrite_existing_domain(self):
        """Registering same name should overwrite."""
        reg = DomainRegistry()
        d1 = self._make_mock_domain("dup")
        d2 = self._make_mock_domain("dup")
        reg.register(d1)
        reg.register(d2)

        assert reg.get("dup") is d2
        assert len(reg.list_domains()) == 1


# =============================================================================
# MTG DOMAIN CATEGORY LOADING
# =============================================================================


class TestMTGDomainCategories:
    """Test MTGDomain category loading from templates.yaml."""

    def test_mtg_domain_has_27_categories(self):
        """MTG domain should expose exactly 27 categories."""
        from trainforge.domains.mtg import MTGDomain

        domain = MTGDomain()
        cats = domain.get_categories()
        assert len(cats) == 27, f"Expected 27 categories, got {len(cats)}: {cats}"

    def test_mtg_domain_name(self):
        """MTG domain name should be 'mtg'."""
        from trainforge.domains.mtg import MTGDomain

        domain = MTGDomain()
        assert domain.name == "mtg"

    def test_mtg_display_name(self):
        """MTG display name should be human-readable."""
        from trainforge.domains.mtg import MTGDomain

        domain = MTGDomain()
        assert domain.display_name == "Magic: The Gathering"

    def test_mtg_system_message_loaded(self):
        """System message should be loaded from templates.yaml."""
        from trainforge.domains.mtg import MTGDomain

        domain = MTGDomain()
        msg = domain.system_message
        assert len(msg) > 0
        assert "Magic: The Gathering" in msg or "expert" in msg.lower()

    def test_mtg_notation_legend_loaded(self):
        """Notation legend should be loaded from templates.yaml."""
        from trainforge.domains.mtg import MTGDomain

        domain = MTGDomain()
        legend = domain.notation_legend
        assert len(legend) > 0
        # Should contain MTG-specific notation
        assert "{T}" in legend or "Tap" in legend

    def test_mtg_known_categories(self):
        """Should include known category names."""
        from trainforge.domains.mtg import MTGDomain

        domain = MTGDomain()
        cats = domain.get_categories()
        expected = [
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
        ]
        for cat in expected:
            assert cat in cats, f"Missing category: {cat}"

    def test_mtg_get_templates_for_category(self):
        """Should return TemplateConfig objects for a valid category."""
        from trainforge.domains.mtg import MTGDomain

        domain = MTGDomain()
        templates = domain.get_templates_for_category(category="combo_query")
        assert len(templates) > 0
        # combo_query has 4 templates: how_does_it_work, what_do_i_need, why_does_this_work, what_is_the_result
        template_ids = [t.template_id for t in templates]
        assert "how_does_it_work" in template_ids

    def test_mtg_get_templates_empty_category(self):
        """Should return empty list for nonexistent category."""
        from trainforge.domains.mtg import MTGDomain

        domain = MTGDomain()
        templates = domain.get_templates_for_category(category="nonexistent")
        assert templates == []
