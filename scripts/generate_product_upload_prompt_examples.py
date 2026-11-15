"""Generate representative synthetic prompts; never reads production data."""
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.test_product_upload_compact import fixture, prompt

row = fixture('LIVE', 'NBA', 'Courtside Legacy')
# Explicit synthetic identities make checked-in examples reproducible.
old = row['id']
key = '12345678-1234-4234-8234-123456789abc'
row['id'] = key
op = row['data']['upload_operation']
op['id'] = key
row['data']['mockup_save_token'] = op['output']['save_token'] = 'synthetic-save-001'
receipt = row['data']['mockup_saves']['saved']['receipt']
receipt['webp_folder']['id'] = 'id:synthetic-webp-folder'
for item in receipt['successes']:
    item['metadata']['id'] = item['metadata']['id'].replace(old, 'synthetic')
row['data'].update(subjects=['Michael Jordan'], customer_facing_title='Michael Jordan — Courtside Legacy',
                   confirmed_limit=100, worldwide=True, sku_prefix='MJCL',
                   product_context='Basketball collector artwork; no specific event or score is asserted.')
folder = ROOT/'docs/product-upload-compact-examples'
folder.mkdir(parents=True, exist_ok=True)
lengths={}
for mode in ('LIVE', 'DRAFT', 'UPDATE'):
    row['mode'] = mode
    if mode == 'UPDATE':
        op['product_id']='gid://shopify/Product/123456789'
        op['product']={'handle':'synthetic-courtside-legacy','title':'Michael Jordan — Courtside Legacy'}
        row['data'].pop('customer_facing_title') # Media-only, no requested title edit.
    text=prompt(row)
    (folder/(mode.lower()+'.txt')).write_text(text+'\n',encoding='utf-8')
    lengths[mode]={'characters':len(text),'words':len(text.split())}
(folder/'lengths.json').write_text(json.dumps(lengths,indent=2)+'\n',encoding='utf-8')
print(json.dumps(lengths))
