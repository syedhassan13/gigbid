import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { api, setToken, type Schemas } from "../lib/api/client";

/** Degraded-mode banner: polls /api/health; shown when the marketplace MCP server or GigSim is down. */
export function DegradedBanner() {
  const [h, setH] = useState<Schemas["Health"] | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    const poll = async () => {
      const { data, error } = await api.GET("/api/health");
      if (!alive) return;
      setFailed(!!error); if (data) setH(data);
    };
    poll();
    const t = setInterval(poll, 15000);
    return () => { alive = false; clearInterval(t); };
  }, []);
  if (failed) return <div className="banner bad" role="alert" data-testid="degraded-banner">GigBid API unreachable — retrying.</div>;
  if (h && (h.marketplace === "down" || h.mcp.marketplace === "down"))
    return <div className="banner bad" role="alert" data-testid="degraded-banner">Marketplace unavailable — work is queued and will resume automatically. Nothing will be sent.</div>;
  if (h && !h.llm_available)
    return <div className="banner warn" role="status">LLM provider not configured (profile “{h.llm_profile}”): using deterministic fallbacks.</div>;
  return null;
}

const LINKS = [["/inbox", "Inbox"], ["/pipeline", "Pipeline"], ["/messages", "Messages"], ["/runs", "Agent runs"], ["/analytics", "Analytics"], ["/settings", "Settings"]];

export default function Layout() {
  const nav = useNavigate();
  return (
    <div className="shell">
      <nav className="side" aria-label="Main">
        <div className="brand">GigBid</div>
        {LINKS.map(([to, label]) => <NavLink key={to} to={to}>{label}</NavLink>)}
        <button className="btn hide-sm" style={{ marginTop: "auto" }} onClick={() => { setToken(null); nav("/login"); }}>Sign out</button>
      </nav>
      <main>
        <DegradedBanner />
        <Outlet />
      </main>
    </div>
  );
}
