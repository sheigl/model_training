"""Unit tests for YAML template loading integration.

Covers YAML loader paths for template selection, validator resolution,
and shared scaffolding. All templates are loaded from local YAML files
via :class:`YamlTemplateLoader`.
"""

from __future__ import annotations

import logging
from typing import Iterator
from unittest.mock import MagicMock

import pytest

from training_data.generate_synthetic_data import constants
from training_data.generate_synthetic_data.base_generator import BaseGenerator, TemplateConfig
from training_data.generate_synthetic_data.common import (
    _SCAFFOLDING_CACHE,
    _get_scaffold,
    init_scaffolding,
    reset_scaffolding_cache,
    build_commander_prompt,
    build_card_comparision_prompt,
)
from training_data.generate_synthetic_data.models import (
    Model,
    ModelType,
    ModelProvider,
)
from training_data.generate_synthetic_data.query_model import QueryModel
from training_data.generate_synthetic_data.yaml_template_loader import YamlTemplateLoader
from training_data.generate_synthetic_data.common import _dict_to_template_config


# =============================================================================
# Test helpers
# =============================================================================

class MockModel(Model):
    """Mock model for testing."""

    def __init__(self, name: str = "test-model", model_type: ModelType = ModelType.GENERATION):
        self.name = name
        self.type = model_type
        self.provider = ModelProvider.OLLAMA
        self.provider_url = "http://localhost:11434"
        self.api_key = None


def _make_yaml_doc(template_id: str, instruction: str, weight: float = 1.0,
                   validation_rules: list[str] | None = None,
                   min_answer_length: int = 80, max_answer_length: int = 2000) -> dict:
    """Build a mock YAML template doc with parsed fields."""
    return {
        "template_id": template_id,
        "instruction": instruction,
        "weight": weight,
        "validation_rules": validation_rules or [],
        "min_answer_length": min_answer_length,
        "max_answer_length": max_answer_length,
        "version": "1",
    }


def _make_shared_doc(template_id: str, content, template_type: str = "generation") -> dict:
    """Build a mock shared scaffolding YAML doc."""
    return {
        "template_id": template_id,
        "content": content,
    }


class ConcreteGenerator(BaseGenerator[dict]):
    """Concrete generator for testing — mirrors test_base_generator.ConcreteGenerator."""

    def __init__(self, *args, yaml_loader: MagicMock | None = None, **kwargs):
        if yaml_loader is None:
            yaml_loader = MagicMock(spec=YamlTemplateLoader)
            yaml_loader.SHARED_NAMESPACE = YamlTemplateLoader.SHARED_NAMESPACE
            def get_latest_side(gen, tid, ttype):
                if ttype == "generation":
                    return _make_yaml_doc(tid, f"Instruction for {tid}", weight=1.0)
                return None
            yaml_loader.get_latest.side_effect = get_latest_side
            yaml_loader.list_templates.return_value = ["template_a", "template_b"]
        kwargs["yaml_loader"] = yaml_loader
        super().__init__(*args, **kwargs)
        self.data_batches = []

    def get_data_batches(self) -> Iterator[list[dict]]:
        for batch in self.data_batches:
            yield batch

    def build_prompt(self, template: TemplateConfig, data_batch: dict) -> str:
        return f"Prompt for {template.template_id}"

    def get_source_category(self) -> str:
        return "test_category"


def _make_generator(yaml_loader: MagicMock | None = None):
    """Build a ConcreteGenerator with standard mock dependencies."""
    models = {
        ModelType.GENERATION: MockModel("gen", ModelType.GENERATION),
        ModelType.VALIDATION: MockModel("val", ModelType.VALIDATION),
    }
    metrics = MagicMock()
    metrics.generator_name = "unknown"
    metrics.generation_model = "unknown"
    metrics.validation_model = "unknown"
    metrics.run_id = "test-run"
    metrics.flush = MagicMock()
    metrics.print_rolling_summary = MagicMock()
    return ConcreteGenerator(
        models=models,
        validation_pct=1.0,
        target_count=1,
        save_item=MagicMock(),
        metrics=metrics,
        yaml_loader=yaml_loader,
    )


