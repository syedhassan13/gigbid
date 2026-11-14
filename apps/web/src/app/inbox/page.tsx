import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, errText, type Schemas } from "../../lib/api/client";
import { ActionBadge, Empty, ErrorState, Loading, RiskBadge } from "../../components/States";

export default function Inbox() {
  const [rows, setRows] = useState<Schemas["InboxItem"][] | null>(null);
  const [filter, setFilter] = useState("all");
  const [err, setErr] = useState("");
  const load = useCallback(async () => {
    const { data, error } = await api.GET("/api/jobs", { params: { query: { filter } } });
    if (error) setErr(errText(error)); else { setErr(""); setRows(data); }
  }, [filter]);
  useEffect(() => { load(); const t = setInterval(load, 8000); return () => clearInterval(t); }, [load]);

  return (
    <>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h1>Job inbox</h1>
        <div className="row">
          <label htmlFor="filter" className="small" style={{ margin: 0 }}>Show</label>
          <select id="filter" value={filter} onChange={(e) => setFilter(e.target.value)} style={{ width: "auto" }}>
            <option value="all">All</option><option value="bid">Recommended: bid</option><option value="skip">Recommended: skip</option><option value="open">Open</option>
          </select>
          <button className="btn primary" onClick={async () => { await api.POST("/api/jobs/scout"); load(); }}>Scout now</button>
        </div>
      </div>
      {err && <ErrorState error={err} retry={load} />}
      {!rows && !err && <Loading label="Loading jobs" />}
      {rows && rows.length === 0 && <Empty title="No jobs yet" hint="Scouting runs on a schedule from your saved searches. Click “Scout now” to run it immediately." />}
      {rows && rows.length > 0 && (
        <div className="panel" style={{ overflowX: "auto" }}>
          <table data-testid="inbox-table">
            <thead><tr><th>Job</th><th>Fit</th><th>Risk</th><th>Action</th><th className="hide-sm">Price</th><th className="hide-sm">Connects</th><th>Status</th><th /></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.job_id}>
                  <td><Link to={`/jobs/${r.job_id}`}>{r.title ?? r.job_id}</Link><div className="small muted">{r.category} · {r.posted_at?.slice(0, 16).replace("T", " ")}</div></td>
                  <td>{r.fit != null ? <><div className="bar" style={{ width: `${Math.round(r.fit * 60)}px` }} /><span className="small">{r.fit.toFixed(2)}</span></> : "–"}</td>
                  <td><RiskBadge risk={r.risk} scam={r.is_scam} /></td>
                  <td><ActionBadge action={r.action} /></td>
                  <td className="hide-sm">{r.price != null ? `$${r.price}${r.price_unit === "hourly" ? "/h" : ""}` : "–"}</td>
                  <td className="hide-sm">{r.connects ?? "–"}</td>
                  <td><span className="chip">{r.status ?? "new"}</span></td>
                  <td className="row">
                    {r.status === "awaiting_approval" && <Link className="btn primary" to={`/studio/${r.job_id}`}>Review</Link>}
                    {(!r.status || r.status === "queued") && <button className="btn" onClick={async () => { await api.POST("/api/jobs/{job_id}/analyse", { params: { path: { job_id: r.job_id }, query: { force_bid: false } } }); load(); }}>Analyse</button>}
                    {r.action === "skip" && !r.is_scam && <button className="btn" title="Bid anyway" onClick={async () => { await api.POST("/api/jobs/{job_id}/analyse", { params: { path: { job_id: r.job_id }, query: { force_bid: true } } }); load(); }}>Bid anyway</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
