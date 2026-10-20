"""Compact Streamlit workspace using existing reporting clients and SEO editors."""
import csv
import io
import json
from datetime import date, timedelta
import streamlit as st
import seo_phase1 as model
import seo_navigation as nav
import analytics_navigation as anav
import analytics_contracts as contracts
import seo_workspace as workspace
import os_accounts

VIEWS = ('Pages', 'Queries', 'Channels', 'Engagement', 'Ecommerce', 'Events', 'Audience', 'Realtime', 'Overview details', 'Store operations', 'Mappings')

def save(store, state, user):
    try: store.save(state, actor_id=user.get('id') or '')
    except workspace.SEOStoreError as error:
        st.error(str(error)); st.stop()

def table(rows, *, key):
    if rows:
        import seo_page
        displayed=seo_page._paginated_rows(rows,key=key+'-pagination',default_page_size=25) if len(rows)>25 else rows
        st.dataframe(displayed, hide_index=True, use_container_width=True)
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(dict.fromkeys(k for row in rows for k in row)))
        writer.writeheader()
        writer.writerows(rows)
        st.download_button('Export filtered rows', buffer.getvalue(), file_name='seo-report.csv', mime='text/csv', key=key)
    else:
        st.info('No records match this view.')

def fetch(key, callback):
    """Keep same-filter prior results visible on partial-source failure."""
    cache = st.session_state.setdefault('seo-phase1-results', {})
    try:
        value = callback()
        if key not in cache and len(cache)>=16:
            cache.pop(next(iter(cache)))
        cache[key] = value
        st.session_state.setdefault('seo-phase1-errors', {}).pop(str(key),None)
        return value
    except Exception as error:
        st.warning(f'{key[0]} is unavailable for this request. ' + ('Showing previous results for the same filters.' if key in cache else 'Other sources remain available.'))
        st.session_state.setdefault('seo-phase1-errors', {})[str(key)] = type(error).__name__
        return cache.get(key)

def report_rows(report):
    return [{**r.get('dimensions', {}), **r.get('metrics', {})} for r in (report or {}).get('rows', [])]

def task_action(row, context, state, store, user):
    target = row.get('page') or row.get('landingPagePlusQueryString') or row.get('canonical_url') or ''
    query = row.get('query') or ''
    with st.expander('Details and Plan task', expanded=False):
        st.json(row)
        mappings = [m for m in state.get('keyword_mappings', []) if (query and m.get('primary_keyword', '').casefold() == query.casefold()) or (target and m.get('target_page') == target)]
        if mappings:
            st.write('Saved mappings', mappings)
        if query:
            mapped = st.text_input('Mapped target page', value=(mappings[0].get('target_page') if mappings else '') or target, key='seo-detail-mapping-target::'+query.casefold()+'::'+target)
            if st.button('Save mapping'):
                workspace.upsert_record(state, 'keyword_mappings', {'primary_keyword': query, 'target_page': mapped, 'mapping_status': 'Mapped'}, record_id=mappings[0]['id'] if mappings else '', actor=user)
                model.event(state, 'Mapping change', query)
                save(store, state, user)
                st.success('Mapping saved.')
            st.caption('Search metrics describe this query. Conversion metrics belong to the landing page and are never assigned to individual queries.')
        work_type = st.selectbox('Work type', model.TYPES)
        intent = st.text_input('Task intent', value='Review search performance')
        if st.button('Create Plan task', type='primary'):
            task, added = model.create_task(state, title=f'{intent}: {query or target}', target=target, query=query,
                work_type=work_type, intent=intent, evidence={**row,'source':'GSC' if row.get('query') or row.get('page') else 'GA4 landing pages'}, context=context, actor=user)
            save(store, state, user)
            st.success('Task saved to Plan.' if added else 'This open task already exists in Plan.')
            st.caption(task['id'])

