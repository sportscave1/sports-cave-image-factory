"""Native Edition Ops editor integration; status updates do not alter edit state."""
from pathlib import Path
from urllib.parse import quote
import auto_editions_status as status
import psd_directory

CACHE='edition-auto-status-cache'
IDS='edition-auto-status-ids'
EVENT='edition-auto-status-event'


def snapshot(ui,backend,rows,*,force=False):
    ids=list(dict.fromkeys(pid for r in rows if (pid:=psd_directory.product_id(r))))
    user=ui.session_state.get('sports_cave_current_user') or {}
    # Streamlit component events affect display only and are server-signed.
    event=ui.session_state.get('edition-auto-live')
    if isinstance(event,dict) and event.get('nonce')!=ui.session_state.get(EVENT):
        from auto_editions_bulk import SORTS
        if event.get('sort') in SORTS:ui.session_state['edition-auto-sort']=event['sort']
        verified=status.verify_snapshot(event,user,ids)
        if verified is not None:
            ui.session_state[CACHE]=verified;ui.session_state[IDS]=ids
        elif event.get('unavailable') or (isinstance(event.get('rows'),list) and
                {r.get('product_gid') for r in event['rows'] if isinstance(r,dict)}==set(ids)):
            ui.session_state[CACHE]={pid:status.unavailable(pid) for pid in ids};ui.session_state[IDS]=ids
        ui.session_state[EVENT]=event.get('nonce')
    if force or ui.session_state.get(IDS)!=ids or CACHE not in ui.session_state:
        try:
            if not backend:raise RuntimeError('No authoritative database')
            data=status.review_operations(backend.connect,status.batch(backend.connect,ids,writable=status.can_write(user)))
            values={r['product_gid']:r for r in data['rows']}
        except Exception:values={pid:status.unavailable(pid) for pid in ids}
        ui.session_state[CACHE]=values;ui.session_state[IDS]=ids
    return ui.session_state[CACHE]


def link(row,values):
    pid=psd_directory.product_id(row)
    value=values.get(pid,status.unavailable(pid))
    label=(value.get('review_operation') or {}).get('label') or (chr(9989)+' ' if value['status']=='Cloud Ready' else '')+('Needs Review' if value['status']=='Review' else value['status'])
    return '/auto-editions/status?product_gid='+quote(pid,safe='')+'#'+label if pid else ''


def live(ui,rows,values):
    if getattr(ui,'__name__','')!='streamlit':return
    import streamlit.components.v1 as components
    component=components.declare_component('edition_auto_live',path=str(Path(__file__).parent/'components/edition_auto_status'))
    ids=list(dict.fromkeys(pid for r in rows if (pid:=psd_directory.product_id(r))))
    component(technical_only=__import__('auto_editions_technical').enabled(),product_gids=ids,rows=[values.get(pid,status.unavailable(pid)) for pid in ids],key='edition-auto-live',default=None)
