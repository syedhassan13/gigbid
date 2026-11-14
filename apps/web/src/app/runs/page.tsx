import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, errText } from "../../lib/api/client";
import { Empty, ErrorState, Loading } from "../../components/States";

type Run = { thread_id: string; kind: string; status: string; job_id: string; updated: number; usage?: { elapsed_s?: number; tokens?: number; cost_usd?: number } };

export default function Runs() {
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => { api.GET("/api/runs").then(({ data, error }) => (error ? setErr(errText(error)) : setRuns(data as Run[]))); }, []);
  if (err) return <ErrorState error={err} />;
  if (!runs) return <Loading label="Loading runs" />;
  if (!runs.length) return <Empty title="No agent runs yet" />;
  return (
    <>
      <h1>Agent runs</h1>
      <div className="panel" style={{ overflowX: "auto" }}>
        <table><thead><tr><th>Thread</th><th>Graph</th><th>Status</th><th>Latency</th><th>Tokens</th><th>Cost</th></tr></thead>
          <tbody>{runs.map((r) => (
            <tr key={r.thread_id}><td><Link to={`/runs/${encodeURIComponent(r.thread_id)}`}>{r.thread_id.split(":").slice(2).join(":")}</Link></td><td>{r.kind}</td>
              <td><span className="chip">{r.status}</span></td><td>{r.usage?.elapsed_s ?? "–"}s</td><td>{r.usage?.tokens ?? "–"}</td><td>${r.usage?.cost_usd ?? 0}</td></tr>))}
          </tbody></table>
      </div>
    </>
  );
}
