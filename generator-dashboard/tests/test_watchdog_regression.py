"""Regression test: watchdog must not misfire during normal field editing.

Before the fix, the watchdog timer (10s) would fire while the user was actively
typing in a field because only boot() and SSE error handlers called updateProgress().
Normal SSE message events did NOT reset the progress timer.

See repro_field_hang.py for the original diagnostic script.
"""

import time
import pytest
from playwright.sync_api import Page, expect

BASE_URL = "http://localhost:9999"


@pytest.fixture
def page(playwright):
    browser = playwright.chromium.launch(channel="chrome", headless=True)
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_selector("#ctl-count", timeout=10000)
    yield page
    browser.close()


class TestWatchdogRegression:
    """The watchdog should not fire during normal field editing."""

    def test_watchdog_does_not_fire_during_editing(self, page: Page):
        """Stop-all button must stay 'STOP ALL' while user edits fields for >10s."""
        stop_btn = page.locator("#stop-all-btn")
        model = page.locator("#ctl-model")

        # Click into field and type
        model.click()
        model.fill("test-model-value")

        # Wait 12 seconds — crosses the 10s watchdog boundary
        start = time.time()
        while time.time() - start < 12:
            txt = stop_btn.inner_text()
            assert "HUNG" not in txt, (
                f"Watchdog misfired after {time.time()-start:.1f}s during editing. "
                f"Button text: {txt!r}"
            )
            time.sleep(0.5)

        # Field should still be editable
        model.fill("another-value")
        assert model.input_value() == "another-value"

    def test_watchdog_does_not_fire_during_sse_streaming(self, page: Page):
        """SSE streaming alone must keep the watchdog happy."""
        stop_btn = page.locator("#stop-all-btn")

        # Just wait — SSE streams should reset progress timer
        start = time.time()
        while time.time() - start < 12:
            txt = stop_btn.inner_text()
            assert "HUNG" not in txt, (
                f"Watchdog misfired after {time.time()-start:.1f}s during idle SSE. "
                f"Button text: {txt!r}"
            )
            time.sleep(0.5)

    def test_no_watchdog_errors_in_console(self, page: Page):
        """Console should not contain watchdog errors during normal use."""
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

        # Interact normally for 12s
        model = page.locator("#ctl-model")
        model.click()
        model.fill("gpt-4o")
        time.sleep(12)

        watchdog_errors = [e for e in errors if "watchdog" in e.lower()]
        assert not watchdog_errors, (
            f"Watchdog errors found during normal use: {watchdog_errors}"
        )
