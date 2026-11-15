"""Durable, bounded Wall Preview delivery through the existing CRM worker and Resend adapter."""
import html
import logging
import os

from crm_resend import Config, Resend, pace
from email_service import EmailConfiguration, EmailMessage, ResendEmailProvider, EmailDeliveryError
import wall_preview_crm_store as store
from wall_preview_crm_api import BASE, product_url

LOG = logging.getLogger(__name__)


def configuration(address):
    crm = Config()
    return EmailConfiguration(crm.api_key or os.getenv('RESEND_API_KEY',''),
        crm.sender or os.getenv('ACTIVITY_DIGEST_FROM',''),address,
        crm.reply_to or os.getenv('ACTIVITY_DIGEST_REPLY_TO',''))


def configured(address):
    return configuration(address).configured


def message(row, kind='requested', unsubscribe=''):
    title = html.escape(row.get('product_title') or 'Your Sports Cave edition')
    context = html.escape(' · '.join(filter(None,(row.get('frame_label'),row.get('size_label')))))
    url = product_url(row['product_url'],row.get('variant_id'))
    heading = {'requested':'YOUR WALL PREVIEW IS READY','4h':'STILL THINKING ABOUT IT?',
               '24h':'YOUR COLLECTION, YOUR WALL'}[kind]
    # No invented edition counts, stock claims or social proof.
    copy = {'requested':'Here is the edition you confirmed on your wall.',
            '4h':'Take another look at the edition you placed on your wall.',
            '24h':'Explore this collector edition and its current availability.'}[kind]
    image = BASE+'/wall-preview/'+row['share_token']+'/image'
    optout = f'<p><a href="{html.escape(unsubscribe,quote=True)}" style="color:#cfa84b">Unsubscribe</a></p>' if unsubscribe else ''
    body = f'''<!doctype html><html><body style="margin:0;background:#111;color:#f7f3eb;font-family:Arial,sans-serif">
    <table role="presentation" width="100%"><tr><td align="center"><table role="presentation" width="600" style="width:100%;max-width:600px">
    <tr><td style="padding:24px;text-align:center;color:#cfa84b">SPORTS CAVE</td></tr>
    <tr><td style="padding:0 20px;text-align:center"><h1 style="font-size:24px">{heading}</h1><p>{copy}</p></td></tr>
    <tr><td><img src="{image}" alt="{title} on your wall" width="600" style="display:block;width:100%;height:auto"></td></tr>
    <tr><td style="padding:24px;text-align:center"><h2 style="font-size:20px">{title}</h2><p>{context}</p>
    <a href="{html.escape(url,quote=True)}" style="display:inline-block;padding:16px 24px;background:#cfa84b;color:#111;text-decoration:none;font-weight:bold">SECURE YOUR EDITION</a>
    <p>Questions? Reply to this email.</p>{optout}</td></tr></table></td></tr></table></body></html>'''
    subject = 'Your Sports Cave wall preview' if kind=='requested' else ('Still thinking about your Sports Cave edition?' if kind=='4h' else 'See your Sports Cave edition on your wall')
    return {'subject':subject,'html':body,'text':f"{heading}\n{copy}\n{row.get('product_title','')}\n{context}\nSECURE YOUR EDITION: {url}" + ('\nUnsubscribe: '+unsubscribe if unsubscribe else ''),'unsubscribe_url':unsubscribe}


def finish(job,state,reason='',provider_id=None):
    with store.transaction() as cur:
        cur.execute('''UPDATE public.wall_preview_email_jobs SET state=%s,reason=%s,provider_id=%s,
            finished_at=now() WHERE id=%s''',(state,reason,provider_id,str(job['id'])))
        if state=='sent' and job['kind']=='requested':
            cur.execute('UPDATE public.wall_previews SET email_sent_at=now(),updated_at=now() WHERE id=%s',(str(job['preview_id']),))
    LOG.info('wall_preview_email job_id=%s preview_id=%s kind=%s state=%s reason=%s',job['id'],job['preview_id'],job['kind'],state,reason)


