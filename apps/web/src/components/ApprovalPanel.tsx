import { useState } from "react";
import { api, errText } from "../lib/api/client";

type Props = { threadId: string; original: string; edited: string; dryRun?: Record<string, unknown>; onDone: () => void; kind?: "proposal" | "message" };

/** Approve / edit / reject. Edits are sent as a diff-able edited_text; reject needs a reason. */
export default function ApprovalPanel({ threadId, original, edited, dryRun, onDone, kind = "proposal" }: Props) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const changed = edited.trim() !== original.trim();
  async function send(decision: "approve" | "edit" | "reject") {
    setBusy(true); setErr("");
    const body = decision === "edit" ? { decision, edited_text: edited } : decision === "reject" ? { decision, reason } : { decision };
    const { error } = await api.POST("/api/approvals/{thread_id}", { params: { path: { thread_id: threadId } }, body });
    setBusy(false);
    if (error) setErr(errText(error)); else onDone();
  }
  return (
    <section className="panel" aria-label="Approval">
      <h2>Approval</h2>
      {dryRun && (
        <div className="small" data-testid="dry-run">
          <strong>dry_run preview</strong> — what will be sent{kind === "proposal" ? " and what it costs" : ""}:
          {kind === "proposal" && <div>Connects: <b>{String(dryRun["connects_cost"] ?? "-")}</b> · balance after: {String(dryRun["connects_balance_after"] ?? "-")} · bid ${String(dryRun["bid_amount"] ?? "-")} · policy v{String(dryRun["policy_version"] ?? "-")}</div>}
          {Array.isArray(dryRun["violations"]) && (dryRun["violations"] as string[]).length > 0 && <div className="banner bad">Marketplace would reject: {(dryRun["violations"] as string[]).join("; ")}</div>}
        </div>
      )}
      <div className="row" style={{ marginTop: 10 }}>
        <button className="btn primary" disabled={busy} onClick={() => send(changed ? "edit" : "approve")} data-testid="approve">
          {changed ? "Save edit & re-check" : kind === "proposal" ? "Approve & submit" : "Approve & send"}
        </button>
        <input aria-label="Reason for rejecting" placeholder="Reason (required to reject)" value={reason} onChange={(e) => setReason(e.target.value)} style={{ maxWidth: 280 }} data-testid="reject-reason" />
        <button className="btn danger" disabled={busy || !reason.trim()} onClick={() => send("reject")} data-testid="reject">Reject</button>
      </div>
      {changed && <p className="small muted">Your edit will be diffed (style memory) and re-checked by the Compliance Guard before you approve the final text.</p>}
      {err && <div className="banner bad" role="alert">{err}</div>}
    </section>
  );
}
