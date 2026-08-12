"""Diagnostic repro: does field editing hang after the 10s watchdog fires?

Simulates the user flow — open dashboard, click into a field, type, wait,
while SSE streams keep flowing. Captures console errors and screenshots.
Run: .venv/bin/python tests/repro_field_hang.py
"""

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:9999"
SHOTS = Path(__file__).resolve().parent / "shots"
SHOTS.mkdir(exist_ok=True)


def main() -> int:
    failures = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()

        console = []
        page.on("console", lambda m: console.append(f"[{m.type}] {m.text}"))
        page.on("pageerror", lambda e: console.append(f"[pageerror] {e}"))

        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_selector("#ctl-count", timeout=10000)
        page.screenshot(path=str(SHOTS / "01_initial.png"))

        print("== Step: click into model field and type ==")
        model = page.locator("#ctl-model")
        model.click()
        model.fill("gpt-4o")
        time.sleep(2)
        print("  typed value:", model.input_value())

        # Check stop-all button text over time — watchdog should not misfire
        stop_btn = page.locator("#stop-all-btn")
        print("== Watching for watchdog misfire over 15s of field editing ==")
        t0 = time.time()
        while time.time() - t0 < 15:
            txt = stop_btn.inner_text()
            print(f"  t={time.time()-t0:5.1f}s stop-all-btn={txt!r}")
            if "HUNG" in txt:
                failures.append(f"watchdog misfired while editing: button={txt!r}")
                page.screenshot(path=str(SHOTS / "02_hung_during_edit.png"))
                break
            time.sleep(1)

        # Is the field still editable after 15s?
        model.fill("claude-3.5")
        page.screenshot(path=str(SHOTS / "03_after_wait.png"))
        print("  value after re-edit:", model.input_value())

        # Check log box state / SSE
        log_box = page.locator(".log-box")
        print("  log box text head:", repr(log_box.inner_text()[:80]))

        print("\n== Console output (last 30) ==")
        for line in console[-30:]:
            print(" ", line)

        browser.close()

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(" -", f)
        return 1
    print("\nNo watchdog misfire observed during editing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