def analytics(user, state, store, reports, initial=None):
    # Analytics-only users retain GA4 access, without gaining GSC or editing SEO records.
    seo_access = os_accounts.can_access_page(user, nav.SEO_OVERVIEW_ROUTE)
    connection={}
    if reports is not None:
        try: connection=reports.connection()
        except Exception:
            st.warning('Connection diagnostics are unavailable. Saved Plan and Review work remains available.')
            return
    identity=tuple(str(connection.get(k) or '') for k in ('id','gsc_site_url','ga4_property_id','connected_at','updated_at'))
    cols = st.columns(5)
    days_label = cols[0].selectbox('Date range', ('28 days', '7 days', '90 days', 'Custom'))
    comparison = cols[1].selectbox('Compare', ('Previous period', 'Off'))
    market = cols[2].selectbox('Market', ('All markets', 'Australia', 'United States', 'United Kingdom'))
    device = cols[3].selectbox('Device', ('All devices', 'Desktop', 'Mobile', 'Tablet'))
    scope = cols[4].selectbox('Traffic scope (GA4)', ('Google organic', 'All organic', 'All channels'), index=2 if initial in ('Channels','Engagement','Ecommerce','Events','Audience','Realtime') else 0)
    through=None
    if reports is not None and seo_access:
        today=model.datetime.now(model.ZoneInfo('America/Los_Angeles')).date()
        watermark=fetch(('GSC final data',identity),lambda:reports.gsc(today-timedelta(days=10),today,('date',),{'search_type':'web'}))
        through=max((r.get('date','') for r in watermark or []),default='') or None
    start, end = model.period(int(days_label.split()[0]) if days_label != 'Custom' else 28,through=through)
    if days_label == 'Custom':
        dates = st.columns(2)
        start = dates[0].date_input('Start', value=start)
        end = dates[1].date_input('End', value=end)
    if start > end:
        st.error('Start date must precede end date.')
        return
    if end > model.period()[1]:
        st.warning('This custom range may contain incomplete source periods; comparisons are provisional.')
    context = {'start': str(start), 'end': str(end), 'market': market, 'device': device, 'scope': scope, 'comparison': comparison}
    st.caption(f'{start} – {end} inclusive · GSC: Google organic only · GA4: {scope}. Final GSC dates may lag; no purchase session rate is inferred from purchase events.')
    if reports is None:
        st.info('Reporting is unavailable in this isolated local workspace. Existing production connections have not been changed. Use an injected development reporting client for verification.')
        view = st.selectbox('View', VIEWS, index=VIEWS.index(initial) if initial in VIEWS else 0, key='seo-phase1-view-' + str(initial))
        if view == 'Mappings' and seo_access:
            import seo_page
            seo_page._render_keywords(store,state,user)
        return
    if st.button('Refresh data', key='seo-phase1-refresh'):
        reports.cache.clear()
        model.event(state, 'Data refresh', source='Google reporting cache', status='Invalidated', detail=context)
        save(store, state, user)
    gfilters = {'market': market, 'device': device, 'search_type': 'web'}
    ga_filters = model.filters_for_ga4(market, device)
    signature = json.dumps([user.get('id'),identity,context], sort_keys=True)
    def gsc(dimensions, old=False):
        span = (end-start).days+1
        a,b = (start-timedelta(days=span), start-timedelta(days=1)) if old else (start,end)
        return fetch(('GSC', signature, dimensions, old), lambda: reports.gsc(a,b,dimensions,gfilters))
    def ga(contract, old=False):
        span = (end-start).days+1
        a,b = (start-timedelta(days=span), start-timedelta(days=1)) if old else (start,end)
        return fetch(('GA4', signature, str(contract), old), lambda: reports.ga4(connection.get('ga4_property_id'),contract,a,b,filters=ga_filters))
    totals = model.gsc_totals(gsc(()) or []) if seo_access else {}
    previous = model.gsc_totals(gsc((), True) or []) if seo_access and comparison != 'Off' else {}
    ga_report = ga(model.ga4_contract(scope))
    ga_totals = report_rows(ga_report)
    ga_total = ga_totals[0] if ga_totals else {}
    old_rows = report_rows(ga(model.ga4_contract(scope), True)) if comparison != 'Off' else []
    old_ga = old_rows[0] if old_rows else {}
    metrics = [('Google organic clicks', totals.get('clicks'), previous.get('clicks')), ('Google organic impressions', totals.get('impressions'), previous.get('impressions'))] if seo_access else []
    metrics += [(scope+' sessions', ga_total.get('sessions'), old_ga.get('sessions')), (scope+' purchases', ga_total.get('ecommercePurchases'), old_ga.get('ecommercePurchases')), ('GA4 attributed purchase revenue (' + str((ga_report or {}).get('currency') or connection.get('ga4_property_currency') or 'currency unavailable') + ')', ga_total.get('purchaseRevenue'), old_ga.get('purchaseRevenue'))]
    for col, (label, value, old) in zip(st.columns(len(metrics)), metrics):
        value, old = model.number(value), model.number(old)
        col.metric(label, 'Unavailable' if value is None else f'{value:,.2f}', delta=f'{(value-old)/old:.1%}' if value is not None and old else None,help=label+' · '+scope if label.startswith('GA4') else label)
    metric = st.selectbox('Chart metric', ('GSC clicks','GSC impressions','GA4 sessions','GA4 purchases','GA4 attributed purchase revenue') if seo_access else ('GA4 sessions','GA4 purchases','GA4 attributed purchase revenue'))
    if metric.startswith('GSC'):
        chart = gsc(('date',)) or []
        field = 'clicks' if metric == 'GSC clicks' else 'impressions'
    else:
        chart = report_rows(ga(model.ga4_contract(scope, ('date',))))
        field = {'GA4 sessions':'sessions', 'GA4 purchases':'ecommercePurchases', 'GA4 attributed purchase revenue':'purchaseRevenue'}[metric]
    if chart:
        st.line_chart([{'date':r['date'], field:float(r[field]) if r.get(field) is not None else None} for r in chart], x='date', y=field)
    view = st.selectbox('View', VIEWS, index=VIEWS.index(initial) if initial in VIEWS else 0, key='seo-phase1-view-' + str(initial))
    if view in ('Queries', 'Mappings') and not seo_access:
        st.info('SEO access is required for this view.')
        return
    if view == 'Mappings':
        import seo_page
        seo_page._render_keywords(store, state, user)
        return
    st.caption('GSC final-data watermark: '+str(through or 'Unavailable')+' · GA4 fetched: '+str((ga_report or {}).get('fetched_at') or 'Unavailable')+' · GA4 quality: '+str(((ga_report or {}).get('quality') or {}).get('status') or 'Unavailable'))
    with st.expander('Source freshness and definitions'):
        st.write('GSC uses Pacific dates and final data. Query rows can omit private queries and need not reconcile to property totals. CTR is summed clicks / summed impressions. Positions are supplied by GSC at the requested grain.')
        st.write('GA4 uses its property timezone, currency and attribution. All organic includes other search engines. Attributed purchase revenue is separate from Shopify sales. No cross-source conversion join is performed.')
        st.json({k:(ga_report or {}).get(k) for k in ('metadata','quality','property_timezone','currency','fetched_at','complete')})
        st.write('Default window ends at least three Pacific days ago. A source can still be delayed; empty reports remain unavailable. Refresh invalidates the shared cache; it does not execute SEO changes.')
    if view == 'Queries':
        rows = gsc(('query','page')) or []
        st.caption('One row per query and page. Query totals and positions come from GSC; conversions are not expanded into query rows.')
        st.session_state['seo-phase1-scan-evidence'] = {'rows':rows, 'context':context}
    elif view == 'Pages':
        rows = gsc(('page',)) or [] if seo_access else []
        with st.expander('Landing-page conversion context (GA4)'):
            table(report_rows(ga(model.ga4_contract(scope, ('landingPagePlusQueryString',)))), key='seo-page-conversion-export')
            st.caption('Separate source table preserves URL query parameters and source grain; no inferred query revenue.')
    elif view == 'Store operations':
        if model.local_mode(): st.info('Shared Shopify operational reporting is unavailable in local mode.')
        else:
            import analytics_page
            analytics_page._shopify_operational_panel({'start_date':start,'end_date':end})
        return
    else:
        keys = {'Overview details':'overview_totals', 'Channels':'traffic_acquisition','Engagement':'pages_screens','Ecommerce':'ecommerce_products','Events':'events','Audience':'countries','Realtime':'realtime'}
        contract = contracts.report_contract(keys[view])
        from dataclasses import replace
        if view == 'Realtime':
            st.caption('Realtime covers the last 30 minutes, all channels. Date range, comparison and traffic scope above do not apply.')
            rows = report_rows(fetch(('GA4 realtime',identity), lambda: reports.ga4(connection.get('ga4_property_id'), contract, start, end)))
        else:
            contract = replace(contract, filters=model.ga4_contract(scope).filters)
            rows = report_rows(ga(contract))
        if view == 'Audience':
            with st.expander('Devices'):
                table(report_rows(ga(replace(contracts.report_contract('devices'), filters=model.ga4_contract(scope).filters))), key='seo-devices-export')
    search = st.text_input('Filter rows', key='seo-phase1-report-search')
    rows = [r for r in rows if search.casefold() in json.dumps(r, default=str).casefold()]
    if view in ('Pages','Queries'):
        opportunity_filter = st.selectbox('Opportunity signal', ('All', 'High impressions / low CTR', 'Approaching page one', 'Declining traffic', 'Landing pages with sessions / no purchases'))
        if opportunity_filter == 'High impressions / low CTR':
            rows = [r for r in rows if model.number(r.get('impressions')) is not None and model.number(r['impressions']) >= 100 and r.get('ctr') is not None and model.number(r['ctr']) < model.number('.02')]
        elif opportunity_filter == 'Approaching page one':
            rows = [r for r in rows if r.get('average_position') is not None and 11 <= model.number(r['average_position']) <= 20]
        elif opportunity_filter == 'Declining traffic':
            dims=('query','page') if view=='Queries' else ('page',)
            previous_rows=gsc(dims,True) if comparison!='Off' else None
            if previous_rows is None:
                st.info('Declining traffic needs an available previous-period comparison.')
                rows=[]
            else:
                old_index={tuple(r.get(d) for d in dims):r for r in previous_rows}
                rows=[r for r in rows if tuple(r.get(d) for d in dims) in old_index and model.number(r.get('clicks')) is not None and model.number(r['clicks']) < model.number(old_index[tuple(r.get(d) for d in dims)]['clicks'])]
        elif opportunity_filter == 'Landing pages with sessions / no purchases':
            if view=='Queries':
                st.info('Choose Pages for landing-page conversion signals. Query revenue is unavailable.')
                rows=[]
            else:
                rows=[r for r in report_rows(ga(model.ga4_contract(scope,('landingPagePlusQueryString',)))) if r.get('sessions') is not None and model.number(r['sessions'])>0 and r.get('ecommercePurchases') is not None and model.number(r['ecommercePurchases'])==0]
                rows=[r for r in rows if search.casefold() in json.dumps(r,default=str).casefold()]
                st.caption('GA4 landing pages: sessions >0 and recorded purchase events =0, in the selected traffic scope. Missing purchase values are excluded.')
        st.caption('Signals: at least 100 impressions and CTR <2%; approaching page one: average position 11–20. Signals require review and do not prove a title problem.')
    table(rows, key='seo-active-export')
    if rows and seo_access and view in ('Pages','Queries'):
        selected = st.selectbox('Inspect row', range(len(rows)), format_func=lambda i: str(rows[i].get('query') or rows[i].get('page') or rows[i].get('landingPagePlusQueryString') or i))
        row=rows[selected]
        with st.expander('Ranking history / related queries'):
            if st.checkbox('Load source details',key='seo-load-source-details',disabled=not bool(row.get('page') or row.get('query'))):
                extra=[]
                if row.get('query'): extra.append({'dimension':'query','operator':'equals','expression':row['query']})
                if row.get('page'): extra.append({'dimension':'page','operator':'equals','expression':row['page']})
                dims=('date',) if row.get('query') else ('query',)
                details=fetch(('GSC details',signature,json.dumps(extra)),lambda:reports.gsc(start,end,dims,{**gfilters,'extra_filters':extra}))
                table(details or [],key='seo-details-export')
        task_action(row, {**context,'search':search,'opportunity_filter':opportunity_filter}, state, store, user)


