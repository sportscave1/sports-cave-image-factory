"""Write reproducible local draft bundle and baseline source manifest."""
import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crm_lifecycle_definition import expanded_flow
out=Path('docs/lifecycle-expansion-evidence');out.mkdir(exist_ok=True)
flows=[]
for kind in ('welcome','post_purchase','win_back'):
    definition=expanded_flow(kind)
    flows.append(dict(trigger=kind,status='DRAFT',definition=definition,email_statuses=['DRAFT']*len(definition['emails'])))
(out/'ten-email-drafts.json').write_text(json.dumps(dict(production_written=False,flows=flows),ensure_ascii=False,indent=2),encoding='utf-8')
manifest=[]
for original in sorted(Path('tmp/lifecycle-baseline').glob('crm_*.py')):
    current=Path(original.name)
    before=hashlib.sha256(original.read_bytes()).hexdigest()
    after=hashlib.sha256(current.read_bytes()).hexdigest()
    manifest.append(dict(file=current.name,unchanged=before==after,before_sha256=before,after_sha256=after))
(out/'source-baseline.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps(dict(changed_existing_modules=[r['file'] for r in manifest if not r['unchanged']],unchanged_existing_modules=sum(r['unchanged'] for r in manifest),draft_emails=10),indent=2))
