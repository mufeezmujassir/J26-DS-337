from __future__ import annotations

from datetime import date, datetime, time, timedelta
from math import asin, cos, radians, sin, sqrt
from typing import Any
from zoneinfo import ZoneInfo

from langgraph.types import interrupt

from app.agents.recommendation_graph.schemas.intent import TravelIntent
from app.agents.recommendation_graph.services.llm_service import IntentExtractionService
from app.agents.recommendation_graph.state import RecommendationGraphState


PERIOD_TIMES = {"morning": "09:00", "afternoon": "14:00", "evening": "18:00", "night": "20:00"}
PERIOD_END_TIMES = {"morning": "13:00", "afternoon": "18:00", "evening": "21:30", "night": "23:30"}

_OUTDOOR_TERMS = {
    "beach", "coastal", "swimming", "water & marine", "surf", "fishing",
    "outdoor", "park", "fort", "hiking", "trekking", "safari", "wildlife",
    "nature & landscapes", "scenic", "monument", "junction", "statue",
    "sightseeing", "archaeolog", "nursery", "garden", "agriculture",
    "plantation", "farm",
}
_INDOOR_TERMS = {
    "museum", "cultural center", "gallery", "spa", "wellness", "restaurant",
    "culinary", "shopping", "library", "theatre", "theater", "cinema", "karaoke",
}


def _outdoor_exposure(candidate: dict[str, Any]) -> bool:
    values = [
        candidate.get("attraction_name", ""),
        *candidate.get("categories", []),
        *candidate.get("activities", []),
    ]
    text = " ".join(str(value).casefold() for value in values if value)
    strong_outdoor = any(term in text for term in {
        "beach", "coastal", "swimming", "water & marine", "surf", "fishing",
        "hiking", "trekking", "safari", "wildlife", "fort", "monument",
        "junction", "statue", "nursery", "garden", "agriculture", "plantation", "farm",
    })
    if strong_outdoor:
        return True
    if any(term in text for term in _INDOOR_TERMS):
        return False
    return any(term in text for term in _OUTDOOR_TERMS)


def _weather_rejection(candidate: dict[str, Any]) -> dict[str, Any] | None:
    """Return an explainable live-weather rejection for exposed outdoor places."""
    if not _outdoor_exposure(candidate):
        return None
    weather = (candidate.get("evidence") or {}).get("weather") or {}
    if weather.get("status") not in {"AVAILABLE", "PARTIALLY_AVAILABLE"}:
        return None
    conditions = (weather.get("details") or {}).get("conditions") or {}
    if conditions.get("actual_source") != "openweathermap":
        # Monthly model/climatology values are planning evidence and must not
        # be treated as a day-specific reason to reject an attraction.
        return None
    rainfall = conditions.get("rainfall_mm")
    probability = conditions.get("precipitation_probability_max")
    descriptions = [
        str(value).strip()
        for value in ((conditions.get("provenance") or {}).get("weather_descriptions") or [])
        if str(value).strip()
    ]
    adverse_description = any(
        token in description.casefold()
        for description in descriptions
        for token in ("rain", "storm", "thunder", "squall")
    )
    adverse = (
        (probability is not None and float(probability) >= 0.70)
        or (rainfall is not None and float(rainfall) >= 10.0)
        or adverse_description
    )
    if not adverse:
        return None
    weather_parts = []
    if descriptions:
        weather_parts.append(", ".join(dict.fromkeys(descriptions)))
    if probability is not None:
        weather_parts.append(f"{float(probability) * 100:.0f}% precipitation probability")
    if rainfall is not None:
        weather_parts.append(f"{float(rainfall):.1f} mm across available forecast intervals")
    weather_summary = "; ".join(weather_parts) or "adverse live weather"
    location = ", ".join(
        value for value in (candidate.get("city"), candidate.get("district_name")) if value
    ) or None
    return {
        "attraction_id": candidate["attraction_id"],
        "attraction_name": candidate["attraction_name"],
        "location": location,
        "weather_summary": weather_summary,
        "reason": (
            "Not recommended for the requested outdoor visit because the live forecast "
            f"indicates {weather_summary}. Prefer a sheltered or indoor alternative."
        ),
    }


