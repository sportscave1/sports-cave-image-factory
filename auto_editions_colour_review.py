"""Identity-pinned colour exception review and owner proposal evidence."""
import json,os
from pathlib import Path
from auto_editions_colour_policy import validate,fingerprint,resolve

REQUIREMENTS=[
    'Confirm the exact file ID and content hash; a different mapping is a new source.',
    'Recover the original embedded ICC or designer/export workflow evidence. A Photoshop working-space label is not source evidence.',
    'Review colour-managed comparisons against trusted artwork/exports; document intended RGB interpretation.',
    'For a reusable default, approve an explicit RGB8 workflow scope and register independent, content-bound workflow provenance.',
    'Keep CMYK, conflicting profiles, unknown workflows and changed content outside that default.',
]


def registry():
    # Bundled records are shown for review even on an app without the worker's
    # configured registry. Displaying them does not activate a default or retry.
    names=[Path(__file__).parent/'config/auto_editions/icc-policies-20261017.json']
    if os.getenv('AUTO_EDITIONS_COLOUR_POLICIES_FILE'):names.append(Path(os.environ['AUTO_EDITIONS_COLOUR_POLICIES_FILE']))
    values=[]
    for p in names:
        if p.is_symlink() or p.stat().st_size>8*1024*1024:raise ValueError('Colour registry unavailable.')
        rows=json.loads(p.read_text(encoding='utf-8-sig'))
        if not isinstance(rows,list) or len(rows)>200:raise ValueError('Colour registry unavailable.')
        for policy in rows:
            validate(policy)
            if not any(x['approval_hash']==policy['approval_hash'] for x in values):values.append(policy)
    return values


def snapshot(connect,pid):
    with connect() as conn,conn.cursor() as cur:
        cur.execute('''SELECT q.source,q.reason,q.preparation_hash,m.dropbox_file_id
            FROM auto_edition_onboarding q JOIN product_psd_mappings m ON m.shopify_product_gid=q.product_gid
            WHERE q.product_gid=%s''',(pid,))
        row=cur.fetchone()
    if not row or not row.get('source') or row['source'].get('file_id')!=row['dropbox_file_id']:
        raise ValueError('Mapping changed or source inspection is unavailable. Refresh the existing preparation first.')
    if row['source'].get('product_gid')!=pid:raise ValueError('Source identity does not belong to this product.')
    if row.get('preparation_hash'):raise ValueError('This source already has a retained preparation; use the existing artwork review.')
    from worker_diagnostics import explain
    from auto_editions_colour_workflows import content_identity
    from auto_editions_status import reason as safe_reason
    content_identity(row['source'])
    diagnostic=explain(row.get('reason'))['code']
    from auto_editions_colour_store import configuration
    config=configuration(connect)
    policies=config['policies'];source=row['source'];matching=None;why=None
    can_propose=diagnostic in ('PROFILE_MISSING','COLOUR_POLICY_PENDING')
    if can_propose:
        try:_,matching=resolve(source,policies,memberships=config['memberships'],default_group=config['default_group'])
        except ValueError as error:why=str(error)
    else:why='Source inspection, CMYK or conflicting-profile evidence requires separate review; an RGB default is not a resolution.'
    choices=[dict(group=p['group'],profile=p['profile'],approval_hash=p['approval_hash'],
                  scope=p.get('scope',{'kind':'exact_revision','members':len(p['members'])}),
                  exact_member=any(m['source']==source for m in p['members'])) for p in policies]
    body=dict(schema=1,source=source,reason=safe_reason(row['reason']),diagnostic=diagnostic,
              registry_hash=fingerprint(policies),registry_mode='configured' if os.getenv('AUTO_EDITIONS_COLOUR_POLICIES_FILE') else 'bundled_review_only',
              default_group=os.getenv('AUTO_EDITIONS_UNTAGGED_RGB_DEFAULT') or None,
              can_propose=can_propose,matching_policy=matching,matching_reason=why,
              candidates=choices,requirements=REQUIREMENTS,status='awaiting_evidence',
              activation='An administrator can approve the pinned interpretation and resume this exact job. Artwork approval remains separate.')
    return {**body,'review_hash':fingerprint(body)}


def proposal(connect,pid,body):
    import base64
    from auto_editions_colour_policy import propose
    current=snapshot(connect,pid)
    if not current['can_propose']:raise ValueError('Resolve source inspection, CMYK or conflicting-profile evidence first. An RGB default cannot resolve this exception.')
    if set(body)!={'review_hash','reference_policy','workflow_id','workflow_scope','provenance','references','comparisons'}:
        raise ValueError('Pinned source, scope and independent evidence are required.')
    if current['review_hash']!=body['review_hash']:raise ValueError('Source or policy registry changed. Refresh and review again.')
    if type(body['workflow_scope']) is not bool:raise ValueError('Choose an explicit policy scope.')
    from auto_editions_colour_store import configuration
    policies=[p for p in configuration(connect)['policies'] if p['approval_hash']==body['reference_policy']]
    if len(policies)!=1:raise ValueError('Trusted reference profile changed. Refresh and review again.')
    if not isinstance(body['workflow_id'],str) or not __import__('re').fullmatch(r'[a-z0-9][a-z0-9-]{0,79}',body['workflow_id']):
        raise ValueError('Use a short lowercase workflow identifier.')
    scope=dict(kind='verified_workflow',workflow_id=body['workflow_id'],mode='RGB',depth=8,
               identity='file_id+content_hash',default_for_untagged_rgb=True) if body['workflow_scope'] else None
    if not isinstance(body['provenance'],dict):raise ValueError('Independent source/workflow provenance required.')
    for name in ('references','comparisons'):
        if not isinstance(body[name],list) or not 1<=len(body[name])<=8:raise ValueError('Provide bounded reference and comparison evidence.')
    value=propose(body['workflow_id'],base64.b64decode(policies[0]['icc_base64'],validate=True),
                  [dict(source=current['source'],provenance=body['provenance'])],body['references'],body['comparisons'],scope=scope)
    return dict(proposal=value,reviewed_hash=fingerprint(value),applied=False,
                next_action='Review the pinned interpretation, then approve and resume. This does not approve the artwork or certify production readiness.')
