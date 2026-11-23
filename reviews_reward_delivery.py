"""One bounded reward per worker cycle; all production writes default off.

Ambiguous Shopify/Resend outcomes are held for human reconciliation, never
blindly replayed. Imported reviews cannot enter this delivery flow.
"""
from datetime import timedelta
from html import escape
import os
import secrets

from crm_logic import now,email,recipient_hash,eligibility
from crm_resend import Config,Resend
from reviews_rewards import eligibility as reward_eligibility

CREATE_CODE='''mutation ReviewRewardCode($input:DiscountCodeBasicInput!) {
 discountCodeBasicCreate(basicCodeDiscount:$input) {
  codeDiscountNode { id } userErrors { field message }
 }
}'''

def discount_input(row,clock):
    return {'title':'Sports Cave media thank you','code':row['code'],
      'startsAt':clock.isoformat(),'endsAt':(clock+timedelta(days=30)).isoformat(),
      'context':{'customers':{'add':[row['customer_id']]}},
      'customerGets':{'value':{'percentage':row['percent']/100},'items':{'all':True}},
      'usageLimit':1,'appliesOncePerCustomer':True,
      'combinesWith':{'orderDiscounts':False,'productDiscounts':False,'shippingDiscounts':False}}

def message(row,unsubscribe):
    code=escape(row['code']);percent=int(row['percent']);url=escape(unsubscribe,quote=True)
    text=f"Thank you for sharing your Sports Cave photo or video. Your {percent}% reward code is {row['code']}. Valid for your customer account for one purchase within 30 days of issue. Cannot combine with other discounts. This reward is independent of your star rating."
    return {'subject':'Your Sports Cave photo/video reward','html':f'<p>Thank you for sharing your photo or video.</p><p>Your {percent}% reward code: <strong>{code}</strong></p><p>For your customer account, one purchase, expires 30 days after issue. Cannot combine with other discounts. Your reward does not depend on your star rating.</p><p><a href="{url}">Unsubscribe</a></p>',
      'text':text+'\nUnsubscribe: '+unsubscribe,'unsubscribe_url':unsubscribe}

def tick(store,shop=None,mailer=None,env=None):
    env=os.environ if env is None else env
    if env.get('REVIEW_REWARDS_DELIVERY_ENABLED','').lower()!='true':return None
    config=Config(env)
    config.require_send()
    if not store.collection_settings()['rewards_enabled']:return None
    if shop is None:
        from crm_shopify import Shopify
        shop=Shopify()
    mailer=mailer or Resend(config)
    with store.db() as conn:
        # A crashed provider call has an unknown external outcome.
        conn.execute("UPDATE sc_review_rewards SET status='HELD',error_code='outcome_unknown',updated_at=now() WHERE status IN ('ISSUING','SENDING') AND updated_at<now()-interval '5 minutes'")
        row=conn.execute("SELECT * FROM sc_review_rewards WHERE status IN ('ELIGIBLE','ISSUED') ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED").fetchone()
        if not row:return None
        # Persist a random code before any remote mutation. Never generate another
        # one for this reward, including after an uncertain network response.
        phase='ISSUING' if row['status']=='ELIGIBLE' else 'SENDING'
        code=row['code'] or 'SCMEDIA'+secrets.token_hex(12).upper()
        conn.execute('UPDATE sc_review_rewards SET status=%s,code=%s,updated_at=now() WHERE review_id=%s',(phase,code,row['review_id']))
        row={**row,'code':code}
    try:
        review=store.get_review(row['review_id'])
        if not review or review['status']=='SPAM' or not reward_eligibility(review,store.media(row['review_id']),store.collection_settings()):raise ValueError('reward_no_longer_eligible')
        from reviews_submission import verified_context
        verified_context(shop,row['order_id'],row['customer_id'],review['product_id'])
        customer=shop.customer(row['customer_id'],fresh=True)
        if not customer or customer.get('id')!=row['customer_id']:raise ValueError('customer_unavailable')
        address=email(customer.get('email'));ok,reason=eligibility(customer,store.suppressed(row['customer_id'],recipient_hash(address)))
        if not ok:raise ValueError(reason)
        if mailer.suppressed(address):raise ValueError('provider_suppression')
        from crm_native_unsubscribe import native_unsubscribe_url
        unsubscribe=native_unsubscribe_url(customer)
        if not unsubscribe:raise ValueError('missing_native_unsubscribe')
        if phase=='ISSUING':
            result=shop.query(CREATE_CODE,{'input':discount_input(row,now())},'review reward discount',fresh=True)['discountCodeBasicCreate']
            if result.get('userErrors') or not (result.get('codeDiscountNode') or {}).get('id'):raise ValueError('discount_not_confirmed')
            store.q("UPDATE sc_review_rewards SET status='ISSUED',discount_id=%s,issued_at=now(),updated_at=now(),error_code=NULL WHERE review_id=%s AND status='ISSUING'",(result['codeDiscountNode']['id'],row['review_id']))
        else:
            # Do not advertise a code after its 30-day validity window.
            from crm_logic import date
            if not row.get('issued_at') or date(row['issued_at'])+timedelta(days=30)<=now():raise ValueError('reward_expired')
            from crm_discount_api import LOOKUP
            current=shop.query(LOOKUP,{'code':row['code']},'review reward discount verification',fresh=True)['codeDiscountNodeByCode']
            facts=(current or {}).get('codeDiscount') or {}
            actual=((facts.get('customerGets') or {}).get('value') or {}).get('percentage')
            if not current or current['id']!=row['discount_id'] or facts.get('__typename')!='DiscountCodeBasic' or facts.get('status')!='ACTIVE' or actual!=row['percent']/100 or facts.get('usageLimit')!=1 or facts.get('asyncUsageCount',0)>0 or not date(facts.get('endsAt')) or date(facts['endsAt'])<=now():raise ValueError('discount_changed')
            provider=mailer.send(address,message(row,unsubscribe),'review-reward:'+str(row['review_id']))
            if not provider:raise ValueError('delivery_not_confirmed')
            store.q("UPDATE sc_review_rewards SET status='SENT',provider_id=%s,updated_at=now(),error_code=NULL WHERE review_id=%s AND status='SENDING'",(provider,row['review_id']))
    except Exception:
        # Log neither customer information nor discount/credential values.
        store.q("UPDATE sc_review_rewards SET status='HELD',error_code='verification_or_provider_failure',updated_at=now() WHERE review_id=%s AND status=%s",(row['review_id'],phase))
    return row['review_id']
