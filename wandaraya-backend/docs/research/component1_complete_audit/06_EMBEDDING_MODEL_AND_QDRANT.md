# Embedding Model and Qdrant

The verified model is `BAAI/bge-large-en-v1.5`, producing 1,024-dimensional normalized vectors (`app/config.py:14`; `embedding_service.py:18-70`). A Sentence Transformer converts the assembled semantic document and query into dense vectors. No fine-tuning or local comparative embedding benchmark was found.

Cosine similarity is `cos(q,d)=(q·d)/(||q|| ||d||)`. With normalized vectors this is the dot product. Qdrant uses `Distance.COSINE`; the indexer rejects a vector whose length is not 1,024 before upsert (`qdrant_indexer.py:39-78`).

Active runtime configuration (B): collection `sri_lanka_attractions_staging`, 6,120 points, green, 1,024-D cosine, one shard/replica, HNSW `m=16`, `ef_construct=100`, `full_scan_threshold=10000`, on-disk payload enabled. `indexed_vectors_count=0` is consistent with a collection below that full-scan threshold and is not by itself proof of missing vectors.

Parameter effects:

| Parameter | Current | Effect of change |
|---|---:|---|
| model | BGE large EN v1.5 | changing requires full re-embedding and quality re-evaluation |
| dimension | 1,024 | must match collection; mismatch is rejected |
| normalization | true | supports stable cosine/dot interpretation |
| distance | cosine | changing alters score geometry and requires a new compatible collection |
| query limit | request-controlled | higher improves candidate recall but increases hydration/context cost |
| collection | environment-dependent | wrong name causes empty/error or targets stale data |
| HNSW `m`, `ef_construct` | 16, 100 | higher normally increases index memory/build time and recall; not changed by audit |

Safe checks:

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/knowledge-base/status
Invoke-RestMethod 'http://localhost:8000/api/v1/knowledge-base/semantic-search?query=quiet%20beach&limit=5'
docker compose ps
```

Do not use the legacy host Qdrant result as the active system result. If the model/dimension changes, create and validate a new collection, re-embed every active record, switch only after parity checks, and retain rollback. Those operations were intentionally not performed.

