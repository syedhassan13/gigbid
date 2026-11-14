# ADR 0006: Platform rules and prompts as configuration
Status: accepted

Policy rules live in `data/policy_pack/rules.yaml` (+ overrides in `agent/config.yaml`), thresholds and budgets in
`agent/config.yaml`, and prompts in versioned `agent/prompts/*.md`. The 2 Nov "platform policy update" is
absorbed by editing configuration (see the change-request commit and the report).
