"""Current public prompt coverage across every selectable category and market."""
import unittest
import pytest
import ads_page as ads
from tests.ads_prompt_contracts import current_ie


@pytest.mark.parametrize('category',[c for c in ads.CATEGORY_OPTIONS if c!='Select category'])
@pytest.mark.parametrize('country',[c for c in ads.COUNTRY_OPTIONS if not c.startswith('Select ')])
def test_current_ie_public_contract_for_every_category_and_market(category,country):
    current_ie(unittest.TestCase(),category=category,country=country)