def plan(user, state, store, navigate, initial=None):
    if not model.local_mode() and st.button("Import saved health findings"):
        from seo_live_analytics import PostgresSEOLiveAnalyticsReader
        try:
            findings=model.saved_health(PostgresSEOLiveAnalyticsReader())
            count=model.import_health(state,findings,user)
            model.event(state,"Health findings imported",source="Saved technical audit",detail={"created":count})
            save(store,state,user)
            st.success(f"{count} technical tasks added; existing tasks retained.")
        except Exception:
            st.warning("Saved audit findings could not be read. No crawl was started.")
    types = ('All', *model.TYPES)
    kind = st.selectbox('Work type', types, index=types.index(initial) if initial in types else 0)
    status = st.selectbox('Status', ('Active', 'All', *model.STATUSES))
    rows = [r for r in state['plan_items'] if (not r.get('admin_only') or os_accounts.is_admin(user)) and (kind=='All' or r.get('work_type')==kind) and (status=='All' or (status=='Active' and r.get('status') in model.ACTIONABLE) or status==r.get('status'))]
    rank = {'High':0,'Medium':1,'Low':2}
    rows.sort(key=lambda r:(rank.get(r.get('priority'),1), r['created_at']))
    table([{k:r.get(k) for k in ('id','title','target','work_type','priority','status','reason')} for r in rows], key='seo-plan-export')
    with st.expander('Add task'):
        with st.form('seo-manual-task'):
            title = st.text_input('Title')
            target = st.text_input('Target page or entity')
            work_type = st.selectbox('Type', model.TYPES)
            intent = st.text_input('Intent', value='Manual review')
            if st.form_submit_button('Add task') and title.strip():
                model.create_task(state,title=title,target=target,work_type=work_type,intent=intent,actor=user)
                save(store,state,user); st.rerun()
    if rows:
        index = st.selectbox('Task', range(len(rows)), format_func=lambda i:rows[i]['title'])
        row = rows[index]
        with st.expander('Task details', expanded=True):
            st.caption(row['id'])
            st.write('Keyword mappings', [m for m in state['keyword_mappings'] if m.get('primary_keyword','').casefold()==str(row.get('query') or '').casefold() and row.get('query')])
            st.json({'evidence':row.get('evidence'), 'context':row.get('context'), 'related_query':row.get('query'), 'related_draft':row.get('draft_id'), 'observed_at':row.get('observed_at')})
            editable=not row.get('source_edit_admin') or os_accounts.is_admin(user)
            if not editable: st.caption('Legacy workflow changes require an administrator.')
            with st.form('seo-task-edit'):
                title=st.text_input('Task title',value=row['title'])
                priority=st.selectbox('Priority', ('High','Medium','Low'), index=('High','Medium','Low').index(row.get('priority','Medium')))
                task_status=st.selectbox('Task status',model.STATUSES,index=model.STATUSES.index(row.get('status','Open')))
                reason=st.text_area('Reason / next action',value=row.get('reason',''))
                if st.form_submit_button('Save task',disabled=not editable):
                    model.update_task(state,row,{'title':title,'priority':priority,'status':task_status,'reason':reason},user)
                    save(store,state,user); st.rerun()
            if st.button('Prepare linked content draft'):
                if not row.get('draft_id'):
                    draft=workspace.upsert_record(state,'blog_records',{'article_title':row['title'],'primary_keyword':row.get('query',''),'target_url':row.get('target',''),'status':'Draft','task_id':row['id']},actor=user)
                    model.update_task(state,row,{'draft_id':draft['id']},user)
                    model.event(state,'Draft/proposal change',draft['id'],detail={'change':'created'})
                    save(store,state,user)
                if navigate:
                    linked_id=row.get('draft_id') or draft['id']
                    st.session_state['seo-blog-edit-select']=linked_id
                    st.session_state['seo-blog-builder-record']=linked_id
                    st.session_state['seo-blog-view']='Blog Builder'
                    navigate(nav.SEO_REVIEW_ROUTE)
                    st.rerun()
                else: st.success('Linked draft is available in Review.')
    with st.expander('Existing manual tools'):
        tool=st.selectbox('Tool',('Choose','Keyword mappings','Internal links','Citations','Outreach','Saved growth tasks','Growth reports and strategy','Health findings and audits'))
        if tool != 'Choose':
            import seo_page
            if tool=='Health findings and audits':
                if model.local_mode(): st.info('Shared audit storage is unavailable in local mode. Add verified findings as technical tasks; no crawl or worker is started.')
                else: seo_page._render_seo_health(user)
            elif tool=='Growth reports and strategy':
                if model.local_mode(): st.info('Shared growth reporting is unavailable in local mode.')
                else: seo_page._render_reports_strategy(store,state,user)
            elif tool=='Saved growth tasks':
                if model.local_mode(): st.info('Shared growth-task storage is unavailable in local mode.')
                else: seo_page._render_tasks_results(user)
            else:
                {'Keyword mappings':seo_page._render_keywords,'Internal links':seo_page._render_internal_linking,'Citations':seo_page._render_citations,'Outreach':seo_page._render_outreach}[tool](store,state,user)


