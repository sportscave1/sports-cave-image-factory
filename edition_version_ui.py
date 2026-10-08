"""Compact Edition Ops controls; existing table and ledger remain authoritative."""
from copy import deepcopy
import uuid
import time
import logging
import streamlit as st
import edition_ops as ops
import edition_versions as versions

STYLE='''<style>
[data-testid="stMainBlockContainer"]:has(.st-key-edition-workspace){padding-top:calc(var(--sc-topbar-height, 64px) + 0.65rem)!important}
.st-key-edition-workspace [data-testid="stVerticalBlock"]{gap:6px}
.st-key-edition-workspace h3{font-size:19px;padding:2px 0}
.st-key-edition-workspace button[kind="secondary"],.st-key-edition-workspace [data-testid="stPopoverButton"]{background:#fff!important;border:1px solid #d7d7d0!important;color:#262926!important;min-height:32px;height:32px;border-radius:4px!important;padding:3px 10px!important;box-shadow:none!important}
.st-key-edition-workspace button[kind="secondary"]:hover{background:#f1f1ed!important}
.st-key-edition-workspace [data-baseweb="select"]>div{min-height:34px;border-radius:4px}
.st-key-edition-workspace [data-testid="stExpander"] summary{padding:4px 8px;min-height:32px}
.st-key-edition-workspace [data-testid="stElementContainer"]{min-width:0;max-width:100%}
</style>'''


def actor():
    return st.session_state.get('sports_cave_current_user') or {}


def sync_error_message(error):
    """Keep transport/SQL internals in logs, with actionable compact UI errors."""
    text=str(error or '').lower()
    if 'mismatch' in text or 'verification' in text:
        return 'Shopify readback did not match the saved value. Retry sync.'
    if '429' in text or 'throttl' in text or 'rate limit' in text:
        return 'Shopify rate limit reached; automatic retry is pending.'
    if 'timeout' in text or 'connection' in text:
        return 'Connection interrupted; the saved value is retained for retry.'
    return 'Sync needs attention. Retry sync; technical details are in the server log.'


def save_cursor_changes(acknowledged=False, submissions=None):
    """Persist only explicit changed rows; missing schema stops the entire batch."""
    import edition_cursor_overrides
    import logging
    originals={ops._stable_row_key(r):r for r in st.session_state[ops.ORIGINAL_ROWS_KEY]}
    if submissions is None:
        submissions=[]
        for row in st.session_state[ops.ROWS_KEY]:
            old=originals.get(ops._stable_row_key(row))
            if old is None or not any(row.get(k)!=old.get(k) for k in ('edition_next_number','edition_total')):continue
            fingerprint=(row.get('edition_run_id'),old['edition_next_number'],row['edition_next_number'],old['edition_total'],row['edition_total'])
            requests=st.session_state.setdefault('edition-cursor-requests',{})
            saved=requests.get(row['handle'])
            if not saved or saved[0]!=fingerprint:
                saved=(fingerprint,str(uuid.uuid4()));requests[row['handle']]=saved
            submissions.append((deepcopy(row),deepcopy(old),saved[1]))
    st.session_state['edition-save-errors']=[]
    if not submissions:
        st.session_state[ops.NOTICE_KEY]='No edited editions to save.'
        return
    try:edition_cursor_overrides.require_schema()
    except Exception as exc:
        logging.getLogger(__name__).exception('Edition override schema preflight failed')
        st.session_state[ops.NOTICE_KEY]=(str(exc) if isinstance(exc,edition_cursor_overrides.SchemaUnavailable)
            else 'Edition database unavailable. No changes saved; your edits are retained. Retry when connectivity is restored.')
        return
    saved_count=0
    st.session_state['edition-sync-verified']=set()
    for row,old,request in submissions:
        try:
            edition_cursor_overrides.save(row['handle'],run_id=row['edition_run_id'],
                expected_next=old['edition_next_number'],next_number=row['edition_next_number'],
                expected_limit=old['edition_total'],edition_limit=row['edition_total'],
                request_id=request,actor_id=actor().get('id'))
            key=ops._stable_row_key(row)
            for collection in (ops.ROWS_KEY,ops.ORIGINAL_ROWS_KEY,ops.EDITOR_ROWS_KEY):
                st.session_state[collection]=[
                    {**r,'edition_next_number':row['edition_next_number'],'edition_total':row['edition_total'],
                     'sync_status':'Pending','sync_error':''}
                    if ops._stable_row_key(r)==key else r for r in st.session_state.get(collection,[])]
            saved_count+=1
            st.session_state.setdefault('edition-sync-watching',set()).add(row['handle'])
            st.session_state.pop('edition-sync-watch-until',None)
        except Exception as exc:
            logging.getLogger(__name__).exception('Edition override save failed handle=%s',row['handle'])
            message='Could not save. Your edited values are retained; retry or ask an administrator to check the server log.'
            if 'Edition changed' in str(exc):message='Changed by another edit or order. Refresh this product before retrying.'
            elif 'administrator required' in str(exc):message='An active administrator account is required.'
            elif 'Number must be within' in str(exc):message='Enter a positive number within the limit, or the terminal sold-out number.'
            st.session_state['edition-save-errors'].append((row['product_title'],message))
    if saved_count:ops._cached_supabase_products_snapshot.clear()
    failed=len(st.session_state['edition-save-errors'])
    st.session_state[ops.NOTICE_KEY]=f'{saved_count} edition changes saved. Shopify verification is shown below. {failed} saves require attention.'


