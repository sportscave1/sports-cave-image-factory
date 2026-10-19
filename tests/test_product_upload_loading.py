"""Generation transitions retain progress/errors and apply completed results once."""
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
ROOT=Path(__file__).parents[1]

@pytest.mark.parametrize('state',['Queued','Running','Failed','Ready'])
def test_generation_loading_transitions(state,monkeypatch):
    import product_upload_jobs as jobs
    node=next(n for n in ast.parse((ROOT/'product_upload_mockups_ui.py').read_text(encoding='utf-8')).body
              if isinstance(n,ast.FunctionDef) and n.name=='poll_generation')
    node.decorator_list=[]
    st=SimpleNamespace(session_state={'_product_upload_active':'one'},progress=Mock(),caption=Mock(),html=Mock(),error=Mock(),info=Mock(),rerun=Mock())
    result=dict(_product_upload_source_hash='source',product_name='Title',sport_category='Cricket')
    app=SimpleNamespace(normalize_generation_result=lambda r:r,_set_mockups_result=Mock())
    monkeypatch.setattr(jobs.JOBS,'snapshot',lambda *a:dict(state=state,total=5,completed=2,stage='Rendering',previews=[],token='job',error='Retry generation'))
    monkeypatch.setattr(jobs.JOBS,'result',lambda *a:result)
    ns={'st':st};exec(compile(ast.Module(body=[node],type_ignores=[]),'poll','exec'),ns)
    for _ in range(2):ns['poll_generation'](app,'one','actor','Title','Cricket','source')
    if state in ('Queued','Running'):
        assert st.progress.call_args.kwargs['text']=='Generating mockups · 2 of 5'
        st.rerun.assert_not_called();app._set_mockups_result.assert_not_called()
    elif state=='Failed':
        st.error.assert_called_with('Retry generation');st.rerun.assert_called_once()
        app._set_mockups_result.assert_not_called()
    else:
        app._set_mockups_result.assert_called_once_with(result);st.rerun.assert_called_once()


def test_loading_style_installed_before_reads_and_scoped_to_product_upload():
    source=(ROOT/'product_upload_mockups_ui.py').read_text(encoding='utf-8')
    assert source.index('product-upload-page-marker')<source.index("event=component")<source.index('row=Intakes')
    css=(ROOT/'product_upload_page.css').read_text(encoding='utf-8')
    assert '[data-testid="stMain"]:has(.product-upload-page-marker) [data-stale="true"]' in css
    assert 'opacity:1!important' in css
    # Rendering remains responsible for disabling unsafe actions; no CSS bypass.
    assert 'pointer-events' not in css
    assert 'elif not running and not result:' in source
