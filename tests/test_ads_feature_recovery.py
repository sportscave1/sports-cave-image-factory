"""Optional Meta enhancement omission must not block a verified paused ad."""
from copy import deepcopy

import pytest
from meta_collection_template_copy import (
    REQUIRED_COLLECTION_FEATURES, MetaCollectionTemplateCopyService, collection_features_match,
)
from tests.test_meta_collection_template_copy import (
    FakeTemplateCopyClient, SOURCE_AD_ID, TARGET_ADSET_ID, target_creative,
)


def test_omitted_optional_cta_still_verifies_one_paused_copy():
    client = FakeTemplateCopyClient()
    original = client.creative

    def read(identity):
        creative = original(identity)
        if identity != 'source-creative':
            creative['degrees_of_freedom_spec']['creative_features_spec'].pop('enhance_cta', None)
        return creative

    client.creative = read
    result = MetaCollectionTemplateCopyService(client).create_one_paused_copy(
        source_ad_id=SOURCE_AD_ID,target_adset_id=TARGET_ADSET_ID,creative_parameters=target_creative())
    assert result['status'] == 'PASS'
    assert result['copied_configured_status'] == 'PAUSED'
    assert result['unavailable_requested_enhancements'] == ['enhance_cta']
    assert all(result['checks'].values()) and len(client.copy_calls) == 1


@pytest.mark.parametrize('name', [name for name in REQUIRED_COLLECTION_FEATURES if name != 'enhance_cta'])
def test_missing_artwork_protection_still_blocks(name):
    features = {name:{'enroll_status':status} for name,status in REQUIRED_COLLECTION_FEATURES.items()}
    features.pop('enhance_cta')
    assert collection_features_match(features)
    features.pop(name)
    assert not collection_features_match(features)


@pytest.mark.parametrize('value', [{},None,{'enroll_status':'OPT_OUT'}])
def test_explicit_conflicting_cta_still_blocks(value):
    features = {name:{'enroll_status':status} for name,status in REQUIRED_COLLECTION_FEATURES.items()}
    features['enhance_cta'] = value
    assert not collection_features_match(features)
