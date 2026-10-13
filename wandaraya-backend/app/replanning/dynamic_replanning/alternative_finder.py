"""Alternative finder for the Dynamic Replanning module.

Calls the external agents to retrieve replacement activities:

- Component 1 (Destination Agent) - returns alternatives for affected
  elements at Step/Day/Plan levels.
- Component 2 (Transport Agent) - called additionally at Plan-Level to
  update transport arrangements.

All HTTP calls are routed through utils helpers, so endpoints/timeouts
are read from config.yaml and errors are handled gracefully (never raised).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.replanning.dynamic_replanning.utils import (
    DEFAULT_CONFIG,
    call_component1_api,
    call_component2_api,
    load_config,
)
from app.schemas.replanning import AffectedElement, IntentAnchor

LOGGER = logging.getLogger(__name__)


class AlternativeFinder:
    """Find replacement options for disrupted itinerary elements."""

    def __init__(
        self,
        config: Dict[str, Any] | None = None,
        call_c1: Any | None = None,
        call_c2: Any | None = None,
    ) -> None:
        self._config = config or self._safe_load_config()
        self._call_c1 = call_c1 or call_component1_api
        self._call_c2 = call_c2 or call_component2_api

        replanning_cfg = self._config.get("replanning", {}) or {}
        plan_cfg = replanning_cfg.get("plan_level", {}) or {}
        if isinstance(plan_cfg, dict):
            self._plan_call_c2 = bool(plan_cfg.get("call_component2", True))
        else:
            self._plan_call_c2 = True

        LOGGER.info(
            "AlternativeFinder initialised (call_component2_on_plan=%s)",
            self._plan_call_c2,
        )

    def find_for_step_level(
        self,
        affected: AffectedElement,
        anchor: IntentAnchor,
        context: Dict[str, Any] | None = None,
    ) -> List[dict]:
        context = context or {}
        payload: Dict[str, Any] = {
            "action": "replace_single_activity",
            "affected": affected.model_dump(mode="json"),
            "anchor": anchor.model_dump(mode="json"),
            "context": context,
        }
        response = self._call_c1(payload)
        alternatives = self._extract_alternatives(response)
        LOGGER.info("Step-Level alternatives found: %d", len(alternatives))
        return alternatives

    def find_for_day_level(
        self,
        affected_day: str,
        anchor: IntentAnchor,
        context: Dict[str, Any] | None = None,
    ) -> List[dict]:
        context = context or {}
        context.setdefault("affected_day", affected_day)
        payload: Dict[str, Any] = {
            "action": "replace_full_day",
            "affected": {"day": affected_day},
            "anchor": anchor.model_dump(mode="json"),
            "context": context,
        }
        response = self._call_c1(payload)
        alternatives = self._extract_alternatives(response)
        LOGGER.info("Day-Level alternatives found: %d (day=%s)", len(alternatives), affected_day or "n/a")
        return alternatives

    def find_for_plan_level(
        self,
        disruption: Dict[str, Any],
        anchor: IntentAnchor,
        context: Dict[str, Any] | None = None,
    ) -> List[dict]:
        context = context or {}
        affected = (
            disruption.get("affected_element", {})
            if isinstance(disruption.get("affected_element"), dict)
            else {}
        )
        payload: Dict[str, Any] = {
            "action": "replace_from_disruption_point",
            "affected": affected,
            "anchor": anchor.model_dump(mode="json"),
            "context": context,
        }
        response = self._call_c1(payload)
        alternatives = self._extract_alternatives(response)
        if self._plan_call_c2:
            try:
                self._call_c2(
                    {
                        "disruption_id": disruption.get("disruption_id"),
                        "affected": affected,
                        "alternatives": alternatives,
                        "anchor": anchor.model_dump(mode="json"),
                        "context": context,
                    }
                )
            except Exception as error:  # noqa: BLE001
                LOGGER.warning("Component 2 call failed: %s", error)
        LOGGER.info("Plan-Level alternatives found: %d", len(alternatives))
        return alternatives

    @staticmethod
    def _extract_alternatives(response: Dict[str, Any]) -> List[dict]:
        if not isinstance(response, dict):
            return []
        for key in ("alternatives", "results", "replacements", "activities"):
            if key in response and isinstance(response[key], list):
                return [alt for alt in response[key] if isinstance(alt, dict)]
        return []

    @staticmethod
    def _safe_load_config() -> Dict[str, Any]:
        try:
            return load_config()
        except (FileNotFoundError, ValueError) as error:
            LOGGER.warning("Could not load replanning config (%s), using defaults", error)
            return DEFAULT_CONFIG


__all__ = ["AlternativeFinder"]
