import { expect, test } from "@playwright/test";
import { apiLogin, jobAwaitingApproval, uiLogin } from "./helpers";

test.describe.configure({ mode: "serial" });

test("onboarding: register, pick persona, connect GigSim, land in inbox", async ({ page }) => {
  const email = `e2e-${Date.now()}@gigbid.test`;
  await page.goto("/login");
  await page.getByRole("button", { name: /Register/ }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Set up GigBid" })).toBeVisible();
  await page.getByLabel(/Data analyst/).check();
  await page.getByTestId("finish-onboarding").click();
  await expect(page.getByRole("heading", { name: "Job inbox" })).toBeVisible();
});

test("approve a proposal: evidence on hover, dry-run cost, submitted", async ({ page, request }) => {
  const token = await apiLogin(request);
  const jobId = await jobAwaitingApproval(request, token, 0);
  await uiLogin(page);
  await page.goto(`/studio/${jobId}`);
  await expect(page.getByTestId("dry-run")).toContainText("Connects");
  const claim = page.getByTestId("claim").first();
  if (await claim.count()) { await claim.focus(); await expect(page.getByRole("tooltip")).toContainText("Evidence"); }
  await page.getByTestId("approve").click();
  await expect(page.getByTestId("run-timeline")).toContainText("submit", { timeout: 60_000 });
});

test("reject with a reason", async ({ page, request }) => {
  const token = await apiLogin(request);
  const jobId = await jobAwaitingApproval(request, token, 1);
  await uiLogin(page);
  await page.goto(`/studio/${jobId}`);
  await expect(page.getByTestId("reject")).toBeDisabled();
  await page.getByTestId("reject-reason").fill("Budget too low for the scope");
  await page.getByTestId("reject").click();
  await expect(page.getByTestId("run-timeline")).toContainText("rejected", { timeout: 60_000 });
});

test("edit a draft: edit is re-checked by compliance and comes back for approval", async ({ page, request }) => {
  const token = await apiLogin(request);
  const jobId = await jobAwaitingApproval(request, token, 2);
  await uiLogin(page);
  await page.goto(`/studio/${jobId}`);
  const editor = page.getByTestId("editor");
  await editor.fill((await editor.inputValue()) + " Email me at someone@example.com to speed things up.");
  await page.getByTestId("approve").click();
  await expect(page.getByTestId("run-timeline")).toContainText("compliance", { timeout: 60_000 });
  await page.goto(`/studio/${jobId}`);
  await expect(page.getByTestId("editor")).not.toHaveValue(/someone@example\.com/);
});

test("degraded mode banner when the marketplace is unavailable", async ({ page }) => {
  await page.route("**/api/health", (route) =>
    route.fulfill({ json: { api: "ok", marketplace: "down", mcp: { marketplace: "down", portfolio: "up", workspace: "up" }, llm_profile: "offline", llm_available: false, worker: "embedded" } }));
  await uiLogin(page);
  await expect(page.getByTestId("degraded-banner")).toContainText("Marketplace unavailable");
});
