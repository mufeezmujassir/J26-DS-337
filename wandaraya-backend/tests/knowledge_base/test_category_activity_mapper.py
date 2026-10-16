from app.knowledge_base.processors.category_activity_mapper import CategoryActivityMapper


def test_google_snake_case_types_are_readable_to_activity_rules():
    result = CategoryActivityMapper.map({
        "name": "Galle Fort",
        "source_metadata": {"types": ["tourist_attraction", "historical_landmark"]},
    })
    assert any(item.name == "Sightseeing" for item in result.activities)
    assert any(item.name == "Culture & Heritage" for item in result.categories)


def test_art_gallery_google_type_maps_to_existing_culture_category_and_activity():
    result = CategoryActivityMapper.map({
        "name": "Ahangama Art Gallery",
        "source_metadata": {"types": ["art_gallery", "point_of_interest"]},
    })
    assert any(item.name == "Culture & Heritage" for item in result.categories)
    assert any(item.name == "Cultural Experience" for item in result.activities)


def test_supporting_text_alone_does_not_create_a_category_or_activity():
    result = CategoryActivityMapper.map(
        {"name": "Unnamed venue", "source_metadata": {"types": []}},
        supporting_text="A historic museum with cultural heritage.",
    )
    assert result.categories == []
    assert result.activities == []
