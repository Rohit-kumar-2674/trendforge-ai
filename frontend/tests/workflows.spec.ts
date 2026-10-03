import { expect, test } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

test('explore, inspect forecasts and evidence, save a watchlist, compare and research', async ({ page }, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'The signal before the noise.' })).toBeVisible();
  await expect(page.getByText('DEMO WORKSPACE', { exact: true })).toBeVisible();
  await expect(page.locator('.trend-table tbody tr')).toHaveCount(7);
  // Compare with the requested viewport; mobile innerWidth itself expands on overflow.
  const contentWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(contentWidth).toBeLessThanOrEqual(page.viewportSize()!.width + 1);
  const folder = path.resolve('../docs/screenshots');
  fs.mkdirSync(folder, { recursive: true });
  await page.screenshot({ path: path.join(folder, `${testInfo.project.name}-overview.png`), fullPage: true, scale: 'css' });

  await page.getByRole('textbox', { name: 'Search trends' }).fill('smart glasses');
  await expect(page.locator('.trend-table tbody tr')).toHaveCount(1);
  await page.locator('.trend-table .entity-link').click();
  await expect(page.getByRole('heading', { level: 1, name: 'AI smart glasses' })).toBeVisible();
  await page.getByRole('button', { name: 'Forecasts', exact: true }).click();
  await expect(page.locator('.forecast-card')).toHaveCount(3);
  await expect(page.getByText('Pending outcome').first()).toBeVisible();
  await page.getByRole('button', { name: 'Analogues', exact: true }).click();
  expect(await page.locator('tbody tr').count()).toBeGreaterThan(2);
  await page.getByRole('button', { name: 'Sources & evidence', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Raw evidence desk' })).toBeVisible();
  await expect(page.getByText('SYNTHETIC', { exact: true }).first()).toBeVisible();
  const save = page.getByRole('button', { name: 'Add to watchlist', exact: true });
  if (await save.count()) await save.click();
  await expect(page.getByRole('button', { name: 'Saved', exact: true })).toBeVisible();
  await page.goto('/#watchlist');
  await expect(page.locator('.trend-table').getByText('AI smart glasses', { exact: true })).toBeVisible();

  await page.goto('/#providers');
  await expect(page.getByRole('heading', { name: 'Alpha Vantage', exact: true })).toBeVisible();
  await expect(page.getByText('NOT CONFIGURED', { exact: true }).first()).toBeVisible();
  await page.goto('/#compare');
  await page.getByRole('button', { name: 'Explore correlation' }).click();
  await expect(page.getByText('Best-lag correlation')).toBeVisible();
  await page.goto('/#research');
  await page.getByRole('button', { name: 'Run experiment' }).click();
  await expect(page.getByRole('heading', { name: 'Experiment results' })).toBeVisible();
  expect(await page.locator('.reliability-chart circle').count()).toBeGreaterThan(0);
  await page.goto('/#reports');
  await expect(page.locator('.report-row').first()).toBeVisible();
  const download = page.waitForEvent('download');
  await page.locator('.report-row').first().getByRole('button', { name: 'JSON' }).click();
  expect((await download).suggestedFilename()).toMatch(/\.json$/);
  expect(errors).toEqual([]);
});

test('navigation, connection dialog and accessible keyboard focus', async ({ page }, testInfo) => {
  await page.goto('/');
  await expect(page.locator('.trend-table')).toBeVisible();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('main')).toBeFocused();
  if (testInfo.project.name === 'android') {
    await page.getByRole('button', { name: 'Open navigation', exact: true }).click();
    await page.getByRole('link', { name: 'Trend radar', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'A different view of momentum.' })).toBeVisible();
  }
  await page.getByRole('button', { name: 'Connection settings', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button', { name: 'Close settings', exact: true }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
});
