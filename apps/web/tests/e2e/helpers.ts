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
  await page.waitForURL(/\/(inbox|onboarding)/);
}

/** Picks a dev job the persona should bid on and runs the bid graph until it waits for approval. */
export async function jobAwaitingApproval(request: APIRequestContext, token: string, index: number): Promise<string> {
  const jobs = await request.get("/api/jobs", { headers: { Authorization: `Bearer ${token}` } });
  const all = (await jobs.json()) as { job_id: string; status: string }[];
  const existing = (all as { job_id: string; status: string }[]).filter((j) => j.status === "awaiting_approval");
  if (existing[0]) return existing[0].job_id;  // reuse anything already waiting
  const ids = ["j-2641e3f2c4", "j-752c9eec85", "j-d2965d6610", "j-6804854958", "j-5f1af3e2b0", "j-44c9ac8bb0", "j-c1a08b415f", "j-9ab811097f", "j-692ba70b85", "j-dcac937327", "j-4028705f48", "j-c858410286", "j-01ab4e2c81", "j-4bf788cdd3", "j-945b643d61", "j-eafcaaeb7f", "j-c364d875c6", "j-db3887cc6d", "j-f706477296", "j-9d5ac3c4fa", "j-bce820c2d7", "j-e05f927c9f", "j-6c29ce89ef", "j-5223bc8f20", "j-929165b666", "j-fb0eb25332", "j-7d38ef4f0d", "j-f7b7f1e12e", "j-f310306788", "j-bbf23a17a3"];
  const seen = new Set(all.map((j) => j.job_id));
  const jobId = process.env[`E2E_JOB_${index}`] ?? ids.find((i) => !seen.has(i))!;
  await request.post(`/api/jobs/${jobId}/analyse?force_bid=true`, { headers: { Authorization: `Bearer ${token}` } });
  for (let i = 0; i < 150; i++) {
    const d = await (await request.get(`/api/jobs/${jobId}`, { headers: { Authorization: `Bearer ${token}` } })).json();
    if (d.status === "awaiting_approval") return jobId;
    await new Promise((r) => setTimeout(r, 2000));
  }
  throw new Error(`job ${jobId} never reached approval`);
}
