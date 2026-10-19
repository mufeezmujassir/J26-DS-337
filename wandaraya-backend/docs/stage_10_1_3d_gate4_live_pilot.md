# Stage 10.1.3D Gate 4 — Controlled Homepage Acquisition and Discovery

**Status:** AWAITING_RESEARCHER_EXECUTION_WITH_GATE4_CAPTURE.

The prior Gate 3 live response proved that the homepage request returned a
content hash. It did not retain the HTML or HTTP metadata needed to make
measured extraction claims, so Gate 4 does not fabricate page title, metadata,
link counts, status, redirects, content type, response size, or timestamp.

The Gate 4-capable command remains explicitly researcher initiated. It fetches
only the exact approved homepage, writes review-only reports after a successful
response, and does not follow candidates, modify attractions, create embeddings,
or write Qdrant.

```cmd
docker exec -it wandaraya-api python -m scripts.run_srilanka_tourism_pilot --config config/srilanka_tourism_pilot.local.json
docker exec -it wandaraya-api python -m scripts.run_srilanka_tourism_pilot --config config/srilanka_tourism_pilot.local.json --execute --confirm-execute
```

The second command reports requested/final URL, status, redirect history,
content type, byte count, timestamp and SHA-256. It produces a review-only
homepage extraction report and a normalized/deduplicated internal URL inventory.
Heuristic URL categories are labels for researcher review, never fetch approval.
