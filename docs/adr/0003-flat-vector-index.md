# ADR 0003: Exact (flat) vector search with on-disk embedding cache
Status: accepted

Context: each persona corpus has ~200 documents (<1,000 chunks). Decision: numpy exact cosine plus BM25 in process,
with embeddings cached on disk by text hash (incremental re-index embeds only new chunks). Postgres (pgvector
image) is in compose for scale-out, but ANN is unnecessary at this size (≈1 ms queries, no recall loss).
