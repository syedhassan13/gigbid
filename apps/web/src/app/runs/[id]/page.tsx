import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, errText } from "../../../lib/api/client";
import { ErrorState, Loading } from "../../../components/States";
import RunTimeline from "../../../components/RunTimeline";

type Detail = { status: string; next: string[]; trace: Record<string, unknown>[]; steps: number; tokens: number; cost_usd: number; run?: { trace_id?: string } };

export default function RunViewer() {
  const { id = "" } = useParams();
  const [d, setD] = useState<Detail | null>(null);
  const [hist, setHist] = useState<{ checkpoint_id: string; next: string[]; status: string; step: number }[]>([]);
  const [err, setErr] = useState("");
  const [showTrace, setShowTrace] = useState(false);
  useEffect(() => {
    api.GET("/api/runs/{thread_id}", { params: { path: { thread_id: id } } }).then(({ data, error }) => (error ? setErr(errText(error)) : setD(data as Detail)));
    api.GET("/api/runs/{thread_id}/history", { params: { path: { thread_id: id } } }).then(({ data }) => setHist((data as typeof hist) ?? []));
  }, [id]);
  if (err) return <ErrorState error={err} />;
  if (!d) return <Loading label="Loading run" />;
  const langsmith = import.meta.env.VITE_LANGSMITH_PROJECT_URL as string | undefined;
  return (
    <>
      <p><Link to="/runs">← Runs</Link></p>
      <h1>Agent run</h1>
      <p className="small muted">{id} · status <span className="chip">{d.status}</span> · {d.steps} steps · {d.tokens} tokens · ${d.cost_usd?.toFixed?.(5) ?? 0}
        {d.run?.trace_id && <> · trace <code>{d.run.trace_id}</code></>}</p>
      <div className="row" style={{ marginBottom: 10 }}>
        <button className="btn" onClick={() => setShowTrace((s) => !s)}>{showTrace ? "Hide" : "Show"} full trace</button>
        {langsmith && d.run?.trace_id && <a className="btn" href={`${langsmith}?searchModel=${d.run.trace_id}`} target="_blank" rel="noreferrer">Open in LangSmith</a>}
      </div>
      <div className="grid2">
        <section className="panel"><h2>Live progress</h2><RunTimeline threadId={id} /></section>
        <section className="panel"><h2>Checkpoints (replay from any node)</h2>
          <ol className="small">{hist.map((h) => <li key={h.checkpoint_id}>step {h.step} → next: {h.next.join(", ") || "end"} <span className="chip">{h.status}</span></li>)}</ol>
        </section>
      </div>
      {showTrace && <section className="panel" style={{ marginTop: 14 }}><h2>Execution trace (PII-masked)</h2>
        <pre style={{ whiteSpace: "pre-wrap", fontSize: 12 }} data-testid="full-trace">{JSON.stringify(d.trace, null, 1)}</pre></section>}
    </>
  );
}
