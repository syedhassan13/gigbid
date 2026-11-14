import { expect, test } from "@playwright/test";
import { apiLogin, jobAwaitingApproval, uiLogin } from "../e2e/helpers";

test.use({ video: { mode: "on", size: { width: 1280, height: 760 } }, viewport: { width: 1280, height: 760 } });
const pause = (ms: number) => new Promise((r) => setTimeout(r, ms));

test("demo: inbox -> evidence -> approve -> pipeline -> client reply", async ({ page, request }) => {
  test.setTimeout(600_000);
  const token = await apiLogin(request);
  const jobId = await jobAwaitingApproval(request, token, 0);
  await uiLogin(page);
  await pause(1500);
  await page.goto(`/jobs/${jobId}`);
  await expect(page.getByTestId("evidence-matrix")).toBeVisible();
  await pause(2500);
  await page.mouse.wheel(0, 500); await pause(1500);
  await page.goto(`/studio/${jobId}`);
  await expect(page.getByTestId("dry-run")).toBeVisible();
  const claim = page.getByTestId("claim").first();
  if (await claim.count()) { await claim.hover(); await pause(2500); }
  await page.mouse.wheel(0, 400); await pause(1200);
  await page.getByTestId("approve").click();
  await expect(page.getByTestId("run-timeline")).toContainText("submit", { timeout: 90_000 });
  await pause(2000);
  // advance simulator time so the client reacts, then let the worker sync the pipeline
  await request.post("http://127.0.0.1:8100/v1/admin/tick?minutes=720", { headers: { Authorization: "Bearer gs-ai-ml-dev-token" } });
  await page.goto("/pipeline"); await pause(3000);
  await page.goto("/messages"); await pause(70_000); await page.reload(); await pause(2000);
  const t = page.locator("section[aria-label=Threads] button").first();
  if (await t.count()) { await t.click(); await pause(4000); }
  await page.goto("/analytics"); await pause(2500);
  await page.goto("/settings"); await pause(2500);
});
