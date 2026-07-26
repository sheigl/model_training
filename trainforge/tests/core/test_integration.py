"""Integration tests for TrainForge - full pipeline verification."""

from __future__ import annotations

import pytest

from trainforge.domain import DomainPlugin, TemplateConfig
from trainforge.generator import BaseGenerator, create_generator
from trainforge.models import Model, ModelType


# =============================================================================
# MOCK DOMAIN FOR INTEGRATION TESTS
# =============================================================================


class IntegrationTestDomain(DomainPlugin):
    """Mock domain for integration testing the full pipeline."""

    @property
    def name(self) -> str:
        return "integration_test"

    @property
    def display_name(self) -> str:
        return "Integration Test Domain"

    @property
    def system_message(self) -> str:
        return "You are a test assistant."

    @property
    def notation_legend(self) -> str:
        return ""

    def get_data_source(self, config=None):
        raise NotImplementedError("Not needed for integration tests")

    def get_generators(self):
        return []

    def get_categories(self):
        return ["test_category"]


class IntegrationTestGenerator(BaseGenerator[dict]):
    """Concrete generator for integration testing."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._prompts_built = []

    def get_data_batches(self) -> list[dict]:
        return [
            {"id": "item1", "data": "first"},
            {"id": "item2", "data": "second"},
        ]

    def build_prompt(self, template: TemplateConfig, data_batch: dict) -> str:
        prompt = f"[{template.template_id}] {data_batch.get('id', 'unknown')}"
        self._prompts_built.append(prompt)
        return prompt

    def get_source_category(self) -> str:
        return "test_category"


# =============================================================================
# FULL PIPELINE INTEGRATION TESTS
# =============================================================================


class TestGeneratorPipelineIntegration:
    """Test the full generator pipeline with mock domain."""

    def test_generator_instantiation_with_domain(self):
        """Should create a generator that references its domain correctly."""
        domain = IntegrationTestDomain()
        gen_model = Model(name="qwen2.5:14b", type=ModelType.GENERATION)
        val_model = Model(name="qwen2.5:14b", type=ModelType.VALIDATION)

        gen = IntegrationTestGenerator(
            domain=domain,
            generation_model=gen_model,
            validation_model=val_model,
        )

        assert gen.domain is domain
        assert gen.domain.name == "integration_test"
        assert gen.generation_model.name == "qwen2.5:14b"

    def test_get_data_batches_returns_items(self):
        """Generator should return data batches."""
        domain = IntegrationTestDomain()
        gen_model = Model(name="qwen2.5:14b", type=ModelType.GENERATION)
        val_model = Model(name="qwen2.5:14b", type=ModelType.VALIDATION)

        gen = IntegrationTestGenerator(
            domain=domain,
            generation_model=gen_model,
            validation_model=val_model,
        )

        batches = gen.get_data_batches()
        assert len(batches) == 2
        assert batches[0]["id"] == "item1"

    def test_build_prompt_with_template(self):
        """Generator should build prompts combining template and data."""
        domain = IntegrationTestDomain()
        gen_model = Model(name="qwen2.5:14b", type=ModelType.GENERATION)
        val_model = Model(name="qwen2.5:14b", type=ModelType.VALIDATION)

        gen = IntegrationTestGenerator(
            domain=domain,
            generation_model=gen_model,
            validation_model=val_model,
        )

        template = TemplateConfig.from_dict("test_tpl", {"instruction": "Do something"})
        batch = {"id": "batch_42"}

        prompt = gen.build_prompt(template, batch)
        assert "test_tpl" in prompt
        assert "batch_42" in prompt

    def test_factory_creates_generator(self):
        """create_generator factory should produce working instance."""
        domain = IntegrationTestDomain()
        gen_model = Model(name="qwen2.5:14b", type=ModelType.GENERATION)
        val_model = Model(name="qwen2.5:14b", type=ModelType.VALIDATION)

        gen = create_generator(
            domain=domain,
            generator_class=IntegrationTestGenerator,
            generation_model=gen_model,
            validation_model=val_model,
            run_id="integration-test-run",
        )

        assert isinstance(gen, IntegrationTestGenerator)
        assert gen.run_id == "integration-test-run"
        assert gen.get_source_category() == "test_category"


# =============================================================================
# MTG DOMAIN INTEGRATION TESTS
# =============================================================================


class TestMTGDomainIntegration:
    """Verify MTGDomain loads templates.yaml correctly."""

    def test_mtg_domain_loads_27_categories(self):
        """MTG domain should load all 27 categories from templates.yaml."""
        from trainforge.domains.mtg import MTGDomain

        domain = MTGDomain()
        cats = domain.get_categories()
        assert len(cats) == 27, f"Expected 27 categories, got {len(cats)}"

    def test_mtg_domain_has_system_message(self):
        """MTG domain should have a non-empty system message."""
        from trainforge.domains.mtg import MTGDomain

        domain = MTGDomain()
        assert len(domain.system_message) > 50

    def test_mtg_domain_has_notation_legend(self):
        """MTG domain should have a non-empty notation legend."""
        from trainforge.domains.mtg import MTGDomain

        domain = MTGDomain()
        assert len(domain.notation_legend) > 50

    def test_mtg_templates_have_validation_rules(self):
        """Templates should include validation rules where defined."""
        from trainforge.domains.mtg import MTGDomain

        domain = MTGDomain()
        templates = domain.get_templates_for_category(category="combo_query")
        assert len(templates) > 0

        # At least one template should have validation_rules
        has_rules = any(t.validation_rules for t in templates)
        assert has_rules, "At least one template should have validation rules"

    def test_mtg_all_categories_have_templates(self):
        """Every category should have at least 1 template."""
        from trainforge.domains.mtg import MTGDomain

        domain = MTGDomain()
        for cat in domain.get_categories():
            templates = domain.get_templates_for_category(category=cat)
            assert len(templates) >= 1, f"Category '{cat}' has no templates"


# =============================================================================
# QUERY MODEL INSTANTIATION TESTS
# =============================================================================


class TestQueryModelInstantiation:
    """Verify QueryModel can be instantiated with both signatures."""

    def test_query_model_with_defaults(self):
        """Should instantiate with default empty params."""
        from trainforge.query_model import QueryModel

        qm = QueryModel()
        assert qm.model_name == ""
        assert qm.provider_url is None
        assert qm.api_key is None

    def test_query_model_with_params(self):
        """Should instantiate with explicit params."""
        from trainforge.query_model import QueryModel

        qm = QueryModel(
            model_name="qwen2.5:14b",
            provider_url="http://localhost:11434",
            api_key="test-key",
        )
        assert qm.model_name == "qwen2.5:14b"
        assert qm.provider_url == "http://localhost:11434"
        assert qm.api_key == "test-key"

    def test_query_model_with_model_object(self):
        """Should work with Model object passed to query()."""
        from trainforge.query_model import QueryModel

        # Just verify instantiation - actual query requires live LLM
        qm = QueryModel(model_name="qwen2.5:14b")
        model_obj = Model(name="qwen2.5:14b", type=ModelType.GENERATION)
        assert isinstance(qm, QueryModel)


# =============================================================================
# VALIDATOR MODULE TESTS (without live LLM)
# =============================================================================


class TestValidatorModule:
    """Test validator module constants and imports."""

    def test_max_fix_attempts(self):
        """MAX_FIX_ATTEMPTS should be 3."""
        from trainforge.validator import MAX_FIX_ATTEMPTS
        assert MAX_FIX_ATTEMPTS == 3

    def test_validate_function_importable(self):
        """validate_and_loop_with_suggested_fix should be importable."""
        from trainforge.validator import validate_and_loop_with_suggested_fix
        assert callable(validate_and_loop_with_suggested_fix)


# =============================================================================
# CROSS-MODULE INTEGRATION
# =============================================================================


class TestCrossModuleIntegration:
    """Test that modules work together correctly."""

    def test_model_used_in_generator(self):
        """Model objects should be properly stored in generator."""
        domain = IntegrationTestDomain()
        gen_model = Model(
            name="qwen2.5:14b",
            type=ModelType.GENERATION,
            provider_url="http://localhost:11434",
        )
        val_model = Model(name="qwen2.5:14b", type=ModelType.VALIDATION)

        gen = IntegrationTestGenerator(
            domain=domain,
            generation_model=gen_model,
            validation_model=val_model,
        )

        assert gen.generation_model.provider_url == "http://localhost:11434"
        assert gen.validation_model.name == "qwen2.5:14b"

    def test_metrics_shared_across_generators(self):
        """Multiple generators should share the same metrics instance."""
        from trainforge.models import ValidationMetrics

        domain = IntegrationTestDomain()
        gen_model = Model(name="qwen2.5:14b", type=ModelType.GENERATION)
        val_model = Model(name="qwen2.5:14b", type=ModelType.VALIDATION)
        shared_metrics = ValidationMetrics(run_id="shared")

        gen1 = IntegrationTestGenerator(
            domain=domain,
            generation_model=gen_model,
            validation_model=val_model,
            metrics=shared_metrics,
        )
        gen2 = IntegrationTestGenerator(
            domain=domain,
            generation_model=gen_model,
            validation_model=val_model,
            metrics=shared_metrics,
        )

        assert gen1.metrics is gen2.metrics
        assert gen1.metrics.run_id == "shared"
