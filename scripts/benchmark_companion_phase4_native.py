"""Exclusive, immutable-fixture Phase 4 trials. Never accesses live providers.

Requires the existing native admission guard and processor lease. Leaves outputs
for independent comparisons; never closes pre-existing documents or Photoshop.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
RELEASED_ROOT=Path('C:/Dev/SportsCaveWorktrees/sports-cave-integrations-companion-phase-1-processing-and-upload-sp-20261019-2a576331')
sys.path[:0]=[str(ROOT),str(ROOT/'scripts/studio')]
from scripts.benchmark_auto_editions_native_v19 import require_admission,processor_lease,Sample,cleanup_proven,preflight,BenchmarkBlocked
from scripts.photoshop_dispatch import run
import auto_editions as ae


def inventory():
    lib=(ROOT/'scripts/photoshop/inspect_psd_editions.jsx').read_text(encoding='utf-8-sig').split('if(typeof SC_PSD_INSPECT_REQUEST')[0]
    return json.loads(run(lib+'''\n(function(){var docs=[];for(var i=0;i<app.documents.length;i++)docs.push({id:app.documents[i].id,name:app.documents[i].name});
    var prefs={};try{prefs.historyStates=app.preferences.numberOfHistoryStates;}catch(e){}
    try{prefs.maxRAMuse=app.preferences.maxRAMuse;}catch(e){}
    var info=app.systemInformation.split(/\\r?\\n/),resources=[];for(var j=0;j<info.length;j++)if(/^(Memory available|Memory used|Memory usage|Scratch volume|Free space|Available space|Image cache levels|Physical memory)/i.test(info[j]))resources.push(info[j]);
    return SCPSDInspector.encode({documents:docs,version:app.version,preferences:prefs,resources:resources});})();'''))


def close_empty_photoshop():
    """Only for an owner-authorised exclusive benchmark window.

    Closing an empty app may release cache when RAM is below the rendering
    guard. This does not admit a render: every subsequent trial still requires
    the unchanged full RAM/native guard. No forced termination or prefs writes.
    """
    import psutil
    state=preflight()
    if not state['allowed']:raise BenchmarkBlocked('Exclusive native ownership required for normal empty-app close.')
    if not state['photoshop_pids']:return
    if len(state['photoshop_pids'])!=1:raise BenchmarkBlocked('Ambiguous Photoshop process ownership.')
    lease=processor_lease()
    try:
        before=inventory()
        if before['documents']:raise BenchmarkBlocked('Existing open documents; Photoshop was not closed.')
        try:run("if(app.documents.length)throw Error('open_documents');executeAction(charIDToTypeID('quit'),new ActionDescriptor(),DialogModes.NO);")
        except RuntimeError:pass # A normal COM server exit can lose its return ACK.
        deadline=time.monotonic()+30
        while any(psutil.pid_exists(pid) for pid in state['photoshop_pids']) and time.monotonic()<deadline:time.sleep(.1)
        if any(psutil.pid_exists(pid) for pid in state['photoshop_pids']):raise BenchmarkBlocked('Normal Photoshop close not confirmed; nothing forcibly terminated.')
    finally:lease.unlink()


VOLATILE_XMP={
    '{http://ns.adobe.com/xap/1.0/mm/}InstanceID',
    '{http://ns.adobe.com/xap/1.0/mm/}DocumentID',
    '{http://ns.adobe.com/xap/1.0/}MetadataDate',
    '{http://ns.adobe.com/xap/1.0/}ModifyDate',
    '{http://ns.adobe.com/xap/1.0/sType/ResourceEvent#}when',
    '{http://ns.adobe.com/xap/1.0/sType/ResourceEvent#}instanceID',
    '{http://ns.adobe.com/xap/1.0/sType/ResourceRef#}instanceID',
}


def stable_xmp(value,profile=None):
    import xml.etree.ElementTree as xml
    root=xml.fromstring(value)
    for node in root.iter():
        for key in VOLATILE_XMP:node.attrib.pop(key,None)
        if profile is not None:
            # Review writer hints against the independently checked actual ICC.
            # Older Photoshop PNGs have no label/65535 even after byte-exact
            # profile repair. A correct embedded writer label is equivalent;
            # a conflicting profile name or false sRGB claim is never ignored.
            label=node.attrib.pop('{http://ns.adobe.com/photoshop/1.0/}ICCProfile',None)
            if label is not None and label not in (profile['name'],profile['description']):
                raise ValueError('Conflicting XMP profile label.')
            space=node.attrib.pop('{http://ns.adobe.com/exif/1.0/}ColorSpace',None)
            if space is not None and space!='65535' and not (space=='1' and 'srgb' in profile['description'].lower()):
                raise ValueError('Conflicting XMP colour-space hint.')
    return xml.tostring(root)


def compare_packages(left,right):
    """Independent all-output comparison, allowing only reviewed XMP volatility.

    This never modifies assets or production validators. The original strict
    V19 comparator remains unchanged. Dates/new derivative instance IDs differ
    even between two released runs; pixels, ICC and other metadata must agree.
    """
    from PIL import Image,ImageChops
    left,right=Path(left),Path(right)
    a=ae.validate_manifest(json.loads((left/'manifest.json').read_text()))
    b=ae.validate_manifest(json.loads((right/'manifest.json').read_text()))
    fields=('source','dimensions','source_dimensions','number_region','plaque_bounds','original_number_bounds','original_text','font','edition_total','resolution','source_modified','upscaled','preparation_geometry','number_layer_name','plaque_layer_name','print_ready')
    if any(a.get(k)!=b.get(k) for k in fields):raise ValueError('Preparation source, colour or geometry differs.')
    # Photoshop's writer may omit ICC on different saves after a history
    # restore. The existing byte-preserving repair must yield the SAME actual
    # profile in EVERY file below. Its list of repairs is diagnostic, not a
    # different colour interpretation; all other colour evidence stays exact.
    colour_a=dict(a['colour_evidence']);colour_b=dict(b['colour_evidence'])
    restored_a=colour_a.pop('restored_exports');restored_b=colour_b.pop('restored_exports')
    if colour_a!=colour_b:raise ValueError('Source colour approval or preservation differs.')
    assert a['edition_total']==100
    names=['original.png','master.png','reference-1.png','reference-100.png']+[f'number-{n}.png' for n in range(1,101)]
    for repairs in (restored_a,restored_b):
        if len(set(repairs))!=len(repairs) or not set(repairs)<=set(names):raise ValueError('Invalid profile-repair evidence.')
    volatile=0
    for name in names:
        with Image.open(left/name) as x,Image.open(right/name) as y:
            x.load();y.load()
            if x.mode!=y.mode or x.size!=y.size:raise ValueError('Geometry/mode differs: '+name)
            if not x.info.get('icc_profile') or x.info['icc_profile']!=y.info.get('icc_profile'):raise ValueError('ICC differs: '+name)
            from auto_editions_colour_source import profile_info
            profile=profile_info(x.info['icc_profile'])
            with ImageChops.difference(x,y) as delta:
                if any(channel.getbbox() for channel in delta.split()):raise ValueError('Decoded pixels differ: '+name)
            if set(x.info)!=set(y.info):raise ValueError('PNG metadata fields differ: '+name)
            for key,value in x.info.items():
                if key in ('xmp','XML:com.adobe.xmp'):
                    if stable_xmp(value,profile)!=stable_xmp(y.info[key],profile):raise ValueError('Nonvolatile XMP differs: '+name)
                    if value!=y.info[key]:volatile+=1
                elif value!=y.info[key]:raise ValueError('Required PNG metadata differs: '+name)
    jpg='edition-001-TEST-NOT-PRINT-READY.jpg'
    if ae.file_hash(left/jpg)!=ae.file_hash(right/jpg):raise ValueError('JPEG bytes differ.')
    return dict(pngs_pixel_exact=len(names),all_100_patches=True,icc_exact=True,required_metadata_exact=True,
                jpeg_bytes_exact=True,volatile_xmp_fields_reviewed=sorted(VOLATILE_XMP),volatile_xmp_records=volatile,
                profile_repairs_before=len(restored_a),profile_repairs_after=len(restored_b))


def product(source,output,identity,variant='candidate'):
    from scripts.render_product_upload_psd import render
    if variant=='baseline':
        import subprocess,types
        module=types.ModuleType('released_native_web');module.__file__=str(ROOT/'scripts/render_product_upload_psd.py')
        exec(compile(subprocess.check_output(['git','show','58569c66:scripts/render_product_upload_psd.py'],cwd=ROOT),module.__file__,'exec'),module.__dict__)
        render=module.render
    import image_factory
    stages={}
    pipeline_started=time.perf_counter()
    def dispatch(script):
        stages['source_validation_staging_seconds']=time.perf_counter()-pipeline_started
        # Diagnostic-only instrumentation of unchanged released operations.
        script=script.replace('var oldDialogs=app.displayDialogs,','var p4timings={},p4start=new Date().getTime(),p4tick=p4start;\n  var oldDialogs=app.displayDialogs,')
        script=script.replace('doc=app.open(new File(r.input));','doc=app.open(new File(r.input));p4timings.open_ms=new Date().getTime()-p4tick;p4tick=new Date().getTime();')
        script=script.replace('var w=doc.width.as', 'p4timings.profile_ms=new Date().getTime()-p4tick;p4tick=new Date().getTime();\n    var w=doc.width.as')
        script=script.replace('report.dimensions=', 'p4timings.resize_ms=new Date().getTime()-p4tick;p4tick=new Date().getTime();\n    report.dimensions=')
        script=script.replace('}catch(error){failure=error;', 'p4timings.export_ms=new Date().getTime()-p4tick;\n  }catch(error){failure=error;')
        script=script.replace('try{if(doc&&!ids', 'p4tick=new Date().getTime();try{if(doc&&!ids')
        script=script.replace('report.owned_document_closed=closed;', 'p4timings.close_ms=new Date().getTime()-p4tick;p4timings.total_ms=new Date().getTime()-p4start;report.timings=p4timings;report.owned_document_closed=closed;')
        begin=time.perf_counter()
        try:return run(script)
        finally:
            stages['native_dispatch_seconds']=time.perf_counter()-begin
            stages['_dispatch_finished']=time.perf_counter()
    start=time.perf_counter();path,receipt=render(source,output/'render',identity,dispatch=dispatch)
    stages['native_web_pipeline_seconds']=time.perf_counter()-start
    stages['post_dispatch_verification_seconds']=time.perf_counter()-stages.pop('_dispatch_finished')
    from PIL import Image
    with Image.open(path) as image:
        image.load();render_pixels=hashlib.sha256(image.tobytes()).hexdigest();web_profile=image.info['icc_profile']
    # ICC creation time and profile ID may vary between otherwise identical
    # LittleCMS-generated web profiles. Do not mask source/edition ICC bytes.
    normalized_profile=web_profile[:24]+bytes(12)+web_profile[36:84]+bytes(16)+web_profile[100:]
    # Same five-image factory as Product Uploads; no prompt/provider work.
    with tempfile.TemporaryDirectory(prefix='sc-p4-images-') as temp:
        start=time.perf_counter()
        result=image_factory.generate_product_images('Pinstripe Immortals - Ruth & Mantle','Baseball',path,base_dir=ROOT,output_root=Path(temp))
        stages['core_mockups_seconds']=time.perf_counter()-start
        from PIL import Image
        assets=[]
        for asset in result['assets']:
            file=Path(asset['webp_path'])
            with Image.open(file) as image:
                image.load();assets.append(dict(key=asset['key'],dimensions=list(image.size),mode=image.mode,
                    pixels=hashlib.sha256(image.tobytes()).hexdigest(),bytes=file.stat().st_size))
        assert len(assets)==5
    stages['total_seconds']=time.perf_counter()-start+stages['native_web_pipeline_seconds']
    return dict(stages=stages,receipt=receipt,assets=assets,render_pixels=render_pixels,
        web_profile_sha256=hashlib.sha256(web_profile).hexdigest(),web_profile_semantics_sha256=hashlib.sha256(normalized_profile).hexdigest(),
        native=json.loads((output/'render/native-status.json').read_text(encoding='utf-8-sig')))


def trial(output,source,kind,strategy='duplicate_merged',variant='candidate'):
    output=Path(output).resolve();source=Path(source).resolve()
    if output.exists() or not output.is_relative_to(ROOT/'output/v19'):
        raise ValueError('New task-local output/v19 trial required.')
    admission=require_admission();lease=processor_lease();uncertain=False;result=dict(admission=admission,kind=kind,strategy=strategy,variant=variant)
    job_started=time.perf_counter()
    try:
        connected=time.perf_counter();before=inventory();result['photoshop_connection_startup_seconds']=time.perf_counter()-connected;result['photoshop_before']=before
        if before['documents']:raise ValueError('Existing open Photoshop documents: no benchmark dispatch permitted.')
        output.mkdir(parents=True)
        staged=output/'input.psd';begin=time.perf_counter();shutil.copyfile(source,staged)
        result['source_copy_seconds']=time.perf_counter()-begin
        sha=ae.file_hash(source);assert ae.file_hash(staged)==sha
        result['source']=dict(sha256=sha,bytes=source.stat().st_size)
        os.environ['AUTO_EDITIONS_COLOUR_POLICY_BACKEND']='file'
        os.environ['AUTO_EDITIONS_COLOUR_POLICIES_FILE']=str(Path.home()/'Documents/SportsCaveAutoEditions/colour-configuration/policies.json')
        os.environ['AUTO_EDITIONS_COLOUR_WORKFLOWS_FILE']=str(Path.home()/'Documents/SportsCaveAutoEditions/colour-configuration/memberships.json')
        import psutil
        ps_before={p.pid:p.io_counters() for p in psutil.process_iter(['name']) if (p.info['name'] or '').lower()=='photoshop.exe'}
        disk_before=psutil.disk_io_counters()
        if kind=='edition':
            manifest=json.loads((source.parent/'prepared/manifest.json').read_text())
            from scripts.prepare_auto_editions import prepare,native_cleanup_uncertain
            if variant=='baseline':
                import subprocess,types
                # Pin BOTH Python and JSX to the released Git objects. No reset
                # or edits in the retained released worktree.
                for name in ('scripts/photoshop/prepare_auto_editions.jsx','scripts/photoshop/inspect_psd_editions.jsx'):
                    assert (RELEASED_ROOT/name).read_text(encoding='utf-8-sig').replace('\r\n','\n')==subprocess.check_output(['git','show','58569c66:'+name],cwd=ROOT).decode('utf-8-sig').replace('\r\n','\n')
                module=types.ModuleType('released_edition_prepare');module.__file__=str(RELEASED_ROOT/'scripts/prepare_auto_editions.py')
                exec(compile(subprocess.check_output(['git','show','58569c66:scripts/prepare_auto_editions.py'],cwd=ROOT),module.__file__,'exec'),module.__dict__)
                prepare=module.prepare
            folder=output/'prepared';uncertain=True
            try:
                with Sample(output) as sample:
                    prepared=prepare(staged,folder,manifest['source'],number_layer=manifest['number_layer_name'],
                        plaque_layer=manifest['plaque_layer_name'],total=100,reference_number=1,scale=4,
                        export_strategy=strategy,native_benchmark=True)
            finally:uncertain=native_cleanup_uncertain(folder)
            result.update(prepared=prepared,resources=sample.result(),timings=json.loads((folder/'timings.json').read_text()))
            from auto_editions_transport import build_package
            names=['manifest.json','original.png','reference-1.png','reference-100.png','master.png']+[f'number-{n}.png' for n in range(1,101)]
            begin=time.perf_counter();result['package']=build_package(folder,names,output/'prepared.zip',compact=True)
            result['packaging_seconds']=time.perf_counter()-begin
        else:
            identity=dict(template_id='product-upload:id:u1tYiAa2O-AAAAAAAACGzQ',file_id='id:u1tYiAa2O-AAAAAAAACGzQ',
                revision='0165e3b47576fc1000000036d367e13',content_hash='ac5aa7d68a7265b76e22a95be0d3e684995599229d2c90c64d00f7927288e013')
            uncertain=True
            try:
                with Sample(output) as sample:result['product']=product(staged,output,identity,variant)
            finally:uncertain=(output/'render/dispatch-intent.json').exists() and not cleanup_proven(output/'render')
            result['resources']=sample.result()
        result['local_job_seconds']=time.perf_counter()-job_started
        disk_after=psutil.disk_io_counters()
        result['system_disk_delta_bytes']=dict(read=disk_after.read_bytes-disk_before.read_bytes,write=disk_after.write_bytes-disk_before.write_bytes)
        result['photoshop_logical_io_delta']={str(pid):{key:getattr(psutil.Process(pid).io_counters(),key)-getattr(value,key) for key in ('read_bytes','write_bytes')} for pid,value in ps_before.items() if psutil.pid_exists(pid)}
        result['retained_trial_bytes']=sum(p.stat().st_size for p in output.rglob('*') if p.is_file())
        assert ae.file_hash(source)==sha and ae.file_hash(staged)==sha
        result['photoshop_after']=inventory();assert result['photoshop_after']['documents']==before['documents']
        return result
    finally:
        if output.exists():(output/'phase4.json').write_text(json.dumps(result,indent=2))
        if not uncertain:lease.unlink()


def companion_product_fixture(source,output):
    """Actual run_one/Photoshop, fixture queue and local sink.

    Current live workflow v3 uses the server decoder. This checks the existing
    native v2 path without changing that production workflow or creating work.
    """
    from types import SimpleNamespace
    import threading
    from urllib.parse import urlparse
    import requests
    from tests.test_companion_phase2_transfers import receiver
    from companion_transfer import Controller
    from companion_atomic import atomic_json
    from scripts.studio.product_upload_render_local import run_one
    require_admission()
    output=Path(output).resolve();source=Path(source)
    if output.exists() or not output.is_relative_to(ROOT/'output/v19'):raise ValueError('New fixture output required.')
    installed=Path('C:/Dev/SportsCaveWorktrees/.studio/installed-releases/approved-e91d5d6ee2e33b57ba3cfb066b11b8125d1d40f8')
    name='scripts/studio/product_upload_render_local.py'
    assert ae.file_hash(ROOT/name)==ae.file_hash(installed/name),'Test must use the actual released companion runner.'
    output.mkdir(parents=True)
    identity=dict(template_id='product-upload:id:u1tYiAa2O-AAAAAAAACGzQ',file_id='id:u1tYiAa2O-AAAAAAAACGzQ',
        revision='0165e3b47576fc1000000036d367e13',content_hash='ac5aa7d68a7265b76e22a95be0d3e684995599229d2c90c64d00f7927288e013')
    job=dict(id='phase4-ruth',token='local-fixture',source=identity,workflow_version=2,
        metadata=dict(id=identity['file_id'],rev=identity['revision'],content_hash=identity['content_hash'],size=source.stat().st_size))
    owned=output/('product-upload-'+job['id']+'-attempt-1');owned.mkdir();shutil.copyfile(source,owned/'input.psd')
    before=ae.file_hash(source);calls=[]
    def request(config,path,body):
        calls.append(path.rsplit('/',1)[-1])
        if path.endswith('/claim'):return dict(job=job)
        if path.endswith('/heartbeat'):return dict(ok=True)
        raise AssertionError('Unexpected fixture render operation: '+path.rsplit('/',1)[-1])
    def acquire():
        require_admission();lease=processor_lease()
        try:
            if inventory()['documents']:raise BenchmarkBlocked('Open document; no native fixture started.')
        except Exception:lease.unlink();raise
        return lease
    controller=Controller();controller.configure(dict(mode='Manual',manual_mbps=50))
    host=SimpleNamespace(HOST_FILE=output/'host.dpapi',JOBS={},HOST_STOP=threading.Event(),
        host_request=request,processor_lease=acquire,atomic_json=atomic_json,transfer_controller=lambda:controller)
    os.environ['AUTO_EDITIONS_COLOUR_POLICY_BACKEND']='file'
    for key,file in [('AUTO_EDITIONS_COLOUR_POLICIES_FILE','policies.json'),('AUTO_EDITIONS_COLOUR_WORKFLOWS_FILE','memberships.json')]:
        os.environ[key]=str(Path.home()/'Documents/SportsCaveAutoEditions/colour-configuration'/file)
    prior_cache=os.environ.get('SPORTS_CAVE_COMPANION_SOURCE_CACHE');os.environ['SPORTS_CAVE_COMPANION_SOURCE_CACHE']=str(output/'cache')
    send=requests.sessions.Session.send
    def local_send(self,request,**kwargs):
        if urlparse(request.url).hostname not in ('127.0.0.1','localhost','::1'):raise AssertionError('No external fixture HTTP.')
        return send(self,request,**kwargs)
    requests.sessions.Session.send=local_send
    try:
        with receiver() as (url,rows,_),Sample(output) as sample:
            assert run_one(dict(base_url=url,token='local-fixture'),host)
        receipt=json.loads((owned/'render-v1/receipt.json').read_text())
        assert rows[0]['sha256']==receipt['render_sha256'] and receipt['source']==identity
        assert json.loads((owned/'completed.json').read_text())['verified'] and not host.JOBS
        assert ae.file_hash(source)==before
        result=dict(real_companion_runner=True,real_photoshop=True,fixture_queue=True,production_requests=0,
            source_unchanged=True,source=identity,receipt=receipt,resources=sample.result(),operations=calls,
            transfer=json.loads((owned/'transfer-timing.json').read_text()))
        (output/'companion-acceptance.json').write_text(json.dumps(result,indent=2));return result
    finally:
        requests.sessions.Session.send=send
        if prior_cache is None:os.environ.pop('SPORTS_CAVE_COMPANION_SOURCE_CACHE',None)
        else:os.environ['SPORTS_CAVE_COMPANION_SOURCE_CACHE']=prior_cache


def finish_companion_mockups(output):
    """Feed the confirmed fixture render into the current WEBP-only factory."""
    import image_factory as factory
    from PIL import Image
    output=Path(output).resolve()
    if not output.is_relative_to(ROOT/'output/v19'):raise ValueError('Owned native fixture required.')
    report=output/'companion-acceptance.json';result=json.loads(report.read_text())
    rendered=output/'product-upload-phase4-ruth-attempt-1/render-v1/render.png'
    if ae.file_hash(rendered)!=result['receipt']['render_sha256']:raise ValueError('Fixture render changed.')
    saved=output/'mockups';saved.mkdir();assets=[];started=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='sc-p4-confirmed-') as temp:
        images=factory.generate_product_images('Pinstripe Immortals - Ruth & Mantle','Baseball',rendered,
            base_dir=ROOT,output_root=Path(temp),final_prompt_items=[],export_jpg=False)
        generated=time.perf_counter()-started
        for asset in images['assets']:
            assert asset['key'] in ('black','oak','white','unframed','size-guide') and not asset['jpg_path']
            files={}
            for key in ('webp_path','preview_path','review_path'):
                path=Path(asset[key]);target=saved/(asset['key']+'-'+key+path.suffix);shutil.copyfile(path,target)
                with Image.open(target) as image:image.verify()
                files[key]=dict(path=str(target),bytes=target.stat().st_size,sha256=ae.file_hash(target))
            assets.append(dict(key=asset['key'],files=files))
    assert len(assets)==5
    result.update(mockups=assets,mockup_generation_seconds=generated,all_current_required_formats_verified=True)
    report.write_text(json.dumps(result,indent=2));return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);parser.add_argument('--source',required=True)
    parser.add_argument('--kind',choices=['edition','product'],required=True);parser.add_argument('--strategy',default='duplicate_merged')
    parser.add_argument('--variant',choices=['baseline','candidate'],default='candidate')
    args=parser.parse_args();print(json.dumps(trial(args.output,args.source,args.kind,args.strategy,args.variant),indent=2),flush=True)