def followup_eligibility(row, config):
    """Same fresh Shopify consent, local/provider suppression and native opt-out rules as CRM."""
    if not config.enabled:
        return None,'marketing_disabled'
    from wall_preview_identity import resolve
    from crm_shopify import Shopify
    from crm_store import Store
    from crm_logic import eligibility, recipient_hash, email, date
    from crm_native_unsubscribe import native_unsubscribe_url
    ident = resolve(row['customer_email'],row.get('customer_name') or 'Collector','guest')
    if not ident.get('shopify_customer_id'):
        return None,'eligibility_unverified'
    customer = Shopify().customer(ident['shopify_customer_id'],fresh=True)
    address = email((customer or {}).get('email'))
    if address != row['customer_email']:
        return None,'recipient_changed'
    records = Store()
    ok, reason = eligibility(customer,records.suppressed(ident['shopify_customer_id'],recipient_hash(address)))
    if not ok:
        return None,reason
    # Conservative suppression for any newer purchase, even without line-item correlation.
    latest = date(((customer or {}).get('lastOrder') or {}).get('createdAt'))
    if latest and latest >= date(row['confirmed_at']):
        return None,'purchased'
    from crm_workspace_store import WorkspaceRecords
    workspace = WorkspaceRecords(records.connect)
    if workspace.frequency_blocked(recipient_hash(address),workspace.setting('sending')['value']['smart_hours']):
        return None,'smart_sending'
    unsubscribe = native_unsubscribe_url(customer)
    if not unsubscribe:
        return None,'missing_native_unsubscribe'
    if Resend(config).suppressed(address):
        return None,'provider_suppression'
    return unsubscribe,''


def tick():
    """One job per CRM cycle; persistent claim prevents parallel workers sending twice."""
    with store.transaction() as cur:
        # A crashed/ambiguous transport is held for review; NEVER blindly replay beyond
        # the provider idempotency window or after changing a preview/email payload.
        cur.execute("UPDATE public.wall_preview_email_jobs SET state='uncertain',reason='worker_interrupted',finished_at=now() WHERE state='processing' AND claimed_at<now()-interval '5 minutes'")
        cur.execute("SELECT * FROM public.wall_preview_email_jobs WHERE state='queued' AND due_at<=now() ORDER BY due_at FOR UPDATE SKIP LOCKED LIMIT 1")
        job = dict(cur.fetchone() or {})
        if not job:
            return False
        cur.execute("UPDATE public.wall_preview_email_jobs SET state='processing',claimed_at=now(),attempts=attempts+1 WHERE id=%s",(str(job['id']),))
        cur.execute('SELECT * FROM public.wall_previews WHERE id=%s',(str(job['preview_id']),))
        row = dict(cur.fetchone() or {})
    submitting = False
    try:
        if not row or row.get('share_revoked_at'):
            finish(job,'suppressed','preview_unavailable');return True
        config = Config()
        if job['kind']!='requested':
            if row.get('purchased_at'):
                finish(job,'suppressed','purchased');return True
            unsubscribe, reason = followup_eligibility(row,config)
            if reason:
                finish(job,'suppressed',reason);return True
        else:
            unsubscribe = ''
        if not configured(row['customer_email']):
            finish(job,'failed','delivery_not_configured');return True
        # Recheck the purchase under the same row lock used by verified order ingestion.
        with store.transaction() as cur:
            cur.execute('SELECT purchased_at FROM public.wall_previews WHERE id=%s FOR UPDATE',(str(row['id']),))
            if job['kind']!='requested' and (cur.fetchone() or {}).get('purchased_at'):
                cur.execute("UPDATE public.wall_preview_email_jobs SET state='suppressed',reason='purchased',finished_at=now() WHERE id=%s",(str(job['id']),))
                return True
        mail = message(row,job['kind'],unsubscribe)
        key = 'wall-preview-email:'+str(job['id'])
        submitting = True
        if job['kind']=='requested':
            pace()
            result = ResendEmailProvider(configuration(row['customer_email']),max_attempts=1).send(
                EmailMessage(mail['subject'],mail['html'],mail['text']),idempotency_key=key)
            provider_id = result.provider_message_id
        else:
            provider_id = Resend(config).send(row['customer_email'],mail,key)
        finish(job,'sent',provider_id=provider_id)
    except EmailDeliveryError as exc:
        # Definitive provider rejection is retryable with a bound; timeout is uncertain.
        known = exc.status_code in (400,401,403,404,405,422,429)
        if known and exc.retryable and int(job['attempts'])<2:
            with store.transaction() as cur:
                cur.execute("UPDATE public.wall_preview_email_jobs SET state='queued',reason='provider_rate_limit',due_at=now()+interval '1 minute' WHERE id=%s",(str(job['id']),))
        else:
            finish(job,'failed' if known else 'uncertain','provider_rejected' if known else 'transport_outcome_unknown')
    except Exception as exc:
        finish(job,'uncertain' if submitting else 'failed','transport_outcome_unknown' if submitting else 'validation_unavailable')
        LOG.warning('wall_preview_email_failed job_id=%s error_type=%s',job['id'],type(exc).__name__)
    return True
