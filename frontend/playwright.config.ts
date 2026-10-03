import { defineConfig, devices } from '@playwright/test';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  timeout: 45_000,
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
    launchOptions: process.env.TRENDFORGE_BROWSER ? { executablePath: process.env.TRENDFORGE_BROWSER, args: ['--no-sandbox', '--disable-dev-shm-usage'] } : {},
  },
  webServer: [
    { command: `${process.env.TRENDFORGE_PYTHON || 'python'} -m trendforge serve`, cwd: root, url: 'http://127.0.0.1:8000/api/system/health', reuseExistingServer: !process.env.CI, timeout: 40_000 },
    { command: 'npm run dev -- --port 5173', url: 'http://127.0.0.1:5173', reuseExistingServer: !process.env.CI, timeout: 40_000 },
  ],
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1512, height: 1080 } } },
    { name: 'android', use: { ...devices['Pixel 7'], viewport: { width: 412, height: 915 } } },
  ],
});
