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
    if selected.get('source_dimensions'):
        doc=inspection.get('document') or {}
        if [doc.get('width_px'),doc.get('height_px')]!=selected['source_dimensions']:
            raise ValueError('Pinned canvas geometry changed; artwork review required.')
    rows=inspection.get('layers',[])
    for role in ('number','plaque')+ (('hidden_number',) if selected.get('hidden_number') else ()):
        expected=selected[role]
        found=[r for r in rows if len(r.get('path',[]))==1 and r['path'][0].get('name')==expected['name']]
        if len(found)!=1:raise ValueError('Pinned '+role+' identity changed; artwork review required.')
        row=found[0]
        if (row.get('layer_id')!=expected['layer_id'] or row.get('bounds_px')!=expected['bounds_px']
                or row.get('kind')!=expected['kind'] or not row.get('visible') or row.get('smart_object_chain')):
            raise ValueError('Pinned '+role+' evidence changed; artwork review required.')
        if role=='hidden_number':
            b=row['bounds_px'];p=selected['plaque']['bounds_px']
            if not (p[0]<=b[0]<b[2]<=p[2] and p[1]<=b[1]<b[3]<=p[3]):
                raise ValueError('Approved obsolete number extends outside its plaque.')
    return selected['plaque']['name']


def reviewed_rows(inspection,source):
    """Only an owner-selected obsolete field may be ignored on a staged copy."""
    selected=resolution(source)
    if not selected or not selected.get('hidden_number'):return inspection.get('layers',[])
    plaque(inspection,source)
    from copy import deepcopy
    rows=deepcopy(inspection['layers'])
    for row in rows:
        if row.get('layer_id')==selected['hidden_number']['layer_id']:row['visible']=False
    return rows
