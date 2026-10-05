"""Inspect CRM subscriptions; --apply creates only missing topics after approval."""
import argparse
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crm_webhooks import SHOPIFY_TOPICS

QUERY='''query CrmWebhooks($after:String) { webhookSubscriptions(first:100,after:$after) {
 nodes { id topic apiVersion { handle } endpoint { ... on WebhookHttpEndpoint { callbackUrl } } } pageInfo { hasNextPage endCursor } } }'''

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true');parser.add_argument('--orders-only',action='store_true');parser.add_argument('--automation-only',action='store_true');parser.add_argument('--abandoned-only',action='store_true',help='Inspect/create only the four abandoned-checkout trigger topics.');args=parser.parse_args(argv)
    import shopify_sync
    from crm_shopify_webhook_config import base_url,callbacks
    if not base_url():raise SystemExit('Configure the existing HTTPS webhook service base URL.')
    targets=callbacks();target=targets['crm']
    # API version is selected by the existing transport and app webhook config.
    if shopify_sync.get_config()['api_version']!='2026-04':
        raise SystemExit('CRM webhook setup requires Shopify API version 2026-04.')
    from crm_automation_capabilities import CONNECTION,TOPICS
    required=set(TOPICS['abandoned']) if args.abandoned_only else {t for ts in TOPICS.values() for t in ts}
    if args.apply and (args.automation_only or args.abandoned_only):
        import tomllib
        data,_=shopify_sync.graphql_request(CONNECTION,{})
        canonical=tomllib.loads((Path(__file__).resolve().parents[1]/'shopify_customer_account/shopify.app.toml').read_text())['client_id']
        app=data['currentAppInstallation']
        if app['app']['apiKey']!=canonical or not {'read_customers','read_orders'}.issubset(s['handle'] for s in app['accessScopes']):
            raise SystemExit('Installed Sports Cave app identity/read scopes are not verified.')
    existing=[];after=None;seen=set()
    while True:
        data,_=shopify_sync.graphql_request(QUERY,{'after':after})
        page=data['webhookSubscriptions'];existing.extend(page['nodes'])
        if not page['pageInfo']['hasNextPage']:break
        after=page['pageInfo']['endCursor']
        if not after or after in seen:raise SystemExit('Webhook pagination did not advance.')
        seen.add(after)
    for topic,enum in SHOPIFY_TOPICS.items():
        if (args.automation_only or args.abandoned_only) and enum not in required:continue
        if args.orders_only and enum not in ('ORDERS_CREATE','ORDERS_UPDATED','ORDERS_PAID','ORDERS_FULFILLED'):continue
        destination=targets['paid'] if enum=='ORDERS_PAID' else target
        same=[r for r in existing if r['topic']==enum]
        if same:
            allowed={target}
            if enum=='ORDERS_PAID':allowed.add(targets['paid'])
            status='registered' if any(shopify_sync._webhook_callback_url(r).rstrip('/') in allowed for r in same) else 'existing callback; review forwarding (not duplicated)'
            if status=='registered' and not any((r.get('apiVersion') or {}).get('handle')=='2026-04' and shopify_sync._webhook_callback_url(r).rstrip('/') in allowed for r in same):status='registered; webhook version requires review (not duplicated)'
            if len(same)>1:status+='; duplicate subscriptions — review only (not deleted)'
        elif args.apply:
            data,_=shopify_sync.graphql_request(shopify_sync.WEBHOOK_SUBSCRIPTION_CREATE_MUTATION,{'topic':enum,'webhookSubscription':{'callbackUrl':destination,'format':'JSON'}})
            if data['webhookSubscriptionCreate'].get('userErrors'):raise SystemExit('Shopify rejected CRM registration; review app permissions/topic availability.')
            # Creating through a 2026-04 API URL alone does not prove the
            # subscription's delivery version. Re-read Shopify's actual result.
            from crm_tracking_health import subscriptions
            from crm_shopify import Shopify
            observed=subscriptions(Shopify())
            if not any(r.get('topic')==enum and shopify_sync._webhook_callback_url(r).rstrip('/')==destination
                       and (r.get('apiVersion') or {}).get('handle')=='2026-04' for r in observed):
                raise SystemExit('Subscription created but callback/version is not verified. Review app webhook configuration; do not create another subscription.')
            status='created'
        else:status='missing'
        print(topic+': '+status)
    return 0
if __name__=='__main__':raise SystemExit(main())
