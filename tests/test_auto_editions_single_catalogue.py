"""Unique catalogue presentation and safe failure diagnostics; synthetic only."""
import asyncio,json,sys
from pathlib import Path
from unittest.mock import patch
import pytest
import auto_editions_v17 as policy
import auto_editions_onboarding_api as api
from auto_editions_onboarding import detect,NeedsRepair
from tests.test_auto_editions_onboarding import inspection
from tests.test_auto_editions_v17 import continuous,prepared
from tests.test_auto_editions_discovery import database,store,pglite_database,PID,rows
from tests.test_auto_editions_api import request,ADMIN


def test_each_product_counted_once_and_remaining_is_a_subset(monkeypatch):
    monkeypatch.setenv('AUTO_EDITIONS_V17_CONTINUOUS_ENABLED','true')
    ready=dict(product_gid='p',display_status='Cloud Ready',uploaded=True)
    review=dict(product_gid='q',display_status='Needs Review',uploaded=True)
    result=policy.dashboard([ready,review,ready.copy(),review.copy()],2)
    assert result['Total mapped']==2 and result['Cloud Ready']==1 and result['Needs Review']==1
    assert result['Remaining']==1 and result['Uploaded']==2


def test_summary_separates_catalogue_from_mapped_without_duplicate_options(prepared):
    d,sql,*_=prepared
    for n in (1000,1001):
        sql.execute('INSERT INTO edition_products VALUES(%s,%s,%s,%s,100,1,true,true)',('gid://shopify/Product/'+str(n),str(n),'Art '+str(n),'art-'+str(n)))
    before=rows(sql,'edition_allocations'),rows(sql,'product_psd_mappings'),rows(sql,'auto_edition_layouts')
    duplicated=d.queue.rows()*2
    with patch.object(d.queue,'rows',return_value=duplicated),patch.object(api,'queue',return_value=d.queue),patch.object(api.api,'actor',return_value=ADMIN):
        result=asyncio.run(api.summary(request('GET')))
    assert result.status_code==200,result.body
    value=json.loads(result.body)
    assert value['catalogue_total']==3 and value['mapped']==1
    assert len(value['rows'])==1 and value['counts']['Needs Review']==1
    assert before==(rows(sql,'edition_allocations'),rows(sql,'product_psd_mappings'),rows(sql,'auto_edition_layouts'))


@pytest.mark.parametrize('profile',[None,''])
def test_known_missing_profile_requires_review_before_photoshop(profile):
    source=inspection();source['document']['profile']=profile
    with pytest.raises(NeedsRepair,match='colour profile is unavailable'):detect(source,100)
    source['document']['profile']='sRGB IEC61966-2.1'
    assert detect(source,100)['number_layer']=='001 / 100'


def test_photoshop_cause_is_retained_without_exposing_paths_or_capabilities(tmp_path):
    sys.path.insert(0,str(Path(__file__).parents[1]/'scripts/studio'));import auto_editions_local as local
    secret='s'*43;ticket='t'*43;lease='l'*43
    row=dict(folder=tmp_path,context=dict(product_gid=PID,lease_token=lease),grant=dict(secret=secret,ticket=ticket,base_url='https://allowed.test'))
    public=local.failure_detail(row,'Preparation',RuntimeError('Photoshop scripting failed: source_profile_requires_review '+secret+' '+ticket+' '+lease+' C:/private/art.psd https://allowed.test?ticket='+ticket))
    detail=json.loads((tmp_path/'failure-detail.json').read_text())
    assert detail['error_type']=='RuntimeError' and 'source_profile_requires_review' in detail['message']
    assert all(value not in json.dumps(detail) for value in (secret,ticket,lease))
    assert row['repair'] is True and 'owner review' in public and 'C:/' not in public
    assert 'private' not in local.failure_detail(row,'Preparation',RuntimeError('Photoshop scripting failed: C:/private/art.psd'))
