import { useState } from "react";

export type Verdict = { claim: string; label: "supported" | "partial" | "unsupported"; score: number; evidence_ids: string[]; unsupported_numbers: string[] };
export type Citation = { sentence: string; evidence_ids: string[] };

function splitSentences(t: string): string[] {
  return t.split(/(?<=[.!?])\s+(?=[A-Z"'(])/).filter(Boolean);
}

/** Renders a draft where every claim shows its evidence on hover / keyboard focus. */
export default function EvidenceHover({ text, verdicts = [], citations = [] }: { text: string; verdicts?: Verdict[]; citations?: Citation[] }) {
  const [open, setOpen] = useState<number | null>(null);
  const sents = splitSentences(text);
  return (
    <div style={{ lineHeight: 1.7 }} data-testid="evidence-draft">
      {sents.map((s, i) => {
        const v = verdicts.find((x) => x.claim === s || s.includes(x.claim) || x.claim.includes(s));
        const c = citations.find((x) => x.sentence === s || s.includes(x.sentence.slice(0, 40)));
        const ids = Array.from(new Set([...(v?.evidence_ids ?? []), ...(c?.evidence_ids ?? [])]));
        if (!v && !c) return <span key={i}>{s} </span>;
        const label = v?.label ?? "supported";
        return (
          <span key={i}>
            <span className={`claim ${label}`} tabIndex={0} role="button" aria-describedby={`ev-${i}`} data-testid="claim"
              onMouseEnter={() => setOpen(i)} onMouseLeave={() => setOpen(null)} onFocus={() => setOpen(i)} onBlur={() => setOpen(null)}>
              {s}
              {open === i && (
                <span className="tip" id={`ev-${i}`} role="tooltip">
                  <strong>{label}</strong>{v && <> · support {v.score.toFixed(2)}</>}
                  <br />Evidence: {ids.length ? ids.map((id) => <span key={id} className="chip" style={{ margin: 2 }}>{id}</span>) : "none"}
                  {v?.unsupported_numbers?.length ? <><br />Unsupported numbers: {v.unsupported_numbers.join(", ")}</> : null}
                </span>
              )}
            </span>{" "}
          </span>
        );
      })}
    </div>
  );
}
