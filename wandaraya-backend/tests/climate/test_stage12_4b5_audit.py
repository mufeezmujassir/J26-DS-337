import pytest
from scripts.audit_stage12_4b5_historical import EXPECTED, unique_object


def test_sixteen_years_include_all_leap_days():
    assert len(EXPECTED) == 5844
    assert {'20120229', '20160229', '20200229', '20240229'} <= EXPECTED


def test_duplicate_raw_json_keys_are_rejected():
    with pytest.raises(ValueError, match='duplicate JSON key'):
        unique_object([('20100101', 1), ('20100101', 2)])
