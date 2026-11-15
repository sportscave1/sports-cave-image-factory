"""Owner-reviewed local colour policies. Empty by default; no assumed RGB space.

Membership is an exact pinned source identity, never a filename, folder or layer
name heuristic. Future members need verified provenance, not repeated ICC approval.
The policy file is an operator-controlled configuration, not companion input.
"""
import base64
from datetime import datetime,timezone
import hashlib
import json
import os
import re
from pathlib import Path
from auto_editions_colour_source import ColourReview,profile_info


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def evidence_file(path, purpose):
    path=Path(path)
    if not path.is_file() or path.is_symlink():raise ValueError('A local evidence file is required.')
    from auto_editions_colour_source import _hash
    return dict(name=path.name,sha256=_hash(path),purpose=purpose)


def propose(group, icc, members, references, comparisons, *, scope=None):
    """Comparisons are human-reviewed reference/proof artifacts, not auto approval."""
    if not group or not members or not references or not comparisons:
        raise ValueError('Provide source group, verified members, trusted references and comparison evidence.')
    for row in members:
        if set(row)!={'source','provenance'} or not row['provenance']:
            raise ValueError('Each source membership requires verified provenance.')
        import auto_editions as ae
        source=row['source']
        if set(source) not in ({'product_gid','file_id','revision','content_hash'}, {'template_id','file_id','revision','content_hash'}):
            raise ValueError('An exact source or template identity is required.')
        if 'template_id' in source and not source['template_id']:raise ValueError('Template identity required.')
        ae.source_identity(source.get('product_gid','gid://shopify/Product/1'),
                           dict(id=source['file_id'],rev=source['revision'],content_hash=source['content_hash']))
    for item in references+comparisons+[m['provenance'] for m in members]:
        if (not isinstance(item,dict) or not item.get('name') or not item.get('purpose')
                or not re.fullmatch(r'[a-f0-9]{64}',str(item.get('sha256','')))):
            raise ValueError('Evidence needs a purpose and SHA-256.')
    result=dict(schema=1,group=group,profile=profile_info(icc),icc_base64=base64.b64encode(icc).decode(),
                members=members,references=references,comparisons=comparisons,status='awaiting_approval',print_ready=False)
    if scope is not None:
        from auto_editions_colour_workflows import validate_scope
        validate_scope(scope);result.update(schema=2,scope=scope)
    return result


def approve(proposal, owner, reviewed_hash):
    if not owner or proposal.get('status')!='awaiting_approval' or fingerprint(proposal)!=reviewed_hash:
        raise ValueError('Approve the exact reviewed proposal with an identified owner.')
    # Revalidate the proposal before persisting an approval.
    checked=propose(proposal['group'],base64.b64decode(proposal['icc_base64'],validate=True),
                    proposal['members'],proposal['references'],proposal['comparisons'],scope=proposal.get('scope'))
    if checked!=proposal:raise ValueError('Colour review content changed.')
    approved={**proposal,'status':'approved','owner':owner,'approved_at':datetime.now(timezone.utc).isoformat(),
              'reviewed_hash':reviewed_hash}
    return {**approved,'approval_hash':fingerprint(approved)}


def validate(policy):
    if policy.get('schema') not in (1,2) or (policy.get('schema')==2)!=('scope' in policy):
        raise ColourReview('Colour policy awaiting approval: unsupported policy scope.')
    if policy.get('schema')==2:
        from auto_editions_colour_workflows import validate_scope
        validate_scope(policy['scope'])
    content={k:v for k,v in policy.items() if k!='approval_hash'}
    if policy.get('status')!='approved' or not policy.get('owner') or fingerprint(content)!=policy.get('approval_hash'):
        raise ColourReview('Colour policy awaiting approval: no unchanged owner approval.')
    proposal={k:v for k,v in policy.items() if k not in ('approval_hash','owner','approved_at','reviewed_hash')}
    proposal['status']='awaiting_approval'
    if fingerprint(proposal)!=policy.get('reviewed_hash'):
        raise ColourReview('Colour policy awaiting approval: reviewed scope changed.')
    icc=base64.b64decode(policy['icc_base64'],validate=True)
    if profile_info(icc)!=policy['profile']:raise ColourReview('ICC export mismatch: approved profile changed.')
    return icc


def load_policies():
    filename=os.getenv('AUTO_EDITIONS_COLOUR_POLICIES_FILE')
    if not filename:return []
    path=Path(filename)
    if path.is_symlink() or path.stat().st_size>8*1024*1024:raise ColourReview('Colour policy awaiting approval: invalid policy registry.')
    policies=json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(policies,list) or len(policies)>200:raise ValueError('Bounded policy registry required.')
    for policy in policies:validate(policy)
    return policies


def resolve(source, policies=None, *, memberships=None, default_group=None):
    if policies is None and os.getenv('AUTO_EDITIONS_COLOUR_POLICY_BACKEND')=='audit':
        import supabase_backend
        from auto_editions_colour_store import configuration
        config=configuration(supabase_backend.read_connection)
        policies=config['policies']
        if memberships is None:memberships=config['memberships']
        if default_group is None:default_group=config['default_group']
    policies=load_policies() if policies is None else policies
    from auto_editions_colour_workflows import matches
    matches=matches(source,policies,memberships=memberships,default_group=default_group)
    if not matches:raise ColourReview('Colour policy awaiting approval: missing source profile; verified source-group approval required.')
    if len(matches)!=1:raise ColourReview('Colour policy awaiting approval: conflicting source-group memberships.')
    policy=matches[0];icc=validate(policy)
    return icc,dict(group=policy['group'],approval_hash=policy['approval_hash'],**({'scope':policy['scope']} if 'scope' in policy else {}),
                    owner=policy['owner'],icc_sha256=policy['profile']['sha256'],pixels_converted=False)
