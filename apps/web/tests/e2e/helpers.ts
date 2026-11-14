import { expect, type APIRequestContext, type Page } from "@playwright/test";

export const EMAIL = process.env.E2E_EMAIL ?? "reviewer@gigbid.local";
export const PASSWORD = process.env.E2E_PASSWORD ?? "change-me-locally";

export async function apiLogin(request: APIRequestContext, email = EMAIL, password = PASSWORD): Promise<string> {
  const r = await request.post("/api/auth/login", { data: { email, password } });
  expect(r.ok()).toBeTruthy();
  return (await r.json()).token as string;
}

export async function uiLogin(page: Page, email = EMAIL, password = PASSWORD) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

/** Picks a dev job the persona should bid on and runs the bid graph until it waits for approval. */
export async function jobAwaitingApproval(request: APIRequestContext, token: string, index: number): Promise<string> {
  const jobs = await request.get("/api/jobs", { headers: { Authorization: `Bearer ${token}` } });
  const existing = ((await jobs.json()) as { job_id: string; status: string }[]).filter((j) => j.status === "awaiting_approval");
  if (existing[index]) return existing[index].job_id;
  const ids = ["j-752c9eec85", "j-d2965d6610", "j-6804854958"];
  const jobId = process.env[`E2E_JOB_${index}`] ?? ids[index];
  await request.post(`/api/jobs/${jobId}/analyse?force_bid=true`, { headers: { Authorization: `Bearer ${token}` } });
  for (let i = 0; i < 90; i++) {
    const d = await (await request.get(`/api/jobs/${jobId}`, { headers: { Authorization: `Bearer ${token}` } })).json();
    if (d.status === "awaiting_approval") return jobId;
    await new Promise((r) => setTimeout(r, 2000));
  }
  throw new Error(`job ${jobId} never reached approval`);
}
