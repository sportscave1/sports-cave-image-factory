"""Background responsiveness, exact source, cancellation and bounded caching."""
from pathlib import Path
import threading,time
from unittest.mock import Mock
import pytest
from product_upload_jobs import Jobs
import product_upload_artwork as artwork


def wait(jobs,key='one',actor='actor',operation='prepare'):
    end=time.monotonic()+5
    while time.monotonic()<end:
        job=jobs.snapshot(key,actor,operation)
        if job['state'] not in ('Queued','Running'):return job
        time.sleep(.005)
    raise AssertionError('Job did not finish')


def test_immediate_ack_duplicate_click_progress_and_actor_isolation():
    jobs=Jobs();gate=threading.Event();entered=threading.Event();calls=[]
    def work(progress):
        calls.append(1);entered.set();progress('Downloading PSD',10,100);gate.wait(3);progress('Checking file');return 'verified'
    start=time.monotonic();first=jobs.submit('one','actor','prepare',{'rev':'one'},work)
    assert time.monotonic()-start<.1 and entered.wait(1)
    second=jobs.submit('one','actor','prepare',{'rev':'one'},work)
    assert first['token']==second['token'] and calls==[1]
    assert jobs.snapshot('one','actor','prepare')['completed']==10
    assert jobs.snapshot('one','other','prepare') is None
    gate.set();job=wait(jobs)
    assert job['state']=='Ready' and jobs.result('one','actor','prepare',job['token'])=='verified'
    jobs.pool.shutdown()


def test_failed_job_retry_and_stale_result_cannot_overwrite_new_selection():
    jobs=Jobs();gate=threading.Event()
    jobs.submit('one','actor','prepare',{'rev':'one'},lambda p:(_ for _ in ()).throw(ValueError('Retry preparation')))
    assert wait(jobs)['state']=='Failed'
    old=jobs.submit('one','actor','prepare',{'rev':'one'},lambda p:(gate.wait(2),'old')[1])
    jobs.cancel('one','actor')
    new=jobs.submit('one','actor','prepare',{'rev':'two'},lambda p:'new')
    gate.set();assert wait(jobs)['state']=='Ready'
    assert jobs.result('one','actor','prepare',old['token']) is None
    assert jobs.result('one','actor','prepare',new['token'])=='new'
    jobs.pool.shutdown()


def test_background_queue_is_bounded():
    jobs=Jobs();gate=threading.Event()
    for number in range(16):jobs.submit(str(number),'actor','prepare',{},lambda p:gate.wait(2))
    with pytest.raises(ValueError,match='busy'):jobs.submit('overflow','actor','prepare',{},lambda p:None)
    gate.set();jobs.pool.shutdown()


def test_cache_pruning_preserves_active_derivatives_and_never_other_files(tmp_path):
    folders=[]
    for index in range(12):
        folder=tmp_path/('%064x'%index);folder.mkdir();(folder/'artwork.png').write_bytes(b'png');folders.append(folder)
    unrelated=tmp_path/'unrelated.psd';unrelated.write_bytes(b'original')
    keep=folders[-1]
    with artwork.lease(folders[0]):
        artwork.prune_cache(keep)
        assert folders[0].exists() and keep.exists()
    assert len(list(tmp_path.glob('*/artwork.png')))<=8
    assert unrelated.read_bytes()==b'original'


def test_terminal_preparation_progress_reruns_only_once(monkeypatch):
    import ast
    from types import SimpleNamespace
    import product_upload_jobs as jobs
    tree=ast.parse((Path(__file__).parents[1]/'product_upload_mockups_ui.py').read_text(encoding='utf-8'))
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='poll_render');fn.decorator_list=[]
    st=SimpleNamespace(session_state={'_product_upload_active':'one'},rerun=Mock())
    monkeypatch.setattr(jobs.JOBS,'snapshot',lambda *a:dict(state='Failed',token='failure'))
    scope=dict(st=st);exec(compile(ast.Module(body=[fn],type_ignores=[]),'progress-poll','exec'),scope)
    for _ in range(4):scope['poll_render']('one','actor','Failed')
    st.rerun.assert_called_once()


def test_generate_callback_uses_latest_form_values_without_doing_image_work(monkeypatch):
    import ast
    from types import SimpleNamespace
    import product_upload_jobs as jobs
    tree=ast.parse((Path(__file__).parents[1]/'product_upload_mockups_ui.py').read_text(encoding='utf-8'))
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='render_design');fn.decorator_list=[]
    callbacks={}
    def button(label,**kwargs):
        if label=='Generate mockups':callbacks['generate']=kwargs['on_click']
        return False
    st=SimpleNamespace(session_state={'_product_upload_active':'one'},subheader=Mock(),caption=Mock(),
        text_input=lambda *a,**k:k.get('value',''),selectbox=lambda *a,**k:'Football',button=button,error=Mock())
    app=SimpleNamespace(_mockups_result=lambda:None,alphabetize_options=lambda values,**k:values,
        SPORT_OPTIONS=['Football'],get_sport_category=lambda value,custom:value,BASE_DIR=Path('.'),
        MOCKUPS_GENERATION_SEMAPHORE=threading.Semaphore(1),build_mockup_final_prompt_items=Mock())
    row=dict(id='one',data=dict(name='Original.psd',workflow_version=3,server_artwork={'state':'Ready'},source={'content_hash':'a'*64}))
    submit=Mock();monkeypatch.setattr(jobs,'generate',submit);monkeypatch.setattr(jobs.JOBS,'snapshot',lambda *a:None)
    import product_upload_sport
    selection=dict(id='id:football',sport='Football',path='/Team/product-images/Football')
    monkeypatch.setattr(product_upload_sport,'render_selector',lambda *a,**k:selection)
    monkeypatch.setattr(product_upload_sport,'selected',lambda key:selection)
    app._files_access_token=lambda:'fixture'
    app._files_team_root=lambda token:'/Team'
    app.dropbox_integration=Mock()
    monkeypatch.setattr('product_upload_export.resolve_category',lambda *a:selection)
    scope=dict(st=st,Path=Path);exec(compile(ast.Module(body=[fn],type_ignores=[]),'render-design','exec'),scope)
    scope['render_design'](app,row,{'id':'actor'})
    st.session_state['product-upload-name-one']='Current product title'
    callbacks['generate']()
    assert submit.call_args.args[3]=='Current product title'
    assert submit.call_args.args[4]=='Football'
    submit.reset_mock()
    selection=None
    callbacks['generate']()
    submit.assert_not_called()