def review(user,state,store,initial=None):
    import seo_page
    choice=st.selectbox('Content workflow',('Saved drafts','Blog projects','Saved proposals'),index=1 if initial=='Blog projects' else 0)
    if choice=='Blog projects':
        if model.local_mode():
            seo_page._render_blog_v2(state,user,project_store=model.LocalBlogProjects(store),reporting_reader=model.LocalResearch(st.session_state.get('seo-phase1-scan-evidence')))
        else: seo_page._render_blog_v2(state,user)
        if model.local_mode():
            state=store.load()
            projects=[p for p in state['blog_projects'] if os_accounts.is_admin(user) or p.get('owner_id')==user.get('id')]
        else:
            import seo_blog_workflow
            try:
                projects=seo_blog_workflow.PostgresBlogProjectStore().list_projects(owner_id=user.get('id') or '',include_all=os_accounts.is_admin(user))
            except Exception: projects=[]
        if projects:
            selected=st.selectbox('Project internal review',range(len(projects)),format_func=lambda i:projects[i].get('title') or projects[i].get('project_id') or projects[i]['id'])
            project=dict(projects[selected])
            project['id']=project.get('project_id') or project['id']
            st.caption('Current revision: '+model.valid_decision(state,project)+'. Approval does not publish.')
            decision=st.selectbox('Project decision',('Approved','Changes requested'))
            if st.button('Save project review decision'):
                model.review_decision(state,project,decision,user); save(store,state,user); st.rerun()
    elif choice=='Saved proposals':
        if model.local_mode(): st.info('Shared proposals are unavailable in isolated local mode.')
        else:
            import seo_growth_intelligence
            seo_page._render_recommendation_review(user,seo_growth_intelligence.default_store())
    else:
        seo_page._render_blog(store,state,user)
        # The existing editor owns drafting, research, links, media references and pack export.
        drafts=workspace.active_records(state,'blog_records')
        if drafts:
            focused=st.session_state.get('seo-blog-builder-record') or st.session_state.get('seo-blog-edit-select') or ''
            focus_index=next((i for i,d in enumerate(drafts) if d['id']==focused),0)
            selected=st.selectbox('Internal review',range(len(drafts)),index=focus_index,format_func=lambda i:drafts[i].get('article_title') or drafts[i]['id'],key='seo-phase1-review-draft::'+focused)
            draft=drafts[selected]
            st.caption('Current revision: '+model.valid_decision(state,draft)+'. Approval never publishes to Shopify.')
            decision=st.selectbox('Decision',('Approved','Changes requested'))
            if st.button('Save review decision'):
                model.review_decision(state,draft,decision,user); save(store,state,user); st.rerun()