# =============================================================================
# select_templates — YAML loader path
# =============================================================================

class TestSelectTemplatesYaml:
    """Tests for BaseGenerator.select_templates with a YamlTemplateLoader."""

    def test_select_templates_yaml_present(self):
        """When the yaml_loader returns entries, TemplateConfig objects are built from them."""
        loader = MagicMock(spec=YamlTemplateLoader)
        loader.SHARED_NAMESPACE = YamlTemplateLoader.SHARED_NAMESPACE
        loader.list_templates.return_value = ["template_a", "template_b"]

        def get_latest_side(gen, tid, ttype):
            if ttype == "generation":
                return _make_yaml_doc(tid, f"YAML instruction for {tid}", weight=3.0)
            return None

        loader.get_latest.side_effect = get_latest_side
        gen = _make_generator(yaml_loader=loader)

        selected = gen.select_templates(k=10)

        assert len(selected) == 10
        for tc in selected:
            assert tc.task_instruction.startswith("YAML instruction for")
            assert tc.weight == 3.0
            assert tc.version == "1"
        # get_latest called once per template_id from list_templates
        assert loader.get_latest.call_count == 2

    def test_select_templates_yaml_absent_raises(self):
        """When yaml_loader returns no template IDs, ValueError is raised."""
        loader = MagicMock(spec=YamlTemplateLoader)
        loader.list_templates.return_value = []
        gen = _make_generator(yaml_loader=loader)

        with pytest.raises(ValueError, match="No templates found"):
            gen.select_templates(k=1)

    def test_select_templates_yaml_missing_for_some(self):
        """When the yaml_loader returns None for some template_ids, they are skipped."""
        loader = MagicMock(spec=YamlTemplateLoader)
        loader.SHARED_NAMESPACE = YamlTemplateLoader.SHARED_NAMESPACE
        loader.list_templates.return_value = ["template_a", "template_b"]

        def get_latest_side(gen, tid, ttype):
            if ttype == "generation" and tid == "template_a":
                return _make_yaml_doc(tid, "YAML A", weight=5.0)
            return None  # template_b missing from YAML

        loader.get_latest.side_effect = get_latest_side
        gen = _make_generator(yaml_loader=loader)

        selected = gen.select_templates(k=20)

        yaml_a = [t for t in selected if t.task_instruction == "YAML A"]
        assert len(yaml_a) > 0
        assert len(selected) == 20

    def test_yaml_list_templates_called(self):
        """list_templates is called to discover template IDs."""
        loader = MagicMock(spec=YamlTemplateLoader)
        loader.list_templates.return_value = ["tid1", "tid2", "tid3"]
        gen = _make_generator(yaml_loader=loader)

        gen.select_templates(k=5)

        loader.list_templates.assert_called_once_with("test_category")


# =============================================================================
# Validator template resolution (QueryModel._resolve_validator_template)
# =============================================================================

