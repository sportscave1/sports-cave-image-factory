"""Explicit, operator-controlled workflow provenance; never infer from canvas/title.

Workflow/default approvals and verified membership receipts are separate. Receipts
bind actual source content to a reviewed workflow, not to a product or filename.
Changing image content requires fresh provenance; metadata-only revisions may be
reused only under the explicit schema-2 owner-approved content-identity scope.
"""
import json,os,re
from pathlib import Path
from auto_editions_colour_source import ColourReview


def validate_scope(scope):
    expected={'kind','workflow_id','mode','depth','identity','default_for_untagged_rgb'}
    if (not isinstance(scope,dict) or set(scope)!=expected
            or scope['kind']!='verified_workflow' or scope['mode']!='RGB' or scope['depth']!=8
            or scope['identity']!='file_id+content_hash' or scope['default_for_untagged_rgb'] is not True
            or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}',str(scope['workflow_id']))):
        raise ColourReview('Colour policy awaiting approval: explicit verified RGB8 workflow scope required.')


def content_identity(source):
    import auto_editions as ae
    try:
        ae.source_identity(source.get('product_gid','gid://shopify/Product/1'),
                           dict(id=source['file_id'],rev=source['revision'],content_hash=source['content_hash']))
    except (ValueError,KeyError,TypeError,AttributeError) as error:
        raise ColourReview('Colour policy awaiting approval: invalid pinned workflow source.') from error
    return source['file_id'],source['content_hash']


def load_memberships():
    name=os.getenv('AUTO_EDITIONS_COLOUR_WORKFLOWS_FILE')
    if not name:return []
    p=Path(name)
    if p.is_symlink() or p.stat().st_size>8*1024*1024:raise ColourReview('Invalid workflow membership registry.')
    rows=json.loads(p.read_text(encoding='utf-8-sig'))
    if not isinstance(rows,list) or len(rows)>1000:raise ColourReview('Bounded workflow membership registry required.')
    return rows


def verified_membership(policy,path,source,provenance,verified_by):
    """Offline operator action after checking workflow lineage, never a UI assertion.

    Provenance must identify a trusted designer/export manifest or equivalent
    independent workflow evidence. Same dimensions, names or folders are not proof.
    """
    from auto_editions_colour_policy import validate,fingerprint
    from auto_editions_colour_source import inspect_psd
    import auto_editions as ae
    validate(policy);validate_scope(policy.get('scope'))
    if not verified_by or not provenance or not all(isinstance(e,dict) and e.get('name') and e.get('purpose') and re.fullmatch(r'[a-f0-9]{64}',str(e.get('sha256',''))) for e in provenance):
        raise ValueError('Identified operator and hashed independent workflow evidence required.')
    content_identity(source)
    if ae.file_hash(path,dropbox=True)!=source['content_hash']:raise ColourReview('Source content changed before workflow verification.')
    meta=inspect_psd(path)
    if (meta['state'],meta['mode'],meta['depth'])!=('untagged',3,8):raise ColourReview('Only independently inspected untagged RGB8 sources enter a default workflow.')
    row=dict(schema=1,workflow_id=policy['scope']['workflow_id'],policy_approval_hash=policy['approval_hash'],source=source,
             inspection={k:meta[k] for k in ('state','mode','depth','width','height')},
             provenance=provenance,verified_by=verified_by,status='verified')
    return {**row,'receipt_hash':fingerprint(row)}


def matches(source,policies,*,memberships=None,default_group=None):
    from auto_editions_colour_policy import validate,fingerprint
    default_group=os.getenv('AUTO_EDITIONS_UNTAGGED_RGB_DEFAULT','') if default_group is None else default_group
    # Default disabled without an explicitly selected, approved workflow policy.
    found=[]
    hashes=[p.get('approval_hash') for p in policies]
    if len(set(hashes))!=len(hashes):raise ColourReview('Colour policy awaiting approval: duplicate policy records.')
    for p in policies:
        validate(p)
        exact=any(m['source']==source for m in p.get('members',[]))
        scope=p.get('scope')
        if scope:
            # Already reviewed file bytes may be mapped to another product or
            # receive a metadata-only revision, solely under the reviewed scope.
            exact=exact or any(content_identity(m['source'])==content_identity(source) for m in p['members'])
        if exact:found.append(p);continue
        if not scope or p['group']!=default_group:continue
        if memberships is None:memberships=load_memberships()
        for r in memberships:
            if r.get('workflow_id')!=scope['workflow_id'] or content_identity(r.get('source',{}))!=content_identity(source):continue
            content={k:v for k,v in r.items() if k!='receipt_hash'};meta=r.get('inspection',{})
            if (r.get('schema')!=1 or r.get('status')!='verified' or not r.get('verified_by') or not r.get('provenance')
                    or r.get('policy_approval_hash')!=p['approval_hash'] or fingerprint(content)!=r.get('receipt_hash')
                    or (meta.get('state'),meta.get('mode'),meta.get('depth'))!=('untagged',3,8)):
                raise ColourReview('Colour policy awaiting approval: workflow provenance is stale or conflicting.')
            found.append(p);break
    # A new workflow may extend the old group's coverage without replacing its
    # exact approvals. Keep the original receipt/evidence for exact legacy
    # members, only when every overlapping workflow agrees on the ICC bytes.
    legacy=[p for p in found if p.get('schema')==1]
    if len(legacy)==1 and all(p['profile']['sha256']==legacy[0]['profile']['sha256'] for p in found):return legacy
    return found


def recovery_sources(policies,*,memberships=None,default_group=None):
    from auto_editions_colour_policy import resolve,validate
    selectors=[]
    for p in policies:
        validate(p)
        selectors.extend(dict(source=m['source'],content_identity=bool(p.get('scope'))) for m in p['members'])
    default=os.getenv('AUTO_EDITIONS_UNTAGGED_RGB_DEFAULT','') if default_group is None else default_group
    if default:
        receipts=load_memberships() if memberships is None else memberships
        for r in receipts:
            try:
                _,policy=resolve(r.get('source'),policies,memberships=receipts,default_group=default)
                if policy['group']==default:selectors.append(dict(source=r['source'],content_identity=True))
            except ValueError:continue
    return selectors
