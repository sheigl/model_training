"""Process management for the generator dashboard.

Discovers running generators via ``ps`` (so generators launched outside the
dashboard are seen too), starts new ones through the ``run_*.sh`` shell scripts
with output redirected to ``generator-dashboard/logs/<slug>.log``, and stops
them by killing the process tree / session group.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass

from dotenv import load_dotenv

from config import BASE_DIR, GENERATORS, SCRAPERS, GeneratorSpec, ScraperSpec

MAIN_MODULE = "training_data.generate_synthetic_data.main"


@dataclass
class RunningInstance:
    pid: int
    count: int
    cmdline: str


def _parse_ps_output(raw: str) -> list[tuple[int, str]]:
    """Parse ``ps -eo pid=,args=`` output into (pid, cmdline) pairs."""
    results: list[tuple[int, str]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        pid_str, _, cmdline = line.partition(" ")
        if pid_str.isdigit() and cmdline.strip():
            results.append((int(pid_str), cmdline.strip()))
    return results


def _flag_value(cmdline: str, flag: str) -> int | None:
    """Return the integer value following *flag* in a cmdline (argparse-style)."""
    tokens = cmdline.split()
    for i, tok in enumerate(tokens):
        if tok.startswith(flag + "="):
            value = tok.split("=", 1)[1]
            try:
                return int(value)
            except ValueError:
                return None
        if tok == flag and i + 1 < len(tokens):
            try:
                return int(tokens[i + 1])
            except ValueError:
                return None
    return None


def _is_generator_process(cmdline: str) -> bool:
    return MAIN_MODULE in cmdline


def scan_running() -> dict[str, list[RunningInstance]]:
    """Map each generator slug to the processes currently running it."""
    raw = subprocess.run(
        ["ps", "-eo", "pid=,args="],
        capture_output=True,
        text=True,
        check=False,
    ).stdout

    instances: dict[str, list[RunningInstance]] = {}
    for pid, cmdline in _parse_ps_output(raw):
        if not _is_generator_process(cmdline):
            continue
        for spec in GENERATORS:
            count = _flag_value(cmdline, spec.flag)
            if count is not None and count > 0:
                instances.setdefault(spec.slug, []).append(
                    RunningInstance(pid=pid, count=count, cmdline=cmdline)
                )
    return instances


def _is_scraper_process(cmdline: str) -> bool:
    """True when the cmdline references one of the scraper run scripts."""
    return any(f"run_{spec.slug}.sh" in cmdline for spec in SCRAPERS)


def scan_scrapers() -> dict[str, list[RunningInstance]]:
    """Map each scraper slug to the processes currently running it.

    Scrapers are detected by their ``run_<slug>.sh`` wrapper name so items that
    share a python module (e.g. the EDHREC modes) stay unambiguous.
    """
    raw = subprocess.run(
        ["ps", "-eo", "pid=,args="],
        capture_output=True,
        text=True,
        check=False,
    ).stdout

    instances: dict[str, list[RunningInstance]] = {}
    for pid, cmdline in _parse_ps_output(raw):
        if not _is_scraper_process(cmdline):
            continue
        for spec in SCRAPERS:
            if f"run_{spec.slug}.sh" in cmdline:
                instances.setdefault(spec.slug, []).append(
                    RunningInstance(pid=pid, count=0, cmdline=cmdline)
                )
    return instances


def is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def start(
    spec: GeneratorSpec,
    count: int,
    model: str,
    validation_model: str,
    validation_pct: float,
    dry_run: bool = False,
    observer_model: str = "",
    shadow_validation_model: str = "",
) -> int:
    """Launch ``run_<slug>.sh`` as a detached process, logging to ``logs/<slug>.log``.

    All optional values are passed as named flags (never positional), so the
    run scripts parse them position-independently (Story 049).
    """
    if not spec.script.exists():
        raise FileNotFoundError(f"Script not found: {spec.script}")

    cmd = [
        "bash", str(spec.script),
        "--count", str(count),
        "--model", model,
        "--validation-model", validation_model,
        "--validation-pct", str(validation_pct),
    ]
    if dry_run:
        cmd.append("--dry-run")
    if observer_model:
        cmd.extend(["--observer-model", observer_model])
    if shadow_validation_model:
        cmd.extend(["--shadow-validation-model", shadow_validation_model])
    return _spawn(spec, cmd)


def start_scraper(spec: ScraperSpec, extra_args: list[str] | None = None) -> int:
    """Launch ``run_<slug>.sh`` for a scraper with its default + extra args."""
    if not spec.script.exists():
        raise FileNotFoundError(f"Script not found: {spec.script}")

    cmd = ["bash", str(spec.script), *list(spec.default_args), *(extra_args or [])]
    return _spawn(spec, cmd)


def _spawn(spec, cmd: list[str]) -> int:
    """Detach a shell command, append its output to the spec's log, write a pid file."""
    spec.log_path.parent.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    load_dotenv(BASE_DIR / ".env")
    env.update({k: v for k, v in os.environ.items()})
    env["BASE_DIR"] = str(BASE_DIR)
    # Stream output line-by-line so the dashboard log tailer sees it live.
    env["PYTHONUNBUFFERED"] = "1"

    with open(spec.log_path, "a") as logf:
        proc = subprocess.Popen(
            cmd,
            cwd=str(BASE_DIR),
            stdout=logf,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=env,
        )

    spec.pid_path.write_text(str(proc.pid))
    return proc.pid


