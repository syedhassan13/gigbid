import { useEffect, useState } from "react";
import { api, errText } from "../../lib/api/client";
import { ErrorState, Loading } from "../../components/States";

type A = {
  funnel: Record<string, number>;
  by_category: { category: string; submitted: number; replied: number; hired: number; connects: number; reply_rate: number | null }[];
  by_arm: { arm: string; submitted: number; replied: number; reply_rate: number | null }[];
  connects: { spent: number; per_reply: number };
  latency_s: { p50: number | null; p95: number | null; n: number };
  cost_usd: { total: number; per_run_mean: number | null };
  top_rejection_reasons: [string, number][];
};

export default function Analytics() {
  const [a, setA] = useState<A | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => { api.GET("/api/analytics").then(({ data, error }) => (error ? setErr(errText(error)) : setA(data as A))); }, []);
  if (err) return <ErrorState error={err} />;
  if (!a) return <Loading label="Loading analytics" />;
  const max = Math.max(1, ...Object.values(a.funnel));
  return (
    <>
      <h1>Analytics</h1>
      <div className="grid2">
        <section className="panel"><h2>Funnel</h2>
          {Object.entries(a.funnel).map(([k, v]) => (
            <div key={k} className="row small" style={{ margin: "4px 0" }}><span style={{ width: 130 }}>{k.replace("_", " ")}</span><div className="bar" style={{ width: `${(v / max) * 200}px` }} /><b>{v}</b></div>))}
        </section>
        <section className="panel"><h2>Cost & latency per proposal run</h2>
          <p className="small">p50 {a.latency_s.p50 ?? "–"}s · p95 {a.latency_s.p95 ?? "–"}s (n={a.latency_s.n})</p>
          <p className="small">LLM cost total ${a.cost_usd.total} · mean per run ${a.cost_usd.per_run_mean ?? 0}</p>
          <p className="small">Connects spent {a.connects.spent} · {a.connects.per_reply} per reply</p>
        </section>
      </div>
      <section className="panel" style={{ marginTop: 14 }}><h2>Reply and hire rate by category</h2>
        <table><thead><tr><th>Category</th><th>Submitted</th><th>Replied</th><th>Hired</th><th>Reply rate</th><th>Connects</th></tr></thead>
          <tbody>{a.by_category.map((c) => <tr key={c.category}><td>{c.category}</td><td>{c.submitted}</td><td>{c.replied}</td><td>{c.hired}</td><td>{c.reply_rate ?? "–"}</td><td>{c.connects}</td></tr>)}</tbody></table>
      </section>
      <div className="grid2" style={{ marginTop: 14 }}>
        <section className="panel"><h2>X2 experiment arms</h2>
          <table><thead><tr><th>Arm</th><th>Submitted</th><th>Replied</th><th>Rate</th></tr></thead>
            <tbody>{a.by_arm.map((r) => <tr key={r.arm}><td>{r.arm === "A" ? "A · evidence-first" : r.arm === "B" ? "B · question-first" : r.arm}</td><td>{r.submitted}</td><td>{r.replied}</td><td>{r.reply_rate ?? "–"}</td></tr>)}</tbody></table>
        </section>
        <section className="panel"><h2>Top rejection reasons</h2>
          {a.top_rejection_reasons.length ? <ol className="small">{a.top_rejection_reasons.map(([r, n]) => <li key={r}>{r} ({n})</li>)}</ol> : <p className="muted small">No rejections yet.</p>}
        </section>
      </div>
    </>
  );
}
