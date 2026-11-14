# The reranker made my RAG worse, and better retrieval still didn't win more replies

*Draft for LinkedIn / Medium (~1,500 words). Every number links to a results file in the GigBid repository.*

I spent the last weeks building **GigBid**, a multi-agent copilot for freelancers. It scouts job posts, decides
whether a job is worth the bidding credits, writes a proposal in which every claim must point to real portfolio
evidence, and waits for the human to approve anything before it leaves the system. The stack is LangGraph, three
MCP servers of my own, open-weight models, FastAPI and React.

This post is not a tutorial. It is about the experiment that surprised me most: the part of the pipeline I was
*sure* would help made things clearly worse, and the part that did help didn't change the outcome I actually cared about.

## The setup: a corpus built to defeat naive RAG

A proposal is only as good as the evidence the writer sees. So I built three synthetic freelancer personas (an
ML engineer, a full-stack developer and a data analyst) and made their portfolios deliberately awkward:

* every project is described **three ways**: a business case study, a technical README with code, and one or more past proposals;
* some skills appear **only in code**. The case study says "a background job queue", while the repo says `from celery import Celery`;
* each persona has **150 past proposals labelled won, replied or ignored**, and the label depends on *how* the proposal was written, not only what it says.

The dev set has 200 jobs per persona (budgets sampled from 1.25 million real Upwork postings on Kaggle). Each
relevant job knows which project it came from, so I have gold evidence for every requirement. Metrics are computed at
document level: Recall@5, MRR and nDCG@10.

## The hypothesis I wrote down first

Before running anything I wrote: *requirement decomposition + hybrid retrieval will raise evidence Recall@5 by at
least 15 points over a naive baseline on jobs with four or more requirements.* It seemed obvious. A job asking for
five things should get five searches, and exact library names like "dbt" or "Celery" should be caught by BM25 where
embeddings blur them.

Then I implemented eleven configurable variants: naive dense (V0), decomposition, hybrid BM25+dense with
reciprocal rank fusion, a cross-encoder reranker, outcome-aware boosting, multi-vector items, contextual chunk
headers, HyDE, a corrective-RAG loop and a small skill graph. Each is one config object, so one command reruns the
whole comparison.

## Result 1: the reranker hurt, a lot

Cross-encoder reranking is the default advice for "precision at small k". I used an open MS-MARCO MiniLM
cross-encoder on CPU. On my corpus:

* hybrid retrieval alone: **Recall@5 0.573**
* the same candidates re-ordered by the cross-encoder: **Recall@5 0.377**

Adding the reranker to my final pipeline in the ablation dropped Recall@5 from **0.810 to 0.479**
(`evals/results/ablation.json`). It also cost about 6 seconds per query on a laptop CPU.

Why? MS-MARCO is web questions over web passages. My most valuable evidence is code (`import celery`,
`from prophet import Prophet`) and terse README bullet lists. The cross-encoder confidently ranked fluent prose
above the repository that actually proves the skill. The scores also exposed this: on code chunks the reranker's
sigmoid outputs were around 0.0003, effectively "no idea". My first version of the evidence tool even used those
scores to decide "weak evidence, don't claim this", and it refused to claim Celery experience the portfolio
clearly had. I now use the reranker (when enabled) only for *ordering*, and a separate calibrated *support* score
(lexical coverage + cosine) for the "may I claim this?" decision.

## Result 2: decomposition also hurt ranking

My hypothesis failed too. The exact configuration I predicted would win (decomposition + hybrid) improved Recall@5 on
multi-requirement jobs by **+7.6 points**, half the 15 I wrote down. Combined with my best indexing, decomposition
made things *worse* (0.82 → 0.61).

The reason is the evidence structure. A job asking for "Python, NLP, spaCy, named-entity recognition, LLM" is
really asking for *one project*. Five separate searches each return the generic best match for their own word, and
merging five lists dilutes the one project that matches the job as a whole. I still search per requirement for the
UI's requirement→evidence matrix, where per-requirement coverage is the point. I just don't use it for ranking.

## What actually won

Measured, not assumed: **contextual chunk headers + hybrid BM25/dense + outcome-aware boosting**, with a single
whole-job query. Each chunk gets a one-line header ("from Nadia's repository README 'forecast-service'; client
industry: retail; skills: …; this chunk is source code"). Proposals that won or got replies get a boost, and ignored
ones are demoted.

* Recall@5 **0.820** vs 0.436 for the naive baseline; nDCG@10 **0.836** vs 0.508 (`rag_variants.json`)
* p95 query latency **12 ms** on CPU, because no cross-encoder is needed
* the ablation says every part matters: removing outcome boosting costs 0.16 Recall@5, removing hybrid 0.11, removing contextual headers 0.06.

The contextual header is the cheap trick I'd recommend first. It lets BM25 and the embedder "see" which project a
fragment belongs to, so a code chunk with no prose still lands next to its case study.

## Result 3: better retrieval did not mean more replies

Here is the humbling part. I evaluate proposals against simulated clients with hidden preferences: must-have
skills, a budget ceiling, and a dislike of generic openings. On a fixed set of 60 jobs, going from the naive retriever
to the winning one moved the mean reply probability from **0.325 to 0.346**, and the sampled reply rate actually
went *down*, from 0.333 to 0.217 (`gigsim_outcomes.json`). Nearly doubling evidence recall barely moved the outcome.

Three reasons:

1. **The writer only uses the top one or two items.** Recall beyond rank two cannot change the letter.
2. **Clients reward things retrieval doesn't control:** using the client's own terms, covering the must-have
   skills by name, and not opening with "Dear Sir, I am passionate…".
3. **Noise.** At n = 60 the sampling noise is larger than the effect.

The same lesson showed up in my A/B extension: an evidence-first opening against a question-first opening. A paired
test on reply probability favoured evidence-first (p = 0.002), but the sampled replies leaned the other way and were
not significant (McNemar p = 0.10). Two reasonable metrics, two different stories. I report both.

## What I'd tell someone building agentic RAG

* **Write the hypothesis down before you run anything.** Mine was wrong twice, and that is the most useful thing I learned.
* **Separate ordering from permission.** A score good enough to sort by is not automatically good enough to decide "you may claim this".
* **Domain beats defaults.** An off-the-shelf reranker trained on web QA can be actively harmful on code-heavy evidence.
* **Measure the outcome you care about, not just retrieval.** Retrieval metrics were the easiest to move and the least connected to replies.
* **Ground every claim.** GigBid splits each draft into claims and checks each against evidence before a critic sees it.
  Unsupported claims are removed, never "fixed" by the model.

The code, results files and evaluation harness are open in the repository. Every number above is regenerated by
`make eval`.

---
*Résumé bullet (from the results files):*
Built GigBid, a LangGraph multi-agent freelancer copilot with 3 MCP servers and human-approved actions; measured 11 RAG
variants and shipped a contextual + hybrid + outcome-aware retriever that raised evidence Recall@5 from 0.44 to 0.82 (nDCG@10 0.51 → 0.84) at 12 ms p95 on CPU.
