# Group Emotion Integration

Status: **DEFERRED / NOT INTEGRATED INTO COMPONENT 1**.

The repository contains `app/group_decision` emotion/decision artifacts belonging to broader group-decision work, but Component 1’s unified context tuple contains only weather, time of day, holiday/event and historical seasonality. `ENABLE_GROUP_EMOTION_CONTEXT=False`, `ENABLE_R4_EXPERIMENTAL_RERANKING=False`, and the Stage 12.6 response contract marks group context deferred. No group-emotion score enters R0-R3.

This boundary is deliberate because the component is incomplete. The audit did not connect, modify or enable it. Component 1 must not claim five active scored dimensions. It has four active evidence dimensions plus a reserved/deferred fifth contract.

Before future integration (E), the system needs an authorized group input contract, consent/privacy rules, identity isolation, calibrated aggregation method, missing-member policy, adversarial/edge-case tests, R4 ablation, and human validation. A future adapter should return explicit availability/provenance rather than silently treating missing group data as neutral.

Evidence: `app/config.py:42-44`, `app/recommendation/unified_context/schemas.py`, `app/agents/recommendation_graph`, and Stage 12.6 group-emotion contract documentation (A/C).