def refresh_handle(handle, *, discard_edits=False):
    backend=ops._configured_supabase_backend()
    records=backend.list_edition_products_read_only(handles=[handle],limit=1)
    if not records:return
    ops._cached_supabase_products_snapshot.clear()
    fresh=ops._row_from_supabase_product(records[0]);key=ops._stable_row_key(fresh)
    dirty=not discard_edits and key in ops._editable_changed_keys(
        st.session_state.get(ops.ROWS_KEY,[]),st.session_state.get(ops.ORIGINAL_ROWS_KEY,[]))
    for collection in (ops.ROWS_KEY,ops.ORIGINAL_ROWS_KEY,ops.EDITOR_ROWS_KEY):
        rows=st.session_state.get(collection,[])
        if dirty:
            # A background result must never consume a newer, unsaved edit or
            # replace the optimistic concurrency token it was based on.
            continue
        st.session_state[collection]=[deepcopy(fresh) if ops._stable_row_key(r)==key else r for r in rows]


@st.dialog('Start New Edition Version',width='small')
def version_dialog(row):
    st.write(row['product_title'])
    st.caption('Current: '+row['edition_label']+' · '+row.get('edition_run_id',''))
    key='edition-version-request-'+row['handle']
    request=st.session_state.setdefault(key,str(uuid.uuid4()))
    with st.form('edition-new-version'):
        name=st.text_input('New version label',value='Updated artwork',max_chars=80)
        a,b=st.columns(2)
        start=a.number_input('Starting number',1,100,min(100,row['edition_next_number']))
        total=b.number_input('Maximum edition size',1,100,row['edition_total'])
        reason=st.text_input('Design revision reason',max_chars=500)
        st.caption('This must be a genuinely separate artwork release. Earlier allocations and certificates remain valid. A release disclosure will be added to the same Shopify product.')
        cancel,confirm=st.columns(2)
        cancelled=cancel.form_submit_button('Cancel')
        submitted=confirm.form_submit_button('Create New Edition Version',type='primary')
    if cancelled:st.rerun()
    if submitted:
        try:
            result=versions.create(row['handle'],expected_run=row['edition_run_id'],request_id=request,
                name=name,start=start,total=total,reason=reason,actor_id=actor().get('id'))
            ops._cached_supabase_products_snapshot.clear()
            st.session_state.setdefault('edition-sync-watching',set()).add(row['handle'])
            st.session_state.pop('edition-sync-watch-until',None)
            refresh_handle(row['handle'],discard_edits=True)
            st.session_state.pop(key,None)
            st.session_state[ops.NOTICE_KEY]='New version saved · PENDING SYNC. Allocations are paused until Shopify confirms.'
            st.session_state[ops.NOTICE_LEVEL_KEY]='warning'
            st.rerun()
        except Exception as exc:st.error(str(exc))


def release_controls():
    rows=st.session_state.get(ops.ROWS_KEY,[])
    selected=st.session_state.get(ops.EDITOR_PRODUCT_SELECTION_KEY)
    row=next((r for r in rows if ops._stable_row_key(r)==selected),None)
    if not row:return
    with st.container(horizontal=True):
        st.caption(row['edition_label']+' · '+str(row.get('run_status') or 'active').upper())
        if st.button('Review Allocations',key='edition-review'):
            st.session_state['edition-review-run']=row.get('edition_run_id')
        if st.button('Start New Edition Version',disabled=actor().get('role')!='admin' or not row.get('edition_run_id') or row.get('run_status') in ('expired','pending_sync')):
            version_dialog(row)
        if str(row.get('sync_status') or '').casefold() in ops.SHOPIFY_RETRY_STATUSES or row.get('run_status')=='pending_sync':
            if st.button('Retry Shopify sync'):
                versions.kick(row['handle']);st.session_state.setdefault('edition-sync-watching',set()).add(row['handle'])
                st.session_state.pop('edition-sync-watch-until',None)
    if row.get('sync_error'):st.caption(sync_error_message(row['sync_error']))
    if st.session_state.get('edition-review-run')==row.get('edition_run_id') and row.get('edition_run_id'):
        try:
            data=versions.details(row['edition_run_id'])
            st.dataframe(data['allocations'],hide_index=True,width='stretch')
            with st.form('edition-reconcile'):
                reason=st.text_input('Reconciliation reason')
                st.caption('Repairs derived boundaries only. Issued numbers and recorded sales are preserved.')
                if st.form_submit_button('Reconcile existing release',disabled=actor().get('role')!='admin'):
                    versions.reconcile(row['handle'],row['edition_run_id'],actor().get('id'),reason)
                    st.session_state.setdefault('edition-sync-watching',set()).add(row['handle'])
                    st.session_state.pop('edition-sync-watch-until',None)
                    refresh_handle(row['handle']);st.success('Reconciled; Shopify sync pending.')
        except Exception as exc:st.error(str(exc))


