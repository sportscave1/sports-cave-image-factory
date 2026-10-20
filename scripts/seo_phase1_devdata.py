"""Loopback-only synthetic data and raw Google response transport for SEO acceptance."""
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
import json
import os
from urllib.parse import urlsplit

DSN='postgresql://postgres:synthetic-seo-preview-only@127.0.0.1:55447/seo_phase1?sslmode=disable'


def connect():
    import psycopg
    from psycopg.rows import dict_row
    value=urlsplit(os.environ.get('DATABASE_URL',''))
    if (value.hostname,value.port,value.path)!=('127.0.0.1',55447,'/seo_phase1'):
        raise RuntimeError('SEO development data requires its own loopback database.')
    return psycopg.connect(DSN,row_factory=dict_row)


def prepare(repo):
    """Existing migration chain, applied only after validating the isolated DSN."""
    from types import SimpleNamespace
    backend=SimpleNamespace(connect=connect)
    import seo_workspace,google_seo,google_seo_phase4,seo_blog_workflow,seo_growth_intelligence
    # Explicit local schema preparation; never call the production server launcher.
    ordered=('20260812_seo_workspace_v1.sql','20260812_seo_workspace_v2.sql','20260813_google_seo_phase1.sql','20260813_google_seo_phase3_storage.sql','20260813_google_seo_phase4_join.sql','20260814_google_seo_phase4_reporting_snapshots.sql','20260814_seo_growth_intelligence_v1.sql','20260817_analytics_seo_blog_rebuild.sql','20260817_gsc_canonical_pipeline_repair.sql','20260818_seo_interactive_performance.sql','20260819_gsc_reporting_snapshot_repair.sql','20260820_gsc_property_totals_repair.sql')
    with connect() as conn:
        for filename in ordered:
            conn.execute((repo/'migrations'/filename).read_text(encoding='utf-8'))
    seo_workspace.PostgresSEOStore(backend).ensure_schema()
    google_seo.PostgresGoogleSEOStore(backend).ensure_schema()
    google_seo_phase4.PostgresSEOPhase4Store(backend).ensure_schema()
    seo_blog_workflow.PostgresBlogProjectStore(backend).ensure_schema()
    import supabase_backend
    supabase_backend.ensure_dashboard_schema()
    with connect() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS seo_phase1_dev_marker(id integer PRIMARY KEY CHECK(id=1),label text NOT NULL)")
        conn.execute("INSERT INTO seo_phase1_dev_marker VALUES(1,'Synthetic SEO Phase 1 only') ON CONFLICT DO NOTHING")
        conn.execute("INSERT INTO seo_google_connections(workspace_key,connection_status,gsc_site_url,ga4_property_id,ga4_property_name,ga4_property_currency,ga4_property_timezone) VALUES('sports-cave','connected','sc-domain:seo-preview.invalid','properties/57995487','Synthetic SEO property','AUD','Australia/Sydney') ON CONFLICT(workspace_key) DO NOTHING")
        conn.execute("INSERT INTO seo_growth_tasks(id,workspace_key,status,title,target_page,reason) VALUES('dev-legacy-task','sports-cave','approved','Improve existing collection','https://seo-preview.invalid/collections/art','Synthetic GSC evidence') ON CONFLICT DO NOTHING")
        conn.execute("INSERT INTO seo_growth_recommendations(id,workspace_key,status,recommended_action,current_page,priority,reason) VALUES('dev-legacy-proposal','sports-cave','awaiting_approval','Review collection metadata','https://seo-preview.invalid/collections/art','High','Synthetic saved proposal') ON CONFLICT DO NOTHING")
        conn.execute("INSERT INTO seo_technical_url_audits_v2(workspace_key,canonical_url,source,issue_code,severity,issue_summary,correction_steps,status) VALUES('sports-cave','https://seo-preview.invalid/products/art','HTML audit','missing_meta_description','Medium','Missing description','Prepare a description for review','Open') ON CONFLICT DO NOTHING")
        conn.execute("CREATE TABLE IF NOT EXISTS seo_phase1_dev_google_calls(id bigserial PRIMARY KEY,stage text NOT NULL,payload jsonb NOT NULL,created_at timestamptz DEFAULT now())")
    # Shared JSON store seed retains all existing fixture records on reruns.
    with connect() as conn:
        exists=conn.execute("SELECT 1 FROM seo_workspace_state WHERE workspace_key='sports-cave'").fetchone()
    if not exists:
        state=seo_workspace.default_state()
        seo_workspace.upsert_record(state,'blog_records',{'id':'dev-existing-draft','article_title':'Existing draft kept intact','article_draft':'Synthetic original content','status':'Draft','primary_keyword':'sports art'})
        seo_workspace.upsert_record(state,'keyword_mappings',{'id':'dev-mapping','primary_keyword':'sports art','target_page':'https://seo-preview.invalid/products/art'})
        with connect() as conn:
            conn.execute("INSERT INTO seo_workspace_state(workspace_key,schema_version,payload) VALUES('sports-cave',2,%s::jsonb)",(json.dumps(state),))
    project_store=seo_blog_workflow.PostgresBlogProjectStore(backend)
    if not project_store.get_project('dev-existing-project'):
        project_store.save_project({'project_id':'dev-existing-project','title':'Existing v2 project','brief':{'primary_keyword':'sports art'},'status':'Idea'})


