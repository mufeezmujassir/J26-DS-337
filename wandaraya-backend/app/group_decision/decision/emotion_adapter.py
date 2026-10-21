"""Emotion Adapter for Decision Engine.

Attaches emotion signals to structured preference records.
"""

from __future__ import annotations

import logging
from typing import Any
from pydantic import BaseModel

from app.group_decision.conflict.normalize import normalize_name
from app.group_decision.decision.schemas import EmotionSignal, PreferenceRecord

logger = logging.getLogger(__name__)


def attach_emotion(
    records: list[Any],
    message_signals: dict[str, Any],
    policy: str = "max",
) -> list[PreferenceRecord]:
    """Attach EmotionSignal objects to structured preference records based on message_id.

    Args:
        records: List of preference records (dicts or PreferenceRecord instances).
        message_signals: Mapping of message_id to EmotionSignal dict or instance.
        policy: Conflict resolution policy when a member has multiple messages/records
                referencing the same option. Options:
                - 'max' (default): Use the signal with the highest expression intensity.
                - 'latest': Use the signal from the latest message in record order.

    Returns:
        New list of PreferenceRecord instances with emotion field populated.
    """
    if policy not in ("max", "latest"):
        raise ValueError(
            f"Invalid aggregation policy '{policy}'. Allowed policies: 'max', 'latest'."
        )

    # 1. Validate and convert input records to PreferenceRecord models
    validated: list[PreferenceRecord] = []
    for r in records:
        if isinstance(r, PreferenceRecord):
            # Shallow copy to avoid mutating caller's objects
            validated.append(r.model_copy(deep=True))
        elif isinstance(r, dict):
            validated.append(PreferenceRecord.model_validate(r))
        elif isinstance(r, BaseModel):
            validated.append(PreferenceRecord.model_validate(r.model_dump()))
        else:
            raise ValueError(f"Unsupported record type: {type(r)}")

    if not validated:
        return []

    # 2. Extract initial signals by message_id
    # Map (member, category, normalized_option) -> list of (record_index, signal)
    option_signals_map: dict[tuple[str, str, str], list[tuple[int, EmotionSignal | None]]] = {}

    for idx, rec in enumerate(validated):
        signal: EmotionSignal | None = None
        if rec.message_id and rec.message_id in message_signals:
            raw_sig = message_signals[rec.message_id]
            if isinstance(raw_sig, EmotionSignal):
                signal = raw_sig
            elif isinstance(raw_sig, dict):
                signal = EmotionSignal.model_validate(raw_sig)
            else:
                logger.warning("Unrecognized signal type for message_id %s: %s", rec.message_id, type(raw_sig))
        elif rec.emotion is not None:
            # If record already carried an emotion signal
            signal = rec.emotion

        # Extract normalized option name if available
        val = rec.value
        opt_raw = getattr(val, "name", None) or (val.get("name") if isinstance(val, dict) else None)
        if opt_raw:
            c_name = normalize_name(opt_raw, category=rec.category)
            key = (rec.member, rec.category, c_name)
            if key not in option_signals_map:
                option_signals_map[key] = []
            option_signals_map[key].append((idx, signal))

    # 3. Resolve multi-message signals per (member, category, option)
    resolved_signals: dict[tuple[str, str, str], EmotionSignal | None] = {}

    for key, entries in option_signals_map.items():
        non_none_signals = [sig for _, sig in entries if sig is not None]
        if not non_none_signals:
            resolved_signals[key] = None
        elif policy == "max":
            # Highest intensity among member's messages for this option
            best_sig = max(non_none_signals, key=lambda s: s.intensity)
            resolved_signals[key] = best_sig
        else:  # "latest"
            # Signal from latest record that had a signal
            latest_sig = next((sig for _, sig in reversed(entries) if sig is not None), None)
            resolved_signals[key] = latest_sig

    # 4. Populate emotion field in records
    for idx, rec in enumerate(validated):
        val = rec.value
        opt_raw = getattr(val, "name", None) or (val.get("name") if isinstance(val, dict) else None)
        if opt_raw:
            c_name = normalize_name(opt_raw, category=rec.category)
            key = (rec.member, rec.category, c_name)
            target_signal = resolved_signals.get(key)
            rec.emotion = target_signal
        else:
            # Non-named category (e.g. Budget, Schedule)
            if rec.message_id and rec.message_id in message_signals:
                raw_sig = message_signals[rec.message_id]
                rec.emotion = EmotionSignal.model_validate(raw_sig) if isinstance(raw_sig, dict) else raw_sig

    return validated
