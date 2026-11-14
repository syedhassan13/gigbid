import { useCallback, useEffect, useState } from "react";
import { api, errText, type Schemas } from "../../lib/api/client";
import { Empty, ErrorState, Loading } from "../../components/States";
import ApprovalPanel from "../../components/ApprovalPanel";

type Thread = { id: string; job_id: string; last_message?: { sender: string; text: string } | null; run_thread_id?: string | null; run_status?: string | null };
type Msg = { id: string; sender: string; text: string; created_at: string };

export default function Messages() {
  const [threads, setThreads] = useState<Thread[] | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [pending, setPending] = useState<Schemas["Pending"][]>([]);
  const [text, setText] = useState("");
  const [err, setErr] = useState("");
  const load = useCallback(async () => {
    const t = await api.GET("/api/messages/threads");
    const p = await api.GET("/api/approvals");
    if (!t.data) setErr("Could not load conversations (marketplace unavailable?)"); else { setErr(""); setThreads(t.data as Thread[]); }
    if (p.data) setPending(p.data.filter((x) => x.kind === "conv"));
  }, []);
  useEffect(() => { load(); const i = setInterval(load, 10000); return () => clearInterval(i); }, [load]);
  useEffect(() => {
    if (!sel) return;
    api.GET("/api/messages/threads/{thread_id}", { params: { path: { thread_id: sel } } }).then(({ data }) => setMsgs(((data as { messages?: Msg[] })?.messages) ?? []));
  }, [sel, pending.length]);
  const pend = pending.find((p) => (p.payload as { thread_id?: string }).thread_id === sel);
  const draftText = ((pend?.payload as { draft?: { text?: string } } | undefined)?.draft?.text) ?? "";
  useEffect(() => { setText(draftText); }, [draftText]);

  if (err) return <ErrorState error={err} retry={load} />;
  if (!threads) return <Loading label="Loading conversations" />;
  return (
    <>
      <h1>Messages</h1>
      {threads.length === 0 ? <Empty title="No client conversations yet" hint="Threads appear when a client replies to a submitted proposal." /> : (
        <div className="thread">
          <section className="panel" aria-label="Threads">
            {threads.map((t) => (
              <button key={t.id} className="btn" style={{ width: "100%", textAlign: "left", marginBottom: 6, background: sel === t.id ? "var(--chip)" : undefined }} onClick={() => setSel(t.id)}>
                <div><b>{t.id}</b> {pending.some((p) => (p.payload as { thread_id?: string }).thread_id === t.id) && <span className="badge warn">reply drafted</span>}</div>
                <div className="small muted">{t.last_message?.text.slice(0, 70)}</div>
              </button>
            ))}
          </section>
          <section className="panel" aria-label="Conversation">
            {!sel ? <p className="muted">Select a thread.</p> : (
              <>
                {msgs.map((m) => <div key={m.id} className={`msg ${m.sender}`}><div className="small muted">{m.sender} · {m.created_at.slice(0, 16)}</div>{m.text}</div>)}
                {pend ? (
                  <>
                    <h2>Suggested reply <span className="chip">{String((pend.payload as { intent?: { intent?: string } }).intent?.intent)}</span></h2>
                    {((pend.payload as { slots?: { start: string }[] }).slots ?? []).length > 0 && <p className="small">Proposed interview slots: {((pend.payload as { slots?: { start: string }[] }).slots ?? []).map((s) => <span key={s.start} className="chip" style={{ margin: 2 }}>{s.start.replace("T", " ")}</span>)}</p>}
                    <label htmlFor="reply">Reply (edit before approving)</label>
                    <textarea id="reply" value={text} onChange={(e) => setText(e.target.value)} style={{ minHeight: 120 }} />
                    <ApprovalPanel kind="message" threadId={pend.thread_id} original={draftText} edited={text} dryRun={(pend.payload as { dry_run?: Record<string, unknown> }).dry_run} onDone={load} />
                  </>
                ) : <button className="btn" style={{ marginTop: 10 }} onClick={async () => { await api.POST("/api/messages/threads/{thread_id}/draft", { params: { path: { thread_id: sel } } }); setTimeout(load, 4000); }}>Draft a reply</button>}
              </>
            )}
          </section>
        </div>
      )}
    </>
  );
}