class TestValidatorResolution:
    """Tests for QueryModel._resolve_validator_template with YAML loader."""

    def test_yaml_loader_generator_specific(self):
        """A generator-specific validator from yaml_loader takes precedence."""
        loader = MagicMock(spec=YamlTemplateLoader)
        loader.SHARED_NAMESPACE = YamlTemplateLoader.SHARED_NAMESPACE
        loader.get_latest.side_effect = lambda gen, tid, ttype: (
            {"template_id": tid, "instruction": f"YAML {gen}/{tid} prompt"}
            if gen == "combo_query" and tid == "validator"
            else None
        )
        qm = QueryModel()
        qm.yaml_loader = loader

        result = qm._resolve_validator_template("combo_query", "qa_validation")

        assert result is not None
        assert "YAML combo_query/validator prompt" in result

    def test_yaml_loader_shared_fallback(self):
        """When no generator-specific YAML validator exists, shared is used."""
        loader = MagicMock(spec=YamlTemplateLoader)
        loader.SHARED_NAMESPACE = YamlTemplateLoader.SHARED_NAMESPACE

        def get_latest_side(gen, tid, ttype):
            if gen == "combo_query" and tid == "validator":
                return None  # no generator-specific override
            return {"template_id": tid, "instruction": f"SHARED {tid} prompt"}

        loader.get_latest.side_effect = get_latest_side
        qm = QueryModel()
        qm.yaml_loader = loader

        result = qm._resolve_validator_template("combo_query", "qa_validation")

        assert result is not None
        assert "SHARED qa_validation prompt" in result

    def test_yaml_loader_inline_fallback(self):
        """With yaml_loader=None, _resolve_validator_template returns None."""
        qm = QueryModel()
        qm.yaml_loader = None

        result = qm._resolve_validator_template("combo_query", "qa_validation")

        assert result is None

    def test_qa_validation_prompt_uses_yaml_template(self):
        """__build_qa_validation_prompt uses the YAML-stored template when available."""
        loader = MagicMock(spec=YamlTemplateLoader)
        loader.SHARED_NAMESPACE = YamlTemplateLoader.SHARED_NAMESPACE
        template_text = "VALIDATE: q={question} a={answer} ctx={context} cat={category}"
        loader.get_latest.return_value = {"template_id": "qa_validation", "instruction": template_text}
        qm = QueryModel()
        qm.yaml_loader = loader

        prompt = qm._QueryModel__build_qa_validation_prompt(
            question="Q1?", answer="A1", context="ctx", category="combo_query",
        )

        assert prompt == "VALIDATE: q=Q1? a=A1 ctx=ctx cat=combo_query"

    def test_card_validation_prompt_uses_yaml_template(self):
        """__build_card_validation_prompt uses the YAML-stored template when available."""
        loader = MagicMock(spec=YamlTemplateLoader)
        loader.SHARED_NAMESPACE = YamlTemplateLoader.SHARED_NAMESPACE
        template_text = "CARD VAL: {card1_name} vs {card2_name} q={question} a={answer}"
        loader.get_latest.return_value = {"template_id": "card_validation", "instruction": template_text}
        qm = QueryModel()
        qm.yaml_loader = loader

        prompt = qm._QueryModel__build_card_validation_prompt(
            card1={"name": "Sol Ring", "type": "Artifact", "text": "T: CC", "manaCost": "{1}"},
            card2={"name": "Fellwar Stone", "type": "Artifact", "text": "T: any", "manaCost": "{2}"},
            question="Which is better?",
            answer="Sol Ring.",
        )

        assert prompt == "CARD VAL: Sol Ring vs Fellwar Stone q=Which is better? a=Sol Ring."


# =============================================================================
# Scaffolding cache (common.py)
# =============================================================================

