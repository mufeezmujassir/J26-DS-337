# Component 1 PP1 Demonstration Guide

## Preparation

1. Confirm `GET /health` and the knowledge-base status route return successfully.
2. Enable only the research flags documented in `FLUTTER_COMPONENT1_SETUP.md`.
3. Enter the local research token in Settings; do not project or log it.
4. Confirm the Research Insights dashboard shows live knowledge-base values.

## A — Semantic search

On Discover, enter `Peaceful beaches near Mirissa.` Wait for the debounce and show the real returned candidates. Explain that any displayed value is a semantic score, not recommendation accuracy.

Expected structure: attraction ID/name/location/categories/activities and a nullable semantic score. Do not promise a particular attraction or order before the live call.

## B — Context-aware recommendation

Open the preference form, choose a live district, future date and time, verified category interests, group size, and duration. Submit with R3 selected. On Results, expand the evidence and limitations returned for each candidate.

Expected structure: original semantic rank/score, experimental rank/final score, movement, nullable context score, four evidence dimensions, explanation, missing dimensions and limitations.

## C — Time comparison

Repeat the exact request while changing only arrival time. Compare the returned time-of-day evidence. If no opening evidence is available, demonstrate the explicit unavailable state rather than claiming a change.

## D — R0 versus R3

Submit the same query, district, timestamp, interests, group size, duration, limit and candidate-pool settings once under R0 and once under R3. Record each live response before comparing. If external evidence changed between calls, label the comparison as not fully controlled. Rank movement does not establish improved accuracy.

## E — Missing evidence

Open a candidate whose returned evidence has a null score or unavailable status. Show the backend explanation, missing-data indicators and limitations. Point out that the UI does not transform null into zero.

## F — LangGraph clarification

In AI Assistant, start a new session and enter an intentionally incomplete request such as `I want a nature trip.` Show the actual clarification question, answer it, and continue with the same session identifier. The workflow panel may show only node names/statuses returned by the backend; it never invents timestamps or hidden prompts.

## G — Architecture

Open Research Insights → Pipeline. Walk from intent processing through BGE embedding, Qdrant retrieval, PostgreSQL hydration, four context adapters, experimental reranking, and explanation. State clearly that this is a verified architecture view, not a fabricated live trace. Group Emotion is marked Future Integration.

## Failure-safe presentation

If a protected route is disabled, show the 503 state and explain the safety flag. If the backend is offline, show the application's honest connection state. Never substitute fixture candidates during the live demonstration.
