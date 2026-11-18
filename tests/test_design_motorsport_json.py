import json
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from design_motorsport import MOTORSPORT_JSON
from design_review_metadata import parse_handoff
from home_morning_brief_actions import _prompt
import morning_design_queue as queue
import product_upload_sport as selector


def test_motorsport_rule_is_at_json_step_and_is_shared_with_edits():
    prompt = _prompt('Silver & Soul', 'Verified Formula One tribute.')
    assert prompt.count(MOTORSPORT_JSON) == 1
    assert prompt.index('**6. Write the Smart Upload JSON') < prompt.index(MOTORSPORT_JSON)
    edited = _prompt('Silver & Soul', 'Existing approved edit', edit={
        'source':dict(id='id:art',rev='R1',path_display='/Review/Art.psd'),
        'metadata':{},
    })
    assert MOTORSPORT_JSON in edited


def test_waiting_job_gets_series_rule_without_changing_story_or_send_receipt():
    key = queue.identity('2026-11-18', 'legends', {'title':'Silver & Soul'})
    story = 'Verified Lewis Hamilton Formula One artwork; preserve the selected sources.'
    current = queue._job_prompt(key, 'Silver & Soul', story)
    job = dict(id=key,title='Silver & Soul',prompt=current.replace(MOTORSPORT_JSON,''))
    upgraded = queue._waiting_prompt(job)
    assert MOTORSPORT_JSON in upgraded and story in upgraded
    assert queue._receipt(dict(job,prompt=upgraded)) == queue._receipt(job)
    assert queue._waiting_prompt(dict(job,prompt=upgraded)) == upgraded


@pytest.mark.parametrize('sport', ['Formula One', 'NASCAR', 'V8 Supercars', 'MotoGP', 'Cricket'])
def test_specific_json_sport_selects_its_upload_folder_instead_of_generic_motorsport(monkeypatch, sport):
    source = dict(id='id:art',rev='R1',path_display='/Review/Art.psd')
    raw = dict(dropbox_file_id=source['id'],dropbox_revision='R1',dropbox_path=source['path_display'],
               design_title='Verified Art',sport=sport,intended_collections=['verified-collection'],
               review_status='ready_for_review',upload_intent='new_product',existing_shopify_product_id=None)
    details = parse_handoff(json.dumps(raw).encode(),source)
    root = '/Fixture'
    names = ['Motorsport','Formula One','NASCAR','V8 Supercars','MotoGP','Cricket']
    folders = [dict(id='id:'+str(i),name=name+' Wall Art',path_display=root+'/04_OUTPUT/product-images/'+name+' Wall Art',
                    **{'.tag':'folder'}) for i,name in enumerate(names)]
    api = SimpleNamespace(normalize_dropbox_path=lambda path:path,
        path_is_within_root=lambda path,base:path.startswith(base+'/'),
        list_folder_page=lambda *args,**kwargs:dict(entries=folders,has_more=False),
        get_metadata_if_exists=lambda token,key:next((folder for folder in folders if folder['id']==key),None))
    app = SimpleNamespace(dropbox_integration=api,
        os_accounts=SimpleNamespace(can_access_page=lambda *args:True),
        _files_access_token=lambda:'fixture',_files_team_root=lambda token:root)
    monkeypatch.setattr(selector,'_test_fixture',(app,details['sport']),raising=False)
    ui = AppTest.from_string("""
import product_upload_sport as selector
app, sport = selector._test_fixture
selector.render_selector(app,'fixture',{'id':'fixture'},suggested_sport=sport)
""").run()
    assert not ui.exception and not ui.error
    assert ui.selectbox[0].value == 'id:'+str(names.index(sport))


def test_motorsport_integration_reaches_shared_stages_and_waiting_jobs():
    from design_motorsport import MOTORSPORT_PLACEMENT, MOTORSPORT_INTEGRATION, MOTORSPORT_FINISH_CHECK
    from home_design_refresh import _refresh_prompt
    new = _prompt('Boss in Red', 'Verified Allan Moffat period touring-car tribute.')
    refresh = _refresh_prompt(dict(title='Current Moffat design', product_id='123'), 'https://example.test/product')
    for prompt in (new, refresh):
        for rule, start, end in ((MOTORSPORT_PLACEMENT, '**2.', '**3.'),
                                 (MOTORSPORT_INTEGRATION, '**3.', '**4.'),
                                 (MOTORSPORT_FINISH_CHECK, '**4.', '**5.')):
            assert prompt.count(rule) == 1
            assert prompt.index(start) < prompt.index(rule) < prompt.index(end)
        assert 'one creative image-generation call' in prompt
        assert 'never reinstate a corrected cutout seam' in prompt
        assert 'never invent missing detail or accept a lookalike' in prompt
    edited = _prompt('Moffat', 'A targeted edit', edit={
        'source':dict(id='id:art',rev='R1',path_display='/Review/Art.psd'), 'metadata':{}})
    assert all(rule in edited for rule in (MOTORSPORT_PLACEMENT, MOTORSPORT_INTEGRATION, MOTORSPORT_FINISH_CHECK))
    key = queue.identity('2026-11-19', 'legends', {'title':'Moffat'})
    current = queue._job_prompt(key, 'Moffat', 'Keep the verified original sources.')
    job = dict(id=key, title='Moffat', prompt=current.replace(MOTORSPORT_INTEGRATION, ''))
    upgraded = queue._waiting_prompt(job)
    assert MOTORSPORT_INTEGRATION in upgraded
    assert 'Keep the verified original sources.' in upgraded
    assert queue._receipt(dict(job, prompt=upgraded)) == queue._receipt(job)
    assert queue._waiting_prompt(dict(job, prompt=upgraded)) == upgraded
