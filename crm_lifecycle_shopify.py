"""Narrow read-only extensions through the existing Shopify.query transport."""
from pathlib import Path
from datetime import timedelta
import json
from crm_logic import date,now

ORDER_FACTS=(Path(__file__).parent/'docs/lifecycle-order-facts.graphql').read_text()
PRODUCT_AVAILABILITY=(Path(__file__).parent/'docs/lifecycle-product-availability.graphql').read_text()

def order_facts(shop,ids):
    result={}
    for start in range(0,len(ids),50):
        batch=ids[start:start+50]
        nodes=shop.query(ORDER_FACTS,{'ids':batch},'lifecycle order eligibility',0,True)['nodes']
        for node in nodes:
            if not isinstance(node,dict) or node.get('id') not in batch:continue
            if not isinstance(node.get('risk'),dict) or not isinstance(node.get('disputes'),list) or not isinstance(node.get('fulfillments'),list):
                raise ValueError('Order risk, dispute or fulfillment verification unavailable')
            result[node['id']]=node
        if any(identity not in result for identity in batch):raise ValueError('Order history access is incomplete')
    return result

def operational_facts(node,fulfilled):
    successful=[f for f in node.get('fulfillments',[]) if f.get('status')=='SUCCESS']
    delivered=[date(f.get('deliveredAt')) for f in successful]
    fulfilled_dates=[date(f.get('createdAt')) for f in successful]
    return dict(fraudulent=(node.get('risk') or {}).get('recommendation') not in ('ACCEPT','NONE'),
        disputed=any(d.get('status')!='WON' for d in node.get('disputes',[])),
        unresolved_return=node.get('returnStatus') not in (None,'NO_RETURN','RETURNED'),
        fulfilled_at=max(fulfilled_dates) if fulfilled and fulfilled_dates and all(fulfilled_dates) else None,
        delivered_at=max(delivered) if fulfilled and delivered and all(delivered) else None)

def sync_order_facts(store,shop,at=None):
    at=at or now();state=store.state('lifecycle-order-facts-sync')
    if date(state.get('next_at')) and date(state['next_at'])>at:return
    rows=store.q('''SELECT shopify_order_id FROM shopify_orders
      WHERE upper(financial_status) IN ('PAID','PARTIALLY_REFUNDED','REFUNDED')
      AND (raw_json->'lifecycleFacts'->>'verified_at' IS NULL OR
           raw_json->'lifecycleFacts'->>'verified_at'<%s)
      ORDER BY COALESCE(raw_json->'lifecycleFacts'->>'verified_at',''),created_at DESC LIMIT 20''',((at-timedelta(hours=6)).isoformat(),))
    if rows:
        values=order_facts(shop,[r['shopify_order_id'] for r in rows])
        with store.db() as conn:
            for identity,value in values.items():
                conn.execute("UPDATE shopify_orders SET raw_json=COALESCE(raw_json,'{}'::jsonb)||%s::jsonb WHERE shopify_order_id=%s",(json.dumps({'lifecycleFacts':{**value,'verified_at':at.isoformat()}}),identity))
    store.set_state('lifecycle-order-facts-sync',{'next_at':(at+timedelta(seconds=30 if rows else 300)).isoformat()})
