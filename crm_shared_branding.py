"""Resolve future delivery branding without mutating authored or sent snapshots."""
from copy import deepcopy
import json


def current(store,settings):
    from crm_brand_templates import BrandTemplates
    result=deepcopy(settings)
    result['email_defaults']=BrandTemplates(store.connect).default_sections(settings)
    result['shared_branding_policy']=1
    return result


def flow_settings(store,row,settings,document=None):
    key='flow-branding:'+str(row['id'])
    candidate=current(store,settings)
    with store.db() as conn:
        receipt=conn.execute('SELECT first_submitted_at FROM crm_marketing_sends WHERE id=%s FOR UPDATE',(row['id'],)).fetchone()
        saved=conn.execute('SELECT value FROM crm_runtime_state WHERE key=%s',(key,)).fetchone()
        if saved:return saved['value']
        value=deepcopy(settings if receipt and receipt['first_submitted_at'] else candidate)
        if receipt and receipt['first_submitted_at'] and not settings.get('shared_branding_policy') and document and document.get('html_sections'):
            value['email_defaults']=deepcopy(document['html_sections'])
        conn.execute('INSERT INTO crm_runtime_state(key,value) VALUES(%s,%s::jsonb)',(key,json.dumps(value)))
        return value


def campaign_settings(store,campaign_id,settings,document=None):
    """Pin once under a campaign row lock, before any provider submission.

    Legacy campaigns that already started retain their original revision to avoid
    mixing versions or changing provider idempotency payloads.
    """
    candidate=current(store,settings)
    key='campaign-branding:'+str(campaign_id)
    with store.db() as conn:
        conn.execute('SELECT id FROM crm_campaigns WHERE id=%s FOR UPDATE',(campaign_id,)).fetchone()
        row=conn.execute('SELECT value FROM crm_runtime_state WHERE key=%s',(key,)).fetchone()
        if row:return row['value']
        started=conn.execute("SELECT 1 FROM crm_marketing_sends WHERE campaign_id=%s AND (first_submitted_at IS NOT NULL OR status IN ('SUBMITTING','UNCERTAIN','ACCEPTED','DELIVERED')) LIMIT 1",(campaign_id,)).fetchone()
        value=deepcopy(settings if started else candidate)
        if started and not settings.get('shared_branding_policy') and document and document.get('html_sections'):
            value['email_defaults']=deepcopy(document['html_sections'])
        conn.execute('INSERT INTO crm_runtime_state(key,value) VALUES(%s,%s::jsonb)',(key,json.dumps(value)))
        return value


def rebrand(message,document,old,new,campaign_id,send_id):
    """Replace only verified renderer envelope boundaries; body bytes survive.

    Unrecognised/custom embedded HTML fails closed for explicit migration.
    """
    if old==new:return deepcopy(message)
    from crm_campaign_content import render_campaign
    from crm_email_size import REPRESENTATIVE_UNSUBSCRIBE
    marker='SC_BRANDING_BODY_SLOT_86F2'
    old=deepcopy(old)
    if not old.get('shared_branding_policy') and document.get('html_sections'):
        old['email_defaults']=deepcopy(document['html_sections'])
    doc=deepcopy(document);doc.pop('middle_sections',None)
    doc.update(content_mode='HTML',custom_html=marker,blocks=[])
    envelopes=[render_campaign(doc,cfg,production=True,unsubscribe_url=REPRESENTATIVE_UNSUBSCRIBE,
                              campaign_id=str(campaign_id),send_id=str(send_id)) for cfg in (old,new)]
    result=deepcopy(message)
    for field in ('html','text'):
        before,after=envelopes[0][field].split(marker)
        start,end=envelopes[1][field].split(marker)
        value=message[field]
        if not value.startswith(before) or not value.endswith(after):
            raise ValueError('Stored email envelope requires explicit branding migration.')
        result[field]=start+value[len(before):len(value)-len(after) if after else None]+end
    return result
