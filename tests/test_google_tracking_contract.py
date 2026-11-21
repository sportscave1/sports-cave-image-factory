from google_tracking_contract import health, paid_term, ACCOUNT_SUFFIX, CAMPAIGN_SUFFIX
import pytest

@pytest.mark.parametrize("value", ["", "sc_google_paid_", "sc_google_paid_0", "sc_google_paid_x", "sc_google_paid_123junk", "sc_google_paid_{campaignid}"])
def test_unexpanded_or_invalid_marker_is_not_paid(value):
    assert not paid_term(value)

def test_suffix_policy_and_campaign_override():
    assert paid_term("sc_google_paid_24420240881")
    account={"autoTaggingEnabled":True,"finalUrlSuffix":ACCOUNT_SUFFIX}
    campaign={"id":"24420240881"}
    assert health(account,campaign)["status"]=="verified"
    campaign["finalUrlSuffix"]=CAMPAIGN_SUFFIX
    assert health(account,campaign)["status"]=="verified"
    campaign["finalUrlSuffix"]="utm_source=google&utm_medium=cpc"
    assert health(account,campaign)["status"]=="attention"
    assert "shopify_paid_marker" in health(account,campaign)["missing"]

def test_no_private_urls_or_values_exposed_and_duplicate_parameters_fail():
    account={"autoTaggingEnabled":False,"finalUrlSuffix":ACCOUNT_SUFFIX+"&private=secret&UTM_MEDIUM=organic"}
    result=health(account,{})
    assert not result["checks"]["unique_parameters"]
    assert not result["checks"]["auto_tagging"]
    assert "secret" not in str(result)