@st.fragment
def table():
    ops._render_table()
    release_controls()
    restored={r['handle'] for r in st.session_state.get(ops.ROWS_KEY,[]) if r.get('run_status')=='pending_sync' or r.get('sync_status')=='Pending'}
    st.session_state.setdefault('edition-sync-watching',set()).update(restored)
    if st.session_state.get('edition-sync-watching'):sync_status()


@st.fragment
def advanced():
    with st.popover('Advanced',on_change='rerun',key='edition-advanced') as panel:
        if panel.open:
            backend=ops._configured_supabase_backend()
            rows=st.session_state.get(ops.ROWS_KEY,[])
            ops._render_pull_new_products_button(st,backend)
            ops._render_advanced_controls(backend,rows,inline=True)
            if backend:
                from edition_order_recovery import render
                render(backend,rows)


@st.fragment
def archive():
    with st.expander('Expired Editions',key='edition-expired',on_change='rerun') as panel:
        if not panel.open:return
        search=st.text_input('Search expired editions',key='edition-expired-search')
        if search!=st.session_state.get('edition-expired-applied'):
            st.session_state['edition-expired-applied']=search;st.session_state['edition-expired-page']=0
        page=st.session_state.get('edition-expired-page',0)
        try:
            rows=versions.archive(search,page*25,26)
            if not rows:st.caption('No expired editions.');return
            st.dataframe([{'Product':r['product_title'],'Version':r['edition_name'],'Last Number':r['last_allocated_number'],
                'Sold':r['sold_count'],'Expired Date':r['archived_at'],'Status':'EXPIRED'} for r in rows[:25]],hide_index=True,width='stretch')
            with st.container(horizontal=True):
                if st.button('Previous editions',disabled=page==0):st.session_state['edition-expired-page']=page-1;st.rerun(scope='fragment')
                st.caption('Page '+str(page+1))
                if st.button('Next editions',disabled=len(rows)<=25):st.session_state['edition-expired-page']=page+1;st.rerun(scope='fragment')
            selection=st.selectbox('Historical details',[None]+rows[:25],format_func=lambda r:'Choose version' if r is None else r['product_title']+' · '+r['edition_name'])
            if selection:
                st.caption(selection['retired_reason']);st.caption('Release '+str(selection['id']))
                st.link_button('Shopify product','https://www.sportscaveshop.com/products/'+selection['shopify_handle'])
                data=versions.details(selection['id'])
                st.dataframe(data['allocations'],hide_index=True);st.dataframe(data['audit'],hide_index=True)
        except Exception as exc:st.warning('Archive unavailable: '+str(exc))


@st.fragment(run_every=3)
def sync_status():
    handles=list(st.session_state.get('edition-sync-watching',set()))[:50]
    if not handles:
        verified=st.session_state.get('edition-sync-verified',set())
        if verified:st.caption(f'{len(verified)} editions verified in Shopify · 0 pending')
        return
    deadline=st.session_state.setdefault('edition-sync-watch-until',time.monotonic()+90)
    if time.monotonic()>deadline:
        st.caption('Sync continues in the background. Refresh the product to check its latest status.')
        return
    try:
        with versions.backend.connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT p.shopify_handle,p.product_title,p.metafields_sync_status,p.last_metafield_error,
              r.status,to_jsonb(r)->>'sync_error' AS version_error FROM edition_products p
              JOIN edition_runs r ON r.id=p.active_edition_run_id WHERE p.shopify_handle=ANY(%s)""",(handles,))
            rows=cur.fetchall()
        failed=[]
        verified=st.session_state.setdefault('edition-sync-verified',set())
        for r in rows:
            error=r.get('version_error') or r.get('last_metafield_error')
            if str(r['metafields_sync_status']).lower()=='synced' and r['status']!='pending_sync':
                refresh_handle(r['shopify_handle'])
                st.session_state['edition-sync-watching'].discard(r['shopify_handle'])
                verified.add(r['shopify_handle'])
            elif error:
                failed.append((r['product_title'],sync_error_message(error)))
        pending=max(0,len(st.session_state['edition-sync-watching'])-len(failed))
        st.caption(f'{len(verified)} editions verified in Shopify · {pending} pending · {len(failed)} require attention')
        if failed:
            with st.expander('Shopify sync details'):
                for title,error in failed:st.caption(title+' — '+error)
    except Exception:
        logging.getLogger(__name__).exception('Edition sync status unavailable')
        st.caption('Sync status unavailable. Saved values are retained; retry when connectivity is restored.')


def workspace():
    ops._ensure_state()
    st.html(STYLE)
    with st.container(key='edition-workspace'):
        table()
        archive()
        from design_tracking_page import render
        render()
