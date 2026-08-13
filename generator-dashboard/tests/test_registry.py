"""Registry integrity tests: 27 generators, scripts/flags/classes/categories valid."""

import re

import config
from config import GENERATORS, GENERATOR_BY_SLUG


def test_twenty_seven_generators():
    assert len(GENERATORS) == 27


def test_unique_keys():
    assert len({g.slug for g in GENERATORS}) == 27
    assert len({g.flag for g in GENERATORS}) == 27
    assert len({g.category for g in GENERATORS}) == 27
    assert len({g.class_name for g in GENERATORS}) == 27
    assert set(GENERATOR_BY_SLUG) == {g.slug for g in GENERATORS}


def test_shell_scripts_exist_and_use_flag():
    for spec in GENERATORS:
        script = config.GEN_SYNTH_DIR / f"run_{spec.slug}.sh"
        assert script.exists(), f"missing {script.name}"
        assert spec.flag in script.read_text(), f"{script.name} must pass {spec.flag}"


def test_class_names_defined_in_generator_sources():
    sources = "\n".join(p.read_text() for p in config.GEN_SYNTH_DIR.glob("generate_*.py"))
    for spec in GENERATORS:
        assert re.search(rf"class\s+{spec.class_name}\b", sources), spec.class_name


def test_flags_defined_in_main_parser():
    main_src = (config.GEN_SYNTH_DIR / "main.py").read_text()
    for spec in GENERATORS:
        assert spec.flag in main_src, f"{spec.flag} missing from main.py"


def test_categories_have_yaml_templates():
    templates_dir = config.GEN_SYNTH_DIR / "templates"
    for spec in GENERATORS:
        assert (templates_dir / f"{spec.category}.yaml").exists(), (
            f"no templates/{spec.category}.yaml"
        )


def test_default_counts_positive():
    for spec in GENERATORS:
        assert spec.default_count > 0


def test_all_scripts_define_model_defaults():
    for spec in GENERATORS:
        model, validation, observer, shadow = config.script_model_defaults(spec)
        assert model is not None, f"{spec.slug}: missing DEFAULT_MODEL"
        assert validation is not None, f"{spec.slug}: missing DEFAULT_VALIDATION_MODEL"
        assert "openai" in model and "openai" in validation


def test_script_model_defaults_parses(monkeypatch, tmp_path):
    (tmp_path / "run_test.sh").write_text(
        'DEFAULT_MODEL="host,openai,gemma4:31b,$LITELLM_API_KEY"\n'
        'DEFAULT_VALIDATION_MODEL="host,openai,glm-5.2,$LITELLM_API_KEY"\n'
        "OTHER=stuff\n"
    )
    monkeypatch.setattr(config, "GEN_SYNTH_DIR", tmp_path)
    model, validation, observer, shadow = config.script_model_defaults(
        config.GeneratorSpec("test", "--x", "cat", "Cls", 1)
    )
    assert model == "host,openai,gemma4:31b,$LITELLM_API_KEY"
    assert validation == "host,openai,glm-5.2,$LITELLM_API_KEY"
    assert observer is None
    assert shadow is None


def test_script_model_defaults_missing_script():
    from config import GeneratorSpec

    spec = GeneratorSpec("does_not_exist", "--x", "cat", "Cls", 1)
    assert config.script_model_defaults(spec) == (None, None, None, None)
