import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, errText, type Schemas } from "../../../lib/api/client";
import { ActionBadge, ErrorState, Loading, RiskBadge } from "../../../components/States";
import RunTimeline from "../../../components/RunTimeline";

type Match = { requirement: string; evidence_ids: string[]; best_score: number; covered: boolean; note: string };

export default function JobDetail() {
  const { id = "" } = useParams();
  const [d, setD] = useState<Schemas["JobDetail"] | null>(null);
  const [err, setErr] = useState("");
  const [running, setRunning] = useState<string | null>(null);
  const load = useCallback(async () => {
    const { data, error } = await api.GET("/api/jobs/{job_id}", { params: { path: { job_id: id } } });
    if (error) setErr(errText(error)); else { setErr(""); setD(data); }
  }, [id]);
  useEffect(() => { load(); }, [load]);
  async function analyse(force = false) {
    const { data } = await api.POST("/api/jobs/{job_id}/analyse", { params: { path: { job_id: id }, query: { force_bid: force } } });
    if (data) setRunning(data.thread_id);
  }
  if (err) return <ErrorState error={err} retry={load} />;
  if (!d) return <Loading label="Loading job" />;
  const spec = (d.analyses?.job_spec ?? {}) as Record<string, unknown>;
  const risk = (d.analyses?.risk ?? null) as { risk_score: number; is_scam: boolean; client_score: number; flags: { code: string; evidence: string }[]; summary: string } | null;
  const fit = (d.analyses?.fit ?? null) as { fit_score: number; matches: Match[]; reasons: string[] } | null;
  const price = d.price as { amount?: number; unit?: string; rationale?: string[] };
  const decision = d.decision as { action?: string; reasons?: string[] };
  return (
    <>
      <p><Link to="/inbox">← Inbox</Link></p>
      <h1>{String(d.job.title ?? id)}</h1>
      <div className="row" style={{ marginBottom: 12 }}>
        <ActionBadge action={decision?.action} /> <RiskBadge risk={risk?.risk_score} scam={risk?.is_scam} />
        <span className="chip">{d.status ?? "not analysed"}</span>
        {!d.analyses?.fit && <button className="btn primary" onClick={() => analyse(false)}>Analyse now</button>}
        {decision?.action === "skip" && !risk?.is_scam && <button className="btn" onClick={() => analyse(true)}>Bid anyway</button>}
        {d.interrupt && <Link className="btn primary" to={`/studio/${id}`}>Open proposal studio</Link>}
        {d.thread_id && <Link className="btn" to={`/runs/${encodeURIComponent(d.thread_id)}`}>Agent run</Link>}
      </div>
      {d.error && <div className="banner warn">{d.error}</div>}
      {running && <div className="panel"><RunTimeline threadId={running} onDone={() => { setRunning(null); load(); }} /></div>}
      <div className="grid2">
        <section className="panel">
          <h2>Job post <span className="small muted">(untrusted client text)</span></h2>
          <pre style={{ whiteSpace: "pre-wrap", fontFamily: "inherit", fontSize: 14 }}>{String(d.job.description ?? "")}</pre>
          <p className="small muted">{String(d.job.budget_type)} · ${String(d.job.budget_min)}–${String(d.job.budget_max)} · {String(d.job.connects_cost)} Connects</p>
        </section>
        <section className="panel">
          <h2>JobSpec</h2>
          {spec.requirements ? (
            <>
              <div className="small"><b>Requirements:</b> {(spec.requirements as string[]).map((r) => <span key={r} className="chip" style={{ margin: 2 }}>{r}</span>)}</div>
              <div className="small"><b>Deliverables:</b> {(spec.deliverables as string[] | undefined)?.join("; ") || "–"}</div>
              <div className="small"><b>Hidden needs:</b> {(spec.hidden_needs as string[] | undefined)?.join("; ") || "–"}</div>
              <div className="small"><b>Screening:</b> {(spec.screening_questions as string[] | undefined)?.join(" / ") || "–"}</div>
            </>
          ) : <p className="muted small">Not analysed yet.</p>}
          <h2>Risk report</h2>
          {risk ? (<><p className="small">Client score {risk.client_score.toFixed(2)} · {risk.summary}</p>
            <ul className="small">{risk.flags.map((f, i) => <li key={i}><b>{f.code}</b>: {f.evidence}</li>)}</ul></>) : <p className="muted small">–</p>}
        </section>
      </div>
      <section className="panel" style={{ marginTop: 14 }}>
        <h2>Requirement → evidence matrix {fit && <span className="chip">fit {fit.fit_score.toFixed(2)}</span>}</h2>
        {fit ? (
          <table data-testid="evidence-matrix"><thead><tr><th>Requirement</th><th>Portfolio items that prove it</th><th>Support</th></tr></thead>
            <tbody>{fit.matches.map((m) => (
              <tr key={m.requirement}><td>{m.requirement}</td>
                <td>{m.covered ? m.evidence_ids.map((e) => <span key={e} className="chip" style={{ margin: 2 }}>{e}</span>) : <span className="badge bad">no evidence — will not be claimed</span>}</td>
                <td>{m.best_score.toFixed(2)}</td></tr>))}</tbody></table>
        ) : <p className="muted small">–</p>}
      </section>
      <div className="grid2" style={{ marginTop: 14 }}>
        <section className="panel"><h2>Price rationale</h2>
          {price?.amount ? <><p><b>${price.amount}{price.unit === "hourly" ? "/h" : " fixed"}</b></p><ul className="small">{price.rationale?.map((r, i) => <li key={i}>{r}</li>)}</ul></> : <p className="muted small">Priced only for jobs worth bidding on.</p>}
        </section>
        <section className="panel"><h2>Bid-or-skip reasoning</h2>
          <ul className="small">{decision?.reasons?.map((r, i) => <li key={i}>{r}</li>) ?? <li>–</li>}</ul>
        </section>
      </div>
    </>
  );
}
