import { useEffect, useRef, useState } from "react";
import { getToken } from "../lib/api/client";

type Ev = { id: number; type: string; node?: string; status?: string | null; trace?: Array<Record<string, unknown>>; usage?: Record<string, unknown>; payload?: unknown };

/** Live node-by-node progress streamed (SSE) from LangGraph's stream modes via the API. */
export default function RunTimeline({ threadId, onDone }: { threadId: string; onDone?: (status?: string | null) => void }) {
  const [events, setEvents] = useState<Ev[]>([]);
  const [state, setState] = useState<"connecting" | "live" | "done" | "error">("connecting");
  const doneRef = useRef(onDone);
  doneRef.current = onDone;
  useEffect(() => {
    setEvents([]);
    const es = new EventSource(`/api/runs/${encodeURIComponent(threadId)}/stream?token=${encodeURIComponent(getToken() ?? "")}`);
    const push = (e: MessageEvent) => {
      setState("live");
      const ev = JSON.parse(e.data) as Ev;
      setEvents((xs) => (xs.some((x) => x.id === ev.id) ? xs : [...xs, ev]));
      if (ev.type === "done") lastStatus = ev.status;
    };
    let lastStatus: string | null | undefined;
    ["update", "interrupt", "done"].forEach((t) => es.addEventListener(t, push as EventListener));
    // the server closes the stream only when the run is no longer running/resuming (replayed "done" events don't count)
    es.addEventListener("end", () => { es.close(); setState("done"); doneRef.current?.(lastStatus); });
    es.onerror = () => setState((s) => (s === "done" ? s : "error"));
    return () => es.close();
  }, [threadId]);
  return (
    <div>
      <p className="small muted" aria-live="polite">Stream: {state === "connecting" ? "connecting…" : state === "live" ? "running" : state === "done" ? "finished" : "reconnecting…"}</p>
      <ol className="timeline" data-testid="run-timeline">
        {events.map((e) => (
          <li key={e.id}>
            <strong>{e.type === "update" ? e.node : e.type}</strong>
            {e.status && <span className="chip" style={{ marginLeft: 8 }}>{e.status}</span>}
            {e.type === "done" && e.usage && <span className="small muted"> · {String(e.usage["elapsed_s"])}s · {String(e.usage["tokens"])} tokens · ${String(e.usage["cost_usd"])}</span>}
            {e.trace?.filter((t) => t.kind !== "node_end").map((t, i) => (
              <div key={i} className="small muted">{String(t.kind)}: {JSON.stringify(Object.fromEntries(Object.entries(t).filter(([k]) => !["ts", "node", "kind"].includes(k)))).slice(0, 220)}</div>
            ))}
          </li>
        ))}
        {state !== "done" && <li className="muted">waiting for the next node…</li>}
      </ol>
    </div>
  );
}
