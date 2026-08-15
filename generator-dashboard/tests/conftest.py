"""Test bootstrap: make the generator-dashboard modules importable under pytest."""

import asyncio
import sys
import threading
from pathlib import Path

DASHBOARD_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = DASHBOARD_DIR.parent

for p in (DASHBOARD_DIR, REPO_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def run_async(coro):
    """Run a coroutine to completion on a fresh event loop.

    Playwright's sync API (used by the e2e suites) leaves a running event loop
    in the main thread, which makes ``asyncio.run()`` raise "cannot be called
    from a running event loop". ``run_until_complete`` has the same guard in
    Python 3.13+, so the coroutine is run inside a dedicated worker thread
    where the thread-local running-loop check never trips — keeping the
    SSE-stream tests order-independent.
    """
    box: dict[str, object] = {}

    def _runner() -> None:
        loop = asyncio.new_event_loop()
        try:
            box["value"] = loop.run_until_complete(coro)
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()

    thread = threading.Thread(target=_runner)
    thread.start()
    thread.join()
    return box["value"]
