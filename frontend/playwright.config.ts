import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  timeout: 30000,
  fullyParallel: true,
  reporter: "list",
  use: {
    baseURL: process.env["UI_BASE_URL"] || "http://127.0.0.1:4200",
    viewport: { width: 1440, height: 1000 },
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