def _matches(row, expression):
    if not expression:return True
    if 'andGroup' in expression:return all(_matches(row,e) for e in expression['andGroup']['expressions'])
    if 'orGroup' in expression:return any(_matches(row,e) for e in expression['orGroup']['expressions'])
    if 'notExpression' in expression:return not _matches(row,expression['notExpression'])
    rule=expression.get('filter',{})
    return str(row.get(rule.get('fieldName'),''))==str(rule.get('stringFilter',{}).get('value',''))


class DevelopmentGoogleClient:
    """GoogleReports/CanonicalGA4Client run unchanged against deterministic raw responses."""
    def _gsc_endpoint(self,site):return 'https://google-preview.invalid/gsc'
    def _post(self,endpoint,payload,*,stage):
        with connect() as conn:
            conn.execute('INSERT INTO seo_phase1_dev_google_calls(stage,payload) VALUES(%s,%s::jsonb)',(stage,json.dumps(payload)))
        if endpoint.endswith(':checkCompatibility'):
            return {'dimensionCompatibilities':[{'dimensionMetadata':{'apiName':r['name']},'compatibility':'COMPATIBLE'} for r in payload.get('dimensions',[])], 'metricCompatibilities':[{'metricMetadata':{'apiName':r['name']},'compatibility':'COMPATIBLE'} for r in payload.get('metrics',[])]}
        if stage=='gsc_direct':return self.gsc(payload)
        return self.ga4(payload)

    def gsc(self,payload):
        start=date.fromisoformat(payload['startDate']);end=date.fromisoformat(payload['endDate'])
        dims=payload.get('dimensions',[]); groups=defaultdict(lambda:[0,0,0])
        rules=[r for group in payload.get('dimensionFilterGroups',[]) for r in group.get('filters',[])]
        day=start
        while day<=end:
            if day>date.today()-timedelta(days=3):break
            for country,device in [('aus','mobile'),('usa','desktop')]:
                for query,page,clicks,impressions,position in [('sports art','/products/art?variant=1',2,200,12),('wall art','/collections/art',4,100,7)]:
                    row={'date':str(day),'country':country,'device':device,'query':query,'page':'https://seo-preview.invalid'+page}
                    if any(row.get(r['dimension'])!=r['expression'] for r in rules if r.get('operator')=='equals'):continue
                    # Privacy rows are absent from query exports, but included in property totals.
                    extra=1 if not any(d in dims for d in ('query','page')) and not any(r.get('dimension') in ('query','page') for r in rules) else 0
                    values=groups[tuple(row[d] for d in dims)]
                    values[0]+=clicks+extra;values[1]+=impressions+10*extra;values[2]+=position*(impressions+10*extra)
            day+=timedelta(days=1)
        rows=[{'keys':list(key),'clicks':v[0],'impressions':v[1],'ctr':v[0]/v[1],'position':v[2]/v[1]} for key,v in groups.items()]
        offset=int(payload.get('startRow',0));limit=int(payload.get('rowLimit',25000))
        return {'rows':rows[offset:offset+limit]}

    def ga4(self,payload):
        dims=[d['name'] for d in payload.get('dimensions',[])];metrics=[m['name'] for m in payload.get('metrics',[])]
        dates=payload.get('dateRanges',[{'startDate':str(date.today()),'endDate':str(date.today())}])[0]
        start=date.fromisoformat(dates['startDate']);end=date.fromisoformat(dates['endDate']); groups=defaultdict(lambda:defaultdict(float))
        day=start
        while day<=end:
            for source,channel,factor in [('google','Organic Search',1),('bing','Organic Search',2),('facebook','Paid Social',3)]:
                for country,device in [('AU','mobile'),('US','desktop')]:
                    for path,purchases in [('/products/art?variant=1',1),('/collections/art',0)]:
                        row={'date':day.strftime('%Y%m%d'),'sessionSource':source,'sessionDefaultChannelGroup':channel,'countryId':country,'country':'Australia' if country=='AU' else 'United States','deviceCategory':device,'landingPagePlusQueryString':path,'pagePathPlusQueryString':path,'pageTitle':'Synthetic page','itemName':'Synthetic artwork','itemId':'dev-product','eventName':'purchase'}
                        if not _matches(row,payload.get('dimensionFilter')):continue
                        group=groups[tuple(row.get(d,'Synthetic') for d in dims)]
                        for metric in metrics:
                            group[metric]+=float(purchases*factor*50 if metric in ('purchaseRevenue','totalRevenue','itemRevenue') else purchases*factor if metric in ('ecommercePurchases','itemsPurchased') else .5 if 'Rate' in metric else 10*factor)
            day+=timedelta(days=1)
        rows=[{'dimensionValues':[{'value':v} for v in key],'metricValues':[{'value':str(values[m])} for m in metrics]} for key,values in groups.items()]
        return {'dimensionHeaders':[{'name':d} for d in dims],'metricHeaders':[{'name':m} for m in metrics],'rows':rows[int(payload.get('offset',0)):int(payload.get('offset',0))+int(payload.get('limit',25000))],'rowCount':len(rows),'metadata':{'currencyCode':'AUD','timeZone':'Australia/Sydney'}}
