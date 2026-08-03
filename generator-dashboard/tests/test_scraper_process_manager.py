"""Tests for scraper process management."""

import pytest

import config
import process_manager
from config import ScraperSpec
from process_manager import _is_scraper_process, scan_scrapers


def test_is_scraper_process():
    assert _is_scraper_process("bash /x/training_data/run_edhrec_guides.sh --guides")
    assert _is_scraper_process("bash run_funtrivia.sh SOME_URL")
    assert not _is_scraper_process("python -m training_data.generate_synthetic_data.main --synergy 3")
    assert not _is_scraper_process("bash run_combos.sh")


def test_scan_scrapers_maps_wrapper_to_slug(monkeypatch):
    fake_ps = (
        "1111 bash /x/training_data/run_edhrec_guides.sh --guides\n"
        "2222 python /x/training_data/scrape_edhrec.py --guides\n"
        "3333 bash /x/training_data/run_mtg_archetypes.sh\n"
    )

    class Result:
        stdout = fake_ps

    monkeypatch.setattr(process_manager.subprocess, "run", lambda *a, **k: Result())

    running = scan_scrapers()
    assert running["edhrec_guides"][0].pid == 1111
    assert running["mtg_archetypes"][0].pid == 3333
    assert "edhrec_commanders" not in running


def test_scan_scrapers_empty(monkeypatch):
    class Result:
        stdout = "1 /usr/lib/systemd/systemd\n2 bash\n"

    monkeypatch.setattr(process_manager.subprocess, "run", lambda *a, **k: Result())
    assert scan_scrapers() == {}


class FakeProc:
    def __init__(self, *args, **kwargs):
        self.pid = 99991


def test_start_scraper_builds_cmd_with_default_and_extra_args(monkeypatch, tmp_path):
    captured = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        return FakeProc()

    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(process_manager.subprocess, "Popen", fake_popen)

    spec = config.SCRAPER_BY_SLUG["edhrec_top_color"]
    pid = process_manager.start_scraper(spec, extra_args=["--top-by-color", "red"])
    assert pid == 99991
    cmd = captured["cmd"]
    assert cmd[0] == "bash"
    assert cmd[1].endswith("run_edhrec_top_color.sh")
    assert cmd[-2:] == ["--top-by-color", "red"]
    assert (tmp_path / "edhrec_top_color.pid").read_text() == "99991"
    assert (tmp_path / "edhrec_top_color.log").exists()


def test_start_scraper_forces_unbuffered_output(monkeypatch, tmp_path):
    captured = {}

    def fake_popen(cmd, **kwargs):
        captured["env"] = kwargs.get("env")
        return FakeProc()

    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(process_manager.subprocess, "Popen", fake_popen)

    process_manager.start_scraper(config.SCRAPER_BY_SLUG["funtrivia"])
    assert captured["env"]["PYTHONUNBUFFERED"] == "1"


def test_start_scraper_missing_script(monkeypatch, tmp_path):
    spec = ScraperSpec("nope", "Nope", "desc", "scrape_nope.py")
    with pytest.raises(FileNotFoundError):
        process_manager.start_scraper(spec)


def test_stop_scraper_removes_pid_file(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(process_manager, "scan_scrapers", lambda: {})

    spec = config.SCRAPER_BY_SLUG["funtrivia"]
    (tmp_path / "funtrivia.pid").write_text("999999999")

    killed = process_manager.stop_scraper(spec)
    assert killed == [999999999]
    assert not (tmp_path / "funtrivia.pid").exists()
