"""Build the frozen, seeded intent-preservation dataset.

This orchestrator:
1. Loads the 300 real Sri Lankan attractions.
2. Generates 1000 realistic itineraries from those attractions.
3. Creates 3000 (original, disruption, revised) triples with a controlled
   distribution of break types (2100 preserved, 900 broken).
4. Extracts the 14 canonical features for every triple.
5. Labels rows with the rule-based labeler and adds 5% label noise.
6. Stratifies the data into train/dev/test (80/10/10) by label.
7. Persists the full set and splits, writes metadata, and computes SHA-256.

The dataset is deterministic under the specified random seed (default 42).
"""

from __future__ import annotations

import argparse
import hashlib  # noqa: F401  (kept for parity; used via compute_sha256 helper)
import json
import logging
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from app.replanning.dynamic_replanning.classifiers import (
    BROKEN_BUDGET_OVERRUN,
    BROKEN_LOCATION_SHIFT,
    BROKEN_MISSING_BOOKING,
    BROKEN_MISSING_MUST_SEE,
    BROKEN_MULTIPLE_MINOR,
    BROKEN_TIME_SHIFT,
    BROKEN_TYPES,
    BROKEN_VIBE_MISMATCH,
    LABEL_BROKEN,
    LABEL_NOISE_RATE,
    LABEL_PRESERVED,
    PROCESSED_DIR,
    RAW_ATTRACTIONS_FILENAME,
    RAW_DIR,
    load_jsonl,
)
from app.replanning.dynamic_replanning.classifiers._dataset_io import (
    compute_sha256,
    save_jsonl,
    stratified_split,
    write_metadata,
)
from app.replanning.dynamic_replanning.classifiers._disruption_simulator import (
    DisruptionSimulator,
)
from app.replanning.dynamic_replanning.classifiers._feature_extractor import (
    extract_features,
)
from app.replanning.dynamic_replanning.classifiers._itinerary_generator import (
    ItineraryGenerator,
)
from app.replanning.dynamic_replanning.classifiers._labeler import IntentLabeler

LOGGER = logging.getLogger("build_intent_dataset")

GENERATED_README = """# Intent Preservation Dataset (Frozen)

- **Source**: 300 real Sri Lankan attractions from `data/replanning/intent/raw/sri_lankan_attractions.jsonl` (committed).
- **Construction**: Deterministic with `seed=42`. Itineraries → disruptions → revised plans → 14 features → labels (rules + 5% noise).
- **Trip durations**: {3,5,7,10,14} days with weights [0.30, 0.30, 0.25, 0.10, 0.05] (real Sri Lankan tour-package distribution).
- **Features**: 14 features comparing original vs revised plan.
- **Labels**: `preserved=1`, `broken=0` (from rules + 5% noise). Real-data-supported (all rows derive from real attractions).
- **Production model**: Single Random Forest classifier (no scaler). No Jupyter notebooks — evaluation via scripts only.
- **Regenerate**: `python -m app.replanning.dynamic_replanning.classifiers.build_intent_dataset`
"""

DEFAULT_SEED = 42
DEFAULT_NUM_ITINERARIES = 1000
DEFAULT_TOTAL_ROWS = 3000

# Target composition for the frozen dataset.
TARGET_PRESERVED_ROWS = 2100
TARGET_BROKEN_ROWS = 900

# Exact broken-type quotas used to construct the frozen dataset.
BROKEN_TYPE_QUOTAS: Dict[str, int] = {
    BROKEN_VIBE_MISMATCH: 160,
    BROKEN_BUDGET_OVERRUN: 160,
    BROKEN_MISSING_BOOKING: 140,
    BROKEN_MISSING_MUST_SEE: 140,
    BROKEN_TIME_SHIFT: 120,
    BROKEN_LOCATION_SHIFT: 100,
    BROKEN_MULTIPLE_MINOR: 80,
}

CANONICAL_DURATIONS: List[int] = [3, 5, 7, 10, 14]


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the frozen intent-preservation dataset."
    )
    parser.add_argument(
        "--raw-dir",
        default=str(RAW_DIR),
        help="Directory containing raw attractions JSONL.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(PROCESSED_DIR),
        help="Directory to write processed dataset files.",
    )
    parser.add_argument(
        "--num-itineraries",
        type=int,
        default=DEFAULT_NUM_ITINERARIES,
        help="Number of base itineraries to generate.",
    )
    parser.add_argument(
        "--total-rows",
        type=int,
        default=DEFAULT_TOTAL_ROWS,
        help="Total number of rows to produce.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help="Random seed.",
    )
    return parser.parse_args(argv)


def build_break_plan(total_rows: int, seed: int) -> List[str | None]:
    """Return a shuffled plan of break types (``None`` == preserved)."""
    rng = random.Random(seed + 100)

    broken_list: List[str] = []
    for break_type, quota in BROKEN_TYPE_QUOTAS.items():
        broken_list.extend([break_type] * quota)
    rng.shuffle(broken_list)

    plan: List[str | None] = [None] * TARGET_PRESERVED_ROWS + broken_list
    rng.shuffle(plan)

    if len(plan) > total_rows:
        plan = plan[:total_rows]
    while len(plan) < total_rows:
        plan.append(None)

    return plan


