import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, errText, getToken } from "../../lib/api/client";

const PERSONAS = [
  { id: "ai_ml", label: "AI/ML engineer (synthetic persona: Nadia Qureshi)", floor: 45, target: 65 },
  { id: "fullstack", label: "Full-stack web developer (synthetic persona: Bilal Siddiqui)", floor: 35, target: 50 },
  { id: "data_analyst", label: "Data analyst (synthetic persona: Sana Malik)", floor: 25, target: 40 },
] as const;

export default function Onboarding() {
  const nav = useNavigate();
  const [persona, setPersona] = useState<(typeof PERSONAS)[number]["id"]>("ai_ml");
  const [marketplace, setMarketplace] = useState<"gigsim" | "upwork_live">("gigsim");
  const [floor, setFloor] = useState(45);
  const [target, setTarget] = useState(65);
  const [budget, setBudget] = useState(120);
  const [searches, setSearches] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function finish(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setErr("");
    const { error } = await api.POST("/api/auth/onboarding", { body: {
      persona, marketplace, rate_floor: floor, target_rate: target, weekly_connects_budget: budget,
      saved_searches: searches.split(",").map((s) => s.trim()).filter(Boolean), categories: [] } });
    if (error) { setBusy(false); return setErr(errText(error)); }
    if (file) {
      const fd = new FormData(); fd.append("file", file);
      await fetch("/api/settings/portfolio", { method: "POST", body: fd, headers: { Authorization: `Bearer ${getToken()}` } });
    }
    if (marketplace === "upwork_live") {
      const { data } = await api.GET("/api/auth/upwork/start");
      const url = (data as { authorize_url?: string } | undefined)?.authorize_url;
      if (url) { window.location.href = url; return; }
    }
    await api.POST("/api/jobs/scout");
    nav("/inbox");
  }
  return (
    <main style={{ maxWidth: 640, margin: "6vh auto", padding: 16 }}>
      <form className="panel" onSubmit={finish}>
        <h1>Set up GigBid</h1>
        <fieldset style={{ border: 0, padding: 0 }}>
          <legend className="muted small">1. Choose a persona (or upload your own work below)</legend>
          {PERSONAS.map((p) => (
            <label key={p.id} style={{ display: "flex", gap: 8, alignItems: "center", color: "inherit" }}>
              <input type="radio" name="persona" style={{ width: "auto" }} checked={persona === p.id}
                onChange={() => { setPersona(p.id); setFloor(p.floor); setTarget(p.target); }} /> {p.label}
            </label>
          ))}
        </fieldset>
        <label htmlFor="mp">2. Connect a marketplace</label>
        <select id="mp" value={marketplace} onChange={(e) => setMarketplace(e.target.value as "gigsim" | "upwork_live")}>
          <option value="gigsim">GigSim (simulator — safe, graded)</option>
          <option value="upwork_live">Upwork (official MCP server, OAuth — drafts only)</option>
        </select>
        <label htmlFor="pf">3. Upload portfolio (optional: .md case study or .pdf CV)</label>
        <input id="pf" type="file" accept=".md,.pdf,.txt" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <div className="grid2">
          <div><label htmlFor="floor">Rate floor ($/h)</label><input id="floor" type="number" min={1} value={floor} onChange={(e) => setFloor(+e.target.value)} /></div>
          <div><label htmlFor="target">Target rate ($/h)</label><input id="target" type="number" min={1} value={target} onChange={(e) => setTarget(+e.target.value)} /></div>
        </div>
        <label htmlFor="budget">Weekly Connects budget</label>
        <input id="budget" type="number" min={0} value={budget} onChange={(e) => setBudget(+e.target.value)} />
        <label htmlFor="ss">Saved searches (comma-separated; blank = persona defaults)</label>
        <input id="ss" value={searches} onChange={(e) => setSearches(e.target.value)} placeholder="LLM, RAG, forecasting" />
        {err && <div className="banner bad" role="alert" style={{ marginTop: 10 }}>{err}</div>}
        <button className="btn primary" style={{ marginTop: 16 }} disabled={busy} type="submit" data-testid="finish-onboarding">
          {busy ? "Setting up…" : "Finish and scout jobs"}
        </button>
      </form>
    </main>
  );
}
