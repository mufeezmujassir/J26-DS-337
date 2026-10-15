"""Generate the frozen, seeded disruption-detection dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Allow direct script execution as well as module import.
if __package__ in (None, ""):  # pragma: no cover - script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from app.replanning.disruption_detection.classifiers import (  # noqa: E402
    DATA_DIR,
    FEATURE_NAMES,
    LABEL_DISRUPTION,
    LABEL_NORMAL,
    SEVERITY_LEVELS,
    SEVERITY_NONE,
)

LOGGER = logging.getLogger("generate_disruption_data")

GENERATOR_VERSION = "1.0.0"
DEFAULT_SEED = 42
DEFAULT_NUM_ROWS = 1500

# Target class counts before label noise is applied.
TARGET_COUNTS: Dict[Tuple[str, str], int] = {
    (LABEL_NORMAL, SEVERITY_NONE): 600,   # 40%
    (LABEL_DISRUPTION, "step"): 450,      # 30%
    (LABEL_DISRUPTION, "day"): 300,       # 20%
    (LABEL_DISRUPTION, "plan"): 150,      # 10%
}

# Fraction of rows whose label is deliberately corrupted.
LABEL_NOISE_RATE = 0.05

# Severity ranking (weakest to strongest) used when several rules match.
_SEVERITY_RANK = {SEVERITY_NONE: 0, "step": 1, "day": 2, "plan": 3}


def bootstrap_label(features: Dict[str, Any]) -> Tuple[str, str]:
    """Derive a ``(label, severity)`` pair from a feature vector."""
    severity = SEVERITY_NONE

    rain_duration = float(features.get("rain_duration_hours", 0.0))
    is_outdoor = int(features.get("is_outdoor_activity", 0))
    closure_flag = int(features.get("closure_flag", 0))
    capacity_issue = int(features.get("capacity_issue", 0))
    crowd_level = float(features.get("crowd_level_score", 0.0))
    heat_warning = int(features.get("heat_warning", 0))
    complaint_score = float(features.get("complaint_score", 0.0))
    change_request = int(features.get("change_request", 0))
    gps_deviation = float(features.get("gps_deviation_km", 0.0))
    delay = int(features.get("time_delay_minutes", 0))
    num_affected = int(features.get("num_affected_activities", 0))

    def escalate(level: str) -> None:
        nonlocal severity
        if _SEVERITY_RANK[level] > _SEVERITY_RANK[severity]:
            severity = level

    if rain_duration > 3 and is_outdoor == 1:
        escalate("step")
    if closure_flag == 1:
        escalate("step")
    if capacity_issue == 1 and crowd_level > 0.6:
        escalate("step")
    if heat_warning == 1 and is_outdoor == 1:
        escalate("step")
    if complaint_score > 0.7:
        escalate("step")
    if change_request == 1:
        escalate("day")
    if gps_deviation > 5 or delay > 60:
        escalate("day")
    if num_affected >= 3:
        escalate("plan")

    if severity == SEVERITY_NONE:
        return LABEL_NORMAL, SEVERITY_NONE
    return LABEL_DISRUPTION, severity


def _benign_features(rng: random.Random) -> Dict[str, Any]:
    """Generate a feature vector that matches no bootstrap rule."""
    return {
        "rain_duration_hours": round(rng.uniform(0.0, 3.0), 2),
        "rain_intensity_score": round(rng.uniform(0.0, 0.5), 2),
        "temperature_celsius": round(rng.uniform(15.0, 34.0), 1),
        "heat_warning": 0,
        "is_outdoor_activity": rng.randint(0, 1),
        "closure_flag": 0,
        "capacity_issue": 0,
        "crowd_level_score": round(rng.uniform(0.0, 0.6), 2),
        "complaint_score": round(rng.uniform(0.0, 0.7), 2),
        "change_request": 0,
        "gps_deviation_km": round(rng.uniform(0.0, 5.0), 2),
        "time_delay_minutes": rng.randint(0, 60),
        "num_affected_activities": rng.randint(0, 2),
    }


def _step_features(rng: random.Random, subtype: str) -> Dict[str, Any]:
    """Generate a feature vector matching exactly one step-level rule."""
    features = _benign_features(rng)

    if subtype == "weather":
        features["rain_duration_hours"] = round(rng.uniform(3.5, 8.0), 2)
        features["rain_intensity_score"] = round(rng.uniform(0.6, 1.0), 2)
        features["is_outdoor_activity"] = 1
    elif subtype == "places_closure":
        features["closure_flag"] = 1
    elif subtype == "places_capacity":
        features["capacity_issue"] = 1
        features["crowd_level_score"] = round(rng.uniform(0.65, 1.0), 2)
    elif subtype == "heat":
        features["heat_warning"] = 1
        features["temperature_celsius"] = round(rng.uniform(35.0, 40.0), 1)
        features["is_outdoor_activity"] = 1
    elif subtype == "complaint":
        features["complaint_score"] = round(rng.uniform(0.72, 1.0), 2)
    elif subtype == "mixed":
        features["closure_flag"] = 1
        features["complaint_score"] = round(rng.uniform(0.72, 1.0), 2)
    else:  # pragma: no cover - guarded by callers
        raise ValueError(f"Unknown step subtype: {subtype}")

    return features


def _day_features(rng: random.Random, subtype: str) -> Dict[str, Any]:
    """Generate a feature vector matching a day-level rule."""
    features = _benign_features(rng)

    if subtype == "change_request":
        features["change_request"] = 1
    elif subtype == "gps_deviation":
        features["gps_deviation_km"] = round(rng.uniform(5.5, 10.0), 2)
    elif subtype == "gps_delay":
        features["time_delay_minutes"] = rng.randint(61, 120)
    elif subtype == "mixed":
        features["change_request"] = 1
        features["gps_deviation_km"] = round(rng.uniform(5.5, 10.0), 2)
    else:  # pragma: no cover - guarded by callers
        raise ValueError(f"Unknown day subtype: {subtype}")

    return features


def _plan_features(rng: random.Random, subtype: str) -> Dict[str, Any]:
    """Generate a feature vector matching the plan-level rule."""
    features = _benign_features(rng)
    features["num_affected_activities"] = rng.randint(3, 5)

    if subtype == "mixed":
        features["change_request"] = 1
    return features


# Subtype pools per target class, giving every source good coverage.
_STEP_SUBTYPES = (
    "weather",
    "places_closure",
    "places_capacity",
    "heat",
    "complaint",
    "mixed",
)
_DAY_SUBTYPES = ("change_request", "gps_deviation", "gps_delay", "mixed")
_PLAN_SUBTYPES = ("capacity", "mixed")

# Maps a generated subtype to the disruption source that drives it.
_SUBTYPE_SOURCE = {
    "weather": "weather",
    "heat": "weather",
    "places_closure": "places",
    "places_capacity": "places",
    "complaint": "complaint",
    "change_request": "complaint",
    "gps_deviation": "gps",
    "gps_delay": "gps",
    "capacity": "places",
    "mixed": "mixed",
    "normal": "normal",
}


def _sample_features(
    rng: random.Random, label: str, severity: str
) -> Tuple[Dict[str, Any], str]:
    """Sample a feature vector + source for a target ``(label, severity)``."""
    if label == LABEL_NORMAL:
        return _benign_features(rng), "normal"

    if severity == "step":
        subtype = rng.choice(_STEP_SUBTYPES)
        return _step_features(rng, subtype), _SUBTYPE_SOURCE[subtype]
    if severity == "day":
        subtype = rng.choice(_DAY_SUBTYPES)
        return _day_features(rng, subtype), _SUBTYPE_SOURCE[subtype]
    if severity == "plan":
        subtype = rng.choice(_PLAN_SUBTYPES)
        return _plan_features(rng, subtype), _SUBTYPE_SOURCE[subtype]

    raise ValueError(f"Unknown target class: {(label, severity)}")


def _apply_label_noise(
    rows: List[Dict[str, Any]], rng: random.Random, rate: float
) -> int:
    """Flip the label of ``rate`` fraction of rows; returns the flip count."""
    num_flips = int(round(len(rows) * rate))
    indices = rng.sample(range(len(rows)), num_flips)
    severities = list(SEVERITY_LEVELS)

    for index in indices:
        row = rows[index]
        if row["label"] == LABEL_NORMAL:
            row["label"] = LABEL_DISRUPTION
            row["severity"] = rng.choice(severities)
            row["source"] = "mixed"
        else:
            row["label"] = LABEL_NORMAL
            row["severity"] = SEVERITY_NONE
            row["source"] = "normal"

    return num_flips


def generate_rows(seed: int = DEFAULT_SEED) -> List[Dict[str, Any]]:
    """Generate the full 1,500-row dataset deterministically for ``seed``."""
    rng = random.Random(seed)
    rows: List[Dict[str, Any]] = []

    for (label, severity), count in TARGET_COUNTS.items():
        for _ in range(count):
            features, source = _sample_features(rng, label, severity)
            # Recompute bootstrap labels to keep rules and labels consistent.
            boot_label, boot_severity = bootstrap_label(features)
            if (boot_label, boot_severity) != (label, severity):
                LOGGER.warning(
                    "Bootstrap mismatch: target=(%s,%s) got=(%s,%s)",
                    label,
                    severity,
                    boot_label,
                    boot_severity,
                )
                label, severity = boot_label, boot_severity

            row: Dict[str, Any] = dict(features)
            row["label"] = label
            row["severity"] = severity
            row["source"] = source
            rows.append(row)

    rng.shuffle(rows)
    num_flips = _apply_label_noise(rows, rng, LABEL_NOISE_RATE)
    LOGGER.info(
        "Generated %d rows; applied %d label-noise flips (%.0f%%)",
        len(rows),
        num_flips,
        LABEL_NOISE_RATE * 100,
    )
    return rows


def _proportional_counts(sizes: List[int], target: int) -> List[int]:
    """Allocate ``target`` items across buckets using largest remainders."""
    total = sum(sizes)
    if total == 0:
        return [0 for _ in sizes]

    raw = [size * target / total for size in sizes]
    counts = [int(value) for value in raw]
    remainder = target - sum(counts)

    order = sorted(
        range(len(sizes)),
        key=lambda index: (-(raw[index] - counts[index]), index),
    )
    for index in order[:remainder]:
        counts[index] += 1
    return counts


def stratified_split(
    rows: List[Dict[str, Any]], seed: int = DEFAULT_SEED
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split rows 80/10/10, stratified by ``(label, severity)``."""
    rng = random.Random(seed + 1)
    bucket_keys = sorted(
        {(row["label"], row["severity"]) for row in rows}
    )
    buckets: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for row in rows:
        buckets.setdefault((row["label"], row["severity"]), []).append(row)

    sizes = [len(buckets[key]) for key in bucket_keys]
    dev_counts = _proportional_counts(sizes, 150)
    test_counts = _proportional_counts(sizes, 150)

    train: List[Dict[str, Any]] = []
    dev: List[Dict[str, Any]] = []
    test: List[Dict[str, Any]] = []

    for position, key in enumerate(bucket_keys):
        bucket = buckets[key][:]
        rng.shuffle(bucket)
        n_dev = dev_counts[position]
        n_test = test_counts[position]
        n_train = len(bucket) - n_dev - n_test

        train.extend(bucket[:n_train])
        dev.extend(bucket[n_train:n_train + n_dev])
        test.extend(bucket[n_train + n_dev:])

    for split in (train, dev, test):
        rng.shuffle(split)

    return train, dev, test


