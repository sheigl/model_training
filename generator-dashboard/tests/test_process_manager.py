"""Tests for process_manager helpers and start/stop behavior."""

import config
import process_manager
from process_manager import (
    _flag_value,
    _is_generator_process,
    _parse_ps_output,
    scan_running,
)


def test_parse_ps_output_skips_garbage():
    raw = (
        "  1234 python -m training_data.generate_synthetic_data.main --synergy 5\n"
        "\n"
        "5678 /usr/bin/bash run_synergy.sh\n"
        "  notap id cmd\n"
    )
    assert _parse_ps_output(raw) == [
        (1234, "python -m training_data.generate_synthetic_data.main --synergy 5"),
        (5678, "/usr/bin/bash run_synergy.sh"),
    ]


def test_flag_value_space_and_equals_forms():
    assert _flag_value("--combo-queries 5000 --model m", "--combo-queries") == 5000
    assert _flag_value("--combo-queries=250", "--combo-queries") == 250
    assert _flag_value("--card-search", "--card-search") is None


def test_flag_value_no_prefix_collision():
    assert _flag_value("--commander 5 --commander-building 3", "--commander") == 5
    assert _flag_value("--commander-building 3", "--commander") is None
    assert _flag_value("--commander 5", "--commander-building") is None


def test_is_generator_process():
    assert _is_generator_process("python -m training_data.generate_synthetic_data.main --synergy 3")
    assert not _is_generator_process("python -m training_data.something_else.main")


def test_scan_running_maps_flags_to_slugs(monkeypatch):
    fake_ps = (
        "1234 python -m training_data.generate_synthetic_data.main --synergy 3000\n"
        "5678 python -m training_data.generate_synthetic_data.main --combo-queries 100 --rules-scenarios 50\n"
    )

    class Result:
        stdout = fake_ps

    monkeypatch.setattr(process_manager.subprocess, "run", lambda *a, **k: Result())

    running = scan_running()
    assert running["synergy"][0].pid == 1234
    assert running["synergy"][0].count == 3000
    assert running["combos"][0].pid == 5678
    assert running["combos"][0].count == 100
    assert running["rules_scenarios"][0].pid == 5678


def test_scan_running_empty_when_no_generators(monkeypatch):
    class Result:
        stdout = "1 /usr/lib/systemd/systemd\n2 bash\n"

    monkeypatch.setattr(process_manager.subprocess, "run", lambda *a, **k: Result())
    assert scan_running() == {}


class FakeProc:
    def __init__(self, *args, **kwargs):
        self.pid = 99999


def test_start_writes_pid_file_and_log_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(process_manager.subprocess, "Popen", lambda *a, **k: FakeProc())

    spec = config.GENERATOR_BY_SLUG["synergy"]
    pid = process_manager.start(
        spec, count=10, model="m1", validation_model="v1", validation_pct=1.0
    )
    assert pid == 99999
    assert (tmp_path / "synergy.pid").read_text() == "99999"
    assert (tmp_path / "synergy.log").exists()


def test_start_respects_dry_run(monkeypatch, tmp_path):
    captured = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        return FakeProc()

    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(process_manager.subprocess, "Popen", fake_popen)

    spec = config.GENERATOR_BY_SLUG["archetypes"]
    process_manager.start(
        spec, count=5, model="m", validation_model="v", validation_pct=0.5, dry_run=True
    )
    assert captured["cmd"][0] == "bash"
    assert captured["cmd"][-1] == "--dry-run"
    assert captured["cmd"][1].endswith("run_archetypes.sh")


def test_start_includes_observer_model(monkeypatch, tmp_path):
    captured = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        return FakeProc()

    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(process_manager.subprocess, "Popen", fake_popen)

    spec = config.GENERATOR_BY_SLUG["synergy"]
    process_manager.start(
        spec, count=5, model="m", validation_model="v", validation_pct=1.0, observer_model="obs"
    )
    assert "--observer-model" in captured["cmd"]
    assert "obs" in captured["cmd"]
    assert "--enable-observer" in captured["cmd"]


def test_start_excludes_observer_when_empty(monkeypatch, tmp_path):
    captured = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        return FakeProc()

    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(process_manager.subprocess, "Popen", fake_popen)

    spec = config.GENERATOR_BY_SLUG["synergy"]
    process_manager.start(
        spec, count=5, model="m", validation_model="v", validation_pct=1.0
    )
    assert "--observer-model" not in captured["cmd"]
    assert "--enable-observer" not in captured["cmd"]


def test_stop_removes_pid_file(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(process_manager, "scan_running", lambda: {})

    spec = config.GENERATOR_BY_SLUG["synergy"]
    (tmp_path / "synergy.pid").write_text("999999999")

    killed = process_manager.stop(spec)
    assert killed == [999999999]
    assert not (tmp_path / "synergy.pid").exists()


def test_stop_with_no_running_and_no_pid_file(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(process_manager, "scan_running", lambda: {})
    assert process_manager.stop(config.GENERATOR_BY_SLUG["synergy"]) == []
