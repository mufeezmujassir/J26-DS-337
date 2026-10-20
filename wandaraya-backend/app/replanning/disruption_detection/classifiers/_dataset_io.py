"""Dataset persistence, hashing and splitting helpers.

These utilities are shared by :mod:`build_disruption_dataset` and keep the
on-disk format (JSON Lines + ``metadata.json``) byte-for-byte compatible with
the format the training, inference and evaluation scripts already expect.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

LOGGER = logging.getLogger(__name__)

_DEFAULT_BUFFER = 64 * 1024


def save_jsonl(rows: Iterable[Dict[str, Any]], path: str | Path) -> Path:
    """Write ``rows`` as JSON Lines (UTF-8, one object per line).

    Returns the resolved path so callers can hash the file they just wrote.
    """
    resolved = Path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(
        json.dumps(row, ensure_ascii=False) + "\n" for row in rows
    )
    resolved.write_text(text, encoding="utf-8")
    LOGGER.info("Saved %d rows to %s", text.count("\n"), resolved)
    return resolved


def load_jsonl(path: str | Path) -> List[Dict[str, Any]]:
    """Load a JSON Lines file into a list of dicts."""
    resolved = Path(path)
    if not resolved.is_file():
        raise FileNotFoundError(f"Dataset not found: {resolved}")

    rows: List[Dict[str, Any]] = []
    with resolved.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError as exc:  # pragma: no cover - defensive
                raise ValueError(
                    f"Invalid JSON on line {line_number} of {resolved}: {exc}"
                ) from exc
    return rows


def write_metadata(metadata: Dict[str, Any], path: str | Path) -> Path:
    """Persist a metadata manifest as pretty-printed JSON."""
    resolved = Path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    LOGGER.info("Wrote metadata to %s", resolved)
    return resolved


def compute_sha256(path: str | Path) -> str:
    """Return the hex SHA-256 digest of a file's bytes."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(_DEFAULT_BUFFER), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _proportional_counts(sizes: Sequence[int], target: int) -> List[int]:
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
    rows: Sequence[Dict[str, Any]],
    train_ratio: float = 0.8,
    dev_ratio: float = 0.1,
    test_ratio: float = 0.1,
    seed: int = 42,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split ``rows`` into train/dev/test, stratified by ``(label, severity)``.

    Ratios must sum to 1.0 (within a small tolerance). The split is fully
    deterministic for a given ``seed`` and preserves the ``(label, severity)``
    proportion in every subset.
    """
    ratio_sum = train_ratio + dev_ratio + test_ratio
    if abs(ratio_sum - 1.0) > 1e-9:
        raise ValueError(
            f"Split ratios must sum to 1.0, got {ratio_sum!r}"
        )

    total = len(rows)
    rng = random.Random(seed + 1)

    bucket_keys = sorted({(row["label"], row["severity"]) for row in rows})
    buckets: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for row in rows:
        buckets.setdefault((row["label"], row["severity"]), []).append(row)

    sizes = [len(buckets[key]) for key in bucket_keys]
    dev_target = int(round(total * dev_ratio))
    test_target = int(round(total * test_ratio))
    dev_counts = _proportional_counts(sizes, dev_target)
    test_counts = _proportional_counts(sizes, test_target)

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


__all__ = [
    "save_jsonl",
    "load_jsonl",
    "write_metadata",
    "compute_sha256",
    "stratified_split",
]
