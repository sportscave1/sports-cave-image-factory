"""Consent-isolated Shopify sync, consumed by the existing durable CRM worker."""
import logging
import json
from datetime import datetime

import wall_preview_crm_store as store
from wall_preview_identity import normalize_email
from shopify_sync import graphql_request

LOG = logging.getLogger(__name__)
FIELDS = 'id firstName lastName defaultEmailAddress { emailAddress marketingState marketingUpdatedAt }'
LOOKUP = '''query WallPreviewCustomer($query:String!,$after:String) {
 customers(first:50,query:$query,after:$after) { nodes { '''+FIELDS+''' }
 pageInfo { hasNextPage endCursor } } }'''
CREATE = '''mutation WallPreviewCustomerCreate($input:CustomerInput!) {
 customerCreate(input:$input) { customer { '''+FIELDS+''' } userErrors { field message } } }'''
UPDATE = '''mutation WallPreviewCustomerName($input:CustomerInput!) {
 customerUpdate(input:$input) { customer { '''+FIELDS+''' } userErrors { field message } } }'''
TAG = '''mutation WallPreviewCustomerTag($id:ID!,$tags:[String!]!) {
 tagsAdd(id:$id,tags:$tags) { userErrors { field message } } }'''
CONSENT = '''mutation WallPreviewCustomerConsent($input:CustomerEmailMarketingConsentUpdateInput!) {
 customerEmailMarketingConsentUpdate(input:$input) {
 customer { '''+FIELDS+''' } userErrors { field message } } }'''


def operation(document, variables, field, transport):
    data, _ = transport(document, variables, timeout=10)
    result = data.get(field)
    if not isinstance(result,dict) or result.get('userErrors'):
        # Provider messages may contain PII; use a safe category only.
        raise ValueError('shopify_customer_operation_rejected')
    return result


def synchronize(row, transport=graphql_request):
    address = normalize_email(row['customer_email'])
    phrase = 'email:"'+address.replace('\\','\\\\').replace('"','\\"')+'"'
    matches, after, seen = {}, None, set()
    for _ in range(3):
        data, _ = transport(LOOKUP,{'query':phrase,'after':after},timeout=10)
        page = data['customers']
        for item in page['nodes']:
            if str((item.get('defaultEmailAddress') or {}).get('emailAddress') or '').lower() == address:
                matches[item['id']] = item
        info = page['pageInfo']
        if type(info.get('hasNextPage')) is not bool:
            raise ValueError('incomplete_customer_lookup')
        if not info['hasNextPage']:
            break
        after = info.get('endCursor')
        if not after or after in seen:
            raise ValueError('incomplete_customer_lookup')
        seen.add(after)
    else:
        raise ValueError('customer_lookup_bound_reached')
    if len(matches)>1:
        raise ValueError('ambiguous_customer_match')
    pieces = str(row.get('customer_name') or '').strip().split(maxsplit=1)
    names = dict(zip(('firstName','lastName'),pieces))
    if matches:
        customer = next(iter(matches.values()))
        missing = {k:v for k,v in names.items() if not customer.get(k)}
        if missing:
            customer = operation(UPDATE,{'input':{'id':customer['id'],**missing}},'customerUpdate',transport)['customer']
    else:
        # Shopify enforces email uniqueness; retries always repeat the exact lookup first.
        customer = operation(CREATE,{'input':{'email':address,**names}},'customerCreate',transport)['customer']
    tags = ['Wall Preview']
    if row.get('market_country_code'):
        tags.append('Wall Preview Market: '+row['market_country_code'])
    operation(TAG,{'id':customer['id'],'tags':tags},'tagsAdd',transport)
    latest = (customer.get('defaultEmailAddress') or {}).get('marketingUpdatedAt')
    latest = datetime.fromisoformat(latest.replace('Z','+00:00')) if latest else None
    # An intervening unsubscribe must not be overwritten by a delayed/retried job.
    if row.get('submitted_marketing_opt_in') is True and (not latest or latest <= row['marketing_consent_at']):
        consent = {'marketingState':'SUBSCRIBED','marketingOptInLevel':'SINGLE_OPT_IN',
                   'consentUpdatedAt':row['marketing_consent_at'].isoformat()}
        customer = operation(CONSENT,{'input':{'customerId':customer['id'],'emailMarketingConsent':consent}},
                             'customerEmailMarketingConsentUpdate',transport)['customer']
    state = (customer.get('defaultEmailAddress') or {}).get('marketingState') or 'UNKNOWN'
    return customer['id'],state


def tick():
    """One bounded sync per cycle; email delivery remains independent of Shopify availability."""
    with store.transaction() as cur:
        cur.execute("""UPDATE public.wall_preview_customer_jobs SET state=CASE WHEN attempts<5 THEN 'queued' ELSE 'failed' END,
            reason='worker_interrupted' WHERE state='processing' AND claimed_at<now()-interval '5 minutes'""")
        cur.execute("""SELECT * FROM public.wall_preview_customer_jobs WHERE state='queued' AND due_at<=now()
            ORDER BY due_at FOR UPDATE SKIP LOCKED LIMIT 1""")
        job = dict(cur.fetchone() or {})
        if not job:return False
        cur.execute("UPDATE public.wall_preview_customer_jobs SET state='processing',claimed_at=now(),attempts=attempts+1 WHERE id=%s",(str(job['id']),))
    try:
        with store.transaction() as cur:
            cur.execute('SELECT * FROM public.wall_previews WHERE id=%s',(str(job['preview_id']),))
            row = dict(cur.fetchone())
            # Serialize all previews for this email across processes; never trust posted customer IDs.
            cur.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',('wall-preview-customer:'+row['customer_email'],))
            customer_id,state = synchronize(row)
            cur.execute('UPDATE public.wall_previews SET shopify_customer_id=%s,email_marketing_state=%s,updated_at=now() WHERE id=%s',
                        (customer_id,state,str(row['id'])))
            cur.execute("""UPDATE public.wall_preview_events SET metadata=metadata || %s::jsonb
                WHERE preview_id=%s AND event_key='email-requested'""",
                        (json.dumps({'shopify_customer_id':customer_id}),str(row['id'])))
            cur.execute("UPDATE public.wall_preview_customer_jobs SET state='done',finished_at=now(),reason='' WHERE id=%s",(str(job['id']),))
    except Exception as error:
        with store.transaction() as cur:
            cur.execute("""UPDATE public.wall_preview_customer_jobs SET state=CASE WHEN attempts<5 THEN 'queued' ELSE 'failed' END,
                due_at=now()+interval '5 minutes',reason='shopify_sync_unavailable',finished_at=CASE WHEN attempts>=5 THEN now() ELSE NULL END WHERE id=%s""",(str(job['id']),))
        LOG.warning('wall_preview_customer_sync_failed job_id=%s error_type=%s',job['id'],type(error).__name__)
    return True