def history(user,state):
    events=list(state['workspace_events'])
    if not model.local_mode():
        import supabase_backend
        existing,errors=model.read_saved_events(supabase_backend,actor_id=user.get('id') or '',admin=os_accounts.is_admin(user))
        events.extend(existing)
        if errors: st.caption('Unavailable history sources: '+', '.join(errors)+'. Other events remain available.')
    hidden={r['id'] for r in state['plan_items'] if r.get('admin_only') and not os_accounts.is_admin(user)}
    events=[e for e in events if e.get('target') not in hidden]
    actions=sorted({r.get('action','') for r in events})
    selected=st.selectbox('Action',('All',*actions))
    sources=sorted({r.get('source','') for r in events})
    source=st.selectbox('Source',('All',*sources))
    rows=sorted((r for r in events if (selected=='All' or r.get('action')==selected) and (source=='All' or r.get('source')==source)),key=lambda r:r.get('time',''),reverse=True)
    import seo_page
    visible=seo_page._paginated_rows(rows,key='seo-history-list',default_page_size=25) if len(rows)>25 else rows
    for row in visible:
        with st.expander(f"{row.get('time')} · {row.get('action')} · {row.get('target') or row.get('source')} · {row.get('status')}"):
            st.json(row.get('detail') or {})
    if not rows: st.info('No activity matches the selected history filters.')
    st.caption('Refresh, scans, task saves and draft saves describe separate actions. No execution record means no SEO fix was executed.')


