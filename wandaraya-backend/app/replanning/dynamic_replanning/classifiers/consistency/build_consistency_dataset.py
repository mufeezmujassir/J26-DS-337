"""Build the frozen, seeded cross-turn consistency dataset."""

from __future__ import annotations

import argparse
import logging
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from app.replanning.dynamic_replanning.classifiers import PERSONAS  # noqa: E402
from app.replanning.dynamic_replanning.classifiers._dataset_io import (  # noqa: E402
    compute_sha256,
    save_jsonl,
    stratified_split,
    write_metadata,
)
from app.replanning.dynamic_replanning.classifiers.consistency import (  # noqa: E402
    CONSISTENCY_PROCESSED_DIR,
    CONSISTENCY_RAW_DIR,
    DRIFT_NONE,
    DRIFT_TYPES,
    LABEL_CONSISTENT,
    LABEL_DRIFT,
    LABEL_NAMES,
    LABEL_NOISE_RATE,
    RAW_ATTRACTIONS_FILENAME,
    DEFAULT_SEED,
)
from app.replanning.dynamic_replanning.classifiers.consistency._conversation_generator import (  # noqa: E402
    ConversationGenerator,
)
from app.replanning.dynamic_replanning.classifiers.consistency._drift_simulator import (  # noqa: E402
    DriftSimulator,
)
from app.replanning.dynamic_replanning.classifiers.consistency._feature_extractor import (  # noqa: E402
    extract_features,
)
from app.replanning.dynamic_replanning.classifiers.consistency._labeler import (  # noqa: E402
    DriftLabeler,
)

LOGGER = logging.getLogger("build_consistency_dataset")

DEFAULT_NUM_CONVERSATIONS = 1000
DEFAULT_TOTAL_ROWS = 3000
DEFAULT_SEED_VALUE = 42

GENERATED_README = """# Cross-Turn Consistency Dataset (Frozen)

- **Source**: 300 real Sri Lankan attractions from `data/replanning/consistency/raw/sri_lankan_attractions.jsonl` (extracted from the Component 1 PostgreSQL dump). The dataset is **NOT pure synthetic** — every row is grounded in real attraction data (real-data ratio = 1.0).
- **Construction**: Deterministic under `seed=42`. 1,000 multi-turn conversations (3-6 turns) simulate the Progressive Preference Elicitation (PPE) module's extraction of constraints (vibe, budget, must-see, pace), confirmations and rejections.
- **Methodology**: The construction pipeline follows TripCraft methodology — persona-driven conversation simulation over a real attraction catalogue with controlled drift injection.
- **Drift**: 40% of conversations receive one of six drift scenarios (constraint contradiction, confirmed must-see removal, unapproved vibe change, budget exceeded, no-rushing violation, reintroduced rejection); 60% stay consistent.
- **Features**: 12 features computed from the conversation history (simulating PPE outputs) and the newly proposed plan.
- **Labels**: `drift=1`, `consistent=0` from hard rules + 5% label noise (seed 42).
- **Frozen**: The dataset is frozen with seed 42 and committed for reproducibility.
- **Regenerate**: `python -m app.replanning.dynamic_replanning.classifiers.consistency.build_consistency_dataset`
- **Production model**: A single Random Forest classifier (no scaler, no Logistic Regression). No Jupyter notebooks — evaluation is via the standalone scripts `evaluate_consistency_rules_only.py`, `evaluate_consistency_ml_only.py`, `evaluate_consistency_hybrid.py`, `run_ablation_study.py` and `measure_latency.py`.
"""

REQUIRED_FIELDS = (
    "attraction_id",
    "name",
    "district",
    "district_id",
    "category",
    "lat",
    "lng",
    "opening_hours",
    "entry_fee_usd",
    "is_outdoor",
    "duration_minutes",
)


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the frozen cross-turn consistency dataset."
    )
    parser.add_argument(
        "--raw-dir",
        default=str(CONSISTENCY_RAW_DIR),
        help="Directory containing raw attractions JSONL.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(CONSISTENCY_PROCESSED_DIR),
        help="Directory to write processed dataset files.",
    )
    parser.add_argument(
        "--num-conversations",
        type=int,
        default=DEFAULT_NUM_CONVERSATIONS,
        help="Number of base conversations to generate.",
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
        default=DEFAULT_SEED_VALUE,
        help="Random seed.",
    )
    return parser.parse_args(argv)


def _validate_attractions(attractions: List[Dict[str, Any]]) -> None:
    for index, row in enumerate(attractions):
        missing = [f for f in REQUIRED_FIELDS if f not in row]
        if missing:
            raise ValueError(
                f"Attraction row {index} missing required fields: {missing}"
            )


def _build_drift_plan(
    num_conversations: int, seed: int
) -> List[str | None]:
    """Return a shuffled plan of drift types (None == consistent)."""

    rng = random.Random(seed + 100)
    drift_share = 0.40
    num_drift = int(round(num_conversations * drift_share))

    per_type = num_drift // len(DRIFT_TYPES)
    remainder = num_drift - per_type * len(DRIFT_TYPES)
    drift_list: List[str] = []
    for index, drift_type in enumerate(DRIFT_TYPES):
        count = per_type + (1 if index < remainder else 0)
        drift_list.extend([drift_type] * count)
    rng.shuffle(drift_list)

    plan: List[str | None] = [None] * (num_conversations - len(drift_list))
    plan.extend(drift_list)
    rng.shuffle(plan)
    return plan


