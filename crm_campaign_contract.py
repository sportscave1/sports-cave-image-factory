"""Persisted production settings; preview URLs never authorize live dispatch."""
from copy import deepcopy
import json
import os
from crm_resend import Config
from crm_campaign_content import RENDER_VERSION


def capture(settings, env=None):
    result=deepcopy(settings)
    config=Config(os.environ if env is None else env)
    result['_delivery']={'version':1,'renderer':RENDER_VERSION,
                         'sender':config.sender,'reply_to':config.reply_to}
    return result


def comparable(settings):
    # This URL is used only for previews without a real unsubscribe URL.
    # Production rendering always receives a validated recipient Shopify URL.
    return json.loads(json.dumps({k:v for k,v in settings.items()
                                if k!='test_unsubscribe_url'},sort_keys=True))


def validate(reviewed, current):
    current=deepcopy(current)
    # Pre-contract snapshots retain their existing checks. New reviews also
    # freeze the actual From/Reply-To and rendering implementation version.
    if '_delivery' not in reviewed:current.pop('_delivery',None)
    old,new=comparable(reviewed),comparable(current)
    changed=sorted(k for k in old.keys()|new.keys() if old.get(k)!=new.get(k))
    if changed:
        raise ValueError('Sender or rendering settings changed: '+', '.join(changed)+'. Re-review this campaign.')
    # Publication's database fence requires the exact persisted review object.
    return deepcopy(reviewed)
