from pathlib import Path
import sys, subprocess, json, time
sys.path.insert(0,str(Path('scripts/studio').resolve()))
import studio, preview_runtime
r=preview_runtime.Preview(studio.DEFAULT_HOME,'20261127-9ead4f59','codex-speed-20261128-upload',artwork_scratch=True)
out=Path('output/upload-queue-speed')/sys.argv[1];out.mkdir(parents=True,exist_ok=False)
e={"commit":subprocess.check_output(["git","rev-parse","HEAD"]).decode().strip(),"base":"ec0d54c3455a73b2bc18358d2b11f4a5ea2abee5"}
try:
 r.start();e['policy']=r.evidence
 r._docker('exec',r.container_id,'python','-B','-c',"from pathlib import Path;Path('/tmp/source/design_review_validation.py').write_text("+repr(Path('design_review_validation.py').read_text())+")")
 migrations=[Path('migrations',name).read_text() for name in ('20261117110000_product_upload_staff_queue.sql','20261118070000_product_upload_manual_restart.sql')]
 setup="import psycopg; c=psycopg.connect('postgresql://studio@127.0.0.1:55432/studio?sslmode=disable');"+';'.join('c.execute('+repr(m)+')' for m in migrations)+";c.commit()"
 r._docker('exec',r.container_id,'python','-B','-c',setup)
 child="""import sys,time,json,os,uuid
sys.path.insert(0,'/tmp/source')
os.environ['DATABASE_URL']='postgresql://studio@127.0.0.1:55432/studio?sslmode=disable'
import product_upload_staff_queue as q
from psd_directory import REVIEW_FOLDER
source={'.tag':'file','id':'id:synthetic','rev':uuid.uuid4().hex,'name':'Synthetic.psd','path_display':REVIEW_FOLDER+'/Synthetic.psd'}
rows=[]
for i in range(4):
 t=time.perf_counter();key=q.enqueue({'id':'synthetic-staff'},source,'Synthetic','NFL Wall Art');rows.append((time.perf_counter()-t)*1000)
 assert key
print(json.dumps(dict(enqueue_ms=rows)))
"""
 baseline=subprocess.check_output(['git','show','ec0d54c3455a73b2bc18358d2b11f4a5ea2abee5:product_upload_staff_queue.py']).decode()
 candidate=Path('product_upload_staff_queue.py').read_text()
 e['baseline_samples']=[]
 def install_queue(source):
  transfer=subprocess.run(['docker','--context',r.docker_context,'exec','-i',r.container_id,'python','-B','-c',"from pathlib import Path;import sys;Path('/tmp/source/product_upload_staff_queue.py').write_text(sys.stdin.read())"],input=source.encode(),capture_output=True,timeout=30)
  assert transfer.returncode==0,transfer.stderr
 install_queue(baseline)
 for i in range(3):
  p=r._docker('exec',r.container_id,'python','-B','-c',child)
  e['baseline_samples'].append(json.loads(p.stdout.splitlines()[-1]))
 install_queue(candidate)
 e['cold_samples']=[]
 for i in range(3):
  p=r._docker('exec',r.container_id,'python','-B','-c',child)
  e['cold_samples'].append(json.loads(p.stdout.splitlines()[-1]))
 print(json.dumps(e['cold_samples']),flush=True)
 import io,tarfile
 buf=io.BytesIO()
 with tarfile.open(fileobj=buf,mode='w') as archive:
  vendor=Path('C:/Users/hello/Documents/sports-cave-image-factory/.venv/Lib/site-packages')
  archive.add(vendor/'py.py',arcname='py.py')
  archive.add('worker_diagnostics.py',arcname='worker_diagnostics.py')
  for name in ('auto_editions_local.py','edition_test_local.py'):archive.add(Path('scripts/studio')/name,arcname='scripts/studio/'+name)
  for package in ('pytest','_pytest','pluggy','iniconfig','packaging','pygments'):
   for file in (vendor/package).rglob('*.py'):archive.add(file,arcname=str(file.relative_to(vendor)).replace('\\','/'))
  for pattern in ('tests/*.py','migrations/*.sql','scripts/sql/*.sql','supabase/migrations/*.sql'):
   for file in Path('.').glob(pattern):archive.add(file,arcname=str(file).replace('\\','/'))
 transfer=subprocess.run(['docker','--context',r.docker_context,'exec','-i',r.container_id,'python','-B','-c',"import tarfile,sys;tarfile.open(fileobj=sys.stdin.buffer,mode='r|').extractall('/tmp/source',filter='data')"],input=buf.getvalue(),capture_output=True,timeout=30)
 assert transfer.returncode==0,transfer.stderr
 r._docker('exec',r.container_id,'python','-B','-c',"from pathlib import Path;p=Path('/tmp/source/config/auto_editions');p.mkdir(parents=True,exist_ok=True);(p/'icc-policies-20261017.json').write_text('[]');(p/'colour-runtime-20261017.json').write_text('{\"default_group\":\"\"}')")
 p=r._docker('exec','-w','/tmp/source','-e','STATUS_PHASE1_ISOLATED_POSTGRES=1',r.container_id,'python','-B','-m','pytest','-q','tests/test_product_upload_staff_queue.py','tests/test_design_review_gallery.py','tests/test_design_review_smart_upload.py',timeout=180,check=False)
 (out/'tests.log').write_text(p.stdout+p.stderr);e['tests_exit']=p.returncode
 print(p.stdout[-3000:]+p.stderr[-1000:],flush=True)
 assert p.returncode==0
 browser_payload='BASELINE_QUEUE='+repr(baseline)+'\nCANDIDATE_QUEUE='+repr(candidate)+'\n'+Path('scripts/upload_queue_browser_contract.py').read_text()
 browser=subprocess.run(['docker','--context',r.docker_context,'exec','-i',r.container_id,'python','-B','-'],input=browser_payload.encode(),capture_output=True,timeout=240)
 (out/'browser.log').write_bytes(browser.stdout+browser.stderr)
 print(browser.stdout.decode()[-2000:]+browser.stderr.decode()[-2000:],flush=True)
 e['browser_exit']=browser.returncode
 frames=json.loads(r._docker('exec',r.container_id,'python','-B','-c',"import pathlib,json,base64;print(json.dumps({p.name:base64.b64encode(p.read_bytes()).decode() for p in pathlib.Path('/tmp/upload-browser-frames').glob('*.png')}))").stdout)
 import base64
 for name,data in frames.items():(out/name).write_bytes(base64.b64decode(data))
 assert browser.returncode==0
 e["browser"]=json.loads(next(line.split("=",1)[1] for line in browser.stdout.decode().splitlines() if line.startswith("UPLOAD_BROWSER_RESULT=")))
 e.update(phase2_verified=True,functional_checks_passed=True,behaviour_preserved=True,purpose="upload-cold-dependency",baseline_samples_ms=[s["enqueue_ms"][0] for s in e["baseline_samples"]],candidate_samples_ms=[s["enqueue_ms"][0] for s in e["cold_samples"]])

finally:
 r.stop();(out/'enqueue-diagnosis.json').write_text(json.dumps(e,indent=2))
