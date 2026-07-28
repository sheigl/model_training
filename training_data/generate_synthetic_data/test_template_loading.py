"""Unit tests for Story 042 — Legacy CLI Template Loading Integration.

Covers the store-present, store-absent, version-override, validator-override,
and shared-scaffolding fallback paths. Backward compatibility (``template_store=None``)
is verified by the existing suite — these tests focus on the new store paths.
"""

from __future__ import annotations

import logging
from typing import Iterator
from unittest.mock import MagicMock

import yaml

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
from training_data.generate_synthetic_data.template_store import TemplateStore
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


def _make_gen_doc(template_id: str, instruction: str, weight: float = 1.0,
                  validation_rules: list[str] | None = None,
                  min_answer_length: int = 80, max_answer_length: int = 2000) -> dict:
    """Build a mock generation template store doc with valid yaml_content."""
    yaml_content = yaml.dump({
        "instruction": instruction,
        "weight": weight,
        "validation_rules": validation_rules or [],
        "min_answer_length": min_answer_length,
        "max_answer_length": max_answer_length,
    }, default_flow_style=False, sort_keys=False)
    return {
        "generator": "test_category",
        "template_id": template_id,
        "template_type": "generation",
        "version": 1,
        "yaml_content": yaml_content,
        "is_latest": True,
    }


def _make_shared_doc(template_id: str, content, template_type: str = "generation") -> dict:
    """Build a mock shared scaffolding store doc."""
    return {
        "generator": TemplateStore.SHARED_NAMESPACE,
        "template_id": template_id,
        "template_type": template_type,
        "version": 1,
        "yaml_content": yaml.dump({"content": content}, default_flow_style=False, sort_keys=False),
        "is_latest": True,
    }


def _make_validator_doc(generator: str, template_id: str, instruction: str) -> dict:
    """Build a mock validator store doc."""
    return {
        "generator": generator,
        "template_id": template_id,
        "template_type": "validator",
        "version": 1,
        "yaml_content": yaml.dump({"instruction": instruction}, default_flow_style=False, sort_keys=False),
        "is_latest": True,
    }


class ConcreteGenerator(BaseGenerator[dict]):
    """Concrete generator for testing — mirrors test_base_generator.ConcreteGenerator."""

    TEMPLATES = [
        TemplateConfig("template_a", "Instruction A", weight=1.0),
        TemplateConfig("template_b", "Instruction B", weight=2.0),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data_batches = []

    def get_data_batches(self) -> Iterator[list[dict]]:
        for batch in self.data_batches:
            yield batch

    def build_prompt(self, template: TemplateConfig, data_batch: dict) -> str:
        return f"Prompt for {template.template_id}"

    def get_source_category(self) -> str:
        return "test_category"


def _make_generator(template_store=None, yaml_loader=None,
                    template_version_override=None,
                    validator_template_version_override=None):
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
        template_store=template_store,
        yaml_loader=yaml_loader,
        template_version_override=template_version_override,
        validator_template_version_override=validator_template_version_override,
    )


# =============================================================================
# select_templates — store-present / store-absent / version-override
# =============================================================================

