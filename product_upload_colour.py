"""Reuse colour approval for the exact physical PSD in the web/mockup workflow.

Product Uploads precedes Shopify identity. This adapter does not extend a policy
to another file, revision or content, nor change Edition Ops approval matching.
"""
import os
from auto_editions_colour_source import ColourReview
from auto_editions_colour_policy import resolve
from auto_editions_colour_workflows import matches,load_memberships,content_identity


def resolve_web(source,config=None):
    content_identity(source) # Validate pinned ID/revision/hash, never names.
    if config is None:
        from auto_editions_colour_policy import load_policies
        config=dict(policies=load_policies(),memberships=load_memberships(),
                    default_group=os.getenv('AUTO_EDITIONS_UNTAGGED_RGB_DEFAULT',''))
    policies=config['policies'];memberships=config['memberships'];default=config['default_group']
    direct=matches(source,policies,memberships=memberships,default_group=default)
    candidates={p['approval_hash']:(p,source) for p in direct}
    for policy in policies:
        # A source's colour interpretation is still the same for a web derivative
        # before a product exists. Keep the approval's original identity in its
        # receipt; do not forge a product ID or alter its stored membership.
        for member in policy['members']:
            original=member['source']
            if all(original.get(k)==source.get(k) for k in ('file_id','revision','content_hash')):
                candidates.setdefault(policy['approval_hash'],(policy,original))
    if not candidates:
        raise ColourReview('This PSD has no embedded colour profile and no matching exact-source approval. Request an owner colour-appearance review for this file and revision; retrying alone will not approve it.')
    if len(candidates)!=1:raise ColourReview('Conflicting colour approvals for this PSD; owner review required.')
    policy,approved_source=next(iter(candidates.values()))
    return resolve(approved_source,policies=[policy],memberships=memberships,default_group=default)
