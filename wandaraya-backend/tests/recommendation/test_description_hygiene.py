from types import SimpleNamespace

from app.recommendation.unified_context.orchestrator import (
    _description_is_polluted,
    _metadata_description,
    _preference_tokens,
)


def test_imported_guide_fragment_is_replaced_by_focused_metadata_summary():
    imported = (
        "Walk around Galle Fort. 4 Talpe Beach. Beach club with great vibe. "
        "== Sleep == Hotels and hostels. === Mid-range === Guest house."
    )
    assert _description_is_polluted(imported)

    attraction = SimpleNamespace(
        name="Galle Dutch Fort",
        city="Galle",
        rating=4.7,
        review_count=100,
    )
    summary = _metadata_description(
        attraction,
        "Galle",
        ["History & Archaeology", "Culture & Heritage"],
        ["Heritage Exploration", "Sightseeing"],
    )
    assert "culture & heritage" in summary.casefold()
    assert "beach club" not in summary.casefold()


def test_cultural_preferences_expand_to_database_taxonomy_fragments():
    tokens = _preference_tokens(["cultural sightseeing"], ["culture", "heritage"])
    assert {"cultur", "heritage", "history", "archaeolog"}.issubset(tokens)
    assert "beach" not in tokens