class TestSelectTemplatesStore:
    """Tests for BaseGenerator.select_templates with a TemplateStore."""

    def test_select_templates_store_present(self):
        """When the store returns docs, TemplateConfig objects are built from store docs."""
        store = MagicMock(spec=TemplateStore)
        store.SHARED_NAMESPACE = TemplateStore.SHARED_NAMESPACE
        store.get_latest.side_effect = lambda gen, tid, ttype: _make_gen_doc(
            tid, f"STORE instruction for {tid}", weight=3.0,
        )
        gen = _make_generator(template_store=store)

        selected = gen.select_templates(k=10)

        assert len(selected) == 10
        # Every selected template should come from the store (weight 3.0)
        for tc in selected:
            assert tc.task_instruction.startswith("STORE instruction for")
            assert tc.weight == 3.0
        # get_latest called once per class template (2 templates)
        assert store.get_latest.call_count == 2

    def test_select_templates_store_absent(self):
        """With template_store=None, the class-level TEMPLATES constant is used."""
        gen = _make_generator(template_store=None)

        selected = gen.select_templates(k=50)

        assert len(selected) == 50
        valid_ids = {t.template_id for t in gen.TEMPLATES}
        for tc in selected:
            assert tc.template_id in valid_ids
            # Class constants have instructions "Instruction A"/"Instruction B"
            assert tc.task_instruction in ("Instruction A", "Instruction B")

    def test_select_templates_store_empty_falls_back_to_class(self):
        """When the store returns None for every template_id, class constants are used."""
        store = MagicMock(spec=TemplateStore)
        store.SHARED_NAMESPACE = TemplateStore.SHARED_NAMESPACE
        store.get_latest.return_value = None
        gen = _make_generator(template_store=store)

        selected = gen.select_templates(k=5)

        assert len(selected) == 5
        for tc in selected:
            assert tc.task_instruction in ("Instruction A", "Instruction B")

    def test_select_templates_partial_store_fallback(self):
        """When the store has a doc for only some template_ids, missing ones use class constants."""
        store = MagicMock(spec=TemplateStore)
        store.SHARED_NAMESPACE = TemplateStore.SHARED_NAMESPACE

        def get_latest_side(gen, tid, ttype):
            if tid == "template_a":
                return _make_gen_doc(tid, "STORE A", weight=5.0)
            return None  # template_b missing from store

        store.get_latest.side_effect = get_latest_side
        gen = _make_generator(template_store=store)

        selected = gen.select_templates(k=20)

        store_a = [t for t in selected if t.task_instruction == "STORE A"]
        class_b = [t for t in selected if t.task_instruction == "Instruction B"]
        assert len(store_a) + len(class_b) == 20
        assert len(store_a) > 0
        assert len(class_b) > 0


class TestSelectTemplatesVersionOverride:
    """Tests for the template_version_override fallback chain."""

    def test_select_templates_version_override(self):
        """When template_version_override is set, get_version is called instead of get_latest."""
        store = MagicMock(spec=TemplateStore)
        store.SHARED_NAMESPACE = TemplateStore.SHARED_NAMESPACE
        store.get_version.return_value = _make_gen_doc(
            "template_a", "VERSIONED instruction", weight=7.0,
        )
        gen = _make_generator(template_store=store, template_version_override=3)

        selected = gen.select_templates(k=5)

        assert len(selected) == 5
        for tc in selected:
            assert tc.task_instruction == "VERSIONED instruction"
            assert tc.weight == 7.0
        # get_version called for each class template
        assert store.get_version.call_count == 2
        # get_latest should NOT be called (version found)
        store.get_latest.assert_not_called()

    def test_select_templates_version_missing_falls_back_to_latest(self, caplog):
        """When the overridden version is missing, fall back to latest and log a warning."""
        store = MagicMock(spec=TemplateStore)
        store.SHARED_NAMESPACE = TemplateStore.SHARED_NAMESPACE
        # get_version returns None (version missing), get_latest returns a doc
        store.get_version.return_value = None
        store.get_latest.return_value = _make_gen_doc("template_a", "LATEST instruction", weight=2.0)
        gen = _make_generator(template_store=store, template_version_override=99)

        with caplog.at_level(logging.WARNING):
            selected = gen.select_templates(k=3)

        assert len(selected) == 3
        for tc in selected:
            assert tc.task_instruction == "LATEST instruction"
        # get_version tried, then get_latest used as fallback
        assert store.get_version.call_count == 2
        assert store.get_latest.call_count == 2
        # A warning was logged
        assert any("not found" in rec.message for rec in caplog.records)

    def test_select_templates_version_missing_and_latest_missing(self, caplog):
        """When both version and latest are missing, fall back to class constant."""
        store = MagicMock(spec=TemplateStore)
        store.SHARED_NAMESPACE = TemplateStore.SHARED_NAMESPACE
        store.get_version.return_value = None
        store.get_latest.return_value = None
        gen = _make_generator(template_store=store, template_version_override=5)

        selected = gen.select_templates(k=4)

        assert len(selected) == 4
        for tc in selected:
            assert tc.task_instruction in ("Instruction A", "Instruction B")


