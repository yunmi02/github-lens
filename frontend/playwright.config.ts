import { defineConfig } from "@playwright/test";
import path from "node:path";
export default defineConfig({
  testDir: "./e2e",
  timeout: 30000,
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:8011",
    headless: true,
    channel: "chrome",
    viewport: { width: 1440, height: 1000 },
  },
  webServer: {
    command:
      "..\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --app-dir ../backend --host 127.0.0.1 --port 8011 --workers 1",
    url: "http://127.0.0.1:8011/api/health",
    reuseExistingServer: false,
    env: {
      DATABASE_URL:
        "sqlite:///" + path.resolve("../data/e2e.db").replaceAll("\\", "/"),
      DATA_DIR: path.resolve("../data/e2e"),
      ADMIN_PASSWORD: "e2e-test-password-123",
      AI_API_KEY: "",
      SCHEDULE_ENABLED: "false",
      AGENT_AUTO_RESEARCH: "false",
      RESEARCH_BACKEND: "computer_use",
      OCR_PROVIDER: process.env.REAL_NETWORK ? "paddle" : "disabled",
      NO_PROXY: "*",
    },
  },
  reporter: "list",
});
