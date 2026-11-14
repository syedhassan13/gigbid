import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, errText, type Schemas } from "../../../lib/api/client";
import { ErrorState, Loading } from "../../../components/States";
import EvidenceHover, { type Citation, type Verdict } from "../../../components/EvidenceHover";
import ApprovalPanel from "../../../components/ApprovalPanel";
import RunTimeline from "../../../components/RunTimeline";

export default function Studio() {
  const { id = "" } = useParams();
  const [d, setD] = useState<Schemas["JobDetail"] | null>(null);
  const [err, setErr] = useState("");
  const [text, setText] = useState("");
  const [running, setRunning] = useState<string | null>(null);
  const [regen, setRegen] = useState<number | null>(null);
  const load = useCallback(async () => {
    const { data, error } = await api.GET("/api/jobs/{job_id}", { params: { path: { job_id: id } } });
    if (error) return setErr(errText(error));
    setD(data); setErr("");
    const cl = ((data.interrupt?.draft as Record<string, unknown> | undefined)?.cover_letter ?? (data.draft as Record<string, unknown>)?.cover_letter ?? "") as string;
    setText(cl);
  }, [id]);
  useEffect(() => { load(); }, [load]);
  if (err) return <ErrorState error={err} retry={load} />;
  if (!d) return <Loading label="Loading draft" />;
  const intr = d.interrupt as Record<string, unknown> | null;
  const draft = (intr?.draft ?? d.draft) as { cover_letter?: string; screening_answers?: string[]; citations?: Citation[]; variant?: string };
  const verification = (intr?.verification ?? d.verification) as { before?: Record<string, number>; after?: Record<string, number>; verdicts?: Verdict[] };
  const critiques = (intr?.critiques ?? d.critiques) as { passed: boolean; issues: string[]; score: number }[];
  const compliance = (intr?.compliance ?? d.compliance) as { fixes_applied?: string[]; blocked_reason?: string | null };
  const paragraphs = text.split(/\n\s*\n/);

  async function regenerate(i: number) {
    setRegen(i);
    const { data } = await api.POST("/api/approvals/{thread_id}/regenerate", { params: { path: { thread_id: d!.thread_id! } }, body: { paragraph: paragraphs[i], instruction: null } });
    setRegen(null);
    const t = (data as { text?: string } | undefined)?.text;
    if (t) setText(paragraphs.map((p, j) => (j === i ? t : p)).join("\n\n"));
  }
  return (
    <>
      <p><Link to={`/jobs/${id}`}>← Job detail</Link></p>
      <h1>Proposal studio</h1>
      <p className="muted small">{String((d.job as Record<string, unknown>).title)} · arm {draft?.variant ?? "–"} · status <span className="chip">{d.status}</span></p>
      {running && <div className="panel"><RunTimeline threadId={running} onDone={() => { setRunning(null); load(); }} /></div>}
      {!intr && d.status !== "awaiting_approval" && <div className="banner warn">Nothing is waiting for approval on this job (status: {d.status}).</div>}
      <div className="grid2">
        <section className="panel">
          <h2>Draft — hover or focus a claim to see its evidence</h2>
          <EvidenceHover text={draft?.cover_letter ?? ""} verdicts={verification?.verdicts ?? []} citations={draft?.citations ?? []} />
          {!!draft?.screening_answers?.length && (<><h2>Screening answers</h2><ol className="small">{draft.screening_answers.map((a, i) => <li key={i}>{a}</li>)}</ol></>)}
          <h2>Verifier, Critic and Compliance</h2>
          <p className="small">Unsupported claims: before verification <b>{verification?.before?.unsupported ?? 0}</b> → after <b>{verification?.after?.unsupported ?? 0}</b> (of {verification?.before?.claims ?? 0} claims)</p>
          <ul className="small" data-testid="critic-comments">
            {critiques?.map((c, i) => <li key={i}>Critic pass {i + 1}: {c.passed ? "passed" : c.issues.join("; ")} (score {c.score})</li>)}
            {compliance?.fixes_applied?.map((f, i) => <li key={`c${i}`}>Compliance: {f}</li>)}
            {compliance?.blocked_reason && <li className="badge bad">Blocked: {compliance.blocked_reason}</li>}
          </ul>
        </section>
        <section className="panel">
          <h2><label htmlFor="editor" style={{ color: "inherit", fontSize: 16, margin: 0 }}>Edit</label></h2>
          <textarea id="editor" value={text} onChange={(e) => setText(e.target.value)} data-testid="editor" />
          <div className="row small" style={{ marginTop: 6 }}>
            {paragraphs.map((_, i) => <button key={i} className="btn" disabled={regen !== null || !d.thread_id} onClick={() => regenerate(i)}>{regen === i ? "Regenerating…" : `Regenerate ¶${i + 1}`}</button>)}
          </div>
        </section>
      </div>
      {intr && d.thread_id && (
        <div style={{ marginTop: 14 }}>
          <ApprovalPanel threadId={d.thread_id} original={draft?.cover_letter ?? ""} edited={text} dryRun={intr.dry_run as Record<string, unknown>}
            onDone={() => setRunning(d.thread_id!)} />
        </div>
      )}
    </>
  );
}
