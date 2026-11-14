import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, errText } from "../../lib/api/client";
import { ErrorState, Loading } from "../../components/States";

type Card = { job_id: string; title: string; price: number; price_unit: string; variant: string; category: string };
const COLS = ["drafted", "submitted", "viewed", "replied", "interview", "hired", "lost"];

export default function Pipeline() {
  const [data, setData] = useState<Record<string, Card[]> | null>(null);
  const [err, setErr] = useState("");
  const load = useCallback(async () => {
    const { data, error } = await api.GET("/api/pipeline");
    if (error) setErr(errText(error)); else { setErr(""); setData(data as Record<string, Card[]>); }
  }, []);
  useEffect(() => { load(); const t = setInterval(load, 10000); return () => clearInterval(t); }, [load]);
  if (err) return <ErrorState error={err} retry={load} />;
  if (!data) return <Loading label="Loading pipeline" />;
  return (
    <>
      <h1>Pipeline</h1>
      <p className="muted small">Cards move as marketplace events arrive (viewed, replied, interview, hired, lost).</p>
      <div className="kanban" data-testid="kanban">
        {COLS.map((c) => (
          <section key={c} className="kcol" aria-label={c}>
            <strong style={{ textTransform: "capitalize" }}>{c}</strong> <span className="small muted">{data[c]?.length ?? 0}</span>
            {(data[c] ?? []).map((k) => (
              <div key={k.job_id} className="kcard"><Link to={`/jobs/${k.job_id}`}>{k.title}</Link>
                <div className="small muted">${k.price}{k.price_unit === "hourly" ? "/h" : ""} · arm {k.variant ?? "-"}</div></div>
            ))}
          </section>
        ))}
      </div>
    </>
  );
}