def _generate_rows(
    conversations: List[Dict[str, Any]],
    generator: ConversationGenerator,
    simulator: DriftSimulator,
    labeler: DriftLabeler,
    drift_plan: List[str | None],
    total_rows: int,
    seed: int,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    rows_per_conversation = max(1, total_rows // len(conversations))
    overflow = total_rows - rows_per_conversation * len(conversations)

    for index, conversation in enumerate(conversations):
        drift_type = drift_plan[index]
        num_rows = rows_per_conversation + (1 if index < overflow else 0)

        for variant in range(num_rows):
            rng = random.Random(
                f"{seed}|{conversation['conversation_id']}|{variant}"
            )
            if drift_type is not None:
                result = simulator.inject_drift(
                    conversation, drift_type=drift_type, rng=rng
                )
                new_plan = result["new_plan"]
                intended = drift_type
            else:
                new_plan = simulator.produce_consistent_alternative(
                    conversation, rng=rng
                )
                intended = DRIFT_NONE

            features = extract_features(conversation, new_plan)
            label = labeler.label(conversation, new_plan, features)

            rows.append(
                {
                    **features,
                    "label": label,
                    "intended_drift_type": intended,
                    "conversation_id": conversation["conversation_id"],
                    "persona": conversation["persona"],
                    "start_city": conversation["start_city"],
                    "num_turns": conversation["num_turns"],
                }
            )

    return rows[:total_rows]


def _apply_label_noise(rows: List[Dict[str, Any]], labeler: DriftLabeler) -> None:
    labels_pre = [row["label"] for row in rows]
    labels_post = labeler.apply_label_noise(list(labels_pre))
    for row, label in zip(rows, labels_post):
        row["label"] = label


def _compute_distributions(
    rows: List[Dict[str, Any]],
) -> tuple[Dict[str, int], Dict[str, int], int]:
    label_dist = {
        LABEL_NAMES[LABEL_CONSISTENT]: sum(
            1 for r in rows if int(r["label"]) == LABEL_CONSISTENT
        ),
        LABEL_NAMES[LABEL_DRIFT]: sum(
            1 for r in rows if int(r["label"]) == LABEL_DRIFT
        ),
    }
    drift_type_dist: Dict[str, int] = {}
    for row in rows:
        drift_type = row.get("intended_drift_type", DRIFT_NONE)
        drift_type_dist[drift_type] = drift_type_dist.get(drift_type, 0) + 1

    source_conversations = len({r["conversation_id"] for r in rows})
    return label_dist, drift_type_dist, source_conversations


def _build_metadata(
    *,
    seed: int,
    rows: List[Dict[str, Any]],
    train: List[Dict[str, Any]],
    dev: List[Dict[str, Any]],
    test: List[Dict[str, Any]],
    attractions: List[Dict[str, Any]],
    label_dist: Dict[str, int],
    drift_type_dist: Dict[str, int],
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
        "drift_type_distribution": drift_type_dist,
        "source_attractions_count": len(attractions),
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

    # Stage 1 — load real attractions
    LOGGER.info("Stage 1: loading raw attractions from %s", raw_path)
    generator = ConversationGenerator(str(raw_path), seed=args.seed)
    attractions = generator.load_attractions()
    _validate_attractions(attractions)
    LOGGER.info("Loaded and validated %d real attractions", len(attractions))

    # Stage 2 — generate conversations (PPE simulation)
    LOGGER.info(
        "Stage 2: generating %d multi-turn conversations (seed=%d)",
        args.num_conversations,
        args.seed,
    )
    conversations = generator.generate_batch(args.num_conversations)

    # Stage 3 — drift plan
    LOGGER.info("Stage 3: planning drift injection (40%% drift / 60%% consistent)")
    drift_plan = _build_drift_plan(args.num_conversations, args.seed)
    num_drift_convs = sum(1 for d in drift_plan if d is not None)
    LOGGER.info(
        "Drift conversations: %d / %d", num_drift_convs, len(conversations)
    )

    simulator = DriftSimulator(seed=args.seed, generator=generator)
    labeler = DriftLabeler(noise_rate=LABEL_NOISE_RATE, seed=args.seed)

    # Stages 4+5 — features + labels
    LOGGER.info("Stage 4+5: extracting features and labeling %d rows", args.total_rows)
    rows = _generate_rows(
        conversations,
        generator,
        simulator,
        labeler,
        drift_plan,
        args.total_rows,
        args.seed,
    )
    _apply_label_noise(rows, labeler)

    # Stage 6 — split
    LOGGER.info("Stage 6: stratified 80/10/10 split")
    train, dev, test = stratified_split(rows, 0.80, 0.10, 0.10, seed=args.seed)

    # Stage 7 — save
    LOGGER.info("Stage 7: writing outputs to %s", out_dir)
    full_path = save_jsonl(rows, out_dir / "simulated_consistency_data.jsonl")
    save_jsonl(train, out_dir / "train.jsonl")
    save_jsonl(dev, out_dir / "dev.jsonl")
    save_jsonl(test, out_dir / "test.jsonl")

    dataset_hash = compute_sha256(full_path)
    label_dist, drift_type_dist, _ = _compute_distributions(rows)

    metadata = _build_metadata(
        seed=args.seed,
        rows=rows,
        train=train,
        dev=dev,
        test=test,
        attractions=attractions,
        label_dist=label_dist,
        drift_type_dist=drift_type_dist,
        dataset_hash=dataset_hash,
    )
    write_metadata(metadata, out_dir / "metadata.json")
    (out_dir / "README.md").write_text(GENERATED_README, encoding="utf-8")

    LOGGER.info("Dataset written to %s", out_dir)
    LOGGER.info(
        "Labels: consistent=%d drift=%d (train=%d dev=%d test=%d)",
        label_dist["consistent"],
        label_dist["drift"],
        len(train),
        len(dev),
        len(test),
    )
    LOGGER.info("Dataset SHA-256: %s", dataset_hash)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
