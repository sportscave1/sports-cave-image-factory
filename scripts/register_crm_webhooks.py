"""Inspect CRM subscriptions; --apply creates only missing topics after approval."""
import argparse
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crm_webhooks import SHOPIFY_TOPICS

QUERY='''query CrmWebhooks($after:String) { webhookSubscriptions(first:100,after:$after) {
 nodes { id topic endpoint { ... on WebhookHttpEndpoint { callbackUrl } } } pageInfo { hasNextPage endCursor } } }'''

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true');args=parser.parse_args(argv)
    import shopify_sync
    from crm_logic import safe_url
    target=os.environ.get('SPORTS_CAVE_WEBHOOK_BASE_URL','').rstrip('/')+'/webhooks/shopify/crm'
    if not safe_url(target):raise SystemExit('Configure the existing HTTPS webhook service base URL.')
    existing=[];after=None
    while True:
        data,_=shopify_sync.graphql_request(QUERY,{'after':after})
        page=data['webhookSubscriptions'];existing.extend(page['nodes'])
        if not page['pageInfo']['hasNextPage']:break
        after=page['pageInfo']['endCursor']
    for topic,enum in SHOPIFY_TOPICS.items():
        same=[r for r in existing if r['topic']==enum]
        if same:
            status='registered' if any(shopify_sync._webhook_callback_url(r).rstrip('/')==target for r in same) else 'existing callback; review forwarding (not duplicated)'
        elif args.apply:
            data,_=shopify_sync.graphql_request(shopify_sync.WEBHOOK_SUBSCRIPTION_CREATE_MUTATION,{'topic':enum,'webhookSubscription':{'callbackUrl':target,'format':'JSON'}})
            if data['webhookSubscriptionCreate'].get('userErrors'):raise SystemExit('Shopify rejected CRM registration; review app permissions/topic availability.')
            status='created'
        else:status='missing'
        print(topic+': '+status)
    return 0
if __name__=='__main__':raise SystemExit(main())
