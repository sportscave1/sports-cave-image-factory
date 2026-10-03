"""Editable master HTML in existing runtime-state storage; drafts own copied HTML."""
from copy import deepcopy
import json
from crm_checkout_styles import MARKER,CLASSES,default_html,rules

KEY='abandoned_checkout_master_v1'


def load(store):
    row=store.state(KEY)
    return row if row else {'revision':0,'html':default_html()}


def validate(html):
    from crm_campaign_html import import_html
    from crm_abandoned_checkout import reject_unresolved,block_html
    from crm_checkout_preview import sample
    from crm_checkout_styles import compile_html
    from crm_email_size import LIMIT_BYTES
    if not isinstance(html,str) or html.count(MARKER)!=1:raise ValueError('Keep exactly one <!--SC_ABANDONED_CHECKOUT--> insertion point.')
    reject_unresolved(html.replace(MARKER,''))
    theme=rules(html)
    if not CLASSES<=set(theme):raise ValueError('Keep the sc-cart-* class styling contract; edit its values freely.')
    # Reserved image/CTA elements come only from checked checkout data.
    from html.parser import HTMLParser
    class Protected(HTMLParser):
        def handle_starttag(self,tag,attrs):
            attrs=dict(attrs)
            if {'sc-cart-button','sc-cart-image'} & set(attrs.get('class','').split()):raise ValueError('Keep checkout image and recovery CTA inside the protected block.')
    Protected().feed(html)
    hydrated=compile_html(html.replace(MARKER,block_html(sample({}),test=True)),theme)
    markup,_,checks=import_html(hydrated)
    if not all(checks.values()):raise ValueError('Use safe email HTML, valid public image URLs and HTTPS links.')
    if max(len(html.encode()),len(markup.encode()))>LIMIT_BYTES:raise ValueError('Keep the template below 95 KB. Final hydrated size is rechecked before sending.')
    return html


def save(store,user,html,revision):
    from crm_navigation import require
    require(user,'crm_automations_manage');validate(html)
    with store.db() as conn:
        # Insert/lock serializes first save as well as concurrent later edits.
        conn.execute('INSERT INTO crm_runtime_state(key,value) VALUES(%s,%s::jsonb) ON CONFLICT DO NOTHING',(KEY,json.dumps({'revision':0,'html':default_html()})))
        old=conn.execute('SELECT value FROM crm_runtime_state WHERE key=%s FOR UPDATE',(KEY,)).fetchone()['value']
        if old['revision']!=revision:raise ValueError('Template changed elsewhere. Reopen it before saving.')
        value={'revision':revision+1,'html':html}
        conn.execute('UPDATE crm_runtime_state SET value=%s::jsonb,updated_at=now() WHERE key=%s',(json.dumps(value),KEY))
    return deepcopy(value)


def use(store,doc):
    from crm_abandoned_checkout import apply_template
    apply_template(doc,load(store)['html'])
