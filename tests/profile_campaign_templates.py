"""Opt-in local timing/call profile. Requires disposable crm_postgres_server.mjs."""
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crm_campaign_store import CampaignStore
from crm_campaign_library import library_rows,template_html,save_template,insert_template
from crm_campaign_content import new_document
from crm_template_cache import invalidate
from tests.crm_db_fixture import connect,Connection
from tests.test_crm import ADMIN

if os.getenv('CRM_TEST_POSTGRES')!='1':raise SystemExit('Set CRM_TEST_POSTGRES=1 for the disposable loopback fixture.')
s=CampaignStore(connect)
rows=[save_template(s,ADMIN,'Profile template '+str(i),'<p>'+('sample '*500)+'</p>') for i in range(12)]
stats={};original=Connection.execute;calls=[]
def execute(self,sql,args=()):
    calls.append(sql)
    return original(self,sql,args)
def measure(name,fn):
    calls.clear();start=time.perf_counter();value=fn()
    stats[name]={'ms':round((time.perf_counter()-start)*1000,3),'sql_statements':len(calls),
                 'selects':sum(x.startswith('SELECT') for x in calls)}
    return value
try:
    invalidate()
    with patch.object(Connection,'execute',execute):
        listing=measure('list_cold',lambda:library_rows(s))
        measure('list_repeat',lambda:library_rows(s))
        meta=next(r for r in listing if r['id']==rows[0]['id'])
        measure('edit_body',lambda:template_html(s,meta))
        measure('edit_body_repeat',lambda:template_html(s,meta))
        doc=new_document();doc.update(content_mode='HTML',custom_html='')
        measure('use',lambda:insert_template(doc,template_html(s,meta),meta))
        measure('save',lambda:save_template(s,ADMIN,meta['name'],'<p>changed</p>',meta))
    print(json.dumps(stats,indent=2))
finally:
    for row in rows:
        latest=s.get('templates',row['id']);s.archive_design(ADMIN,row['id'],latest['version'])
