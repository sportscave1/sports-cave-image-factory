"""Resend marketing adapter reusing the OS transport; all sends opt-in gated."""
import base64
import hashlib
import hmac
import os
import time
import threading
import uuid
from urllib.parse import quote
from crm_logic import email,safe_url
from crm_templates import LOGO_PATH

class MarketingDisabled(RuntimeError):pass
class ProviderUnavailable(RuntimeError):pass

_RATE_LOCK=threading.Lock()
_NEXT_REQUEST=0.0

def pace():
    """Leave room below Resend's default request rate; only CRM uses this gate."""
    global _NEXT_REQUEST
    with _RATE_LOCK:
        delay=max(0,_NEXT_REQUEST-time.monotonic())
        if delay:time.sleep(delay)
        _NEXT_REQUEST=time.monotonic()+0.55

class Config:
    def __init__(self,env=None):
        env=os.environ if env is None else env
        master=env.get('CRM_MARKETING_ENABLED','').lower()=='true'
        self.enabled=master and env.get('CRM_MARKETING_SEND_ENABLED','').lower()=='true'
        # The old queued template tests are NOT the Stage 1 admin diagnostic.
        self.tests_enabled=master and env.get('CRM_MARKETING_TEST_ENABLED','').lower()=='true'
        self.api_key=env.get('RESEND_MARKETING_API_KEY','')
        from email.utils import formataddr
        self.sender=formataddr((env.get('RESEND_FROM_NAME',''),env.get('RESEND_FROM_EMAIL',''))) if env.get('RESEND_FROM_EMAIL') and env.get('RESEND_FROM_NAME') else ''
        self.reply_to=env.get('RESEND_REPLY_TO','')
        self.public_base=(env.get('CRM_PUBLIC_BASE_URL') or env.get('SPORTS_CAVE_WEBHOOK_BASE_URL','')).rstrip('/')
        app=(env.get('SPORTS_CAVE_OS_BASE_URL') or env.get('PUBLIC_APP_URL') or 'https://sports-cave-image-factory.onrender.com').rstrip('/')
        self.logo_url=app+LOGO_PATH
        self.secret=env.get('CRM_UNSUBSCRIBE_SECRET','')
        self.resend_webhook_secret=env.get('CRM_RESEND_WEBHOOK_SECRET','')
    def require_send(self,test=False):
        if not (self.tests_enabled if test else self.enabled):raise MarketingDisabled('Marketing delivery is disabled. Drafts and previews remain available.')
        if not self.api_key or not self.sender or not self.reply_to:raise MarketingDisabled('Marketing delivery configuration is incomplete.')
    def unsubscribe_url(self,send_id):
        if len(self.secret)<32:raise MarketingDisabled('Marketing unsubscribe signing is not configured.')
        if not safe_url(self.public_base):raise MarketingDisabled('CRM_PUBLIC_BASE_URL must be a public HTTPS unsubscribe base URL.')
        value=str(uuid.UUID(str(send_id)));signature=hmac.new(self.secret.encode(),('crm-marketing-opt-out/v1:'+value).encode(),hashlib.sha256).hexdigest()
        return self.public_base+'/crm/unsubscribe?token='+value+'.'+signature
    def verify_token(self,token):
        try:
            if not isinstance(token,str) or len(token)>101:return None
            value,sig=token.split('.',1)
            value=str(uuid.UUID(value))
            expected=hmac.new(self.secret.encode(),('crm-marketing-opt-out/v1:'+value).encode(),hashlib.sha256).hexdigest()
            legacy=hmac.new(self.secret.encode(),value.encode(),hashlib.sha256).hexdigest()
            # Retain any earlier issued links indefinitely; both are restricted to
            # existing production receipt IDs by the POST handler.
            return value if len(self.secret)>=32 and (hmac.compare_digest(sig,expected) or hmac.compare_digest(sig,legacy)) else None
        except (ValueError,AttributeError,TypeError):return None

    def test_unsubscribe_url(self):
        return self.public_base+'/crm/unsubscribe/test' if safe_url(self.public_base) else ''

class Resend:
    def __init__(self,config=None,session=None):
        self.config=config or Config()
        if session is None:
            import requests
            session=requests.Session()
        self.session=session
    def request(self,method,path,**kwargs):
        try:
            pace()
            response=self.session.request(method,'https://api.resend.com'+path,headers={'Authorization':'Bearer '+self.config.api_key},timeout=15,**kwargs)
            if response.status_code==404 and method=='GET' and response.json().get('name') in ('not_found','not_found_error'):
                return None
            if not 200<=response.status_code<300:raise ProviderUnavailable('Provider suppression check is unavailable.')
            return response.json()
        except Exception:raise ProviderUnavailable('Provider operation is temporarily unavailable.') from None
    def suppressed(self,address):
        path=quote(email(address),safe='')
        suppression=self.request('GET','/suppressions/'+path)
        contact=self.request('GET','/contacts/'+path)
        return suppression is not None or bool(contact and contact.get('unsubscribed'))
    def recipient_for(self,provider_id,hashed):
        # Only used to honor an old unsubscribe after Shopify's address changes.
        data=self.request('GET','/emails/'+quote(str(provider_id),safe='')) or {}
        from crm_logic import recipient_hash
        return next((email(a) for a in data.get('to',[]) if email(a) and recipient_hash(a)==hashed),None)
    def suppress(self,address):
        # Suppression-only write. Never subscribe contacts or change Shopify consent.
        self.request('POST','/suppressions',json={'email':email(address)})
    def send(self,address,message,key,test=False):
        self.config.require_send(test)
        from email_service import EmailConfiguration,EmailMessage,ResendEmailProvider
        class MarketingProvider(ResendEmailProvider):
            def _payload(self,mail):
                payload=super()._payload(mail)
                payload['headers']={'List-Unsubscribe':'<'+message['unsubscribe_url']+'>'}
                if message.get('unsubscribe_one_click') is True:
                    payload['headers']['List-Unsubscribe-Post']='List-Unsubscribe=One-Click'
                return payload
        configuration=EmailConfiguration(self.config.api_key,self.config.sender,email(address),self.config.reply_to)
        provider=MarketingProvider(configuration,session=self.session,max_attempts=1)
        pace()
        result=provider.send(EmailMessage(message['subject'],message['html'],message['text']),idempotency_key=key)
        return result.provider_message_id

def verify_resend(raw,headers,secret,clock=time.time):
    """Official Svix verifier: untouched bytes, signature and five-minute tolerance."""
    try:
        from svix.webhooks import Webhook
        timestamp=headers.get('svix-timestamp','');event=headers.get('svix-id','')
        if not event or abs(clock()-int(timestamp))>300:return False
        key=base64.b64decode(secret.removeprefix('whsec_'),validate=True)
        if len(key)<16:return False
        Webhook(secret).verify(raw,dict(headers))
        return True
    except Exception:return False