def _expected_behavior(evidence: dict[str, Any]) -> str:
    """Summarize all four evidence layers without inventing unavailable facts."""
    parts: list[str] = []
    weather = evidence.get("weather") or {}
    conditions = (weather.get("details") or {}).get("conditions") or {}
    if weather.get("status") in {"AVAILABLE", "PARTIALLY_AVAILABLE"}:
        minimum = conditions.get("temperature_min_c")
        maximum = conditions.get("temperature_max_c")
        rainfall = conditions.get("rainfall_mm")
        period = conditions.get("rainfall_period")
        values = []
        if minimum is not None and maximum is not None:
            values.append(f"{float(minimum):.1f}–{float(maximum):.1f}°C")
        if rainfall is not None:
            label = "monthly rainfall" if period in {"calendar_month", "monthly_total", "historical_calendar_month_mean"} else "forecast rainfall"
            values.append(f"{float(rainfall):.1f} mm {label}")
        parts.append("Weather: " + (", ".join(values) + ". " if values else "") + weather.get("explanation", "Weather evidence available."))
    else:
        parts.append("Weather: " + weather.get("explanation", "No verified weather evidence is available."))

    labels = (
        ("Time/opening", "time_of_day"),
        ("Seasonality", "historical_seasonality"),
        ("Holiday/event", "holiday_event"),
    )
    for label, key in labels:
        item = evidence.get(key) or {}
        parts.append(f"{label}: {item.get('explanation') or 'No verified evidence is available for this layer.'}")
    return "\n".join(parts)


