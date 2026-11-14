export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" aria-live="polite">
      <span className="muted small">{label}…</span>
      <div className="skeleton" /><div className="skeleton" style={{ width: "70%" }} /><div className="skeleton" style={{ width: "40%" }} />
    </div>
  );
}

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return <div className="panel"><strong>{title}</strong>{hint && <p className="muted small">{hint}</p>}</div>;
}

export function ErrorState({ error, retry }: { error: string; retry?: () => void }) {
  return (
    <div className="banner bad" role="alert">
      {error} {retry && <button className="btn" onClick={retry}>Retry</button>}
    </div>
  );
}

export function RiskBadge({ risk, scam }: { risk?: number | null; scam?: number | boolean | null }) {
  if (scam) return <span className="badge bad">scam</span>;
  if (risk == null) return <span className="badge">-</span>;
  return <span className={`badge ${risk >= 0.6 ? "bad" : risk >= 0.35 ? "warn" : "ok"}`}>risk {risk.toFixed(2)}</span>;
}

export function ActionBadge({ action }: { action?: string | null }) {
  if (!action) return <span className="badge">pending</span>;
  return <span className={`badge ${action === "bid" ? "ok" : action === "watch" ? "warn" : "bad"}`}>{action}</span>;
}
