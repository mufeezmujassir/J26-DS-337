"""Pydantic schemas and validation for Step 9: Rule-based Conflict Detector.

Defines schemas for preference records across categories (Destination, Activity,
Budget, Schedule, and auxiliary categories) and schemas for conflict outputs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator, model_validator


ALLOWED_CATEGORIES = {
    "Destination",
    "Activity",
    "Budget",
    "Food",
    "Accommodation",
    "Schedule",
    "Transport",
    "Travel Style",
}

CONFLICT_CATEGORIES = {
    "Destination",
    "Activity",
    "Budget",
    "Schedule",
}

ALLOWED_STANCES = {"positive", "negative", "neutral"}


class DestinationValue(BaseModel):
    """Schema for Destination preference value."""

    name: str = Field(..., description="Destination name (e.g. 'ella')")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Any) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Destination name must be a non-empty string.")
        return v.strip()


class ActivityValue(BaseModel):
    """Schema for Activity preference value."""

    name: str = Field(..., description="Activity name (e.g. 'hiking')")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Any) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Activity name must be a non-empty string.")
        return v.strip()


class BudgetValue(BaseModel):
    """Schema for Budget preference value.

    E.g. 'under 5000' is min=0.0, max=5000.0.
    """

    min: float | None = Field(default=None, description="Minimum budget limit")
    max: float | None = Field(default=None, description="Maximum budget limit")
    currency: str = Field(default="LKR", description="Currency code (e.g. 'LKR')")
    scope: Literal["per_person", "total"] = Field(
        default="per_person",
        description="Budget scope: 'per_person' or 'total'",
    )

    @field_validator("min", "max")
    @classmethod
    def validate_non_negative(cls, v: float | None) -> float | None:
        if v is not None and v < 0:
            raise ValueError("Budget bounds cannot be negative.")
        return v

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Currency must be a non-empty string.")
        return v.strip().upper()

    @model_validator(mode="after")
    def validate_range_order(self) -> BudgetValue:
        if self.min is not None and self.max is not None:
            if self.min > self.max:
                raise ValueError(
                    f"Budget min ({self.min}) cannot exceed max ({self.max})."
                )
        return self


class ScheduleValue(BaseModel):
    """Schema for Schedule preference value."""

    start_date: str | None = Field(
        default=None,
        description="Start date in YYYY-MM-DD format",
    )
    end_date: str | None = Field(
        default=None,
        description="End date in YYYY-MM-DD format",
    )
    time_of_day: Literal["morning", "afternoon", "evening"] | None = Field(
        default=None,
        description="Time of day preference",
    )

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_date_format(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError("Date must be a string in YYYY-MM-DD format or None.")
        v = v.strip()
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(
                f"Date '{v}' is not in valid YYYY-MM-DD format."
            ) from exc
        return v

    @model_validator(mode="after")
    def validate_date_range(self) -> ScheduleValue:
        if self.start_date is not None and self.end_date is not None:
            d_start = datetime.strptime(self.start_date, "%Y-%m-%d")
            d_end = datetime.strptime(self.end_date, "%Y-%m-%d")
            if d_start > d_end:
                raise ValueError(
                    f"Schedule start_date ({self.start_date}) cannot be after end_date ({self.end_date})."
                )
        return self

class EmotionSignal(BaseModel):
    """Schema representing emotion expression signal from intensity estimator."""

    intensity: float = Field(..., ge=0.0, le=1.0, description="Expression intensity 0-1")
    valence_sign: Literal[-1, 0, 1] = Field(..., description="Valence sign: -1, 0, or 1")
    dominant_emotion: str = Field(..., description="Dominant emotion label")
    valence: str | None = Field(default=None, description="Valence category (positive/negative/neutral/ambiguous)")
    components: dict[str, Any] | None = Field(default=None, description="Component breakdown scores")

    @field_validator("dominant_emotion")
    @classmethod
    def validate_dominant_emotion(cls, v: Any) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("dominant_emotion must be a non-empty string.")
        return v.strip().lower()


class PreferenceRecord(BaseModel):
    """Validated representation of an input preference record."""

    member: str = Field(..., description="Group member name/identifier")
    category: str = Field(..., description="Preference category")
    stance: Literal["positive", "negative", "neutral"] = Field(
        ...,
        description="Stance towards the item",
    )
    value: dict[str, Any] | DestinationValue | ActivityValue | BudgetValue | ScheduleValue = Field(
        ...,
        description="Category-specific value dictionary",
    )

    message_id: str | None = Field(
        default=None,
        description="Optional identifier of the source message for emotion association",
    )
    emotion: EmotionSignal | None = Field(
        default=None,
        description="Optional emotion signal matching output of src/intensity/estimator.py",
    )

    @field_validator("member")
    @classmethod
    def validate_member(cls, v: Any) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Member must be a non-empty string.")
        return v.strip()

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: Any) -> str:
        if not isinstance(v, str) or v.strip() not in ALLOWED_CATEGORIES:
            raise ValueError(
                f"Invalid category '{v}'. Allowed categories are: {sorted(ALLOWED_CATEGORIES)}"
            )
        return v.strip()

    @model_validator(mode="after")
    def validate_value_payload(self) -> PreferenceRecord:
        val = self.value
        if isinstance(val, BaseModel):
            val_dict = val.model_dump()
        elif isinstance(val, dict):
            val_dict = val
        else:
            raise ValueError(f"Value must be a dictionary or BaseModel, got {type(val)}")

        cat = self.category
        if cat == "Destination":
            self.value = DestinationValue.model_validate(val_dict)
        elif cat == "Activity":
            self.value = ActivityValue.model_validate(val_dict)
        elif cat == "Budget":
            self.value = BudgetValue.model_validate(val_dict)
        elif cat == "Schedule":
            self.value = ScheduleValue.model_validate(val_dict)
        else:
            # Other allowed categories: Food, Accommodation, Transport, Travel Style
            self.value = val_dict
        return self


class ConflictOutput(BaseModel):
    """Output conflict record model."""

    type: Literal["Destination", "Budget", "Schedule", "Activity"] = Field(
        ...,
        description="Conflict category type",
    )
    severity: Literal["hard", "soft"] = Field(
        ...,
        description="Severity level: 'hard' or 'soft'",
    )
    rule_id: str = Field(..., description="Unique rule identifier")
    members: list[str] = Field(..., description="List of involved members")
    items: dict[str, Any] = Field(..., description="Items/aspects of disagreement")
    explanation: str = Field(..., description="Human-readable explanation of conflict")
    features: dict[str, Any] = Field(
        default_factory=dict,
        description="Numerical features for downstream ML processing",
    )
