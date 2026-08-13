"""Test bootstrap: make the generator-dashboard modules importable under pytest."""

import asyncio
import sys
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
    from a running event loop". Running on an explicitly-created loop bypasses
    that check and keeps the SSE-stream tests order-independent.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
