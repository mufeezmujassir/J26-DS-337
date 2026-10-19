from scripts.report_stage12_4a import climate_sources, schema_proposal


def test_source_inventory_is_planning_only():
    sources = climate_sources()
    assert sources
    assert all(item["downloaded"] is False for item in sources)
    assert any("Open-Meteo" in item["source"] for item in sources)


def test_schema_proposal_does_not_claim_migration():
    proposal = schema_proposal()
    assert proposal["proposal_only"] is True
    assert proposal["migration_created"] is False
    assert any(table["name"] == "district_climate_monthly" for table in proposal["tables"])
