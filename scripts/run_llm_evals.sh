#!/usr/bin/env bash
# LLM-dependent evaluations (need GROQ_API_KEY in .env). Sized for Groq's free tier; raise the sizes on a paid tier.
set -e
export PYTHONPATH=. GIGBID_PROFILE=${GIGBID_PROFILE:-open} PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8
PY=${PY:-.venv/Scripts/python}
$PY scripts/single_agent_demo.py                                   # Part A: one agent, one grounded proposal
$PY -m evals.runners.tool_design                                   # R&D A: 40 tasks x 3 tool sets
$PY -m evals.runners.gigsim_outcomes --jobs ${JOBS:-4} --out gigsim_outcomes_open   # LLM writer: claims, replies, injection, cost
$PY -m evals.runners.multiagent_compare --jobs ${MAC_JOBS:-4}      # R&D C: ReAct vs supervisor vs graph
$PY -m evals.runners.judge_calibration --make-sheet                # 30 proposals + LLM judge scores -> YOU fill human_score
$PY scripts/results_table.py && $PY scripts/build_report.py
echo "Now fill human_score in evals/datasets/judge_labels.csv, then: $PY -m evals.runners.judge_calibration --score && $PY scripts/build_report.py"
