# ADR 0004: Open-weight models via Groq for the deployed `open` profile
Status: accepted

Free hosts have no GPU, so the deployment calls hosted open-weight models (gpt-oss-20b for cheap nodes,
gpt-oss-120b for writer/critic/liaison). Embeddings (bge-small-en-v1.5) and the reranker run on CPU (ONNX).
Every node also has a deterministic fallback (profile `offline`), used in CI and as degraded mode.
