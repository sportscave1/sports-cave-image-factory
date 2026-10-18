"""Pinned role evidence from read-only source and labelled-layer review.

Never infer a plaque from position/name or apply an override to changed bytes.
Native font, geometry, pixel and cloud-receipt validation remain mandatory.
"""
import json
from pathlib import Path

REGISTRY=Path(__file__).parent/'config/auto_editions/ordered-source-roles-20261018.json'

def resolution(source):
    if not source:return None
    data=json.loads(REGISTRY.read_text())
    found=[r for r in data['resolutions'] if r['source']==source]
    if len(found)>1:raise ValueError('Conflicting pinned artwork role evidence.')
    return found[0] if found else None

def plaque(inspection,source):
    selected=resolution(source)
    if not selected:return None
    rows=inspection.get('layers',[])
    for role in ('number','plaque'):
        expected=selected[role]
        found=[r for r in rows if len(r.get('path',[]))==1 and r['path'][0].get('name')==expected['name']]
        if len(found)!=1:raise ValueError('Pinned '+role+' identity changed; artwork review required.')
        row=found[0]
        if (row.get('layer_id')!=expected['layer_id'] or row.get('bounds_px')!=expected['bounds_px']
                or row.get('kind')!=expected['kind'] or not row.get('visible') or row.get('smart_object_chain')):
            raise ValueError('Pinned '+role+' evidence changed; artwork review required.')
    return selected['plaque']['name']
