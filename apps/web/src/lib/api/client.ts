// Typed client generated from FastAPI's OpenAPI schema (src/lib/api/schema.d.ts - do not hand-edit;
// regenerate with `npm run gen:api`). This file only adds auth + trace-id middleware.
import createClient, { type Middleware } from "openapi-fetch";
import type { paths, components } from "./schema";

export type Schemas = components["schemas"];

const TOKEN_KEY = "gigbid.token";
export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setToken(t: string | null) {
  try { if (t) localStorage.setItem(TOKEN_KEY, t); else localStorage.removeItem(TOKEN_KEY); } catch { /* storage blocked */ }
}

const auth: Middleware = {
  async onRequest({ request }) {
    const t = getToken();
    if (t) request.headers.set("Authorization", `Bearer ${t}`);
    request.headers.set("X-Trace-Id", crypto.randomUUID().replace(/-/g, ""));
    return request;
  },
};

export const api = createClient<paths>({ baseUrl: "" });
api.use(auth);

export function errText(e: unknown): string {
  if (!e) return "";
  if (typeof e === "string") return e;
  const d = (e as { detail?: unknown }).detail;
  if (typeof d === "string") return d;
  return JSON.stringify(d ?? e);
}
