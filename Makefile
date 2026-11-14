PY ?= python
export PYTHONPATH := $(CURDIR)

.PHONY: dev test eval eval-smoke seed demo lint gigsim api worker web mcp

seed:            ## build synthetic personas + GigSim seed data (+ Kaggle stats if data/raw exists)
	$(PY) scripts/generate_personas.py
	$(PY) scripts/prepare_data.py

dev:             ## run everything locally without Docker (GigSim, MCP servers, API+embedded worker, web dev server)
	$(PY) scripts/dev.py

gigsim:
	GIGSIM_AUTOTICK_SECONDS=30 $(PY) -m uvicorn gigsim.app:app --port 8100
api:
	$(PY) -m uvicorn apps.api.main:app --port 8000
worker:
	arq worker.main.WorkerSettings
mcp:
	$(PY) -m mcp_servers.portfolio.server --http --port 8201 & $(PY) -m mcp_servers.marketplace.server & $(PY) -m mcp_servers.workspace.server
web:
	cd apps/web && npm run dev

test:            ## unit + MCP in-memory + contract tests (slow ones need models/simulator)
	$(PY) -m pytest -q -m "not slow"
	$(PY) -m pytest -q -m slow

eval:            ## full evaluation -> evals/results/*.json (retrieval, decisions, GigSim outcomes + X2, ablation; R&D A/C need an LLM key)
	$(PY) -m evals.runners.rag_eval --limit 60
	$(PY) -m evals.runners.decision_eval
	$(PY) -m evals.runners.gigsim_outcomes --jobs 20
	$(PY) -m evals.runners.ablation --limit 40
	-$(PY) -m evals.runners.tool_design
	-$(PY) -m evals.runners.multiagent_compare
	$(PY) scripts/results_table.py

eval-smoke:      ## 30-job smoke eval used by CI, with failure thresholds
	$(PY) -m evals.runners.decision_eval --smoke
	$(PY) -m evals.runners.gigsim_outcomes --smoke
	$(PY) scripts/check_thresholds.py

demo:            ## seed + start the stack with the reviewer persona preloaded
	$(PY) scripts/dev.py --demo

lint:
	ruff check agent rag mcp_servers apps/api worker evals gigsim scripts
