"""Generate the three SYNTHETIC freelancer persona corpora.

Everything written by this script is synthetic (fictional people, clients and
projects) and every file carries `synthetic: true` in its front matter. The
corpus is deliberately "messy" so naive RAG struggles:

* the same project is described three ways (business case study, technical
  README with code, and one or more past proposals);
* some skills are only implied (a library appears only in code, never by name
  in prose) e.g. a case study says "background job queue" while the repo code
  does `from celery import Celery`;
* ~150 past proposals per persona carry an outcome (won / replied / ignored)
  that correlates with *how* they were written, not just what they say.

Deterministic: `python scripts/generate_personas.py --seed 7`.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "personas"

INDUSTRIES = [
    "healthcare", "fintech", "e-commerce", "logistics", "real estate", "education",
    "legal", "hospitality", "manufacturing", "media", "nonprofit", "insurance",
]
CLIENT_KINDS = ["seed-stage startup", "mid-size agency", "family-owned business", "Series B scale-up",
                "university lab", "solo founder", "regional chain", "consultancy"]

# Each archetype: explicit skills named in prose, implied skills that appear only in code,
# a problem / solution sketch, and a metric template.
PERSONAS = {
    "ai_ml": {
        "name": "Nadia Qureshi", "headline": "AI/ML Engineer - LLM apps, RAG, forecasting, computer vision",
        "rate_floor": 45, "target_rate": 65, "location": "Lahore, PK (remote)", "years": 6,
        "archetypes": [
            {"key": "rag_chatbot", "title": "Retrieval-augmented support assistant",
             "explicit": ["Python", "LLM", "RAG", "FastAPI", "embeddings"], "implied": ["faiss", "langchain", "sentence-transformers"],
             "problem": "support agents spent hours searching policy PDFs", "solution": "a question-answering assistant over their knowledge base with cited answers",
             "metric": "cut average handling time by {p}%"},
            {"key": "doc_classify", "title": "Document classification pipeline",
             "explicit": ["Python", "NLP", "scikit-learn", "text classification"], "implied": ["spacy", "pandas", "joblib"],
             "problem": "thousands of incoming documents were routed by hand", "solution": "an automatic classifier with a human review queue for low-confidence items",
             "metric": "automated {p}% of routing at 96% precision"},
            {"key": "forecast", "title": "Demand forecasting model",
             "explicit": ["Python", "time series", "forecasting", "machine learning"], "implied": ["prophet", "lightgbm", "statsmodels"],
             "problem": "stock-outs and over-ordering every season", "solution": "weekly SKU-level forecasts with prediction intervals",
             "metric": "reduced forecast error (MAPE) by {p}%"},
            {"key": "cv_defect", "title": "Visual defect detection",
             "explicit": ["computer vision", "deep learning", "PyTorch", "Python"], "implied": ["opencv", "albumentations", "torchvision"],
             "problem": "manual inspection missed hairline defects on the line", "solution": "a camera-based defect detector running on an edge box",
             "metric": "caught {p}% more defects than manual inspection"},
            {"key": "llm_finetune", "title": "Fine-tuned LLM for domain extraction",
             "explicit": ["LLM", "fine-tuning", "Hugging Face", "Python"], "implied": ["peft", "transformers", "bitsandbytes"],
             "problem": "a general model kept missing domain-specific fields", "solution": "a LoRA fine-tuned open model for structured extraction",
             "metric": "raised field-level F1 by {p} points"},
            {"key": "recsys", "title": "Product recommendation engine",
             "explicit": ["recommender systems", "Python", "machine learning", "SQL"], "implied": ["implicit", "pandas", "redis"],
             "problem": "customers rarely discovered relevant products", "solution": "personalised recommendations served from an API with nightly retraining",
             "metric": "lifted click-through by {p}%"},
            {"key": "churn_deploy", "title": "Churn prediction model in production",
             "explicit": ["machine learning", "Python", "MLOps", "Docker"], "implied": ["mlflow", "xgboost", "celery"],
             "problem": "the retention team only learned about churn after it happened", "solution": "daily churn scores pushed to the CRM through a background job queue",
             "metric": "helped retain {p}% more at-risk accounts"},
            {"key": "speech", "title": "Speech transcription and summarisation",
             "explicit": ["speech recognition", "LLM", "Python", "AWS"], "implied": ["whisper", "ffmpeg", "boto3"],
             "problem": "call recordings were never reviewed", "solution": "automatic transcripts with summaries and action items",
             "metric": "saved {p} analyst-hours per week"},
            {"key": "ner", "title": "Named-entity extraction from contracts",
             "explicit": ["NLP", "named entity recognition", "Python", "LLM"], "implied": ["spacy", "pydantic", "pdfplumber"],
             "problem": "paralegals copied clauses into spreadsheets", "solution": "an extractor that pulls parties, dates and obligations into a structured table",
             "metric": "cut review time per contract by {p}%"},
            {"key": "agents", "title": "Multi-step LLM agent for operations",
             "explicit": ["LLM", "AI agents", "Python", "API integration"], "implied": ["langgraph", "openai", "tenacity"],
             "problem": "a repetitive back-office workflow took a full-time person", "solution": "a tool-using agent with human approval for every external action",
             "metric": "handled {p}% of tickets end-to-end with approval"},
        ],
    },
    "fullstack": {
        "name": "Bilal Siddiqui", "headline": "Full-stack web developer - React, Next.js, Node, Django",
        "rate_floor": 35, "target_rate": 50, "location": "Karachi, PK (remote)", "years": 7,
        "archetypes": [
            {"key": "saas_dash", "title": "SaaS analytics dashboard",
             "explicit": ["React", "TypeScript", "Node.js", "PostgreSQL"], "implied": ["recharts", "prisma", "tanstack-query"],
             "problem": "customers exported CSVs to understand their own usage", "solution": "an in-app dashboard with filters, drill-downs and scheduled reports",
             "metric": "reduced support tickets about reporting by {p}%"},
            {"key": "ecommerce", "title": "Headless e-commerce storefront",
             "explicit": ["Next.js", "React", "Shopify", "e-commerce"], "implied": ["graphql", "tailwindcss", "vercel"],
             "problem": "the old theme was slow on mobile", "solution": "a headless storefront with server rendering and image optimisation",
             "metric": "improved mobile conversion by {p}%"},
            {"key": "booking", "title": "Appointment booking system",
             "explicit": ["Django", "Python", "React", "PostgreSQL"], "implied": ["celery", "django-rest-framework", "twilio"],
             "problem": "bookings were taken by phone and often double-booked", "solution": "online booking with reminders sent from a background job queue",
             "metric": "cut no-shows by {p}%"},
            {"key": "realtime_chat", "title": "Real-time chat module",
             "explicit": ["Node.js", "WebSockets", "React", "Redis"], "implied": ["socket.io", "express", "jest"],
             "problem": "users left the app to talk to each other", "solution": "in-app real-time messaging with read receipts and moderation",
             "metric": "increased daily active users by {p}%"},
            {"key": "rest_api", "title": "Public REST API and developer portal",
             "explicit": ["REST API", "Node.js", "OpenAPI", "PostgreSQL"], "implied": ["fastify", "zod", "swagger-ui"],
             "problem": "partners integrated through ad-hoc CSV drops", "solution": "a versioned public API with keys, rate limits and docs",
             "metric": "onboarded {p} partners in the first quarter"},
            {"key": "marketplace", "title": "Two-sided marketplace MVP",
             "explicit": ["Next.js", "Stripe", "TypeScript", "PostgreSQL"], "implied": ["stripe-connect", "supabase", "resend"],
             "problem": "the founder validated demand with a spreadsheet", "solution": "an MVP with listings, payouts and reviews",
             "metric": "processed {p}k USD GMV in month one"},
            {"key": "payments", "title": "Subscription billing integration",
             "explicit": ["Stripe", "Node.js", "React", "webhooks"], "implied": ["stripe", "bullmq", "postgres"],
             "problem": "subscriptions were invoiced manually", "solution": "self-serve plans, proration and dunning via webhooks",
             "metric": "recovered {p}% of failed payments"},
            {"key": "admin_panel", "title": "Internal admin panel",
             "explicit": ["React", "Django", "role-based access", "Python"], "implied": ["react-admin", "django-guardian", "pytest"],
             "problem": "ops staff edited records directly in the database", "solution": "an audited admin panel with roles and approvals",
             "metric": "eliminated {p} direct DB edits per week"},
            {"key": "cms_migration", "title": "CMS migration to headless",
             "explicit": ["WordPress", "Next.js", "SEO", "content migration"], "implied": ["contentful", "wp-graphql", "redirects"],
             "problem": "a legacy WordPress site was slow and hard to edit", "solution": "a headless CMS with preserved URLs and SEO metadata",
             "metric": "cut page load time by {p}%"},
            {"key": "auth_sso", "title": "Single sign-on and auth hardening",
             "explicit": ["authentication", "OAuth", "Node.js", "security"], "implied": ["passport", "jose", "argon2"],
             "problem": "enterprise customers required SSO", "solution": "OAuth/OIDC SSO with SCIM provisioning and MFA",
             "metric": "unblocked {p} enterprise deals"},
        ],
    },
    "data_analyst": {
        "name": "Sana Malik", "headline": "Data analyst - SQL, Power BI, Tableau, dbt, Python",
        "rate_floor": 25, "target_rate": 40, "location": "Islamabad, PK (remote)", "years": 5,
        "archetypes": [
            {"key": "sales_dash", "title": "Executive sales dashboard",
             "explicit": ["Power BI", "SQL", "DAX", "data visualization"], "implied": ["power query", "sql server", "row-level security"],
             "problem": "leadership waited a week for the monthly sales deck", "solution": "a self-serve dashboard refreshed daily",
             "metric": "saved {p} hours of manual reporting per month"},
            {"key": "etl", "title": "ELT pipeline and warehouse model",
             "explicit": ["SQL", "data engineering", "ETL", "BigQuery"], "implied": ["dbt", "airflow", "fivetran"],
             "problem": "every team had its own version of revenue", "solution": "a tested warehouse model with one definition of each metric",
             "metric": "reduced metric disputes by {p}%"},
            {"key": "segmentation", "title": "Customer segmentation analysis",
             "explicit": ["Python", "clustering", "customer analytics", "pandas"], "implied": ["scikit-learn", "seaborn", "jupyter"],
             "problem": "marketing sent the same email to everyone", "solution": "behavioural segments with personas and recommended actions",
             "metric": "raised email revenue by {p}%"},
            {"key": "ab_test", "title": "A/B test analysis program",
             "explicit": ["A/B testing", "statistics", "Python", "SQL"], "implied": ["scipy", "statsmodels", "bayesian"],
             "problem": "experiments were called early on noisy results", "solution": "a pre-registered testing process with power analysis and readouts",
             "metric": "cut false-positive launches by {p}%"},
            {"key": "finance_report", "title": "Automated financial reporting",
             "explicit": ["Excel", "financial reporting", "SQL", "automation"], "implied": ["openpyxl", "vba", "power automate"],
             "problem": "month-end close took nine days", "solution": "automated reconciliations and a reporting pack",
             "metric": "shortened month-end close by {p} days"},
            {"key": "survey", "title": "Survey and NPS analysis",
             "explicit": ["survey analysis", "Python", "data visualization", "Tableau"], "implied": ["pandas", "textblob", "likert"],
             "problem": "open-text survey answers were never read", "solution": "themed NPS drivers with a Tableau story",
             "metric": "identified {p} top churn drivers acted on by product"},
            {"key": "attribution", "title": "Marketing attribution model",
             "explicit": ["marketing analytics", "SQL", "Google Analytics", "Looker"], "implied": ["ga4", "bigquery", "lookml"],
             "problem": "budget was split by gut feeling", "solution": "multi-touch attribution with a channel ROI dashboard",
             "metric": "reallocated budget for a {p}% lower CAC"},
            {"key": "inventory", "title": "Inventory analytics",
             "explicit": ["Tableau", "SQL", "supply chain analytics", "Excel"], "implied": ["snowflake", "tableau prep", "abc analysis"],
             "problem": "slow-moving stock tied up cash", "solution": "ABC/XYZ inventory views with reorder alerts",
             "metric": "freed {p}k USD of working capital"},
            {"key": "data_cleaning", "title": "CRM data cleaning and deduplication",
             "explicit": ["data cleaning", "Python", "Excel", "CRM"], "implied": ["recordlinkage", "rapidfuzz", "hubspot api"],
             "problem": "duplicate contacts broke every campaign report", "solution": "fuzzy-matched deduplication with a merge review sheet",
             "metric": "removed {p}% duplicate records"},
            {"key": "kpi_looker", "title": "KPI reporting layer in Looker",
             "explicit": ["Looker", "SQL", "KPI reporting", "data modeling"], "implied": ["lookml", "dbt", "postgres"],
             "problem": "KPIs were computed differently in every spreadsheet", "solution": "a governed semantic layer and KPI tiles",
             "metric": "adopted by {p} teams within a month"},
        ],
    },
}

GENERIC_OPENINGS = [
    "Dear Hiring Manager, I am very interested in your job.",
    "Hello Sir, I have read your job description carefully.",
    "Greetings! I am passionate about delivering quality work.",
    "I am writing to apply for this exciting opportunity.",
]
SPECIFIC_OPENING_TPL = [
    "You need {need} - I shipped almost exactly this for a {kind} in {industry}, where it {metric}.",
    "Your post mentions {need}. Last year I built {solution} for a {industry} client and it {metric}.",
    "{Need} is the hard part of this job; I solved the same problem for a {kind} in {industry}.",
]
FUN_SLUG = re.compile(r"[^a-z0-9]+")


def slug(s: str) -> str:
    return FUN_SLUG.sub("-", s.lower()).strip("-")


def front_matter(meta: dict) -> str:
    lines = ["---"] + [f"{k}: {json.dumps(v)}" for k, v in meta.items()] + ["---", ""]
    return "\n".join(lines)


def code_snippet(arch: dict) -> str:
    libs = arch["implied"]
    py = all(not l.startswith(("react", "tanstack", "socket", "express", "jest", "fastify", "zod", "swagger", "stripe", "supabase", "resend", "bullmq", "passport", "jose", "graphql", "tailwind", "vercel", "prisma", "recharts", "contentful", "wp-")) for l in libs)
    if py:
        imports = "\n".join(f"import {re.sub(r'[^a-z0-9_]', '_', l.lower())}" for l in libs)
        body = f'''
def run_pipeline(config):
    """Entry point used by the scheduler."""
    data = load_inputs(config["source"])
    model = build_model(config)  # uses {libs[0]}
    results = model.process(data)
    persist(results, config["target"])
    return results
'''
        return f"```python\n{imports}\n{body}```"
    imports = "\n".join(f"import {re.sub(r'[^a-zA-Z0-9]', '', l.title())} from '{l}';" for l in libs)
    return f"```ts\n{imports}\n\nexport async function handler(req, res) {{\n  // core flow built on {libs[0]}\n  const result = await service.run(req.body);\n  res.json(result);\n}}\n```"


def make_projects(pkey: str, persona: dict, rng: random.Random, n: int = 20) -> list[dict]:
    projects = []
    archs = persona["archetypes"]
    for i in range(n):
        arch = archs[i % len(archs)]
        industry = rng.choice(INDUSTRIES)
        kind = rng.choice(CLIENT_KINDS)
        year = rng.choice([2021, 2022, 2023, 2024, 2025, 2026])
        p = rng.choice([18, 22, 27, 31, 35, 40, 45, 52, 60])
        metric = arch["metric"].format(p=p)
        title = f"{arch['title']} for a {industry} {kind}"
        sid = f"{pkey}-{slug(arch['key'])}-{i:02d}"
        projects.append({
            "id": sid, "persona": pkey, "archetype": arch["key"], "title": title, "industry": industry,
            "client_kind": kind, "year": year, "explicit": arch["explicit"], "implied": arch["implied"],
            "problem": arch["problem"], "solution": arch["solution"], "metric": metric,
            "duration_weeks": rng.choice([3, 4, 6, 8, 10, 12, 16]),
        })
    return projects


def write_case_study(d: Path, pr: dict) -> None:
    # Business prose. Deliberately avoids naming implied libraries.
    txt = front_matter({"id": f"case:{pr['id']}", "type": "case_study", "persona": pr["persona"], "project": pr["id"],
                        "skills": pr["explicit"], "date": f"{pr['year']}-06-01", "client_industry": pr["industry"], "synthetic": True})
    txt += f"# {pr['title']}\n\n"
    txt += f"**Client:** a {pr['client_kind']} in {pr['industry']} · **Duration:** {pr['duration_weeks']} weeks · **Year:** {pr['year']}\n\n"
    txt += f"## The problem\nThe client's team had a recurring pain: {pr['problem']}. They needed something reliable that their non-technical staff could trust.\n\n"
    txt += f"## What I built\nI designed and delivered {pr['solution']}. I worked with {', '.join(pr['explicit'][:-1])} and {pr['explicit'][-1]}, "
    txt += "and set it up so the client's team could run it without me. Long-running work runs in the background so users never wait.\n\n"
    txt += f"## Outcome\nWithin the first months the system {pr['metric']}. The client extended the engagement for a second phase.\n"
    (d / "case_studies" / f"{pr['id']}.md").write_text(txt, encoding="utf-8")


def write_readme(d: Path, pr: dict) -> None:
    # Technical description of the SAME project; names implied libs only in code + deps.
    rd = d / "repos" / pr["id"]
    rd.mkdir(parents=True, exist_ok=True)
    txt = front_matter({"id": f"repo:{pr['id']}", "type": "repo_readme", "persona": pr["persona"], "project": pr["id"],
                        "skills": pr["explicit"] + pr["implied"], "date": f"{pr['year']}-05-15", "client_industry": pr["industry"], "synthetic": True})
    txt += f"# {pr['archetype'].replace('_', '-')}-service\n\nInternal codename for the {pr['industry']} engagement. "
    txt += "Setup: copy `.env.example`, install dependencies, run the entrypoint.\n\n## Architecture\n"
    txt += "- ingestion -> processing -> storage -> API\n- jobs run asynchronously; failures retry with backoff\n- config is environment-driven\n\n"
    txt += f"## Core module\n\n{code_snippet(pr)}\n\n## Dependencies\n" + "\n".join(f"- {l}" for l in pr["implied"]) + "\n"
    (rd / "README.md").write_text(txt, encoding="utf-8")


def proposal_text(pr: dict, job_title: str, style: str, rng: random.Random) -> str:
    need = pr["solution"].split(" with ")[0]
    if style == "generic":
        opening = rng.choice(GENERIC_OPENINGS)
        body = (f" I have many years of experience and I can do this job perfectly. I know {', '.join(pr['explicit'])}. "
                "I will deliver high quality work on time. Please check my profile. Looking forward to hearing from you.")
        return opening + body
    opening = rng.choice(SPECIFIC_OPENING_TPL).format(need=need, Need=need[0].upper() + need[1:], kind=pr["client_kind"],
                                                      industry=pr["industry"], solution=pr["solution"], metric=pr["metric"])
    plan = (f" For \"{job_title}\" I would start with a short discovery call, then deliver in two milestones: "
            f"a working slice in week one and the hardened version after review. "
            f"I would reuse the approach from that project ({', '.join(pr['explicit'][:3])}), adapted to your data.")
    q = " One question: what does success look like for you in the first month?"
    return opening + plan + (q if style == "specific_q" else "")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    if OUT.exists():
        shutil.rmtree(OUT)
    manifest = {"synthetic": True, "generator": "scripts/generate_personas.py", "seed": args.seed, "personas": {}}
    for pkey, persona in PERSONAS.items():
        d = OUT / pkey
        (d / "case_studies").mkdir(parents=True)
        (d / "repos").mkdir()
        projects = make_projects(pkey, persona, rng)
        for pr in projects:
            write_case_study(d, pr)
            write_readme(d, pr)
        # CV (markdown; the loader also accepts PDF CVs)
        skills = sorted({s for a in persona["archetypes"] for s in a["explicit"]})
        cv = front_matter({"id": f"cv:{pkey}", "type": "cv", "persona": pkey, "skills": skills, "date": "2026-09-01", "synthetic": True})
        cv += f"# {persona['name']} (synthetic persona)\n\n{persona['headline']}\n\n{persona['location']} · {persona['years']} years experience\n\n"
        cv += "## Skills\n" + ", ".join(skills) + "\n\n## Selected projects\n"
        cv += "\n".join(f"- {p['title']} ({p['year']}): {p['metric']}" for p in projects[:8]) + "\n"
        (d / "cv.md").write_text(cv, encoding="utf-8")
        # Reviews (one per ~2/3 of projects)
        reviews = []
        for pr in projects:
            if rng.random() < 0.7:
                stars = rng.choice([5, 5, 5, 4, 4, 3])
                text = {5: f"Excellent work on our {pr['archetype'].replace('_', ' ')}. Communicated clearly and {pr['metric']}.",
                        4: f"Good delivery of the {pr['archetype'].replace('_', ' ')}; a few delays but solid result.",
                        3: "Work was completed, communication could be better."}[stars]
                reviews.append({"id": f"review:{pr['id']}", "type": "review", "persona": pkey, "project": pr["id"], "stars": stars,
                                "text": text, "client_industry": pr["industry"], "date": f"{pr['year']}-09-01", "synthetic": True})
        (d / "reviews.jsonl").write_text("\n".join(json.dumps(r) for r in reviews) + "\n", encoding="utf-8")
        # Past proposals with outcomes; outcome depends on style + relevance (hidden "truth" of what works)
        props = []
        for n in range(150):
            pr = rng.choice(projects)
            relevant = rng.random() < 0.7
            style = rng.choices(["generic", "specific", "specific_q"], weights=[0.35, 0.4, 0.25])[0]
            job_title = f"{'Need' if rng.random() < .5 else 'Looking for'} {pr['archetype'].replace('_', ' ')} expert" if relevant \
                else f"{rng.choice(['Quick fix', 'Help with', 'Small task'])}: {rng.choice(['website bug', 'spreadsheet', 'API issue', 'report'])}"
            base = {"generic": 0.12, "specific": 0.42, "specific_q": 0.55}[style] * (1.0 if relevant else 0.4)
            r = rng.random()
            outcome = "won" if r < base * 0.45 else ("replied" if r < base else "ignored")
            props.append({"id": f"proposal:{pkey}-{n:03d}", "type": "proposal", "persona": pkey, "project": pr["id"] if relevant else None,
                          "job_title": job_title, "text": proposal_text(pr, job_title, style, rng), "style": style, "outcome": outcome,
                          "skills": pr["explicit"] if relevant else [], "client_industry": pr["industry"],
                          "date": f"{rng.choice([2023, 2024, 2025, 2026])}-{rng.randint(1, 12):02d}-15", "synthetic": True})
        (d / "proposals.jsonl").write_text("\n".join(json.dumps(p) for p in props) + "\n", encoding="utf-8")
        profile = {"persona": pkey, "name": persona["name"], "headline": persona["headline"], "rate_floor": persona["rate_floor"],
                   "target_rate": persona["target_rate"], "skills": skills, "synthetic": True}
        (d / "profile.json").write_text(json.dumps(profile, indent=2), encoding="utf-8")
        (d / "projects.json").write_text(json.dumps(projects, indent=2), encoding="utf-8")
        manifest["personas"][pkey] = {"projects": len(projects), "proposals": len(props), "reviews": len(reviews),
                                      "outcomes": {o: sum(p["outcome"] == o for p in props) for o in ("won", "replied", "ignored")}}
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