def worker(user,state,store,reports,navigate):
    connection={}
    if reports:
        connection=fetch(('Connection',),reports.connection) or {}
    cols=st.columns(4)
    if not model.local_mode():
        import seo_page
        shopify=seo_page._cached_default_shopify_health()
    else: shopify={}
    for col,label,key in zip(cols,('Shopify','GSC','GA4','Execution'),('', 'gsc_site_url','ga4_property_id','')):
        col.caption(label)
        if label=='Shopify':
            col.write(shopify.get('status') or 'Unavailable in local mode')
        elif label=='Execution': col.write('Unavailable')
        else:
            loaded=any(k[0]==label and bool(value) for k,value in st.session_state.get('seo-phase1-results',{}).items())
            col.write('Report available in this session' if loaded else 'Selected; report not yet verified' if connection.get(key) else 'Unavailable in local mode' if model.local_mode() else 'Not verified')
    active=[r for r in state['plan_items'] if r.get('status') in model.ACTIONABLE and (not r.get('admin_only') or os_accounts.is_admin(user))]
    reviewable=[r for r in [*state['blog_records'],*state['blog_projects']] if not r.get('archived_at') and (not r.get('project_id') or os_accounts.is_admin(user) or r.get('owner_id')==user.get('id'))]
    reviews=[r for r in reviewable if model.valid_decision(state,r)!='Approved']
    technical=sum(r.get('work_type')=='Technical fix' for r in active)
    st.caption(f'{len(active)} actionable Plan items · {technical} technical findings · {len(reviews)} saved drafts/projects awaiting internal review')
    evidence=st.session_state.get('seo-phase1-scan-evidence')
    st.caption('Planning evidence: '+(json.dumps(evidence['context']) if evidence else 'No query evidence loaded in this session. Open Analytics → Queries first.'))
    if st.button('Update Plan from saved work'):
        tasks=[]; recommendations=[]
        if not model.local_mode():
            import seo_growth_intelligence
            growth=seo_growth_intelligence.default_store()
            try:
                tasks=growth.list_tasks(limit=100)
                recommendations=growth.list_recommendations(limit=100)
            except Exception:
                st.warning('Shared growth work is unavailable; local saved work remains usable.')
        count=model.import_saved_work(state,tasks=tasks,recommendations=recommendations,actor=user)
        model.event(state,'Saved work linked',detail={'created':count})
        save(store,state,user)
        st.success(f'{count} saved work items linked to Plan.')
    busy=st.session_state.get('seo-phase1-busy',False)
    if st.button('Evaluate loaded search opportunities',disabled=busy or not evidence):
        st.session_state['seo-phase1-busy']=True
        try:
            count=model.scan(state,evidence['rows'],evidence['context'],user)
            save(store,state,user)
            st.success(f'Scan completed. {count} new tasks saved; existing open tasks retained.')
        finally: st.session_state['seo-phase1-busy']=False
    st.caption('This bounded scan evaluates up to 500 loaded GSC rows. It does not start an autonomous worker.')
    table([{k:r.get(k) for k in ('title','priority','status','reason')} for r in sorted(active,key=lambda r:({'High':0,'Medium':1,'Low':2}.get(r.get('priority'),1),r['created_at']))[:5]],key='seo-next-export')
    with st.popover('Settings'):
        st.write('Planning scope: Google organic evidence; manual review required. No production execution is permitted.')
        if model.local_mode(): st.caption('Local JSON persistence. Shared connections, schedules and production writes are disabled.')
        elif os_accounts.is_admin(user):
            import seo_page
            seo_page._render_data_connections_admin(user,embedded=True)
    with st.expander('Recent activity'):
        for row in state['workspace_events'][-5:][::-1]: st.write(row.get('time'),row.get('action'),row.get('status'))
    st.caption('Recorder and companion remain in Developer tooling. No SEO execution session or command contract is connected.')
    if navigate and os_accounts.can_access_page(user,'Task Recorder') and st.button('Open Task Recorder'):
        navigate('Task Recorder'); st.rerun()


