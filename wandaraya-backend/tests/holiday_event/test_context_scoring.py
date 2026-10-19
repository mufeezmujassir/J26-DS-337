from types import SimpleNamespace
from app.holiday_event.context_scoring import HolidayEventContextScoringService

CONFIG={"scoring_version":"test","feature_weights":{"holiday":.2,"poya":.35,"verified_event":.25,"interests":.2}}
def feature(**changes):
    data=dict(attraction_id=1,is_poya_day=False,is_public_holiday=None,is_bank_holiday=None,cultural_relevance_score=None,event_context_score=None,event_match_status=None,evidence_sources=["source"],uncertainty_flags=[])
    data.update(changes); return SimpleNamespace(**data)

def engine(): return HolidayEventContextScoringService(None, CONFIG)
def test_no_evidence_returns_null_not_neutral_score():
    result=engine()._score_feature(feature(), [], [])
    assert result.context_suitability_score is None and result.context_confidence == "INSUFFICIENT_EVIDENCE"
def test_poya_cultural_rule_is_eligible_and_not_double_counted():
    result=engine()._score_feature(feature(is_poya_day=True,cultural_relevance_score=.6), ["Religious Heritage"], ["heritage"])
    assert result.poya_score == .6 and result.holiday_score is None and "holiday:dependent_on_poya_evidence" in result.excluded_features
def test_candidate_event_never_contributes_event_score():
    result=engine()._score_feature(feature(event_match_status="candidate",event_context_score=None), [], [])
    assert result.event_score is None and "verified_event:semantic_candidate_not_verified" in result.excluded_features
def test_verified_event_score_and_interest_matching_are_explainable():
    result=engine()._score_feature(feature(event_match_status="verified",event_context_score=1.0), ["Heritage"], ["heritage","beach"])
    assert result.event_score == 1.0 and result.interest_compatibility_score == .5 and result.context_confidence == "HIGH"
