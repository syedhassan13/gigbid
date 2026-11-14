import { useCallback, useEffect, useState } from "react";
import { api, errText, getToken } from "../../lib/api/client";
import { ErrorState, Loading } from "../../components/States";

type S = { autonomy?: string; rate_floor?: number; target_rate?: number; weekly_connects_budget?: number; saved_searches?: string[];
  persona?: string; connected?: { gigsim: boolean; upwork: boolean }; llm_profile?: string; rag_variant?: string };
type Mem = { key: string; pattern?: string; rule?: string; promoted_by?: string; count?: number; category?: string; arm?: string; reply_rate?: number; n?: number };

export default function Settings() {
  const [s, setS] = useState<S | null>(null);
  const [mem, setMem] = useState<{ style: Mem[]; style_candidates: Mem[]; outcome: Mem[] } | null>(null);
  const [err, setErr] = useState("");
  const [saved, setSaved] = useState("");
  const load = useCallback(async () => {
    const a = await api.GET("/api/settings");
    const b = await api.GET("/api/settings/memory");
    if (!a.data) setErr("Could not load settings"); else setS(a.data as S);
    if (b.data) setMem(b.data as typeof mem);
  }, []);
  useEffect(() => { load(); }, [load]);
  async function save() {
    const { error } = await api.PUT("/api/settings", { body: { autonomy: s?.autonomy as "suggest" | "auto_skip_low_fit", rate_floor: s?.rate_floor, target_rate: s?.target_rate,
      weekly_connects_budget: s?.weekly_connects_budget, saved_searches: s?.saved_searches } });
    setSaved(error ? errText(error) : "Saved");
  }
  async function del(ns: string, key: string) {
    await api.DELETE("/api/settings/memory/{namespace}/{key}", { params: { path: { namespace: ns, key } } });
    load();
  }
  async function upload(f: File) {
    const fd = new FormData(); fd.append("file", f);
    const r = await fetch("/api/settings/portfolio", { method: "POST", body: fd, headers: { Authorization: `Bearer ${getToken()}` } });
    setSaved(r.ok ? `Uploaded ${f.name}; portfolio re-indexed` : `Upload failed (${r.status})`);
  }
  if (err) return <ErrorState error={err} retry={load} />;
  if (!s) return <Loading label="Loading settings" />;
  return (
    <>
      <h1>Settings</h1>
      <div className="grid2">
        <section className="panel"><h2>Autonomy & budgets</h2>
          <label htmlFor="auto">Autonomy level</label>
          <select id="auto" value={s.autonomy ?? "suggest"} onChange={(e) => setS({ ...s, autonomy: e.target.value })}>
            <option value="suggest">Suggest only (I confirm every skip)</option>
            <option value="auto_skip_low_fit">Auto-skip low-fit jobs (never auto-send)</option>
          </select>
          <div className="grid2">
            <div><label htmlFor="f">Rate floor</label><input id="f" type="number" value={s.rate_floor ?? 0} onChange={(e) => setS({ ...s, rate_floor: +e.target.value })} /></div>
            <div><label htmlFor="t">Target rate</label><input id="t" type="number" value={s.target_rate ?? 0} onChange={(e) => setS({ ...s, target_rate: +e.target.value })} /></div>
          </div>
          <label htmlFor="b">Weekly Connects budget</label><input id="b" type="number" value={s.weekly_connects_budget ?? 0} onChange={(e) => setS({ ...s, weekly_connects_budget: +e.target.value })} />
          <label htmlFor="ss">Saved searches</label><input id="ss" value={(s.saved_searches ?? []).join(", ")} onChange={(e) => setS({ ...s, saved_searches: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} />
          <div className="row" style={{ marginTop: 12 }}><button className="btn primary" onClick={save}>Save</button><span className="small muted" role="status">{saved}</span></div>
        </section>
        <section className="panel"><h2>Connected accounts</h2>
          <p className="small">GigSim: {s.connected?.gigsim ? <span className="badge ok">connected ({s.persona})</span> : <span className="badge">not connected</span>}</p>
          <p className="small">Upwork (official MCP, OAuth 2.1): {s.connected?.upwork ? <span className="badge ok">connected</span> : <button className="btn" onClick={async () => { const { data } = await api.GET("/api/auth/upwork/start"); const u = (data as { authorize_url?: string })?.authorize_url; if (u) window.location.href = u; }}>Connect Upwork</button>}</p>
          <p className="small muted">Model profile: {s.llm_profile} · RAG: {s.rag_variant}</p>
          <h2>Portfolio</h2>
          <input type="file" accept=".md,.pdf,.txt" aria-label="Add portfolio item" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
        </section>
      </div>
      <section className="panel" style={{ marginTop: 14 }} data-testid="memory-viewer"><h2>What GigBid has learned</h2>
        <p className="small muted">Only patterns that pass a promotion rule become memory. Delete anything you disagree with.</p>
        <h2 className="small">Style memory</h2>
        {mem?.style.length ? <ul className="small">{mem.style.map((m) => <li key={m.key}>{m.rule} <span className="muted">({m.promoted_by})</span> <button className="btn danger" onClick={() => del("style", m.key)}>Delete</button></li>)}</ul> : <p className="small muted">Nothing promoted yet.</p>}
        <h2 className="small">Candidates (not used until promoted)</h2>
        {mem?.style_candidates.length ? <ul className="small">{mem.style_candidates.map((m) => <li key={m.key}>{m.pattern} — seen {m.count}× <button className="btn" onClick={() => del("style_candidates", m.key)}>Delete</button></li>)}</ul> : <p className="small muted">None.</p>}
        <h2 className="small">Outcome memory</h2>
        {mem?.outcome.length ? <ul className="small">{mem.outcome.map((m) => <li key={m.key}>{m.category} / arm {m.arm}: reply rate {m.reply_rate} (n={m.n}) <button className="btn danger" onClick={() => del("outcome", m.key)}>Delete</button></li>)}</ul> : <p className="small muted">Not enough resolved proposals yet.</p>}
      </section>
    </>
  );
}
