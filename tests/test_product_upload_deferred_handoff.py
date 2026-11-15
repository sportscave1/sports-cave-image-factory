"""Exercise actual page mount decisions without cloud access or image work."""
import ast
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from tests.test_product_upload_package import saved_row

ROOT = Path(__file__).resolve().parents[1]


def render_fixture(monkeypatch, row):
    import product_upload_intake as intake
    import product_upload_jobs as jobs
    import product_upload_api as api
    row['data'].update(basic_validated=True)
    key = str(row['id'])
    component = Mock(return_value=None)
    st = SimpleNamespace(session_state={'_product_upload_visit':'visit','_product_upload_active':key},
        query_params={}, html=Mock(), container=lambda **kw:nullcontext(), rerun=Mock())
    app = SimpleNamespace(BASE_DIR=ROOT, current_os_user=lambda:{'id':'owner'},
        get_components_module=lambda:SimpleNamespace(declare_component=lambda *a,**kw:component))
    read=Mock(return_value=row)
    monkeypatch.setattr(intake.Intakes,'read',read)
    monkeypatch.setattr(api,'Dropbox',Mock(side_effect=AssertionError('No Dropbox during page render')))
    snapshot=Mock(return_value=None);monkeypatch.setattr(jobs.JOBS,'snapshot',snapshot)
    public=Mock(wraps=intake.public);monkeypatch.setattr(intake,'public',public)
    node=next(n for n in ast.parse((ROOT/'product_upload_mockups_ui.py').read_text(encoding='utf-8')).body
              if isinstance(n,ast.FunctionDef) and n.name=='render_page')
    design=Mock();ns={'st':st,'render_design':design}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'actual-page','exec'),ns)
    def render():
        component.reset_mock();ns['render_page'](app)
        return [call.kwargs for call in component.call_args_list if call.kwargs.get('section')=='handoff']
    return SimpleNamespace(render=render,st=st,public=public,snapshot=snapshot,design=design,read=read)


@pytest.mark.parametrize('stage',['empty','selected','preparing','generating','saving','partial','failed','missing-folder','changed-source','changed-images','manual'])
def test_final_component_absent_until_complete_current_save(monkeypatch,stage):
    from product_upload_source import invalidate
    row=saved_row();fixture=render_fixture(monkeypatch,row)
    if stage=='empty':fixture.st.session_state.pop('_product_upload_active')
    elif stage in ('selected','preparing'):row['data']['mockups_exported']=False
    elif stage in ('generating','saving'):
        fixture.snapshot.side_effect=lambda key,actor,op:dict(state='Running') if op==('generate' if stage=='generating' else 'save') else None
    elif stage=='partial':row['data']['mockup_saves']['saved']['receipt']['successes'].pop()
    elif stage=='failed':row['data']['mockup_saves']['saved']['receipt']['failures']=[dict(error='Transfer failed')]
    elif stage=='missing-folder':row['data']['mockup_saves']['saved']['receipt']['successes'][0]['metadata'].pop('path_display')
    elif stage=='changed-source':row['data']['source']['rev']='new'
    elif stage=='changed-images':invalidate(row)
    elif stage=='manual':fixture.st.session_state['_product_upload_manual']=True
    assert fixture.render()==[]
    if stage in ('empty','selected','preparing','generating','saving','changed-images','manual'):
        fixture.public.assert_not_called() # No manifest validation/build before Save All.
    if stage not in ('empty','manual'):fixture.design.assert_called_once()


def test_current_receipt_mounts_then_edits_and_new_product_unmount(monkeypatch):
    from product_upload_source import current_source,invalidate
    row=saved_row();fixture=render_fixture(monkeypatch,row)
    ready=fixture.render()
    assert len(ready)==1 and ready[0]['source_version']==current_source(row)['version']
    assert ready[0]['id']==row['id'] and ready[0]['mode']=='DRAFT'
    invalidate(row)
    assert fixture.render()==[]
    # A late old save cannot re-enable this page with only the old exported flag.
    row['data']['mockups_exported']=True
    assert fixture.render()==[]
    fixture.st.session_state['_product_upload_active']='new-product'
    fixture.read.return_value=dict(id='new-product',data={'basic_validated':True},mode='LIVE')
    assert fixture.render()==[]
