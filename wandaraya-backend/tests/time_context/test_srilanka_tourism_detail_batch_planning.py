import json

from app.time_context.governance.detail_batch_planning import build_detail_manifest_from_listing, write_detail_batches


def test_detail_batch_plan_uses_only_listing_observed_detail_urls(tmp_path):
    source = tmp_path / "listing.json"
    source.write_text(json.dumps({"records": [{"source_page_category": "attraction_listing", "extracted_fields": {"referenced_attractions": [
        {"source_url": "https://srilanka.travel/attraction?attraction_id=163", "link_text_original": "Yala", "link_text_normalized": "Yala"},
        {"source_url": "https://www.srilanka.travel/attraction?attraction_id=163", "link_text_original": "Yala", "link_text_normalized": "Yala"},
        {"source_url": "https://srilanka.travel/attraction?attraction_id=160", "link_text_original": "Sigiriya", "link_text_normalized": "Sigiriya"}
    ]}}]}), encoding="utf-8")
    manifest = build_detail_manifest_from_listing(source)
    assert manifest["candidate_count"] == 2
    paths = write_detail_batches(manifest=manifest, reports_dir=tmp_path, batch_size=1)
    assert len(paths) == 2
    assert json.loads(paths[0].read_text())["approved_urls"][0]["authorization_status"] == "approved_for_pilot"
