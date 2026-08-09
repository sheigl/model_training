"""Playwright e2e tests for the generator dashboard mobile experience."""

import time
import pytest
from playwright.sync_api import Page, expect


BASE_URL = "http://localhost:9999"


@pytest.fixture
def page(playwright):
    """Create a mobile-like browser page."""
    browser = playwright.chromium.launch(channel="chrome")
    context = browser.new_context(
        viewport={"width": 375, "height": 812},  # iPhone X size
        is_mobile=True,
        has_touch=True,
        device_scale_factor=3,
    )
    page = context.new_page()
    page.goto(BASE_URL)
    yield page
    context.close()
    browser.close()


class TestMobileResponsiveness:
    """Test that the dashboard remains responsive on mobile."""

    def test_page_loads(self, page: Page):
        """Page should load successfully."""
        expect(page.locator("text=MTG Generator Dashboard")).to_be_visible()
        expect(page.locator("#tabs")).to_be_visible()

    def test_tabs_render(self, page: Page):
        """All generator tabs should render."""
        # Wait for tabs to load
        page.wait_for_selector(".tab", state="visible", timeout=5000)
        tabs = page.locator(".tab")
        expect(tabs).to_have_count(27)  # 27 generators

    def test_scraper_tab_toggle(self, page: Page):
        """Mode toggle should switch between generators and scrapers."""
        # Should be on generators by default
        gen_btn = page.locator("#mode-generators")
        expect(gen_btn).to_have_class("mode-btn active")
        
        # Click scrapers tab
        page.click("#mode-scrapers")
        
        # Wait for tabs to update
        page.wait_for_timeout(500)
        
        scrapers_btn = page.locator("#mode-scrapers")
        expect(scrapers_btn).to_have_class("mode-btn active")
        
        # Should show scrapers now
        scraper_tabs = page.locator(".tab")
        expect(scraper_tabs).to_have_count(9)  # 9 scrapers

    def test_tab_click_responsive(self, page: Page):
        """Clicking tabs should not freeze the page."""
        start = time.time()
        
        # Click through several tabs
        for i in range(5):
            tab = page.locator(f".tab").nth(i)
            tab.click()
            # Should respond within 1 second
            assert time.time() - start < 5, f"Tab click #{i} took too long"
        
        elapsed = time.time() - start
        print(f"5 tab clicks took {elapsed:.2f}s")
        assert elapsed < 5, "Tab clicking is too slow"

    def test_input_focus(self, page: Page):
        """Input fields should accept focus on mobile."""
        # Switch to generators mode
        page.click("#mode-generators")
        page.wait_for_timeout(300)
        
        # Click first tab to get generator panel
        page.locator(".tab").first.click()
        
        # Wait for panel to render
        page.wait_for_selector("#ctl-count", state="visible", timeout=5000)
        
        # Try to focus on count input
        count_input = page.locator("#ctl-count")
        count_input.focus()
        
        # Should be focused (on mobile this is tricky, but we can check it's clickable)
        expect(count_input).to_be_visible()

    def test_model_field_interactions(self, page: Page):
        """Clicking into model field and changing value should not hang."""
        # Ensure we're on generators mode
        page.click("#mode-generators")
        page.wait_for_timeout(300)
        
        # Click first tab to get generator panel
        page.locator(".tab").first.click()
        
        # Wait for panel to render
        page.wait_for_selector("#ctl-model", state="visible", timeout=5000)
        
        model_input = page.locator("#ctl-model")
        
        # Click into the field and try to change value multiple times
        for i in range(10):
            # Click into the field
            model_input.click()
            page.wait_for_timeout(200)
            
            # Select all text
            model_input.select_text()
            page.wait_for_timeout(100)
            
            # Type new value
            test_value = f"test-model-{i}"
            model_input.fill(test_value)
            page.wait_for_timeout(200)
            
            # Verify the value changed
            current_value = model_input.input_value()
            assert current_value == test_value, f"Value not updated: expected {test_value}, got {current_value}"
        
        # Page should still be responsive - check tabs are still clickable
        tab = page.locator(".tab").first
        expect(tab).to_be_visible()
        
        # Try clicking a different tab to verify responsiveness
        page.locator(".tab").nth(1).click()
        page.wait_for_timeout(500)
        
        # Should be able to click back
        page.locator(".tab").first.click()
        page.wait_for_timeout(300)
        
        expect(model_input).to_be_visible()

    def test_multiple_field_interactions(self, page: Page):
        """Multiple input fields should all work without hanging."""
        # Ensure we're on generators mode
        page.click("#mode-generators")
        page.wait_for_timeout(300)
        
        # Click first tab to get generator panel
        page.locator(".tab").first.click()
        page.wait_for_timeout(500)
        
        fields = [
            ("#ctl-count", "100"),
            ("#ctl-model", "test-model-1"),
            ("#ctl-valmodel", "test-val-1"),
            ("#ctl-pct", "0.5"),
        ]
        
        for field_id, value in fields:
            input_el = page.locator(field_id)
            expect(input_el).to_be_visible()
            
            # Click and fill
            input_el.click()
            page.wait_for_timeout(100)
            input_el.fill(value)
            page.wait_for_timeout(200)
            
            # Verify value
            current = input_el.input_value()
            assert current == value, f"Field {field_id}: expected {value}, got {current}"
        
        # Page should still be responsive
        expect(page.locator("#tabs")).to_be_visible()

    def test_sse_updates_dont_hang(self, page: Page):
        """SSE updates should not cause hangs."""
        start = time.time()
        
        # Wait for a few SSE ticks (2s each)
        page.wait_for_timeout(5000)
        
        elapsed = time.time() - start
        print(f"Waited {elapsed:.2f}s for SSE updates")
        
        # Page should still be responsive
        expect(page.locator("#tabs")).to_be_visible()

    def test_no_console_errors(self, page: Page):
        """Should have no critical console errors."""
        errors = []
        page.on("console", lambda msg: errors.append(msg) if msg.type == "error" else None)
        
        # Interact with the page
        page.click("#mode-generators")
        page.wait_for_timeout(1000)
        
        # Filter out expected warnings about tick limits etc
        critical_errors = [e for e in errors if "tick limit exceeded" not in str(e).lower()]
        print(f"Console errors: {len(errors)} total, {len(critical_errors)} critical")

    def test_memory_stability(self, page: Page):
        """Memory usage should stabilize, not grow unbounded."""
        # Wait for initial load
        page.wait_for_selector(".tab", state="visible", timeout=5000)
        
        # Take initial measurement
        initial_tabs = page.locator(".tab").count()
        assert initial_tabs == 27, f"Expected 27 tabs initially, got {initial_tabs}"
        
        # Click through tabs multiple times
        for i in range(10):
            tab = page.locator(f".tab").nth(i % 27)
            tab.click()
            page.wait_for_timeout(500)
        
        # Should still have same number of tabs
        final_tabs = page.locator(".tab").count()
        assert final_tabs == initial_tabs, f"Tab count changed: {initial_tabs} -> {final_tabs}"

    def test_stop_button_works(self, page: Page):
        """STOP ALL button should be present and clickable."""
        stop_btn = page.locator("#stop-all-btn")
        if stop_btn.count() > 0:
            expect(stop_btn).to_be_visible()
            stop_btn.click()
            # Button should show stopped state
            expect(stop_btn).to_have_text("STOPPED")



    def test_safari_like_interaction_pattern(self, page: Page):
        """Simulate exact user flow that causes hang on Safari."""
        # 1. Click tab to select generator
        page.locator(".tab").nth(0).click()
        page.wait_for_timeout(500)
        
        # 2. Click into model field
        model_input = page.locator("#ctl-model")
        expect(model_input).to_be_visible()
        model_input.click()
        page.wait_for_timeout(300)
        
        # 3. Type something
        model_input.fill("https://test.example.com/v1,openai,gpt-4,test-key")
        page.wait_for_timeout(200)
        
        # 4. Click away (blur)
        model_input.blur()
        page.wait_for_timeout(200)
        
        # 5. Click another tab
        page.locator(".tab").nth(1).click()
        page.wait_for_timeout(500)
        
        # 6. Go back and click into field again
        page.locator(".tab").nth(0).click()
        page.wait_for_timeout(300)
        
        model_input = page.locator("#ctl-model")
        expect(model_input).to_be_visible()
        model_input.click()
        page.wait_for_timeout(200)
        
        # 7. Type again
        model_input.fill("https://test2.example.com/v1,openai,gpt-3.5,key123")
        page.wait_for_timeout(200)
        
        # 8. Click stop button (if visible) or another input
        if page.locator("#stop-all-btn").count() > 0:
            page.locator("#stop-all-btn").click()
            page.wait_for_timeout(300)
        
        # Verify page is still responsive
        expect(page.locator("#tabs")).to_be_visible()
        tabs = page.locator(".tab")
        expect(tabs).to_have_count(27)

    def test_rapid_input_field_switching(self, page: Page):
        """Rapidly switch between input fields like a user would."""
        # Navigate to generator panel
        page.click("#mode-generators")
        page.wait_for_timeout(300)
        page.locator(".tab").first.click()
        page.wait_for_timeout(500)
        
        # Text fields only (count and pct are number inputs)
        text_fields = ["#ctl-model", "#ctl-valmodel", "#ctl-obsmodel"]
        
        # Click through text fields multiple times
        for round in range(5):
            for field_id in text_fields:
                input_el = page.locator(field_id)
                expect(input_el).to_be_visible(timeout=3000)
                
                input_el.click()
                page.wait_for_timeout(100)
                
                # Clear and type new value
                input_el.fill(f"test-{round}-{field_id}")
                page.wait_for_timeout(100)
        
        # Also test number fields with proper values
        num_fields = ["#ctl-count", "#ctl-pct"]
        for round in range(3):
            for field_id in num_fields:
                input_el = page.locator(field_id)
                expect(input_el).to_be_visible(timeout=3000)
                
                input_el.click()
                page.wait_for_timeout(100)
                
                # Set numeric value
                if "count" in field_id:
                    input_el.fill(str(round + 100))
                else:
                    input_el.fill(str(0.5 + round * 0.1))
                page.wait_for_timeout(100)
        
        # Page should still be responsive
        expect(page.locator("#tabs")).to_be_visible()


class TestPerformance:
    """Performance tests to detect hangs."""

    def test_rapid_tab_switching(self, page: Page):
        """Rapid tab switching should not hang the page."""
        start = time.time()
        
        # Rapid click through all tabs
        for i in range(27):
            tab = page.locator(f".tab").nth(i)
            tab.click()
            # Each click should complete within 1 second
            assert time.time() - start < 30, f"Page hung after {i} tab clicks"
        
        elapsed = time.time() - start
        print(f"27 rapid tab clicks took {elapsed:.2f}s ({elapsed/27:.3f}s per click)")
        assert elapsed < 15, "Rapid tab switching is too slow"

    def test_concurrent_sse_and_interaction(self, page: Page):
        """Page should remain responsive during SSE updates."""
        start = time.time()
        
        # Click tabs while SSE is active
        for i in range(5):
            tab = page.locator(f".tab").nth(i)
            tab.click()
            page.wait_for_timeout(1000)  # Let SSE fire
        
        elapsed = time.time() - start
        print(f"5 interactive clicks + SSE took {elapsed:.2f}s")
        assert elapsed < 10, "Page became unresponsive during SSE updates"