class TestScaffoldingCache:
    """Tests for init_scaffolding / _get_scaffold / reset_scaffolding_cache."""

    def setup_method(self):
        reset_scaffolding_cache()

    def teardown_method(self):
        reset_scaffolding_cache()

    def test_init_scaffolding_from_yaml_populates_cache(self):
        """init_scaffolding populates the cache from YAML loader data."""
        loader = MagicMock(spec=YamlTemplateLoader)
        loader.get_scaffolding.return_value = {
            "system_message": "YAML SYSTEM MESSAGE",
            "notation_legend": "YAML NOTATION LEGEND",
            "output_format": "YAML OUTPUT FORMAT",
            "card_comparison_instructions": "YAML CARD COMPARE",
            "requirements_base": ["yaml_req1", "yaml_req2"],
        }

        init_scaffolding(yaml_loader=loader)

        assert _SCAFFOLDING_CACHE["SYSTEM_MESSAGE"] == "YAML SYSTEM MESSAGE"
        assert _SCAFFOLDING_CACHE["MTG_NOTATION_LEGEND"] == "YAML NOTATION LEGEND"
        assert _SCAFFOLDING_CACHE["OUTPUT_FORMAT"] == "YAML OUTPUT FORMAT"
        assert _SCAFFOLDING_CACHE["CARD_COMPARISON_INSTRUCTIONS"] == "YAML CARD COMPARE"
        assert _SCAFFOLDING_CACHE["REQUIREMENTS_BASE"] == ["yaml_req1", "yaml_req2"]

    def test_init_scaffolding_none_is_noop(self):
        """init_scaffolding() with no args is a no-op — cache stays empty."""
        init_scaffolding()
        assert len(_SCAFFOLDING_CACHE) == 0

    def test_init_scaffolding_yaml_missing_key_uses_fallback(self):
        """When YAML has partial data, missing keys leave the cache empty (fallback to constants)."""
        loader = MagicMock(spec=YamlTemplateLoader)
        loader.get_scaffolding.return_value = {
            "system_message": "YAML SYSTEM",
            # notation_legend, output_format, etc. are missing
        }

        init_scaffolding(yaml_loader=loader)

        assert _SCAFFOLDING_CACHE["SYSTEM_MESSAGE"] == "YAML SYSTEM"
        assert "MTG_NOTATION_LEGEND" not in _SCAFFOLDING_CACHE
        assert "OUTPUT_FORMAT" not in _SCAFFOLDING_CACHE
        assert "CARD_COMPARISON_INSTRUCTIONS" not in _SCAFFOLDING_CACHE
        assert "REQUIREMENTS_BASE" not in _SCAFFOLDING_CACHE

    def test_init_scaffolding_yaml_none_is_noop(self):
        """When yaml_loader.get_scaffolding() returns None, cache stays empty."""
        loader = MagicMock(spec=YamlTemplateLoader)
        loader.get_scaffolding.return_value = None

        init_scaffolding(yaml_loader=loader)

        assert len(_SCAFFOLDING_CACHE) == 0

    def test_scaffolding_fallback_to_constants(self):
        """With an empty cache, _get_scaffold returns the constants fallback."""
        reset_scaffolding_cache()
        result = _get_scaffold("MTG_NOTATION_LEGEND", constants.MTG_NOTATION_LEGEND)
        assert result == constants.MTG_NOTATION_LEGEND

    def test_scaffolding_cache_hit(self):
        """When the cache has a value, _get_scaffold returns it."""
        _SCAFFOLDING_CACHE["MTG_NOTATION_LEGEND"] = "CACHED VALUE"
        result = _get_scaffold("MTG_NOTATION_LEGEND", constants.MTG_NOTATION_LEGEND)
        assert result == "CACHED VALUE"

    def test_build_commander_prompt_uses_cache(self):
        """build_commander_prompt uses the cached MTG_NOTATION_LEGEND when populated."""
        _SCAFFOLDING_CACHE["MTG_NOTATION_LEGEND"] = "<CACHED LEGEND>"
        prompt = build_commander_prompt()
        assert "<CACHED LEGEND>" in prompt

    def test_build_commander_prompt_falls_back_to_constants(self):
        """build_commander_prompt falls back to constants.MTG_NOTATION_LEGEND when cache empty."""
        reset_scaffolding_cache()
        prompt = build_commander_prompt()
        assert constants.MTG_NOTATION_LEGEND in prompt

    def test_build_card_comparision_prompt_uses_cache(self):
        """build_card_comparision_prompt uses cached scaffolding blocks."""
        _SCAFFOLDING_CACHE["MTG_NOTATION_LEGEND"] = "<CACHED LEGEND>"
        _SCAFFOLDING_CACHE["CARD_COMPARISON_INSTRUCTIONS"] = "<CACHED COMPARE>"
        # build_card_comparision_prompt needs Card objects; use simple mocks
        card1 = MagicMock()
        card1.name = "Card1"
        card2 = MagicMock()
        card2.name = "Card2"
        prompt = build_card_comparision_prompt(card1, card2)
        assert "<CACHED LEGEND>" in prompt
        assert "<CACHED COMPARE>" in prompt

    def test_reset_scaffolding_cache(self):
        """reset_scaffolding_cache clears the cache."""
        _SCAFFOLDING_CACHE["SYSTEM_MESSAGE"] = "cached"
        assert len(_SCAFFOLDING_CACHE) > 0
        reset_scaffolding_cache()
        assert len(_SCAFFOLDING_CACHE) == 0


