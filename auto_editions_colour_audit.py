"""Offline catalogue review. No database, provider, queue or artwork writes.

Input is a bounded authoritative snapshot and separately collected source
evidence. Decisions are proposals; template approval never extends to legacy art.
"""
from collections import Counter
from datetime import datetime,timezone
import re
import auto_editions as ae
from auto_editions_onboarding import detect_roles
from worker_diagnostics import explain


def pinned_source(row):
    return ae.source_identity(row['product_gid'],dict(id=row['mapped_file_id'],
        rev=row['inventory_revision'],content_hash=row['inventory_content_hash']))


def review_catalogue(rows,evidence,*,now=None):
    now=now or datetime.now(timezone.utc)
    if not rows or len(rows)>1000:raise ValueError('A bounded current catalogue snapshot is required.')
    ids=[r['product_gid'] for r in rows]
    if len(ids)!=len(set(ids)):raise ValueError('Ambiguous duplicate mapped product identity.')
    proof={r['product_gid']:r for r in evidence};items=[]
    for row in rows:
        entry=dict(product_gid=row['product_gid'],title=row.get('product_title',''),
            priority=row.get('priority',0),checkpoint_status=row.get('status'),
            diagnostic=explain(row.get('reason'))['code'],source=None,
            decision='pending_uncertain',reasons=[],colour_approved=False,print_ready=False)
        items.append(entry)
        # Completed/review packages take precedence over every reported failure.
        if row.get('preparation_hash') or int(row.get('stored_preparations') or 0)>0:
            entry.update(decision='retain_prepared',preparation_hash=row.get('preparation_hash'))
            continue
        try:entry['source']=pinned_source(row)
        except (KeyError,ValueError):entry['reasons'].append('Current source identity is unavailable.');continue
        if row.get('checkpoint_file_id')!=row.get('mapped_file_id'):
            entry['reasons'].append('Checkpoint mapping differs.');continue
        if row.get('source') and row['source']!=entry['source']:
            entry['reasons'].append('Checkpoint source revision differs.');continue
        if type(row.get('product_edition_total')) is not int or not 1<=row['product_edition_total']<=1000:
            entry['reasons'].append('Authoritative edition limit requires review.');continue
        if (row.get('replacement') or {}).get('stage') not in (None,'','Complete'):
            entry['reasons'].append('Replacement/reset state requires separate review.');continue
        if row.get('status')=='Preparing':
            entry['reasons'].append('An existing preparation lease/state must be reconciled.');continue
        lease=row.get('lease_until')
        if lease and datetime.fromisoformat(lease.replace('Z','+00:00'))>now:
            entry['lease_hold_until']=lease
            entry['reasons'].append('Any future recovery must wait for the existing lease to expire.')
        if row.get('status')=='Awaiting preparation':
            entry.update(decision='continue_existing_queue')
            entry['reasons'].append('Use the existing source/profile checks; no reset or new approval.')
            continue
        e=proof.get(row['product_gid'],{})
        if e.get('source')!=entry['source']:
            entry['reasons'].append('No current pinned source evidence.');continue
        if e.get('fresh_revision_matches') is not True:
            entry['reasons'].append('Fresh Dropbox revision confirmation is required.');continue
        binary=e.get('binary_document') or {}
        if binary.get('state')=='untagged':
            entry.update(source_profile_state='untagged')
            if binary.get('mode')!=3 or binary.get('depth')!=8:
                entry['reasons'].append('Source mode/depth requires separate conversion review.');continue
            try:roles=detect_roles(e.get('retained_inspection') or {},row['product_edition_total'])
            except (ValueError,KeyError,TypeError) as error:
                entry.update(decision='pending_structure_and_colour')
                entry['reasons'].append(str(error));continue
            entry['structure']=roles
            if e.get('source_hash_verified') is not True:
                entry['reasons'].append('Full source content-hash verification is required.');continue
            if entry['diagnostic']=='PROFILE_MISSING':
                entry.update(decision='propose_srgb_legacy_policy')
                entry['reasons'].append('Structurally eligible untagged RGB/8; legacy colour intent remains unapproved.')
            else:
                entry['reasons'].append('Missing ICC is confirmed, but the reported runtime/export cause is unresolved.')
            continue
        if (entry['diagnostic']=='ICC_MISMATCH' and binary.get('state')=='tagged'
                and binary.get('mode')==3 and binary.get('depth')==8
                and re.fullmatch(r'[a-f0-9]{64}',str((binary.get('profile') or {}).get('sha256','')))
                and e.get('omission_proven') is True and e.get('source_hash_verified') is True):
            entry.update(decision='plan_embedded_profile_export_recovery',
                icc_sha256=(binary.get('profile') or {}).get('sha256'),colour_approved=True)
            entry['reasons'].append('Preserve verified embedded ICC; metadata omission proved. Release/retry approval still required.')
        else:entry['reasons'].append('Colour intent or exact export defect remains unverified.')
    rank=lambda r:(0 if r['priority']==8 else 1,-r['priority'],r['product_gid'])
    items.sort(key=rank)
    counts=dict(Counter(r['decision'] for r in items))
    return dict(schema=1,mode='review_only',mapped=len(items),counts=counts,rows=items,
        automatic_retry_authorized=False,legacy_colour_approval_granted=False,
        protected_prepared=sum(r['decision']=='retain_prepared' for r in items),
        paid_unprepared=sum(r['priority']==8 and r['decision']!='retain_prepared' for r in items))