# =============================================================================
# Validator template resolution (QueryModel._resolve_validator_template)
# =============================================================================

class TestValidatorResolution:
    """Tests for QueryModel._resolve_validator_template hybrid lookup."""

    def test_validator_override_generator_specific(self):
        """A generator-specific validator doc takes precedence over the shared one."""
        store = MagicMock(spec=TemplateStore)
        store.SHARED_NAMESPACE = TemplateStore.SHARED_NAMESPACE
        store.get_latest.side_effect = lambda gen, tid, ttype: (
            _make_validator_doc(gen, tid, "GENERATOR-SPECIFIC validator prompt {question}")
            if gen == "combo_query" and tid == "validator"
            else _make_validator_doc(gen, tid, "SHARED validator prompt {question}")
        )
        qm = QueryModel()
        qm.template_store = store

        result = qm._resolve_validator_template("combo_query", "qa_validation")

        assert result is not None
        assert result.startswith("GENERATOR-SPECIFIC validator prompt")

    def test_validator_shared_fallback(self):
        """When no generator-specific doc exists, the shared validator is used."""
        store = MagicMock(spec=TemplateStore)
        store.SHARED_NAMESPACE = TemplateStore.SHARED_NAMESPACE

        def get_latest_side(gen, tid, ttype):
            if tid == "validator":
                return None  # no generator-specific override
            return _make_validator_doc(gen, tid, "SHARED validator prompt {question}")

        store.get_latest.side_effect = get_latest_side
        qm = QueryModel()
        qm.template_store = store

        result = qm._resolve_validator_template("combo_query", "qa_validation")

        assert result is not None
        assert result.startswith("SHARED validator prompt")

    def test_validator_inline_fallback_store_none(self):
        """With template_store=None, _resolve_validator_template returns None (inline fallback)."""
        qm = QueryModel()
        qm.template_store = None

        result = qm._resolve_validator_template("combo_query", "qa_validation")

        assert result is None

    def test_validator_inline_fallback_store_empty(self):
        """When the store has no validator docs at all, None is returned (inline fallback)."""
        store = MagicMock(spec=TemplateStore)
        store.SHARED_NAMESPACE = TemplateStore.SHARED_NAMESPACE
        store.get_latest.return_value = None
        qm = QueryModel()
        qm.template_store = store

        result = qm._resolve_validator_template("combo_query", "qa_validation")

        assert result is None

    def test_qa_validation_prompt_uses_store_template(self):
        """__build_qa_validation_prompt uses the stored template when available."""
        store = MagicMock(spec=TemplateStore)
        store.SHARED_NAMESPACE = TemplateStore.SHARED_NAMESPACE
        template_text = "VALIDATE: q={question} a={answer} ctx={context} cat={category}"
        store.get_latest.return_value = _make_validator_doc(
            TemplateStore.SHARED_NAMESPACE, "qa_validation", template_text,
        )
        qm = QueryModel()
        qm.template_store = store

        prompt = qm._QueryModel__build_qa_validation_prompt(
            question="Q1?", answer="A1", context="ctx", category="combo_query",
        )

        assert prompt == "VALIDATE: q=Q1? a=A1 ctx=ctx cat=combo_query"

    def test_qa_validation_prompt_inline_fallback(self):
        """With no store, __build_qa_validation_prompt uses the inline construction."""
        qm = QueryModel()
        qm.template_store = None

        prompt = qm._QueryModel__build_qa_validation_prompt(
            question="Q1?", answer="A1", context="ctx", category="combo_query",
        )

        # Inline prompt contains the SYSTEM_MESSAGE and MTG_NOTATION_LEGEND
        assert "Q1?" in prompt
        assert "A1" in prompt
        assert "combo_query" in prompt

    def test_card_validation_prompt_uses_store_template(self):
        """__build_card_validation_prompt uses the stored template when available."""
        store = MagicMock(spec=TemplateStore)
        store.SHARED_NAMESPACE = TemplateStore.SHARED_NAMESPACE
        template_text = (
            "CARD VAL: {card1_name} vs {card2_name} q={question} a={answer}"
        )
        store.get_latest.return_value = _make_validator_doc(
            "comparison", "card_validation", template_text,
        )
        qm = QueryModel()
        qm.template_store = store

        prompt = qm._QueryModel__build_card_validation_prompt(
            card1={"name": "Sol Ring", "type": "Artifact", "text": "T: CC", "manaCost": "{1}"},
            card2={"name": "Fellwar Stone", "type": "Artifact", "text": "T: any", "manaCost": "{2}"},
            question="Which is better?",
            answer="Sol Ring.",
        )

        assert prompt == "CARD VAL: Sol Ring vs Fellwar Stone q=Which is better? a=Sol Ring."

    def test_card_validation_prompt_inline_fallback(self):
        """With no store, __build_card_validation_prompt uses inline construction."""
        qm = QueryModel()
        qm.template_store = None

        prompt = qm._QueryModel__build_card_validation_prompt(
            card1={"name": "Sol Ring", "type": "Artifact", "text": "T: CC", "manaCost": "{1}"},
            card2={"name": "Fellwar Stone", "type": "Artifact", "text": "T: any", "manaCost": "{2}"},
            question="Which is better?",
            answer="Sol Ring.",
        )

        assert "Sol Ring" in prompt
        assert "Fellwar Stone" in prompt

    def test_qa_validation_prompt_store_with_mtg_braces(self):
        """Store path works when the template contains MTG notation braces.

        Regression test for the bug where ``.format()`` interpreted MTG mana
        symbols (``{T}``, ``{C}``, ``{W}``, ...) as placeholders and raised
        ``KeyError`` — silently falling back to the inline prompt. With
        ``str.replace()`` the braces are preserved untouched and only the
        real placeholders (``{question}``, ``{answer}``, ...) are substituted.
        """
        store = MagicMock(spec=TemplateStore)
        store.SHARED_NAMESPACE = TemplateStore.SHARED_NAMESPACE
        # Template mimics the real stored validator: contains MTG braces AND
        # the four real placeholders.
        template_text = (
            "MTG: {T} tap, {C} colorless, {W}{U}{B}{R}{G} colors, {X} var, {1}{2} generic\n"
            "Q: {question}\nA: {answer}\nCtx: {context}\nCat: {category}"
        )
        store.get_latest.return_value = _make_validator_doc(
            TemplateStore.SHARED_NAMESPACE, "qa_validation", template_text,
        )
        qm = QueryModel()
        qm.template_store = store

        prompt = qm._QueryModel__build_qa_validation_prompt(
            question="What does {T} mean?",
            answer="Tap the permanent.",
            context="Rule 701.21",
            category="combo_query",
        )

        # Real placeholders substituted...
        assert "Q: What does {T} mean?" in prompt
        assert "A: Tap the permanent." in prompt
        assert "Ctx: Rule 701.21" in prompt
        assert "Cat: combo_query" in prompt
        # ...MTG braces preserved verbatim (NOT eaten by .format()).
        assert "{T} tap" in prompt
        assert "{C} colorless" in prompt
        assert "{W}{U}{B}{R}{G} colors" in prompt
        assert "{X} var" in prompt
        assert "{1}{2} generic" in prompt

    def test_card_validation_prompt_store_with_mtg_braces(self):
        """Store path works for card validation when the template has MTG braces.

        Regression test: the stored card-comparison validator template embeds
        ``MTG_NOTATION_LEGEND`` (with ``{T}``, ``{C}``, ...) and card text/cost
        fields routinely contain braces (e.g. ``manaCost: "{1}"``). ``.format()``
        raised ``KeyError`` on these; ``str.replace()`` leaves them intact.
        """
        store = MagicMock(spec=TemplateStore)
        store.SHARED_NAMESPACE = TemplateStore.SHARED_NAMESPACE
        template_text = (
            "MTG: {T} {C} {W}{U}{B}{R}{G} {X} {1}{2}\n"
            "Card1: {card1_name} ({card1_cost}) {card1_type} — {card1_text}\n"
            "Card2: {card2_name} ({card2_cost}) {card2_type} — {card2_text}\n"
            "Q: {question}\nA: {answer}"
        )
        store.get_latest.return_value = _make_validator_doc(
            "comparison", "card_validation", template_text,
        )
        qm = QueryModel()
        qm.template_store = store

        prompt = qm._QueryModel__build_card_validation_prompt(
            card1={"name": "Sol Ring", "type": "Artifact", "text": "{T}: Add {C}{C}", "manaCost": "{1}"},
            card2={"name": "Fellwar Stone", "type": "Artifact", "text": "{T}: Add one mana", "manaCost": "{2}"},
            question="Which ramps better?",
            answer="Sol Ring — {1} for {C}{C}.",
        )

        # Real placeholders substituted...
        assert "Card1: Sol Ring ({1}) Artifact — {T}: Add {C}{C}" in prompt
        assert "Card2: Fellwar Stone ({2}) Artifact — {T}: Add one mana" in prompt
        assert "Q: Which ramps better?" in prompt
        assert "A: Sol Ring — {1} for {C}{C}." in prompt
        # ...MTG braces in the template body preserved verbatim.
        assert "MTG: {T} {C} {W}{U}{B}{R}{G} {X} {1}{2}" in prompt

    def test_qa_validation_prompt_store_real_template(self):
        """The actual build_qa_validation_prompt_template() works through the store path.

        End-to-end regression: store the real public template (which embeds
        ``MTG_NOTATION_LEGEND`` with all the mana-symbol braces) and confirm the
        store path substitutes the four placeholders without raising and
        without mangling the MTG braces.
        """
        from training_data.generate_synthetic_data.query_model import (
            build_qa_validation_prompt_template,
        )

        store = MagicMock(spec=TemplateStore)
        store.SHARED_NAMESPACE = TemplateStore.SHARED_NAMESPACE
        store.get_latest.return_value = _make_validator_doc(
            TemplateStore.SHARED_NAMESPACE, "qa_validation",
            build_qa_validation_prompt_template(),
        )
        qm = QueryModel()
        qm.template_store = store

        prompt = qm._QueryModel__build_qa_validation_prompt(
            question="Does {T} cause summoning sickness?",
            answer="No — tapping is not attacking.",
            context="Rule 701.21, 302.6",
            category="combo_query",
        )

        # Placeholders substituted...
        assert "Does {T} cause summoning sickness?" in prompt
        assert "No — tapping is not attacking." in prompt
        assert "Rule 701.21, 302.6" in prompt
        assert "Category: combo_query" in prompt
        # ...MTG notation braces from the legend preserved verbatim.
        assert "{T}: Tap" in prompt
        assert "{C}: Colorless mana" in prompt
        assert "{W}: White" in prompt
        assert "{2}{U}{U}" in prompt  # example line in the legend


