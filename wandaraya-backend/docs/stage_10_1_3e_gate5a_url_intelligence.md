# Stage 10.1.3E Gate 5A — Tourism URL Intelligence

Gate 5A is an offline transformation of the measured Gate 4 homepage inventory.
It does not request a page, change the URL allowlist, access PostgreSQL, write
attractions, generate embeddings, update Qdrant, or trigger Airflow.

The inventory preserves each original URL and link text, canonicalizes only the
official `srilanka.travel` / `www.srilanka.travel` hostname variants, removes
fragments, and preserves meaningful query parameters such as `attraction_id`,
`event`, and `information_id`. Unsupported, external and non-HTTP URLs fail
closed.

Classification uses deterministic rules over path, query parameters, and visible
link text. It assigns one primary category and optional secondary Knowledge Base
tags. Categories and scores are for research review only; they are not source
facts, fetch authorization, or tourist recommendation scores.

Build the reports from the saved Gate 4 evidence without network access:

```cmd
docker exec -it wandaraya-api python -m scripts.build_srilanka_tourism_url_inventory
```

Every manifest item remains `discovered_unapproved` and `pending_review`.
Gate 5B must review the proposed items and create a new explicit exact-URL plan
before any follow-up request.