# =============================================================================
# BaseGenerator __init__ wiring
# =============================================================================

class TestBaseGeneratorWiring:
    """Tests that BaseGenerator.__init__ wires the yaml_loader into QueryModel."""

    def test_yaml_loader_wired_to_query_model(self):
        """The yaml_loader is propagated to the QueryModel instance."""
        loader = MagicMock(spec=YamlTemplateLoader)
        loader.SHARED_NAMESPACE = YamlTemplateLoader.SHARED_NAMESPACE
        gen = _make_generator(yaml_loader=loader)

        assert gen._yaml_loader is loader
        assert gen._query_model.yaml_loader is loader

    def test_yaml_loader_defaults_to_none(self):
        """With no yaml_loader arg, both _yaml_loader and query_model.loader are None."""
        gen = _make_generator()

        assert gen._yaml_loader is not None  # ConcreteGenerator provides a default
        # But the default should be wired to query_model
        assert gen._query_model.yaml_loader is gen._yaml_loader


# =============================================================================
# _resolve_validator_version — YAML path
# =============================================================================

class TestResolveValidatorVersion:
    """Tests for BaseGenerator._resolve_validator_version with yaml_loader."""

    def test_yaml_loader_returns_none_for_version(self):
        """When yaml_loader is used, _resolve_validator_version returns None."""
        loader = MagicMock(spec=YamlTemplateLoader)
        gen = _make_generator(yaml_loader=loader)

        result = gen._resolve_validator_version("combo_query")

        assert result is None


# =============================================================================
# QueryModel — YAML loader path for validator templates
# =============================================================================

class TestQueryModelYamlValidator:
    """Tests for QueryModel._resolve_validator_template with a YamlTemplateLoader."""

    def test_qa_validation_prompt_uses_real_yaml_file(self):
        """__build_qa_validation_prompt loads from the actual shared.yaml on disk."""
        loader = YamlTemplateLoader()
        qm = QueryModel()
        qm.yaml_loader = loader

        prompt = qm._QueryModel__build_qa_validation_prompt(
            question="What does {T} mean?", answer="Tap the permanent.",
            context="Rule 701.21", category="combo_query",
        )

        # Placeholders substituted...
        assert "What does {T} mean?" in prompt
        assert "Tap the permanent." in prompt
        assert "Rule 701.21" in prompt
        assert "Category: combo_query" in prompt
        # ...MTG notation braces from the legend preserved verbatim.
        assert "{T}: Tap" in prompt
        assert "{C}: Colorless mana" in prompt
        assert "{W}: White" in prompt

    def test_card_validation_prompt_uses_real_yaml_file(self):
        """__build_card_validation_prompt loads from the actual comparison_validator.yaml on disk."""
        loader = YamlTemplateLoader()
        qm = QueryModel()
        qm.yaml_loader = loader

        prompt = qm._QueryModel__build_card_validation_prompt(
            card1={"name": "Sol Ring", "type": "Artifact", "text": "{T}: Add {C}{C}", "manaCost": "{1}"},
            card2={"name": "Fellwar Stone", "type": "Artifact", "text": "{T}: Add one mana", "manaCost": "{2}"},
            question="Which ramps better?", answer="Sol Ring — {1} for {C}{C}.",
        )

        # Real placeholders substituted...
        assert "Card 1: Sol Ring" in prompt
        assert "Type: Artifact" in prompt
        assert "Cost: {1}" in prompt
        assert "Text: {T}: Add {C}{C}" in prompt
        assert "Card 2: Fellwar Stone" in prompt
        assert "Question: Which ramps better?" in prompt
        assert "Answer to validate:" in prompt
        # ...MTG braces in template body preserved verbatim.
        assert "{T}: Tap" in prompt
        assert "{C}: Colorless mana" in prompt

    def test_qa_validation_yaml_loader_preserves_mtg_braces(self):
        """YAML loader path preserves MTG notation braces (no .format() applied)."""
        loader = YamlTemplateLoader()
        qm = QueryModel()
        qm.yaml_loader = loader

        # The real shared.yaml template contains {T}, {C}, {W}, etc. in the
        # MTG_NOTATION_LEGEND block. If .format() were used instead of str.replace(),
        # this would raise KeyError. Verify those braces survive intact.
        prompt = qm._QueryModel__build_qa_validation_prompt(
            question="What does {T} mean?", answer="Tap.", context="", category="general",
        )

        assert "{T}: Tap" in prompt
        assert "{C}: Colorless mana" in prompt
        assert "{W}: White" in prompt
        assert "{U}: Blue" in prompt
        assert "{B}: Black" in prompt
        assert "{R}: Red" in prompt
        assert "{G}: Green" in prompt
        assert "{X}: Variable amount" in prompt
        assert "{1},{2},{3}" in prompt

    def test_card_validation_yaml_loader_preserves_mtg_braces(self):
        """YAML loader path preserves MTG notation braces in card comparison validator."""
        loader = YamlTemplateLoader()
        qm = QueryModel()
        qm.yaml_loader = loader

        prompt = qm._QueryModel__build_card_validation_prompt(
            card1={"name": "Sol Ring", "type": "Artifact", "text": "{T}: Add {C}{C}", "manaCost": "{1}"},
            card2={"name": "Fellwar Stone", "type": "Artifact", "text": "{T}: Add one mana", "manaCost": "{2}"},
            question="Which is better?", answer="Sol Ring.",
        )

        # MTG notation legend braces preserved...
        assert "{T}: Tap" in prompt
        assert "{C}: Colorless mana" in prompt
        assert "{W}: White" in prompt
        # Card text braces preserved (substituted into the template, not parsed)...
        assert "Text: {T}: Add {C}{C}" in prompt
        assert "Cost: {1}" in prompt