# =============================================================================
# Scaffolding cache (common.py)
# =============================================================================

class TestScaffoldingCache:
    """Tests for init_scaffolding / _get_scaffold / reset_scaffolding_cache."""

    def setup_method(self):
        reset_scaffolding_cache()

    def teardown_method(self):
        reset_scaffolding_cache()

    def test_scaffolding_cache_populated(self):
        """init_scaffolding populates the cache from store docs."""
        store = MagicMock(spec=TemplateStore)
        store.SHARED_NAMESPACE = TemplateStore.SHARED_NAMESPACE

        def get_latest_side(gen, tid, ttype):
            if tid == "system_message":
                return _make_shared_doc(tid, "CACHED SYSTEM MESSAGE")
            if tid == "notation_legend":
                return _make_shared_doc(tid, "CACHED NOTATION LEGEND")
            if tid == "output_format":
                return _make_shared_doc(tid, "CACHED OUTPUT FORMAT")
            if tid == "card_comparison_instructions":
                return _make_shared_doc(tid, "CACHED CARD COMPARE")
            if tid == "requirements_base":
                return _make_shared_doc(tid, ["req1", "req2"])
            return None

        store.get_latest.side_effect = get_latest_side

        init_scaffolding(store=store)

        assert _SCAFFOLDING_CACHE["SYSTEM_MESSAGE"] == "CACHED SYSTEM MESSAGE"
        assert _SCAFFOLDING_CACHE["MTG_NOTATION_LEGEND"] == "CACHED NOTATION LEGEND"
        assert _SCAFFOLDING_CACHE["OUTPUT_FORMAT"] == "CACHED OUTPUT FORMAT"
        assert _SCAFFOLDING_CACHE["CARD_COMPARISON_INSTRUCTIONS"] == "CACHED CARD COMPARE"
        assert _SCAFFOLDING_CACHE["REQUIREMENTS_BASE"] == ["req1", "req2"]

    def test_scaffolding_init_none_is_noop(self):
        """init_scaffolding() with no args is a no-op — cache stays empty."""
        init_scaffolding()
        assert len(_SCAFFOLDING_CACHE) == 0

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

    def test_init_scaffolding_yaml_precedence_over_store(self):
        """When both yaml_loader and store are provided, YAML wins."""
        store = MagicMock(spec=TemplateStore)
        store.SHARED_NAMESPACE = TemplateStore.SHARED_NAMESPACE

        def get_latest_side(gen, tid, ttype):
            return _make_shared_doc(tid, f"STORE {tid.upper()}")

        store.get_latest.side_effect = get_latest_side

        loader = MagicMock(spec=YamlTemplateLoader)
        loader.get_scaffolding.return_value = {
            "system_message": "YAML SYSTEM",
            "notation_legend": "YAML LEGEND",
            "output_format": "YAML FORMAT",
            "card_comparison_instructions": "YAML COMPARE",
            "requirements_base": ["yaml_req"],
        }

        init_scaffolding(yaml_loader=loader, store=store)

        assert _SCAFFOLDING_CACHE["SYSTEM_MESSAGE"] == "YAML SYSTEM"
        assert _SCAFFOLDING_CACHE["MTG_NOTATION_LEGEND"] == "YAML LEGEND"
        # Store should NOT be queried when YAML loader is present
        store.get_latest.assert_not_called()

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
    """Tests that BaseGenerator.__init__ wires the store into QueryModel."""

    def test_template_store_wired_to_query_model(self):
        """The template_store is propagated to the QueryModel instance."""
        store = MagicMock(spec=TemplateStore)
        store.SHARED_NAMESPACE = TemplateStore.SHARED_NAMESPACE
        gen = _make_generator(template_store=store)

        assert gen._template_store is store
        assert gen._query_model.template_store is store

    def test_template_store_defaults_to_none(self):
        """With no template_store arg, both _template_store and query_model.store are None."""
        gen = _make_generator()

        assert gen._template_store is None
        assert gen._query_model.template_store is None

    def test_version_overrides_stored(self):
        """template_version_override and validator_template_version_override are stored."""
        gen = _make_generator(
            template_version_override=2,
            validator_template_version_override=4,
        )

        assert gen._template_version_override == 2
        assert gen._validator_template_version_override == 4

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

        assert gen._yaml_loader is None
        assert gen._query_model.yaml_loader is None

    def test_both_loaders_stored(self):
        """When both template_store and yaml_loader are provided, both are stored."""
        store = MagicMock(spec=TemplateStore)
        loader = MagicMock(spec=YamlTemplateLoader)
        gen = _make_generator(template_store=store, yaml_loader=loader)

        assert gen._template_store is store
        assert gen._yaml_loader is loader
        assert gen._query_model.template_store is store
        assert gen._query_model.yaml_loader is loader


