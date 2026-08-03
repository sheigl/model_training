"""Registry integrity tests for the scraper jobs."""

import config
from config import SCRAPERS, SCRAPER_BY_SLUG, SCRAPERS_DIR


def test_scraper_count():
    assert len(SCRAPERS) == 9


def test_scraper_unique_slugs():
    assert len({s.slug for s in SCRAPERS}) == len(SCRAPERS)
    assert set(SCRAPER_BY_SLUG) == {s.slug for s in SCRAPERS}


def test_scraper_slugs_do_not_collide_with_generators():
    gen_slugs = {g.slug for g in config.GENERATORS}
    scraper_slugs = {s.slug for s in SCRAPERS}
    assert gen_slugs.isdisjoint(scraper_slugs)


def test_run_scripts_exist():
    for spec in SCRAPERS:
        assert spec.script.exists(), f"missing {spec.script.name}"


def test_python_scripts_exist():
    for spec in SCRAPERS:
        assert (SCRAPERS_DIR / spec.python_script).exists(), spec.python_script


def test_run_scripts_invoke_python_script():
    for spec in SCRAPERS:
        text = spec.script.read_text()
        assert spec.python_script in text, f"{spec.script.name} must invoke {spec.python_script}"


def test_edhrec_modes_share_script_with_unique_args():
    edhrec = [s for s in SCRAPERS if s.python_script == "scrape_edhrec.py"]
    assert len(edhrec) == 6
    arg_sets = {s.default_args for s in edhrec}
    assert len(arg_sets) == 6, "each EDHREC mode needs distinct default args"


def test_log_and_pid_paths():
    for spec in SCRAPERS:
        assert spec.log_path.name == f"{spec.slug}.log"
        assert spec.pid_path.name == f"{spec.slug}.pid"
