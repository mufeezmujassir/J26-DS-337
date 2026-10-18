"""Dataset I/O helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

__all__ = [
    "save_jsonl",
    "load_jsonl",
    "write_metadata",
    "compute_sha256",
    "stratified_split",
]


def save_jsonl(rows: List[Dict[str, Any]], path: str | Path) -> Path:
    resolved = Path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    resolved.write_text(text, encoding="utf-8")
    return resolved


def load_jsonl(path: str | Path) -> List[Dict[str, Any]]:
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
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number}: {exc}")
    return rows


def write_metadata(metadata: Dict[str, Any], path: str | Path) -> Path:
    resolved = Path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return resolved


def compute_sha256(path: str | Path) -> str:
    resolved = Path(path)
    h = hashlib.sha256()
    with resolved.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stratified_split(
    rows: List[Dict[str, Any]],
    train_ratio: float = 0.80,
    dev_ratio: float = 0.10,
    test_ratio: float = 0.10,
    seed: int = 42,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    import random

    rng = random.Random(seed + 1)
    buckets: Dict[int, List[Dict[str, Any]]] = {}
    for row in rows:
        label = int(row.get("label", 0))
        buckets.setdefault(label, []).append(dict(row))

    keys = sorted(buckets)
    sizes = [len(buckets[k]) for k in keys]

    def allocate(count_total: int) -> List[int]:
        if count_total == 0 or sum(sizes) == 0:
            return [0 for _ in sizes]
        raw = [s * count_total / sum(sizes) for s in sizes]
        counts = [int(x) for x in raw]
        rem = count_total - sum(counts)
        order = sorted(
            range(len(sizes)),
            key=lambda i: (-(raw[i] - counts[i]), i),
        )
        for i in order[:rem]:
            counts[i] += 1
        return counts

    total = len(rows)
    dev_n = int(round(total * dev_ratio))
    test_n = int(round(total * test_ratio))
    train_n = total - dev_n - test_n

    dev_counts = allocate(dev_n)
    test_counts = allocate(test_n)

    train: List[Dict[str, Any]] = []
    dev: List[Dict[str, Any]] = []
    test: List[Dict[str, Any]] = []

    for pos, k in enumerate(keys):
        bucket = buckets[k][:]
        rng.shuffle(bucket)
        n_dev = dev_counts[pos]
        n_test = test_counts[pos]
        n_train = len(bucket) - n_dev - n_test
        train.extend(bucket[:n_train])
        dev.extend(bucket[n_train : n_train + n_dev])
        test.extend(bucket[n_train + n_dev :])

    for split in (train, dev, test):
        rng.shuffle(split)
    return train, dev, test
