"""Emit production repository SQL for an isolated PostgreSQL runner; no connections."""
import json
import sys
from unittest.mock import MagicMock, patch
import meta_review_store as store
from tests.test_meta_review import CREATIVE, raw


def statements():
    executed=[]
    connection=MagicMock()
    conn=connection.__enter__.return_value
    cur=conn.cursor.return_value.__enter__.return_value
    cur.execute.side_effect=lambda sql,params=():executed.append({'sql':sql,'params':params})
    payload={'account_id':'123','account':{'name':'Fixture','currency':'AUD'},
        'campaigns':[{'id':'cam','name':'Campaign','status':'PAUSED'}],
        'adsets':[{'id':'set','campaign_id':'cam','name':'Ad set'}],
        'ads':[{'id':'1','campaign_id':'cam','adset_id':'set','name':'Ad','creative':CREATIVE},
               {'id':'2','campaign_id':'cam','adset_id':'set','name':'Shared creative','creative':CREATIVE}],
        'daily':[raw(campaign_id='cam',adset_id='set')],
        'assets':[{'ad_id':'1','date':'2026-09-01','breakdown':'body_asset','asset_key':'Exact primary\n\nDo not rewrite.','raw':raw()}],
        'warnings':[],'api_version':'v26.0'}
    with patch.object(store.backend,'connect',return_value=connection): store.save_sync(payload,1)
    return executed


def read_statements():
    executed=[]
    connection=MagicMock()
    cur=connection.__enter__.return_value.cursor.return_value.__enter__.return_value
    cur.fetchall.return_value=[]
    cur.execute.side_effect=lambda sql,params=():executed.append({'sql':sql,'params':params})
    with patch.object(store.backend,'connect',return_value=connection): store.load_history('123')
    return executed


if __name__=='__main__': print(json.dumps(read_statements() if '--read' in sys.argv else statements(),default=str))
