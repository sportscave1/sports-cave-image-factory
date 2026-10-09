"""Incomplete refreshes use the existing durable workspace, never a Meta write."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from uuid import uuid4

import ads_posting_handoff as handoff
from posting_import_csv import canonical_posting_country, posting_product_handle_from_url


def package(ads, result, workflow, folder):
    kind=result['campaign_type']
    shared={k:result.get(k,'') for k in ('product_id','product_name','product_url')}
    shared.update(country=canonical_posting_country(result.get('country')),
                  sport_category=result.get('category',''),campaign_type=kind,
                  product_handle=posting_product_handle_from_url(result.get('product_url')))
    if kind=='Carousel':
        copy=ads._carousel_copy_notes_from_workflow(result,workflow)
        batch={**shared,'source_schema_kind':'carousel','saved_refresh_draft':True,
               'cards':[{**c,'card_number':c['position']} for c in copy['cards']],
               'primary_texts':copy['primary_texts']}
        csv=ads.build_carousel_copy_csv(result,workflow,carousel_notes=copy)
    elif kind=='Instant Experience':
        copy=ads._instant_experience_concept_copy_notes_from_workflow(workflow)
        batch={**shared,'source_schema_kind':'saved_refresh','ads':[
            {**(copy[c['id']][0] if copy.get(c['id']) else {}),'ad_number':i}
            for i,c in enumerate(ads.INSTANT_EXPERIENCE_CONCEPTS,1)]}
        csv=b''  # The complete authored concepts remain in source_copy/workspace.
    else:
        copy=deepcopy(workflow.get('standard_ads') or [])
        batch={**shared,'source_schema_kind':'saved_refresh','ads':copy or [
            {'ad_number':i,'primary_text':'','headline':'','description':''} for i in range(1,4)]}
        csv=bytes(result.get('creative_refresh_csv') or b'')
    assets=[]
    for spec in ads._result_image_slots(result):
        slot=(workflow.get('slots') or {}).get(spec['id']) or {}
        if not slot.get('valid') or not slot.get('data'):continue
        data=bytes(slot['data'])
        receipt=(workflow.get('outcomes') or {}).get(spec['id']) or {}
        assets.append({**spec,'slot_id':spec['id'],'data':data,
            'filename':receipt.get('filename') or slot.get('original_name') or spec['id']+'.jpg',
            'original_name':slot.get('original_name'),
            'content_type':slot.get('content_type') or 'image/jpeg',
            'processed_hash':hashlib.sha256(data).hexdigest(),
            'path':folder+'/creative-refresh-workspace.json'})
    value={'version':handoff.VERSION,'platform':'meta','package_id':str(uuid4()),
        'source':'Creative Refresh','creative_refresh':True,'draft_workspace':True,
        'ad_type':kind,'workflow_type':'creative_refresh','context_key':result['context_key'],
        'source_signature':ads._ads_saved_source_signature(result,workflow),
        'saved_at':datetime.now(timezone.utc).isoformat(),'folder':folder,
        'source_provenance':deepcopy(result.get('creative_refresh_context') or {}),
        'refresh_executions':deepcopy((workflow.get('ad_notes') or {}).get('refresh_executions') or []),
        'batch':batch,'source_copy':copy,'copy_csv':csv,'assets':assets,'files':[]}
    value['package_hash']=handoff.content_hash(value)
    return handoff.validate_saved_package(value)


def prepare_folder(ads,token,root,destination,result,workflow):
    folder=workflow.get('saved_folder_path') or ads._ads_export_folder_path(destination,result,workflow)
    if not ads.dropbox_integration.path_is_within_root(folder,root):
        raise ValueError('The selected destination is outside the approved Files folder.')
    ads.dropbox_integration.ensure_folder_path(token,folder,root_path=root)
    workflow['saved_folder_path']=folder
    return folder
