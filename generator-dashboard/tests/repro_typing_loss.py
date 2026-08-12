"""Second repro: does typing actually lose focus/keystrokes when watchdog fires?

Types char-by-char for >10s in the model field while SSE streams flow, and
checks whether keystrokes are dropped and whether clicking the HUNG button
disables the UI further. Captures screenshots.
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

        model = page.locator("#ctl-model")
        model.click()

        # Type char-by-char across the 10s watchdog boundary
        text = "gpt-4o-2024-05-13"
        print("== Typing char-by-char across 10s watchdog boundary ==")
        for i, ch in enumerate(text):
            page.keyboard.type(ch)
            time.sleep(1.1)  # 11 chars * 1.1s = 12.1s — crosses 10s boundary
            if i in (4, 7):
                page.screenshot(path=str(SHOTS / f"typing_{i}.png"))

        got = model.input_value()
        print(f"  expected: {text!r}")
        print(f"  got:      {got!r}")
        if got != text:
            failures.append(f"keystrokes dropped while typing: expected {text!r}, got {got!r}")

        # Is focus still on the field?
        focused = page.evaluate("document.activeElement && document.activeElement.id")
        print("  focused element id:", focused)

        stop_btn = page.locator("#stop-all-btn")
        print("  stop-all-btn text:", stop_btn.inner_text())

        # Click the HUNG button like a user would
        if "HUNG" in stop_btn.inner_text():
            print("== Clicking the HUNG button ==")
            stop_btn.click()
            time.sleep(1)
            print("  after click:", stop_btn.inner_text(), "disabled:", stop_btn.is_disabled())
            # Does log SSE come back?
            log_box = page.locator(".log-box")
            print("  log box text head:", repr(log_box.inner_text()[:60]))
            page.screenshot(path=str(SHOTS / "04_after_hung_click.png"))

        print("\n== Console output (last 20) ==")
        for line in console[-20:]:
            print(" ", line)

        browser.close()

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(" -", f)
        return 1
    print("\nNo keystroke loss observed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
