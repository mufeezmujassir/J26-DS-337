from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DiscoveredPlace:
    """A deduplicated Google Place discovered by one or more searches."""

    place_id: str
    name: str | None
    latitude: float | None
    longitude: float | None
    primary_type: str | None
    discovered_by_types: set[str] = field(default_factory=set)
    discovered_in_cells: set[str] = field(default_factory=set)
