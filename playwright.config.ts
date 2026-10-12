import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  outputDir: './.runtime/playwright-results',
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:5173',
    browserName: 'chromium',
    headless: true,
  },
  webServer: {
    command: 'pnpm dev',
    url: 'http://127.0.0.1:5173/api/v1/bootstrap',
    timeout: 60_000,
    reuseExistingServer: false,
  },
});
