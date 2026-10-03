"""Explicit server-admin diagnostic; never sends email or backfills journeys."""
import argparse
import json
from pathlib import Path
import sys
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--activate-pixel',action='store_true')
    parser.add_argument('--extension-and-endpoint-deployed',action='store_true')
    parser.add_argument('--endpoint')
    parser.add_argument('--inspect-only',action='store_true',help='Report checks without updating diagnostic storage.')
    args=parser.parse_args(argv)
    from crm_shopify import Shopify
    from crm_store import Store
    from crm_automation_capabilities import verify,activate_pixel
    shop,store=Shopify(),Store()
    if args.inspect_only and args.activate_pixel:parser.error('Inspection cannot activate a pixel.')
    if args.activate_pixel:
        if not args.extension_and_endpoint_deployed or not args.endpoint:
            parser.error('Confirm the released extension and deployed endpoint before activation.')
        import os
        previous=store.state('shopify_automation_pixel')
        settings=previous.get('settings') or store.state('shopify_automation_pixel_setup').get('settings') or {'endpoint':args.endpoint,'shop':os.getenv('SHOPIFY_STORE_DOMAIN',''),'ingestionId':uuid.uuid4().hex}
        pixel=activate_pixel(shop,store,settings)
        print(json.dumps({'pixel_id':pixel['id'],'customer_events_status':'UNVERIFIED — check Shopify Admin Settings → Customer events'}))
    try:result=verify(shop,store,persist=not args.inspect_only)
    except Exception as exc:
        print('Diagnostic could not be persisted: '+type(exc).__name__+'. Check CRM storage or use --inspect-only.',file=sys.stderr)
        return 2
    print('ABANDONED CHECKOUT: '+('READY' if result['triggers']['abandoned']=='AVAILABLE' else 'NOT READY'))
    for reason in result['reasons']['abandoned']:print(' - '+reason)
    print(json.dumps(result,indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