# =============================================================================
# select_templates — YAML loader path
# =============================================================================

class TestSelectTemplatesYaml:
    """Tests for BaseGenerator.select_templates with a YamlTemplateLoader."""

    def test_select_templates_yaml_present(self):
        """When the yaml_loader returns entries, TemplateConfig objects are built from them."""
        loader = MagicMock(spec=YamlTemplateLoader)
        loader.SHARED_NAMESPACE = YamlTemplateLoader.SHARED_NAMESPACE

        def get_latest_side(gen, tid, ttype):
            if ttype == "generation":
                return {
                    "template_id": tid,
                    "instruction": f"YAML instruction for {tid}",
                    "weight": 3.0,
                    "validation_rules": [],
                    "min_answer_length": 80,
                    "max_answer_length": 2000,
                    "version": "1",
                }
            return None

        loader.get_latest.side_effect = get_latest_side
        gen = _make_generator(yaml_loader=loader)

        selected = gen.select_templates(k=10)

        assert len(selected) == 10
        for tc in selected:
            assert tc.task_instruction.startswith("YAML instruction for")
            assert tc.weight == 3.0
            assert tc.version == "1"
        # get_latest called once per class template (2 templates)
        assert loader.get_latest.call_count == 2

    def test_select_templates_yaml_absent_falls_back_to_class(self):
        """When yaml_loader is None, class-level TEMPLATES are used."""
        gen = _make_generator(yaml_loader=None)

        selected = gen.select_templates(k=50)

        assert len(selected) == 50
        valid_ids = {t.template_id for t in gen.TEMPLATES}
        for tc in selected:
            assert tc.template_id in valid_ids
            assert tc.task_instruction in ("Instruction A", "Instruction B")

    def test_select_templates_yaml_missing_falls_back_to_class(self):
        """When the yaml_loader returns None for every template_id, class constants are used."""
        loader = MagicMock(spec=YamlTemplateLoader)
        loader.SHARED_NAMESPACE = YamlTemplateLoader.SHARED_NAMESPACE
        loader.get_latest.return_value = None
        gen = _make_generator(yaml_loader=loader)

        selected = gen.select_templates(k=5)

        assert len(selected) == 5
        for tc in selected:
            assert tc.task_instruction in ("Instruction A", "Instruction B")

    def test_select_templates_partial_yaml_fallback(self):
        """When the yaml_loader has a doc for only some template_ids, missing ones use class constants."""
        loader = MagicMock(spec=YamlTemplateLoader)
        loader.SHARED_NAMESPACE = YamlTemplateLoader.SHARED_NAMESPACE

        def get_latest_side(gen, tid, ttype):
            if ttype == "generation" and tid == "template_a":
                return {
                    "template_id": tid,
                    "instruction": "YAML A",
                    "weight": 5.0,
                    "validation_rules": [],
                    "version": "1",
                }
            return None  # template_b missing from YAML

        loader.get_latest.side_effect = get_latest_side
        gen = _make_generator(yaml_loader=loader)

        selected = gen.select_templates(k=20)

        yaml_a = [t for t in selected if t.task_instruction == "YAML A"]
        class_b = [t for t in selected if t.task_instruction == "Instruction B"]
        assert len(yaml_a) + len(class_b) == 20
        assert len(yaml_a) > 0
        assert len(class_b) > 0

    def test_yaml_loader_takes_precedence_over_store(self):
        """When both yaml_loader and template_store are provided, YAML wins."""
        store = MagicMock(spec=TemplateStore)
        store.SHARED_NAMESPACE = TemplateStore.SHARED_NAMESPACE
        store.get_latest.return_value = _make_gen_doc("template_a", "STORE A", weight=9.0)

        loader = MagicMock(spec=YamlTemplateLoader)
        loader.SHARED_NAMESPACE = YamlTemplateLoader.SHARED_NAMESPACE
        loader.get_latest.side_effect = lambda gen, tid, ttype: {
            "template_id": tid,
            "instruction": f"YAML instruction for {tid}",
            "weight": 3.0,
            "validation_rules": [],
            "version": "1",
        } if ttype == "generation" else None

        gen = _make_generator(template_store=store, yaml_loader=loader)
        selected = gen.select_templates(k=5)

        # All should come from YAML (weight 3.0), not store (weight 9.0)
        for tc in selected:
            assert tc.weight == 3.0
            assert tc.task_instruction.startswith("YAML instruction for")
        # Store.get_latest should NOT be called
        store.get_latest.assert_not_called()


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

    def test_store_path_returns_version(self):
        """When template_store is used, version is returned from the doc."""
        store = MagicMock(spec=TemplateStore)
        store.SHARED_NAMESPACE = TemplateStore.SHARED_NAMESPACE
        store.get_latest.return_value = {"version": 3}
        gen = _make_generator(template_store=store)

        result = gen._resolve_validator_version("combo_query")

        assert result == 3

    def test_both_loaders_yaml_wins(self):
        """When both loaders are present, yaml_loader path wins (returns None)."""
        store = MagicMock(spec=TemplateStore)
        store.get_latest.return_value = {"version": 5}
        loader = MagicMock(spec=YamlTemplateLoader)
        gen = _make_generator(template_store=store, yaml_loader=loader)

        result = gen._resolve_validator_version("combo_query")

        assert result is None
        # Store should not be queried
        store.get_latest.assert_not_called()