def _generate_rows(
    itineraries: List[Dict[str, Any]],
    simulator: DisruptionSimulator,
    labeler: IntentLabeler,
    break_plan: List[str | None],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for index, break_type in enumerate(break_plan):
        itinerary = itineraries[index % len(itineraries)]
        disruption = simulator.simulate_disruption(itinerary)
        revised = simulator.apply_disruption(
            itinerary, disruption, break_type=break_type
        )
        features = extract_features(itinerary, disruption, revised)
        label = labeler.label(itinerary, disruption, revised, features)

        rows.append(
            {
                **features,
                "label": label,
                "intended_broken_type": (
                    break_type if break_type is not None else "preserved"
                ),
                "itinerary_id": itinerary.get("itinerary_id"),
                "disruption_id": disruption.get("disruption_id"),
                "persona": itinerary.get("persona"),
                "duration_days": itinerary.get("duration_days"),
                "start_city": itinerary.get("start_city"),
            }
        )
    return rows


def _apply_label_noise(
    rows: List[Dict[str, Any]], labeler: IntentLabeler
) -> None:
    labels_pre = [row["label"] for row in rows]
    labels_post = labeler.apply_label_noise(list(labels_pre))
    for row, label in zip(rows, labels_post):
        row["label"] = label


def _write_full_dataset(rows: List[Dict[str, Any]], path: Path) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _compute_distributions(
    rows: List[Dict[str, Any]],
) -> tuple[Dict[str, int], Dict[str, int], set, Dict[str, int]]:
    duration_dist = {str(d): 0 for d in CANONICAL_DURATIONS}
    broken_type_dist = {t: 0 for t in BROKEN_TYPES}
    source_districts: set = set()

    for row in rows:
        duration = row.get("duration_days")
        if duration in CANONICAL_DURATIONS:
            duration_dist[str(duration)] = duration_dist.get(str(duration), 0) + 1

        break_type = row.get("intended_broken_type")
        if break_type in broken_type_dist:
            broken_type_dist[break_type] += 1

        start_city = row.get("start_city")
        if start_city:
            source_districts.add(start_city)

    label_dist = {
        "preserved": sum(
            1 for r in rows if int(r["label"]) == LABEL_PRESERVED
        ),
        "broken": sum(1 for r in rows if int(r["label"]) == LABEL_BROKEN),
    }
    return duration_dist, broken_type_dist, source_districts, label_dist


def _build_metadata(
    *,
    seed: int,
    rows: List[Dict[str, Any]],
    train: List[Dict[str, Any]],
    dev: List[Dict[str, Any]],
    test: List[Dict[str, Any]],
    attractions: List[Dict[str, Any]],
    duration_dist: Dict[str, int],
    broken_type_dist: Dict[str, int],
    source_districts: set,
    label_dist: Dict[str, int],
    dataset_hash: str,
) -> Dict[str, Any]:
    return {
        "builder_version": "1.0.0",
        "random_seed": seed,
        "num_rows": len(rows),
        "rows_from_real_itineraries": len(rows),
        "real_data_ratio": 1.0,
        "train_rows": len(train),
        "dev_rows": len(dev),
        "test_rows": len(test),
        "label_distribution": label_dist,
        "broken_type_distribution": {k: int(v) for k, v in broken_type_dist.items()},
        "source_attractions_count": len(attractions),
        "source_districts_count": len(source_districts),
        "duration_distribution": {k: int(v) for k, v in duration_dist.items()},
        "source_categories": [
            "History & Archaeology",
            "Nature & Landscapes",
            "Urban & City Attractions",
            "Culture & Heritage",
            "Religious & Spiritual",
            "Beaches & Coastal",
            "Uncategorized",
            "Wellness & Ayurveda",
            "Food & Culinary",
            "Photography & Scenic Spots",
            "Wildlife & Safari",
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_hash_sha256": dataset_hash,
    }


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    raw_path = Path(args.raw_dir) / RAW_ATTRACTIONS_FILENAME
    out_dir = Path(args.output_dir)
    if not out_dir.is_absolute():
        out_dir = Path.cwd() / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    LOGGER.info("Loading raw attractions from %s", raw_path)
    attractions = load_jsonl(raw_path)
    LOGGER.info("Loaded %d real attractions", len(attractions))

    LOGGER.info(
        "Generating %d itineraries (seed=%d)",
        args.num_itineraries,
        args.seed,
    )
    generator = ItineraryGenerator(raw_path, seed=args.seed)
    itineraries = generator.generate_batch(args.num_itineraries)

    simulator = DisruptionSimulator(
        seed=args.seed, attractions=generator.attractions
    )
    labeler = IntentLabeler(noise_rate=LABEL_NOISE_RATE, seed=args.seed)
    break_plan = build_break_plan(args.total_rows, args.seed)

    LOGGER.info("Building %d rows", args.total_rows)
    rows = _generate_rows(itineraries, simulator, labeler, break_plan)
    _apply_label_noise(rows, labeler)

    full_path = out_dir / "simulated_intent_data.jsonl"
    _write_full_dataset(rows, full_path)

    train, dev, test = stratified_split(rows, 0.80, 0.10, 0.10, seed=args.seed)
    save_jsonl(train, out_dir / "train.jsonl")
    save_jsonl(dev, out_dir / "dev.jsonl")
    save_jsonl(test, out_dir / "test.jsonl")

    dataset_hash = compute_sha256(full_path)

    duration_dist, broken_type_dist, source_districts, label_dist = (
        _compute_distributions(rows)
    )

    metadata = _build_metadata(
        seed=args.seed,
        rows=rows,
        train=train,
        dev=dev,
        test=test,
        attractions=attractions,
        duration_dist=duration_dist,
        broken_type_dist=broken_type_dist,
        source_districts=source_districts,
        label_dist=label_dist,
        dataset_hash=dataset_hash,
    )
    write_metadata(metadata, out_dir / "metadata.json")
    (out_dir / "README.md").write_text(GENERATED_README, encoding="utf-8")

    LOGGER.info("Dataset written to %s", out_dir)
    LOGGER.info(
        "Labels: preserved=%d broken=%d (train=%d dev=%d test=%d)",
        label_dist["preserved"],
        label_dist["broken"],
        len(train),
        len(dev),
        len(test),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())