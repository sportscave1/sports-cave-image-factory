"""Recipient labels and projections. Eligibility remains in existing sources."""
from dataclasses import dataclass
from crm_lifecycle_audience import FILTERS,SORTS
from crm_post_purchase_audience import FILTERS as ORDER_FILTERS,email_cells
from crm_logic import date


@dataclass(frozen=True)
class Audience:
    title: str
    date_label: str
    search: str
    fields: tuple
    filters: tuple = FILTERS
    sorts: tuple = tuple(SORTS)
    default_sort: str = 'Newest'
    enrollment: bool = False


LIFECYCLE={
    'fulfilled':Audience('Recipients','Entered','Customer, email or order',('Reference',),('All','Active','Completed','Stopped'),('Newest','Oldest','Sequence stage')),
    'welcome':Audience('Marketing subscribers','Subscribed','Customer, email or Shopify ID',('Purchased','Source')),
    'post_purchase':Audience('Orders','Order date','Search orders',('Order','Fulfilment','Flow'),
        ORDER_FILTERS,('Newest','Oldest','Customer value','Sequence stage'),enrollment=True),
    'win_back':Audience('Inactive purchasers','Last purchase','Customer, email or Shopify ID',
        ('Inactive days','Paid orders','Customer value'),default_sort='Longest inactivity'),
}


def welcome_values(r,at):return ['Yes' if r['order_count'] else 'No',r['source'] or 'Not provided']


def win_back_values(r,at):
    return [(at-date(r['last_paid_at'])).days if r['last_paid_at'] else '—',r['order_count'],
        str(r['lifetime_value'])+' '+str(r['currency'] or '') if r['lifetime_value'] is not None else 'Not verified']


def order_values(r,at):
    return [r['order_name'] or r['key'],str(r['fulfillment_status'] or 'Unfulfilled').replace('_',' ').capitalize(),
        'Suppressed' if r['suppressed'] else r['flow_state'] or
        {'QUEUED':'Awaiting verification','CHECKING':'Verifying eligibility','FAILED':'Not eligible'}.get(r.get('enrollment_request_state'),'Not enrolled')]


VALUES={'fulfilled':lambda r,at:[r['reference']], 'welcome':welcome_values,'post_purchase':order_values,'win_back':win_back_values}


def project(adapter,row,records,display,at):
    labels=list(adapter.fields)
    if not adapter.enrollment:labels=['Email','Consent','Flow']+labels
    columns=[dict(label=v,name=v,enabled=True) for v in labels]
    active=row['config'].get('published_flow') or row['config']['draft']
    columns += [dict(id=s['step_id'],label='Email '+str(i+1),name=s.get('name') or 'Email '+str(i+1),
        enabled=s.get('enabled',True)) for i,s in enumerate(active['emails'])]
    result=[]
    for r in records:
        values=VALUES['fulfilled' if adapter is LIFECYCLE['fulfilled'] else row['trigger_type']](r,at)
        if not adapter.enrollment:
            values=[r['email'],r['consent'],'Suppressed' if r['suppressed'] else r['flow_state'] or 'Not enrolled',
                ]+values
        cells=[dict(label=str(v or '—'),tone='muted') for v in values]
        if adapter.enrollment:
            for cell in cells:cell['reason']=r.get('enrollment_request_result') or ''
        cells+=sequence_cells(adapter,{**r,'automation_status':row['status']},active,at)
        result.append(dict(key=r['key'],customer=r['name'] or r['email'] or r['customer_id'] or 'Guest',
            created=display(r['audience_at']),created_full=display(r['audience_at']),cells=cells))
    return columns,result


def sequence_cells(adapter,record,flow,at):
    if adapter.enrollment or record.get('enrollment_id'):
        return email_cells(record,flow,at)
    from crm_checkout_progress import cell
    reason='Suppressed' if record['suppressed'] else 'Marketing consent required' if record['consent']!='SUBSCRIBED' else 'Not enrolled'
    return [cell('Disabled' if not step.get('enabled',True) else reason) for step in flow.get('emails',[])]


def adapter_for(row):
    if row['config']['draft'].get('lifecycle_version'):return LIFECYCLE[row['trigger_type']]
    # Legacy/native flows expose only recorded journeys, never inferred audiences.
    return LIFECYCLE['fulfilled']
