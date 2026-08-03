"""Incremental log tailing for the generator dashboard."""

from __future__ import annotations

from pathlib import Path


class LogTailer:
    """Reads a log file incrementally, tracking a byte offset between reads.

    Complete lines are returned as they appear; a partial trailing line (no
    trailing newline yet) is held back until the next read so the dashboard
    never shows a half-written log record.
    """

    def __init__(self, path: Path):
        self.path = path
        self._offset = 0

    def tail(self, lines: int = 200) -> list[str]:
        """Return the last *lines* lines of the file (or [] if it doesn't exist)."""
        if not self.path.exists():
            return []
        size = self.path.stat().st_size
        if size == 0:
            return []
        with open(self.path, "rb") as f:
            read = min(size, max(lines * 256, 4096))
            f.seek(max(size - read, 0))
            data = f.read()
        return data.decode("utf-8", errors="replace").splitlines()[-lines:]

    def new_lines(self) -> list[str]:
        """Return newly-appended complete lines since the last call."""
        if not self.path.exists():
            self._offset = 0
            return []

        with open(self.path, "rb") as f:
            f.seek(self._offset)
            data = f.read()
            self._offset = f.tell()

        if not data:
            return []

        if not data.endswith(b"\n"):
            last_nl = data.rfind(b"\n")
            if last_nl == -1:
                self._offset -= len(data)
                return []
            complete = data[: last_nl + 1]
            self._offset -= len(data[last_nl + 1 :])
            data = complete

        return data.decode("utf-8", errors="replace").splitlines()

    def reset(self) -> None:
        self._offset = 0
