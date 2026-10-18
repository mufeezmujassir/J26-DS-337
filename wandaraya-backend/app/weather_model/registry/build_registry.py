"""Build or refresh the manual weather-model registry from validation evidence."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from app.weather_model.registry.registry_manager import RegistryManager


VALIDATION_PATH = Path("data/weather/reports/backtesting/model_selection_validation.json")
REGISTRY_PATH = Path("data/weather/reports/registry/weather_model_registry.json")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation-path", type=Path, default=VALIDATION_PATH)
    parser.add_argument("--registry-path", type=Path, default=REGISTRY_PATH)
    arguments = parser.parse_args()

    registry = RegistryManager(arguments.registry_path).rebuild_from_validation_file(
        arguments.validation_path
    )
    evidence = Counter(item.evidence_status for item in registry.entries)
    approval = Counter(item.approval_status for item in registry.entries)
    print("\n=== WEATHER MODEL REGISTRY ===")
    print("Total series:          ", len(registry.entries))
    print("Eligible for review:   ", evidence["eligible_for_review"])
    print("Limited evidence:      ", evidence["limited_evidence"])
    print("Insufficient evidence: ", evidence["insufficient_evidence"])
    print("Production approved:   ", sum(item.production_approved for item in registry.entries))
    print("Pending review:        ", approval["pending_review"])
    print("Registry:", arguments.registry_path)


if __name__ == "__main__":
    main()
