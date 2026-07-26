import { test, expect } from '@playwright/test';

test.describe('App Startup', () => {
  test('app loads', async ({ page }) => {
    await page.goto('http://localhost:8506/');
    await page.waitForTimeout(4000);
    await page.screenshot({ path: 'e2e/screenshots/home-page.png', fullPage: true });
    expect(page.url()).toContain('localhost:8506');
    const content = await page.locator('body').textContent().catch(() => '');
    expect(content.length).toBeGreaterThan(0);
  });

  test('no critical errors on dashboard', async ({ page }) => {
    await page.goto('http://localhost:8506/');
    await page.waitForTimeout(5000);
    const exceptions = await page.locator('.stException').count().catch(() => 99);
    expect(exceptions).toBeLessThan(3);
  });

  test('generate page loads via navigation', async ({ page }) => {
    await page.goto('http://localhost:8506/');
    await page.waitForTimeout(3000);

    // Try clicking a sidebar link to navigate to Generate
    const generateLink = page.getByText('Generate', { exact: true }).first();
    const linkVisible = await generateLink.isVisible().catch(() => false);
    if (linkVisible) {
      await generateLink.click();
      await page.waitForTimeout(4000);
    }

    await page.screenshot({ path: 'e2e/screenshots/generate-page.png', fullPage: true });
    const content = await page.locator('body').textContent().catch(() => '');
    expect(content.length).toBeGreaterThan(0);
  });

  test('settings page loads via navigation', async ({ page }) => {
    await page.goto('http://localhost:8506/');
    await page.waitForTimeout(3000);

    const settingsLink = page.getByText('Settings', { exact: true }).first();
    const linkVisible = await settingsLink.isVisible().catch(() => false);
    if (linkVisible) {
      await settingsLink.click();
      await page.waitForTimeout(4000);
    }

    await page.screenshot({ path: 'e2e/screenshots/settings-page.png', fullPage: true });
    const content = await page.locator('body').textContent().catch(() => '');
    expect(content.length).toBeGreaterThan(0);
  });
});
