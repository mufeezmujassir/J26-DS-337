# Stage 10.1.3E Gate 5B — Controlled Multi-Page Acquisition

Gate 5B separates source permission from the researcher approval of each exact
follow-up URL. The homepage approval does not approve any second page. The first
pilot is capped at three URLs; each canonical URL must exist in the Gate 5A
manifest and be explicitly marked `approved_for_pilot`.

Create a researcher-owned local plan from
`config/srilanka_tourism_gate5b_plan.example.json`. It needs an approval
reference and timezone-aware execution timestamp.

Offline plan validation makes **zero** network requests:

```cmd
docker exec -it wandaraya-api python -m scripts.run_srilanka_tourism_gate5b --authorization-config config/srilanka_tourism_pilot.local.json --plan config/srilanka_tourism_gate5b_plan.local.json
```

Only after an empty `errors` list and separate researcher review:

```cmd
docker exec -it wandaraya-api python -m scripts.run_srilanka_tourism_gate5b --authorization-config config/srilanka_tourism_pilot.local.json --plan config/srilanka_tourism_gate5b_plan.local.json --execute --confirm-execute
```

To extract a previously captured HTML file without refetching it, preserve its
original timezone-aware retrieval time and run:

```cmd
docker exec -it wandaraya-api python -m scripts.run_srilanka_tourism_gate5b --authorization-config config/srilanka_tourism_pilot.local.json --plan config/srilanka_tourism_gate5b_plan.local.json --extract-html data/review/captured_page.html --captured-url https://srilanka.travel/attractions --retrieved-at 2026-10-16T10:30:00+05:30
```

Execution retains the HTTPS/domain/exact URL, timeout, one-at-a-time,
three-second interval, single retry, response-size, redirect, and content-type
controls. It writes review artifacts only; it does not write attractions,
embeddings, Qdrant, or Airflow state.
