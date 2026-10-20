from copy import deepcopy
from PIL import ImageCms
import pytest
from auto_editions_colour_policy import propose,approve,fingerprint,resolve
from auto_editions_colour_source import ColourReview
from product_upload_colour import resolve_web


@pytest.fixture
def approved():
    source=dict(product_gid='gid://shopify/Product/123',file_id='id:exact',revision='abc',content_hash='a'*64)
    evidence=dict(name='owner-preview.png',sha256='b'*64,purpose='Explicit intended appearance selection')
    icc=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    proposal=propose('exact-owner-review',icc,[dict(source=source,provenance=evidence)],[evidence],[evidence])
    policy=approve(proposal,'synthetic-owner',fingerprint(proposal))
    web={k:v for k,v in source.items() if k!='product_gid'};web['template_id']='product-upload:'+source['file_id']
    return source,web,icc,dict(policies=[policy],memberships=[],default_group='')


def test_same_exact_file_can_use_approval_before_product_exists(approved):
    original,web,icc,config=approved;before=deepcopy(config)
    with pytest.raises(ColourReview):resolve(web,**config)
    actual,receipt=resolve_web(web,config)
    assert actual==icc and receipt['approval_hash']==config['policies'][0]['approval_hash']
    assert config==before and config['policies'][0]['members'][0]['source']==original
    # Edition Ops matching remains unchanged.
    with pytest.raises(ColourReview):resolve({**original,'product_gid':'gid://shopify/Product/456'},**config)


@pytest.mark.parametrize('field,value',[('file_id','id:other'),('revision','def'),('content_hash','c'*64)])
def test_changed_source_never_inherits_exact_approval(approved,field,value):
    _,web,_,config=approved
    with pytest.raises(ColourReview,match='no matching exact-source approval'):resolve_web({**web,field:value},config)


def test_conflicting_or_tampered_policies_fail_closed(approved):
    _,web,_,config=approved
    policy=config['policies'][0];bad=deepcopy(policy);bad['profile']['sha256']='f'*64
    with pytest.raises(ColourReview):resolve_web(web,{**config,'policies':[bad]})
    from auto_editions_colour_policy import propose,approve
    original=policy['members'][0]['source'];evidence=policy['references'][0]
    proposal=propose('second-owner-review',ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes(),[dict(source=original,provenance=evidence)],[evidence],[evidence])
    other=approve(proposal,'synthetic-owner',fingerprint(proposal))
    with pytest.raises(ColourReview,match='Conflicting'):resolve_web(web,{**config,'policies':[policy,other]})


def test_companion_uses_synced_exact_approval_without_global_default(approved,tmp_path,monkeypatch):
    import json
    _,web,icc,config=approved;p=tmp_path/'policies.json';p.write_text(json.dumps(config['policies']))
    monkeypatch.setenv('AUTO_EDITIONS_COLOUR_POLICIES_FILE',str(p))
    monkeypatch.delenv('AUTO_EDITIONS_COLOUR_WORKFLOWS_FILE',raising=False)
    monkeypatch.delenv('AUTO_EDITIONS_UNTAGGED_RGB_DEFAULT',raising=False)
    assert resolve_web(web)[0]==icc


def test_product_upload_fingerprint_covers_resolver_and_policies(monkeypatch):
    import product_upload_artwork as artwork
    import auto_editions_colour_store as store
    config=dict(policies=[],memberships=[],default_group='')
    monkeypatch.setattr(store,'configuration',lambda _:config)
    before=artwork.settings(None);config['default_group']='changed-reviewed-configuration'
    assert artwork.settings(None)!=before
