import pytest
from app.time_context.governance.gate5e_sync_planning import consolidate_checkpoint,validate_decisions
def queue(): return {'records':[{'external_source_id':'s:36','attraction_name':'Panavitiya Ambalama','source_url':'u36'},{'external_source_id':'s:94','attraction_name':'Panavitiya Ambalama','source_url':'u94'}]}
def checkpoint(): return {'results':[{'external_source_id':'s:36','classification':'new_google_place_candidate','candidates':[{'google_place_id':'p'}]},{'external_source_id':'s:94','classification':'new_google_place_candidate','candidates':[{'google_place_id':'p'}]}]}
def test_complete_consolidation_and_duplicate():
 p=consolidate_checkpoint(checkpoint(),queue());assert len(p)==2 and {x['proposed_action'] for x in p}=={'INSERT_NEW_CANDIDATE'}
def test_missing_source_fails():
 with pytest.raises(ValueError,match='incomplete'): consolidate_checkpoint({'results':[]},queue())
def test_compound_requires_review():
 c={'results':[{'external_source_id':'s:36','classification':'verified_existing_kb_match','google_candidate_kb_identity':'verified_existing_kb_place','official_source_candidate_identity':'compound_source_record_review_required','candidates':[{'google_place_id':'p'}]},{'external_source_id':'s:94','classification':'new_google_place_candidate','candidates':[{'google_place_id':'p2'}]}]};assert consolidate_checkpoint(c,queue())[0]['proposed_action']=='MANUAL_REVIEW_REQUIRED'
def test_decision_cannot_change_google_target():
 p=consolidate_checkpoint(checkpoint(),queue())
 with pytest.raises(ValueError,match='mismatch'): validate_decisions({'decisions':[{'external_source_id':'s:36','decision':'APPROVE_INSERT','google_place_id':'other'}]},p)
