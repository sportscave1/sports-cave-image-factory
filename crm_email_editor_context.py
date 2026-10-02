"""Explicit editor ownership for the shared Campaign / Automation composer."""


def editor_key(state):
    return 'automation_editor' if state.get('email_editor_mode')=='automation' else 'campaign_editor'


def current(state, fallback=None):
    return state.get(editor_key(state),fallback)


def saved_key(state):
    return 'automation_saved' if state.get('email_editor_mode')=='automation' else 'campaign_saved'


def flush_automation(state,*,force=False):
    from copy import deepcopy
    from crm_store import StoreUnavailable
    editor=state.get('automation_editor');context=state.get('automation_editor_context')
    if not editor or not context:return True
    store,user=context;saved=state.get('automation_saved') or {}
    if not force and editor.get('document')==saved.get('document') and editor.get('name')==saved.get('name'):return True
    try:
        updated=store.save(user,editor['name'],editor['document'],editor['id'],editor['version'])
        editor.update(updated);state['automation_saved']=deepcopy(editor)
        state['campaign_save_status']='Saved';state.pop('campaign_save_error',None)
        return True
    except (ValueError,StoreUnavailable,PermissionError) as exc:
        state['campaign_save_status']='Save failed';state['campaign_save_error']=str(exc)
        return False