def _distance_km(left: dict[str, Any], right: dict[str, Any]) -> float | None:
    values = (left.get("latitude"), left.get("longitude"), right.get("latitude"), right.get("longitude"))
    if any(value is None for value in values):
        return None
    lat1, lon1, lat2, lon2 = (radians(float(value)) for value in values)
    delta_lat, delta_lon = lat2 - lat1, lon2 - lon1
    value = sin(delta_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    return 6371.0 * 2 * asin(sqrt(value))


def _build_itinerary(state: RecommendationGraphState, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not candidates or not state.get("travel_date"):
        return []
    visit_date = date.fromisoformat(state["travel_date"])
    period = state.get("approximate_time_period")
    start_text = state.get("travel_time") or PERIOD_TIMES.get(period or "", "09:00")
    current = datetime.combine(visit_date, time.fromisoformat(start_text), tzinfo=ZoneInfo("Asia/Colombo"))
    if state.get("travel_end_time"):
        window_end = datetime.combine(
            visit_date, time.fromisoformat(state["travel_end_time"]), tzinfo=ZoneInfo("Asia/Colombo")
        )
    elif period in PERIOD_END_TIMES:
        window_end = datetime.combine(
            visit_date, time.fromisoformat(PERIOD_END_TIMES[period]), tzinfo=ZoneInfo("Asia/Colombo")
        )
    else:
        window_end = current + timedelta(hours=4)

    eligible = []
    for item in candidates:
        time_evidence = (item.get("evidence") or {}).get("time_of_day") or {}
        opening_status = (time_evidence.get("details") or {}).get("opening_status")
        if opening_status == "CLOSED" or float(item.get("final_experimental_context_score") or 0) <= 0:
            continue
        eligible.append(item)
    if not eligible:
        return []

    requested = [*state.get("requested_activities", []), *state.get("user_interests", [])]
    explicit_terms = {value.casefold() for value in requested if value}
    requested_label = ", ".join(dict.fromkeys(requested)) or "travel preferences"
    selected = [eligible.pop(0)]
    while eligible and len(selected) < 3:
        previous = selected[-1]
        nearby = []
        for item in eligible:
            distance = _distance_km(previous, item)
            if distance is None or distance <= 30:
                nearby.append((item, distance))
        if not nearby:
            break
        directly_named = [
            pair for pair in nearby
            if any(term in pair[0].get("attraction_name", "").casefold() for term in explicit_terms)
        ]
        if directly_named:
            nearby = directly_named
        elif any(
            any(term in item.get("attraction_name", "").casefold() for term in explicit_terms)
            for item in eligible
        ):
            # Do not add an indirectly tagged stop just to fill the itinerary
            # when the remaining direct matches would require an unrealistic
            # cross-district transfer within the requested time window.
            break
        next_item, _ = max(
            nearby,
            key=lambda pair: (
                float(pair[0].get("final_experimental_context_score") or 0)
                + (
                    0.12
                    if any(term in pair[0].get("attraction_name", "").casefold() for term in explicit_terms)
                    else 0
                )
                - (pair[1] or 8) * 0.004
            ),
        )
        selected.append(next_item)
        eligible.remove(next_item)

    itinerary: list[dict[str, Any]] = []
    previous = None
    for item in selected:
        transfer_minutes = 0
        transfer_note = None
        if previous is not None:
            distance = _distance_km(previous, item)
            if distance is not None:
                transfer_minutes = max(10, round((distance * 1.3 / 30 * 60) / 5) * 5)
                transfer_note = f"Approximately {distance:.1f} km straight-line separation; travel time is an estimate."
            else:
                transfer_minutes = 20
                transfer_note = "Travel time is estimated because route evidence is unavailable."
            current += timedelta(minutes=transfer_minutes)
        stop_end = current + timedelta(minutes=60)
        if stop_end > window_end:
            break
        evidence = item.get("evidence") or {}
        available_layers = [
            name.replace("_", " ")
            for name, value in evidence.items()
            if (value or {}).get("status") in {"AVAILABLE", "PARTIALLY_AVAILABLE"}
        ]
        location = ", ".join(
            value for value in (item.get("city"), item.get("district_name")) if value
        ) or None
        itinerary.append({
            "order": len(itinerary) + 1,
            "visit_date": visit_date.isoformat(),
            "start_time": current.strftime("%H:%M"),
            "end_time": stop_end.strftime("%H:%M"),
            "attraction_id": item["attraction_id"],
            "attraction_name": item["attraction_name"],
            "location": location,
            "description": item.get("description"),
            "expected_behavior": _expected_behavior(evidence),
            "reason": (
                f"Matches the requested {requested_label}. "
                + (f"The schedule also uses available {', '.join(available_layers)} evidence."
                   if available_layers else "It is ordered by semantic relevance because contextual evidence is limited.")
            ),
            "transfer_from_previous_minutes": transfer_minutes,
            "transfer_note": transfer_note,
        })
        current = stop_end
        previous = item
    return itinerary


def _merge_intents(previous: dict[str, Any], current: TravelIntent) -> TravelIntent:
    # A complete trip request starts a new recommendation inside the same chat
    # session. Do not leak interests from an earlier request (for example,
    # "beach" or "photography") into the new itinerary. Partial clarification
    # answers still merge with the pending request below.
    if (
        current.destination_text
        and current.travel_date
        and (current.travel_time or current.approximate_time_period)
    ):
        return current
    merged = dict(previous)
    incoming = current.model_dump()
    for key, value in incoming.items():
        if key == "query":
            merged[key] = value
        elif isinstance(value, list):
            merged[key] = list(dict.fromkeys([*(merged.get(key) or []), *value]))
        elif isinstance(value, dict):
            merged[key] = {**(merged.get(key) or {}), **value}
        elif value is not None:
            merged[key] = value
    return TravelIntent.model_validate(merged)


class RecommendationGraphNodes:
    def __init__(self, *, intent_service: IntentExtractionService, destination_tool, activity_tool,
                 recommendation_tool, max_clarification_turns: int):
        self.intent_service = intent_service
        self.destination_tool = destination_tool
        self.activity_tool = activity_tool
        self.recommendation_tool = recommendation_tool
        self.max_clarification_turns = max_clarification_turns

    async def parse_intent(self, state: RecommendationGraphState) -> dict[str, Any]:
        trusted_now = datetime.fromisoformat(state["trusted_current_datetime"])
        current, warnings = await self.intent_service.extract(state["user_message"], trusted_now)
        if "destination" in state.get("missing_fields", []) and "Clarification response:" in state["user_message"]:
            answer = state["user_message"].rsplit("Clarification response:", 1)[1].strip()
            current.destination_text = answer[:120]
        intent = _merge_intents(state.get("intent", {}), current)
        return {
            "intent": intent.model_dump(), "query": intent.query,
            "destination_text": intent.destination_text, "travel_date": intent.travel_date,
            "travel_time": intent.travel_time, "travel_end_time": intent.travel_end_time,
            "approximate_time_period": intent.approximate_time_period,
            "requested_activities": intent.requested_activities, "user_interests": intent.user_interests,
            "user_preferences": intent.user_preferences, "group_preferences": intent.group_preferences,
            "travel_constraints": intent.travel_constraints, "warnings": warnings,
            "nodes_executed": ["parse_intent"], "clarification_required": False,
            "clarification_question": None,
        }

    async def validate_request(self, state: RecommendationGraphState) -> dict[str, Any]:
        missing = []
        if not state.get("destination_text"):
            missing.append("destination")
        if not state.get("travel_date"):
            missing.append("travel_date")
        if not state.get("travel_time") and not state.get("approximate_time_period"):
            missing.append("travel_time")
        if missing and state.get("clarification_turns", 0) >= self.max_clarification_turns:
            return {"missing_fields": missing, "graph_status": "FAILED",
                    "errors": [{"code": "CLARIFICATION_LIMIT_REACHED", "message": "Required travel details remain missing."}],
                    "nodes_executed": ["validate_request"]}
        questions = {
            "destination": "Which Sri Lankan destination or district should I search near?",
            "travel_date": "What date are you planning to visit? You can say today, tomorrow, or YYYY-MM-DD.",
            "travel_time": "What time will you visit? An exact time or morning/afternoon/evening/night is enough.",
        }
        question = questions[missing[0]] if missing else None
        return {"missing_fields": missing, "clarification_required": bool(missing),
                "clarification_question": question,
                "graph_status": "CLARIFICATION_REQUIRED" if missing else "RUNNING",
                "nodes_executed": ["validate_request"]}

    async def clarify_request(self, state: RecommendationGraphState) -> dict[str, Any]:
        answer = interrupt({"session_id": state["session_id"], "question": state["clarification_question"],
                            "missing_fields": state.get("missing_fields", [])})
        if not isinstance(answer, str) or not answer.strip():
            answer = "No clarification supplied"
        combined = f'{state.get("query") or state["user_message"]}\nClarification response: {answer.strip()}'[:2000]
        return {"user_message": combined, "clarification_turns": state.get("clarification_turns", 0) + 1,
                "clarification_required": False, "nodes_executed": ["clarify_request"]}

    async def resolve_destination(self, state: RecommendationGraphState) -> dict[str, Any]:
        try:
            result = await self.destination_tool.ainvoke({"destination_text": state["destination_text"]})
        except Exception as exc:
            return {"graph_status": "FAILED", "destination_id": None,
                    "errors": [{"code": "DESTINATION_RESOLUTION_FAILED", "message": str(exc), "type": type(exc).__name__}],
                    "tool_calls": ["resolve_sri_lanka_destination"], "nodes_executed": ["resolve_destination"]}
        if result["status"] == "RESOLVED":
            return {"destination_id": result["district_id"], "missing_fields": [],
                    "tool_calls": ["resolve_sri_lanka_destination"], "nodes_executed": ["resolve_destination"]}
        if state.get("clarification_turns", 0) >= self.max_clarification_turns:
            return {"destination_id": None, "graph_status": "FAILED", "clarification_required": False,
                    "errors": [{"code": "DESTINATION_CLARIFICATION_LIMIT_REACHED", "message": result.get("message", "Destination was not resolved.")}],
                    "tool_calls": ["resolve_sri_lanka_destination"], "nodes_executed": ["resolve_destination"]}
        return {"destination_id": None, "missing_fields": ["destination"], "clarification_required": True,
                "clarification_question": result.get("message") or "Please provide a more specific Sri Lankan district.",
                "graph_status": "CLARIFICATION_REQUIRED", "tool_calls": ["resolve_sri_lanka_destination"],
                "nodes_executed": ["resolve_destination"]}

    async def resolve_activity(self, state: RecommendationGraphState) -> dict[str, Any]:
        try:
            result = await self.activity_tool.ainvoke({"activity_terms": state.get("requested_activities", [])})
        except Exception as exc:
            return {"activity_type_id": None,
                    "warnings": [f"Activity resolution failed; recommendation continues without an activity filter ({type(exc).__name__})."],
                    "tool_calls": ["resolve_tourism_activity"], "nodes_executed": ["resolve_activity"]}
        warnings = []
        if result["status"] == "UNSUPPORTED":
            warnings.append(result["message"] + " Recommendation continues without an activity taxonomy filter.")
        return {"activity_type_id": result.get("activity_type_id"), "warnings": warnings,
                "tool_calls": ["resolve_tourism_activity"], "nodes_executed": ["resolve_activity"]}

    async def run_recommendation(self, state: RecommendationGraphState) -> dict[str, Any]:
        clock = state.get("travel_time")
        warnings = []
        if not clock:
            period = state["approximate_time_period"]
            clock = PERIOD_TIMES[period]
            warnings.append(f"Approximate period '{period}' was represented as {clock} Asia/Colombo for deterministic scoring.")
        travel_datetime = datetime.combine(
            date.fromisoformat(state["travel_date"]), time.fromisoformat(clock), tzinfo=ZoneInfo("Asia/Colombo")
        )
        request = {
            "query": state.get("query") or state["user_message"],
            "destination_district_id": state["destination_id"],
            "travel_datetime": travel_datetime.isoformat(), "activity_type_id": state.get("activity_type_id"),
            "requested_activities": state.get("requested_activities", []),
            "interests": state.get("user_interests", []), "user_preferences": state.get("user_preferences", {}),
            "group_preferences": state.get("group_preferences", {}), "constraints": state.get("travel_constraints", {}),
            "contextual_metadata": {"agent_workflow": "stage12_6_langgraph"},
            "limit": state["result_limit"], "candidate_pool_size": state["candidate_limit"],
            "configuration": state["reranker_configuration"], "experimental_evaluation_mode": True,
        }
        try:
            response = await self.recommendation_tool.ainvoke(request)
            return {"recommendation_request": request, "recommendation_response": response, "warnings": warnings,
                    "tool_calls": ["run_unified_context_recommendation"], "nodes_executed": ["run_recommendation"]}
        except Exception as exc:
            return {"recommendation_request": request, "graph_status": "FAILED", "warnings": warnings,
                    "errors": [{"code": "RECOMMENDATION_FAILED", "message": str(exc), "type": type(exc).__name__}],
                    "tool_calls": ["run_unified_context_recommendation"], "nodes_executed": ["run_recommendation"]}

    async def verify_results(self, state: RecommendationGraphState) -> dict[str, Any]:
        response = state.get("recommendation_response") or {}
        candidates = response.get("candidates", [])
        errors = []
        ids = [item.get("attraction_id") for item in candidates]
        if len(ids) != len(set(ids)):
            errors.append({"code": "DUPLICATE_CANDIDATE", "message": "Recommendation result contains duplicate attraction IDs."})
        for item in candidates:
            score = item.get("final_experimental_context_score")
            if score is None or not 0 <= score <= 1:
                errors.append({"code": "INVALID_SCORE", "message": f"Invalid score for attraction {item.get('attraction_id')}."})
        if response and response.get("production_candidate_order") != response.get("original_candidate_order"):
            errors.append({"code": "PRODUCTION_ORDER_CHANGED", "message": "Safety invariant violation: production ordering changed."})
        status = "FAILED" if errors or state.get("errors") else ("PARTIAL" if response.get("errors") else "COMPLETED")
        missing = {item["attraction_id"]: item.get("explanation", {}).get("missing_dimensions", []) for item in candidates}
        return {"verification": {"candidate_count": len(candidates), "missing_dimensions": missing},
                "graph_status": status, "errors": errors, "nodes_executed": ["verify_results"]}

    async def compose_response(self, state: RecommendationGraphState) -> dict[str, Any]:
        response = state.get("recommendation_response") or {}
        candidates = response.get("candidates", [])
        not_recommended = [
            rejected for item in candidates
            if (rejected := _weather_rejection(item)) is not None
        ]
        rejected_ids = {item["attraction_id"] for item in not_recommended}
        weather_safe_candidates = [
            item for item in candidates if item.get("attraction_id") not in rejected_ids
        ]
        itinerary = _build_itinerary(state, weather_safe_candidates)
        if state.get("graph_status") == "FAILED":
            text = "I could not complete the experimental recommendation safely. Review the reported errors and try again."
        elif not candidates:
            text = "No matching attractions were returned for the verified destination and travel context."
        elif itinerary:
            if not_recommended:
                text = (
                    f"Live weather is unsuitable for {len(not_recommended)} outdoor option(s), so I built a "
                    f"{len(itinerary)}-stop itinerary using safer indoor or sheltered alternatives for "
                    f"{state['travel_date']} starting at {itinerary[0]['start_time']}. "
                    "The affected outdoor places are listed separately below."
                )
            else:
                text = (
                    f"I found {len(candidates)} directly relevant place(s) and built a "
                    f"{len(itinerary)}-stop itinerary for {state['travel_date']} starting at "
                    f"{itinerary[0]['start_time']}. Closed places were excluded from the schedule."
                )
        elif not_recommended:
            text = (
                "The matching outdoor places are not recommended for the requested time because of adverse "
                "live weather, and no sufficiently relevant sheltered alternative was available."
            )
        else:
            text = (
                f"I found {len(candidates)} directly relevant place(s), but there was not enough verified "
                "opening-time evidence to construct a safe itinerary for the requested window."
            )
        final = {
            "session_id": state["session_id"], "request_id": state["request_id"],
            "graph_status": state.get("graph_status", "FAILED"), "parsed_intent": state.get("intent"),
            "clarification_required": False, "clarification_question": None,
            "reranker_configuration": state["reranker_configuration"], "recommendations": candidates,
            "itinerary": itinerary,
            "not_recommended": not_recommended,
            "original_candidate_order": response.get("original_candidate_order", []),
            "experimental_candidate_order": response.get("experimental_candidate_order", []),
            "production_candidate_order": response.get("production_candidate_order", []),
            "missing_dimensions": state.get("verification", {}).get("missing_dimensions", {}),
            "human_readable_response": text, "errors": [*state.get("errors", []), *response.get("errors", [])],
            "warnings": state.get("warnings", []), "nodes_executed": [*state.get("nodes_executed", []), "compose_response"],
            "tool_calls": state.get("tool_calls", []),
        }
        return {"final_response": final, "nodes_executed": ["compose_response"]}
