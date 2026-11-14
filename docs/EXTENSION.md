# Signature extension: X2 Proposal experiments

**What:** two proposal strategies are tested as an A/B experiment in GigSim, with a significance test on reply rate.

| Arm | Strategy | Where |
|---|---|---|
| A, `evidence_first` | Open with the single most relevant proof (project + measurable outcome). | `agent/nodes/writer.py`, `agent/prompts/writer.md` |
| B, `question_first` | Open with one diagnostic question about the client's problem, then the proof. | same |

* **Assignment in production:** deterministic by job id (md5 parity), configured in `agent/config.yaml → experiment`.
  The arm travels with the draft to GigSim (`variant` field) and to the pipeline board and analytics (per-arm reply rates).
* **Outcome learning:** when ≥3 resolved proposals exist for a (category, arm) cell, `promotion_rules.observe_outcome`
  promotes the cell's reply rate into outcome memory. The writer reads it, and Settings → Memory shows and deletes it.
* **Evaluation (`evals/runners/gigsim_outcomes.py`):** a *paired* design. Every job in a fixed set of 60
  bid-worthy dev jobs is drafted with both arms by the same pipeline, so job difficulty cancels out. Each
  draft is scored by GigSim's client model (`gigsim/client_sim.py`, the same code GigSim runs on `/admin/tick`).
  * continuous outcome: per-job reply probability → paired t-test and Wilcoxon signed-rank;
  * binary outcome: sampled replies → McNemar's exact test on discordant pairs.
* **Results:** `evals/results/gigsim_outcomes.json → x2_ab`, summarised in the README results block.
* **Threats to validity:** the client model is a scoring function we wrote, so arm B can only win through the
  features it rewards (it rewards a question, specificity and overlap with the client's terms; it penalises
  generic openings). This tests whether our *writer* exploits those preferences, not real-world persuasion.
  Results with the offline template writer and with the Groq writer are reported separately.