# =============================================================================
# _dict_to_template_config
# =============================================================================

class TestDictToTemplateConfig:
    """Tests for the extracted _dict_to_template_config function."""

    def test_from_yaml_doc(self):
        """YAML loader dicts with parsed fields are converted correctly."""
        doc = {
            "template_id": "how_does_it_work",
            "instruction": "Generate requirements-focused Q&A pairs.",
            "weight": 0.5,
            "validation_rules": [],
            "min_answer_length": 100,
            "max_answer_length": 3000,
            "version": "1",
        }
        tc = _dict_to_template_config(doc)
        assert tc.template_id == "how_does_it_work"
        assert tc.task_instruction == "Generate requirements-focused Q&A pairs."
        assert tc.weight == 0.5
        assert tc.validation_rules == []
        assert tc.min_answer_length == 100
        assert tc.max_answer_length == 3000
        assert tc.version == "1"

    def test_yaml_doc_defaults_version_to_one(self):
        """YAML docs without an explicit version get '1' when the loader sets it."""
        # The YAML loader always calls result.setdefault("version", "1"), so
        # in practice all loader-produced docs have a version.  When calling
        # _dict_to_template_config directly with a doc that lacks one, the
        # TemplateConfig default (None) applies.
        doc = {
            "template_id": "x",
            "instruction": "Do something.",
        }
        tc = _dict_to_template_config(doc)
        assert tc.version is None

    def test_yaml_doc_with_explicit_version(self):
        """YAML docs with an explicit version string keep it."""
        doc = {
            "template_id": "x",
            "instruction": "Do something.",
            "version": "2",
        }
        tc = _dict_to_template_config(doc)
        assert tc.version == "2"

    def test_missing_fields_use_defaults(self):
        """Missing fields in a YAML doc fall back to TemplateConfig defaults."""
        doc = {"template_id": "minimal", "instruction": "Hi"}
        tc = _dict_to_template_config(doc)
        assert tc.weight == 1.0
        assert tc.validation_rules == []
        assert tc.min_answer_length == 80
        assert tc.max_answer_length == 2000
