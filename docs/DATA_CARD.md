# Data card

GigBid combines **real public data** (Kaggle) with **clearly labelled synthetic data**. No starter kit or
simulator was provided for this assignment, so GigSim, the persona corpora, the policy pack and the
dev set were built here. Every synthetic record carries `synthetic: true` (personas) or `source: "synthetic"` (jobs).

## 1. Real data (Kaggle)

| Dataset | Licence | Rows used | Used for |
|---|---|---|---|
| [asaniczka/upwork-job-postings-dataset-2024-50k-records](https://www.kaggle.com/datasets/asaniczka/upwork-job-postings-dataset-2024-50k-records) | ODC-By | ≤300k | titles, fixed budgets, hourly ranges |
| [asaniczka/all-jobs-on-upwork-200k-plus](https://www.kaggle.com/datasets/asaniczka/all-jobs-on-upwork-200k-plus) | ODC-By | ≤300k per file (3 files) | titles, budgets, hourly ranges → pricing percentiles, historical job stream |
| [ahmedmyalo/upwork-freelance-jobs-60k](https://www.kaggle.com/datasets/ahmedmyalo/upwork-freelance-jobs-60k) | Apache-2.0 | all | descriptions, job cost, rate ranges, **client spend, rating, payment verification, Connects per job** |
| [asaniczka/freelance-contracts-dataset-1-3-million-entries](https://www.kaggle.com/datasets/asaniczka/freelance-contracts-dataset-1-3-million-entries) | ODC-By | ≤300k | realised hourly rates by job title |
| [sarveshchhetri/freelancer-success-earnings-and-churn-prediction](https://www.kaggle.com/datasets/sarveshchhetri/freelancer-success-earnings-and-churn-prediction) | Apache-2.0 | all | reviewed; freelancer-level features (no job titles), so not used in pricing |
| [adityammantri/trial-1](https://www.kaggle.com/datasets/adityammantri/trial-1) ("Fake-Job-Posting-Detection") | **Unknown** | 3,000 sampled | **external scam-rule test only**; read locally, never redistributed |

Attribution: the asaniczka datasets are © asaniczka under ODC-By 1.0. ahmedmyalo and sarveshchhetri are under
Apache-2.0. Raw files live in `data/raw/` (git-ignored) and are downloaded by `scripts/download_kaggle.py`.
**Only derived aggregates are committed** (`evals/datasets/pricing_stats.json`: percentiles per category),
plus a profile of which columns were detected (`data/processed/kaggle_profile.json`, generated).

### Preprocessing (`scripts/prepare_data.py`)
1. Robust column detection per CSV (title, description, budget/job cost, hourly low/high or start/end rate,
   payment type, spend, rating, Connects, payment verification). Numbers are parsed from strings, and values
   ≤0 or ≥1M are dropped.
2. Title → category by keyword vote (ai_ml, web_dev, data_analytics, design, writing, marketing, video,
   mobile, admin, other).
3. Percentiles (p10/p25/p50/p75/p90) of fixed budgets and hourly low/high per category → `pricing_stats.json`
   (1,255,336 rows read). Client spend, rating, verification share and Connects per job are recorded in `kaggle_profile.json`.
4. 1,500 **historical jobs** for GigSim's `/market/stats`: real titles and budgets. When a record has no
   description, the description field says so explicitly.

## 2. Synthetic data

| Artefact | Generator | Contents |
|---|---|---|
| 3 persona corpora (`data/personas/{ai_ml,fullstack,data_analyst}`) | `scripts/generate_personas.py --seed 7` | Fictional people. Each has a CV, 20 projects (each described **three ways**: business case study, technical README with code, and past proposals), about 14 client reviews, and **150 past proposals labelled won / replied / ignored**. Some skills are implied only by code (e.g. `from celery import Celery`). Proposal outcome depends on writing style (generic vs specific vs specific + question) and relevance. |
| GigSim clients | `gigsim/generator.py` | Public history (spend, hires, rating, reviews, verification) plus **hidden preferences** (must-have skills, budget ceiling, dislike of generic openings, responsiveness). Scam clients have no history. |
| Dev set (`evals/datasets/dev_*.jsonl`, 200 jobs/persona) | `scripts/prepare_data.py --seed 11` | Relevant (standard / multi-requirement / vague / low-budget), off-domain, scam, and planted-injection jobs, with gold labels: action, is_scam, is_injection, **gold evidence ids**, fair price band, job type. Budgets are sampled from the **real** Kaggle percentiles. |
| Live stream (`data/processed/stream_jobs.jsonl`) | same | About 320 jobs released over simulated time, including ~8% duplicates, scams and injections. |
| Policy pack (`data/policy_pack`) | hand-written | A summary of marketplace rules (not Upwork's legal text) plus machine-readable `rules.yaml`. |

### Gold-label rules (and their circularity)
* Gold evidence = the case study and repo of the project a job was generated from, plus its won/replied proposals.
* Gold action = `bid` if the job is relevant and its budget clears the persona's floor (hourly ≥ floor;
  fixed ≥ 6 h × floor), otherwise `skip`. Scams and off-domain jobs are always `skip`. Injection jobs keep the
  label of the underlying job.
* Fair band: hourly `[max(floor, client low), max(1.3·floor, client high)]`; fixed `[0.75·budget, 1.1·budget]`.
* **Limitation:** these rules resemble GigBid's decision thresholds, so decision metrics on the dev set are
  **optimistic**. The external scam test (`evals/results/scam_external.json`) shows the rules do not transfer
  to out-of-distribution fraud text.

## 3. Judge calibration
`evals/datasets/judge_labels.csv` has 30 anonymised proposals. `suggested_score` comes from the rule-based
critic and is **not** a human label; `human_score` must be filled in by the author. Kappa is computed only from
`human_score` (`evals/runners/judge_calibration.py`).

Rubric (1–5): 5 = specific to the client's problem, concrete and plausible claims, clear plan, price and one
good question, 110–220 words; 3 = relevant but partly generic; 1 = generic, off-topic, fabricated-sounding or
non-compliant.

## 4. Limitations
* All persona data and GigSim are synthetic. Outcome metrics measure GigSim's client model (a transparent
  scoring function, optionally blended with an LLM), not real clients.
* Kaggle job data is from 2024 and scraped from RSS by the dataset authors. GigBid itself never scrapes.
* Category assignment is keyword-based and noisy, and budgets in some records are placeholders.
* The hidden test set is not in the repo.

## 5. RAG decision (what ships)
The shipped pipeline is **`v_best` = contextual chunks + hybrid BM25/dense (RRF) + outcome-aware boost, whole-job
query**. It was chosen because it had the highest Recall@5 and nDCG@10 among all variants and combinations on
the dev set (`evals/results/rag_variants.json`, `rag_combinations.json`). The originally hypothesised best
(requirement decomposition + cross-encoder rerank) lost. The MS-MARCO MiniLM reranker lowered Recall@5
below plain hybrid, because it scores code and README chunks poorly. Requirement decomposition also lowered
document-level ranking: the per-requirement result lists dilute the project that matches the job as a whole.
The Fit Matcher still searches per requirement, because the requirement→evidence matrix needs per-requirement coverage.
