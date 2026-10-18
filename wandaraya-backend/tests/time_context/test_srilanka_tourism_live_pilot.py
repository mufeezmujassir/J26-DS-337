import asyncio

import pytest

from app.time_context.governance.live_pilot import ConditionApprovalStatus, ControlledSriLankaTourismFetcher, LivePilotSettings, SourceAuthorizationConfiguration, build_dry_run, load_source_authorization_configuration, normalize_pilot_url, stage_content
from app.time_context.governance.srilanka_tourism import SriLankaTourismPermission, TourismPageType, extract_html_fixture


def test_dry_run_denies_without_explicit_technical_execution_and_deduplicates_urls():
    plan = build_dry_run(["https://srilanka.travel/heritage/", "https://srilanka.travel/heritage", "https://example.com/x"], SriLankaTourismPermission(automated_fetch_allowed=True), LivePilotSettings())
    assert [item.reason for item in plan] == ["technical_execution_not_authorized", "duplicate_url", "unapproved_domain"]


def test_dry_run_authorisation_requires_reported_and_technical_approval():
    permission = SriLankaTourismPermission(automated_fetch_allowed=True, technical_execution_approved=True)
    assert build_dry_run(["https://srilanka.travel/heritage"], permission, LivePilotSettings())[0].approved


def test_url_normalisation_html_fixture_and_review_staging_never_write_production():
    assert normalize_pilot_url("https://www.srilanka.travel/x/") == "https://www.srilanka.travel/x"
    record = extract_html_fixture(html="<html><title>Fort</title><body><main><h1>Fort</h1><p>Official text</p></main></body></html>", source_url="https://srilanka.travel/fort", page_type=TourismPageType.ATTRACTION)
    assert record.name == "Fort" and record.description == "Official text"
    staged = stage_content(source_url="https://srilanka.travel/fort", content=b"fixture", permission=SriLankaTourismPermission())
    assert not staged.production_write_performed and not staged.qdrant_write_performed and staged.review_required


def test_emergency_stop_and_invalid_urls_fail_closed():
    permission = SriLankaTourismPermission(automated_fetch_allowed=True, technical_execution_approved=True)
    assert not build_dry_run(["https://srilanka.travel/x"], permission, LivePilotSettings(emergency_stop=True))[0].approved
    with pytest.raises(ValueError): normalize_pilot_url("http://srilanka.travel/x")


def test_full_authorisation_configuration_requires_all_material_scope_details():
    permission = SriLankaTourismPermission(automated_fetch_allowed=True, technical_execution_approved=True)
    config = SourceAuthorizationConfiguration(permission=permission, approved_domains={"srilanka.travel"}, exact_urls=["https://srilanka.travel/x"])
    errors = config.readiness_errors(LivePilotSettings())
    assert "technical_execution_approval_missing" in errors
    assert "retention_conditions_missing" in errors


def test_fetcher_refuses_without_explicit_execute_even_when_permission_fields_are_set():
    permission = SriLankaTourismPermission(automated_fetch_allowed=True, technical_execution_approved=True)
    config = SourceAuthorizationConfiguration(permission=permission, approved_domains={"srilanka.travel"}, exact_urls=["https://srilanka.travel/x"], permitted_content_categories={"attraction"}, retention_conditions="pilot only", attribution_conditions="attribute source", request_rate_restrictions="3 seconds")
    from app.time_context.governance.live_pilot import ControlledSriLankaTourismFetcher
    with pytest.raises(PermissionError, match="explicit execute"):
        import asyncio; asyncio.run(ControlledSriLankaTourismFetcher(config, LivePilotSettings()).fetch_exact_urls(execute=False))


def test_researcher_proposed_operating_rules_do_not_satisfy_source_confirmation_gate():
    permission = SriLankaTourismPermission(automated_fetch_allowed=True, technical_execution_approved=True)
    config = SourceAuthorizationConfiguration(
        permission=permission,
        approved_domains={"srilanka.travel"},
        exact_urls=["https://srilanka.travel/"],
        permitted_content_categories={"attraction"},
        retention_conditions="Research team proposal.",
        attribution_conditions="Research team proposal.",
        request_rate_restrictions="Research team proposal.",
        retention_conditions_status=ConditionApprovalStatus.RESEARCHER_PROPOSED,
        attribution_conditions_status=ConditionApprovalStatus.RESEARCHER_PROPOSED,
        request_rate_restrictions_status=ConditionApprovalStatus.RESEARCHER_PROPOSED,
    )
    errors = config.readiness_errors(LivePilotSettings())
    assert "retention_conditions_not_source_confirmed" in errors
    assert "attribution_conditions_not_source_confirmed" in errors
    assert "request_rate_restrictions_not_source_confirmed" in errors


def test_invalid_json_is_rejected_without_falling_back_to_defaults(tmp_path):
    config_path = tmp_path / "invalid.json"
    config_path.write_text("{invalid", encoding="utf-8")
    with pytest.raises(ValueError):
        load_source_authorization_configuration(config_path)


def _source_confirmed_config() -> SourceAuthorizationConfiguration:
    return SourceAuthorizationConfiguration(
        permission=SriLankaTourismPermission(automated_fetch_allowed=True, technical_execution_approved=True),
        approved_domains={"srilanka.travel"},
        exact_urls=["https://srilanka.travel/"],
        permitted_content_categories={"attraction"},
        retention_conditions="Source-confirmed pilot retention rule.",
        retention_conditions_status=ConditionApprovalStatus.SOURCE_CONFIRMED,
        attribution_conditions="Source-confirmed attribution rule.",
        attribution_conditions_status=ConditionApprovalStatus.SOURCE_CONFIRMED,
        request_rate_restrictions="Source-confirmed request-rate rule.",
        request_rate_restrictions_status=ConditionApprovalStatus.SOURCE_CONFIRMED,
        researcher_execution_approved_at="2026-10-14T12:30:00+05:30",
    )


class _MockResponse:
    is_redirect = False
    status_code = 200
    headers = {"content-type": "text/plain"}
    content = b"fixture"

    def raise_for_status(self) -> None:
        return None


class _MockClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def get(self, _url):
        return _MockResponse()


def test_http_mock_rejects_invalid_content_before_any_persistence():
    fetcher = ControlledSriLankaTourismFetcher(
        _source_confirmed_config(),
        LivePilotSettings(),
        client_factory=lambda **_kwargs: _MockClient(),
    )
    with pytest.raises(ValueError, match="unsupported response content type"):
        asyncio.run(fetcher.fetch_exact_urls(execute=True))
