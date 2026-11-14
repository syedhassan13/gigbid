import { defineConfig } from "@playwright/test";
export default defineConfig({ testDir: "tests/demo", timeout: 600_000, reporter: "list",
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:8000" }, outputDir: "demo-results" });
