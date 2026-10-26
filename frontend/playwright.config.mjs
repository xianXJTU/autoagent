import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 90_000,
  use: {
    baseURL: "http://127.0.0.1:8020",
    trace: "retain-on-failure"
  },
  webServer: {
    command:
      ".venv\\Scripts\\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8020",
    cwd: "..",
    url: "http://127.0.0.1:8020/api/health",
    reuseExistingServer: false,
    timeout: 90_000
  }
});
