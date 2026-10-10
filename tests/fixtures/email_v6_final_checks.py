"""Focused recheck of the final source/template tests and exact baseline classifier."""
from tests.fixtures.email_v6_regression import Gate,KNOWN_BASELINE

def load_tests(loader,tests,pattern):
    return Gate(loader.loadTestsFromNames(sorted(KNOWN_BASELINE)+[
        'tests.test_crm_email_v6','tests.test_crm_email_v6_publication','tests.test_campaign_recovery']))