# =============================================================================
# QueryModel — YAML loader path for validator templates
# =============================================================================

class TestQueryModelYamlValidator:
    """Tests for QueryModel._resolve_validator_template with a YamlTemplateLoader."""

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

    def test_qa_validation_prompt_uses_real_yaml_file(self):
        """__build_qa_validation_prompt loads from the actual shared.yaml on disk."""
        from training_data.generate_synthetic_data.yaml_template_loader import YamlTemplateLoader
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
        from training_data.generate_synthetic_data.yaml_template_loader import YamlTemplateLoader
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
        from training_data.generate_synthetic_data.yaml_template_loader import YamlTemplateLoader
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
        from training_data.generate_synthetic_data.yaml_template_loader import YamlTemplateLoader
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

    def test_from_mongodb_doc(self):
        """MongoDB docs with yaml_content are parsed correctly."""
        import yaml as _yaml
        doc = {
            "template_id": "how_does_it_work",
            "version": 2,
            "yaml_content": _yaml.dump({
                "instruction": "Generate Q&A pairs.",
                "weight": 2.0,
                "validation_rules": ["Rule A"],
                "min_answer_length": 100,
                "max_answer_length": 3000,
            }),
        }
        tc = _dict_to_template_config(doc)
        assert tc.template_id == "how_does_it_work"
        assert tc.task_instruction == "Generate Q&A pairs."
        assert tc.weight == 2.0
        assert tc.validation_rules == ["Rule A"]
        assert tc.min_answer_length == 100
        assert tc.max_answer_length == 3000
        assert tc.version == 2

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
        """YAML docs without an explicit version get '1'."""
        doc = {
            "template_id": "x",
            "instruction": "Do something.",
        }
        tc = _dict_to_template_config(doc)
        assert tc.version == "1"

    def test_mongodb_doc_preserves_version(self):
        """MongoDB docs preserve their integer version."""
        import yaml as _yaml
        doc = {
            "template_id": "x",
            "version": 5,
            "yaml_content": _yaml.dump({"instruction": "Hi"}),
        }
        tc = _dict_to_template_config(doc)
        assert tc.version == 5

    def test_missing_fields_use_defaults(self):
        """Missing fields in a YAML doc fall back to TemplateConfig defaults."""
        doc = {"template_id": "minimal", "instruction": "Hi"}
        tc = _dict_to_template_config(doc)
        assert tc.weight == 1.0
        assert tc.validation_rules == []
        assert tc.min_answer_length == 80
        assert tc.max_answer_length == 2000