def _ppid_map() -> dict[int, list[int]]:
    raw = subprocess.run(
        ["ps", "-eo", "pid=,ppid=,args="],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    mapping: dict[int, list[int]] = {}
    for line in raw.splitlines():
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            mapping.setdefault(int(parts[1]), []).append(int(parts[0]))
    return mapping


def _descendants(pid: int) -> list[int]:
    mapping = _ppid_map()
    result: list[int] = []
    frontier = [pid]
    while frontier:
        current = frontier.pop()
        children = mapping.get(current, [])
        for child in children:
            result.append(child)
            frontier.append(child)
    return result


def _kill_pids(pids: list[int], sig: int) -> None:
    for pid in pids:
        try:
            os.kill(pid, sig)
        except (ProcessLookupError, PermissionError):
            pass


def _kill_tree(pid: int) -> None:
    """Terminate a process and all its descendants (children first)."""
    tree = _descendants(pid) + [pid]
    _kill_pids(tree, signal.SIGTERM)
    time.sleep(0.5)
    alive = [p for p in tree if is_alive(p)]
    if alive:
        _kill_pids(alive, signal.SIGKILL)


def _kill_group(pid: int) -> None:
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    time.sleep(0.5)
    try:
        if is_alive(pid):
            os.killpg(os.getpgid(pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def stop(spec: GeneratorSpec) -> list[int]:
    """Stop all processes running *spec*; returns the PIDs that were targeted."""
    return _stop(spec, scan_running().get(spec.slug, []))


def stop_scraper(spec: ScraperSpec) -> list[int]:
    """Stop all processes running a scraper; returns the PIDs that were targeted."""
    return _stop(spec, scan_scrapers().get(spec.slug, []))


def _stop(spec, running: list[RunningInstance]) -> list[int]:
    pids: set[int] = set()
    spawned_pids: set[int] = set()

    if spec.pid_path.exists():
        try:
            spawned_pids.add(int(spec.pid_path.read_text().strip()))
        except ValueError:
            pass

    for inst in running:
        pids.add(inst.pid)

    pids |= spawned_pids

    for pid in pids:
        if pid in spawned_pids:
            try:
                if os.getpgid(pid) == pid:
                    _kill_group(pid)
                    continue
            except (ProcessLookupError, PermissionError):
                pass
        _kill_tree(pid)

    spec.pid_path.unlink(missing_ok=True)
    return sorted(pids)


def running_instances(spec: GeneratorSpec) -> list[RunningInstance]:
    return scan_running().get(spec.slug, [])
