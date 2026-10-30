import { defineConfig } from '@playwright/test';
import path from 'path';

export default defineConfig({
  testDir: './e2e',
  timeout: 60000,
  expect: {
    timeout: 10000,
  },
  workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:8000',
    channel: 'chrome',
    headless: true,
    viewport: { width: 1280, height: 720 },
    ignoreHTTPSErrors: true,
  },
  webServer: {
    command: '.\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000',
    cwd: path.resolve('..'),
    url: 'http://127.0.0.1:8000/api/health',
    reuseExistingServer: true,
    timeout: 30000,
  },
});