def _serialise(rows: List[Dict[str, Any]]) -> str:
    """Render rows as JSON Lines text with a trailing newline."""
    return "".join(
        json.dumps(row, ensure_ascii=False) + "\n" for row in rows
    )


def _count(rows: List[Dict[str, Any]], field: str) -> Dict[str, int]:
    """Count occurrences of each value of ``field`` across ``rows``."""
    counts: Dict[str, int] = {}
    for row in rows:
        value = str(row.get(field, SEVERITY_NONE))
        counts[value] = counts.get(value, 0) + 1
    return counts


def write_dataset(
    rows: List[Dict[str, Any]],
    output_dir: Path,
    seed: int = DEFAULT_SEED,
) -> Dict[str, Any]:
    """Write all dataset files and return the metadata manifest."""
    output_dir.mkdir(parents=True, exist_ok=True)
    train, dev, test = stratified_split(rows, seed)

    head_text = _serialise(rows)
    (output_dir / "simulated_disruptions.jsonl").write_text(
        head_text, encoding="utf-8"
    )
    (output_dir / "train.jsonl").write_text(
        _serialise(train), encoding="utf-8"
    )
    (output_dir / "dev.jsonl").write_text(_serialise(dev), encoding="utf-8")
    (output_dir / "test.jsonl").write_text(_serialise(test), encoding="utf-8")

    dataset_hash = hashlib.sha256(head_text.encode("utf-8")).hexdigest()

    severity_counts = _count(rows, "severity")
    severity_distribution = {
        level: severity_counts.get(level, 0) for level in SEVERITY_LEVELS
    }
    label_distribution = {
        LABEL_NORMAL: _count(rows, "label").get(LABEL_NORMAL, 0),
        LABEL_DISRUPTION: _count(rows, "label").get(LABEL_DISRUPTION, 0),
    }
    source_distribution = _count(rows, "source")

    metadata: Dict[str, Any] = {
        "generator_version": GENERATOR_VERSION,
        "random_seed": seed,
        "num_rows": len(rows),
        "train_rows": len(train),
        "dev_rows": len(dev),
        "test_rows": len(test),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "label_distribution": label_distribution,
        "severity_distribution": severity_distribution,
        "source_distribution": source_distribution,
        "dataset_hash_sha256": dataset_hash,
        "feature_names": list(FEATURE_NAMES),
    }

    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    LOGGER.info("Wrote dataset to %s", output_dir)
    return metadata


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate the frozen disruption-detection dataset.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DATA_DIR),
        help="Directory to write dataset files into "
        "(default: data/disruption_detection).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"Random seed (default: {DEFAULT_SEED}).",
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    """Entry point: generate and persist the dataset."""
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = Path.cwd() / output_dir

    rows = generate_rows(args.seed)
    metadata = write_dataset(rows, output_dir, args.seed)

    LOGGER.info(
        "Dataset ready: normal=%d disruption=%d severity=%s hash=%s",
        metadata["label_distribution"][LABEL_NORMAL],
        metadata["label_distribution"][LABEL_DISRUPTION],
        metadata["severity_distribution"],
        metadata["dataset_hash_sha256"][:12],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())