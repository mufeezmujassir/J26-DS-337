"""Normalization and synonym mapping for Step 9: Rule-based Conflict Detector.

Provides text cleaning (trim, lowercase, space collapsing) and synonym canonicalization
based on configs/conflict_rules.yaml.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent.parent / "configs" / "conflict_rules.yaml"
)

_CACHED_CONFIG: dict[str, Any] | None = None
_CACHED_SYNONYM_LOOKUP: dict[str, dict[str, str]] | None = None


def load_conflict_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Load conflict rules configuration from YAML file."""
    global _CACHED_CONFIG, _CACHED_SYNONYM_LOOKUP

    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if not path.exists():
        # Fallback to local configs directory
        fallback = Path("configs/conflict_rules.yaml")
        if fallback.exists():
            path = fallback
        else:
            logger.warning("Config file %s not found. Using default empty config.", path)
            return {}

    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    _CACHED_CONFIG = config
    _CACHED_SYNONYM_LOOKUP = _build_synonym_lookup(config.get("synonyms", {}))
    return config


def _clean_str(text: str) -> str:
    """Lowercase, strip, and collapse multiple whitespace / replace hyphens with space."""
    if not text:
        return ""
    # Normalize hyphens and underscores to spaces for alias matching
    cleaned = text.strip().lower()
    cleaned = cleaned.replace("_", " ").replace("-", " ")
    return " ".join(cleaned.split())


def _build_synonym_lookup(synonyms_cfg: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Build reverse lookup dictionary: {category: {cleaned_alias: canonical_name}}."""
    lookup: dict[str, dict[str, str]] = {}
    general_lookup: dict[str, str] = {}

    for cat, mapping in synonyms_cfg.items():
        cat_key = cat.lower()
        lookup[cat_key] = {}
        if not isinstance(mapping, dict):
            continue

        for canonical, aliases in mapping.items():
            canon_clean = _clean_str(canonical)
            # Map canonical to itself
            lookup[cat_key][canon_clean] = canon_clean
            general_lookup[canon_clean] = canon_clean

            # Also add unspaced variant if applicable (e.g. "nuwaraeliya")
            unspaced_canon = canon_clean.replace(" ", "")
            lookup[cat_key][unspaced_canon] = canon_clean
            general_lookup[unspaced_canon] = canon_clean

            if isinstance(aliases, list):
                for alias in aliases:
                    alias_clean = _clean_str(alias)
                    lookup[cat_key][alias_clean] = canon_clean
                    general_lookup[alias_clean] = canon_clean
                    unspaced_alias = alias_clean.replace(" ", "")
                    lookup[cat_key][unspaced_alias] = canon_clean
                    general_lookup[unspaced_alias] = canon_clean

    lookup["_all"] = general_lookup
    return lookup


def normalize_name(
    name: str,
    category: str | None = None,
    config: dict[str, Any] | None = None,
) -> str:
    """Normalize a name by trimming, lowercasing, and resolving synonyms.

    Args:
        name: The raw entity name (e.g., '  Nuwara Eliya  ' or 'trekking').
        category: Optional category name ('Destination', 'Activity', etc.).
        config: Optional pre-loaded config dict.

    Returns:
        Canonical normalized name string.
    """
    global _CACHED_SYNONYM_LOOKUP

    if not isinstance(name, str):
        return ""

    cleaned = _clean_str(name)
    if not cleaned:
        return ""

    lookup = _CACHED_SYNONYM_LOOKUP
    if config is not None:
        lookup = _build_synonym_lookup(config.get("synonyms", {}))
    elif lookup is None:
        cfg = load_conflict_config()
        lookup = _CACHED_SYNONYM_LOOKUP

    if not lookup:
        return cleaned

    cat_key = category.lower() if category else None
    if cat_key and cat_key in lookup and cleaned in lookup[cat_key]:
        return lookup[cat_key][cleaned]

    # Try unspaced version
    unspaced = cleaned.replace(" ", "")
    if cat_key and cat_key in lookup and unspaced in lookup[cat_key]:
        return lookup[cat_key][unspaced]

    # Check general across categories
    general = lookup.get("_all", {})
    if cleaned in general:
        return general[cleaned]
    if unspaced in general:
        return general[unspaced]

    return cleaned
