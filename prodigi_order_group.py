"""Require every separately numbered supplier item before one order Submit."""
from copy import deepcopy
from datetime import datetime,timezone,timedelta
import prodigi_preparation as prep


class WaitingForItems(ValueError): pass


def members(value,order,resolver=None):
    if len(order.get('items',[]))==1:return [value]
    resolver=resolver or prep.resolve
    with prep.connect() as c,c.cursor() as q:
        q.execute("SELECT value FROM app_settings WHERE key LIKE 'prodigi_prepare:%%' AND value->>'order_id'=%s AND NOT COALESCE((value->>'hidden')::boolean,false)", (value['order_id'],))
        rows=[r['value'] for r in q.fetchall()]
    rows=[r for r in rows if r['allocation_id']!=value['allocation_id']]+[value]
    items=order.get('items') or []
    ids=[str(i['id']) for i in items]
    if len(set(ids))!=len(ids):raise ValueError('Duplicate supplier item IDs require review.')
    if any(str(r['item_id']) not in ids for r in rows):raise ValueError('An OS unit points outside this supplier order.')
    result=[]
    for item in items:
        matches=[r for r in rows if str(r['item_id'])==str(item['id'])]
        if len(matches)>1:raise ValueError('Several numbered units point to one supplier item.')
        if not matches:raise WaitingForItems('Waiting for every item in this order to be prepared.')
        unit=matches[0]
        snap=resolver(unit['allocation_id'])
        if prep.digest(snap)!=prep.digest(unit['snapshot']):raise ValueError('A numbered item source changed before order QA.')
        receipt=unit.get('browser') or {};assets=item.get('assets') or []
        if not (receipt.get('verified') is True and receipt.get('full_image_fit_verified') is True):
            raise WaitingForItems('Waiting for all numbered artworks in this order to finish uploading.')
        prep.validate_order(order,snap,unit['order_id'],unit['item_id'],binding=unit.get('consolidation_binding'))
        if len(assets)!=1 or prep.digest(assets[0].get('url'))!=unit.get('url_hash'):
            raise ValueError('A sibling item artwork differs from its verified numbered file.')
        result.append(unit)
    if len({r['allocation_id'] for r in result})!=len(items):raise ValueError('Order allocations are ambiguous.')
    return result


def manifest(order):
    return sorted([dict(id=str(i['id']),quantity=i.get('quantity'),sku=i.get('sku'),
        reference=i.get('merchantReference'),attributes=deepcopy(i.get('attributes') or {}),
        artwork=[prep.digest(a.get('url')) for a in i.get('assets') or []]) for i in order.get('items') or []],key=lambda i:i['id'])


def reserve(cur,value,order,authorisation):
    """Share one committed order-wide intent; child units never own a POST."""
    if len(order.get('items',[]))==1:return
    units=members(value,order)
    receipt=value['submission']
    receipt.update(leader_allocation=value['allocation_id'],items=manifest(order))
    for unit in units:
        if unit['allocation_id']==value['allocation_id']:continue
        if unit.get('submission'):raise ValueError('A sibling already has a submission intent.')
        unit['submission']=deepcopy(receipt)
        unit['submission']['lease_until']=(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat()
        unit.update(status='Submitting',message='Every numbered item passed QA. Confirming one submission for this order.')
        prep.save(cur,unit)


def publish(value):
    receipt=value.get('submission') or {}
    if receipt.get('leader_allocation')!=value['allocation_id']:return
    with prep.connect() as c,c.cursor() as q:
        q.execute("SELECT value FROM app_settings WHERE key LIKE 'prodigi_prepare:%%' AND value->>'order_id'=%s", (value['order_id'],))
        for row in q.fetchall():
            unit=row['value'];child=unit.get('submission') or {}
            if unit['allocation_id']==value['allocation_id'] or child.get('leader_allocation')!=value['allocation_id']:continue
            if child.get('finalised') or unit['status']=='Complete':continue
            for key in ('confirmed','confirmed_at','supplier_status','checked_at','request_issue'):
                if key in receipt:child[key]=receipt[key]
            child['lease_until']=prep.now()
            # Each certificate is generated independently after actual production.
            from prodigi_submission import FINALISED
            finalised=receipt.get('supplier_status') in FINALISED
            unit.update(status=('Certificate pending' if finalised else 'Submitted') if receipt.get('confirmed') else 'Submission uncertain',
                message=('Production confirmed. Awaiting this edition’s customer certificate.' if finalised else
                    'Submitted to Prodigi · awaiting payment/production under your supplier countdown.') if receipt.get('confirmed') else value['message'])
            prep.save(q,unit)


def refresh_qa(cur,value):
    cur.execute("SELECT value FROM app_settings WHERE key LIKE 'prodigi_prepare:%%' AND value->>'order_id'=%s", (value['order_id'],))
    for row in cur.fetchall():
        unit=row['value']
        if unit.get('submission') or unit['status'] not in ('Ready for manual payment','Needs QA'):continue
        unit.pop('dashboard_qa',None)
        unit.update(status='Checking QA',message='Refreshing QA for every numbered item before one order submission.')
        prep.save(cur,unit)