def render(user,route,*,store=None,navigate=None,google_store=None,reporting_reader=None,reports=None):
    if not os_accounts.can_access_page(user,route):
        st.error('You do not have access to this workspace.')
        return
    destination,initial=model.destination(route)
    store=store or model.store_for_workspace(user)
    # Local mode never discovers database credentials or launches a production integration.
    if reports is None and not model.local_mode():
        from google_direct_reporting import GoogleReports
        reports=GoogleReports(connection_store=google_store)
    try: state=store.load() if os_accounts.can_access_page(user,nav.SEO_OVERVIEW_ROUTE) else workspace.default_state()
    except workspace.SEOStoreError as error:
        st.error(str(error)); return
    import streamlit.components.v1 as components
    import seo_page
    seo_page._inject_styles()
    st.markdown('<style>[data-testid="stMetricLabel"] {min-height:3rem;height:auto} [data-testid="stMetricLabel"] p {white-space:normal!important;overflow:visible!important}</style>',unsafe_allow_html=True)
    status='ready'
    try:
        st.subheader(nav.SEO_NAV_LABELS.get(destination,'SEO'))
        if destination==nav.SEO_ANALYTICS_ROUTE: analytics(user,state,store,reports,initial)
        elif destination==nav.SEO_PLAN_ROUTE: plan(user,state,store,navigate,initial)
        elif destination==nav.SEO_REVIEW_ROUTE: review(user,state,store,initial)
        elif destination==nav.SEO_HISTORY_ROUTE: history(user,state)
        else: worker(user,state,store,reports,navigate)
    except Exception:
        status='error'
        raise
    finally:
        payload=json.dumps({'routeKey':os_accounts.page_key_for_route(route),'epoch':int(st.session_state.get('navigation_epoch') or 0),'status':status}).replace('</','<\\/')
        components.html(f'<script>window.parent.SportsCaveTopBar?.completeNavigation?.({payload});</script>',height=0,width=0)
