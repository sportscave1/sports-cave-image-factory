"""Explicit editor ownership for the shared Campaign / Automation composer."""


def editor_key(state):
    return 'automation_editor' if state.get('email_editor_mode')=='automation' else 'campaign_editor'


def current(state, fallback=None):
    return state.get(editor_key(state),fallback)


def saved_key(state):
    return 'automation_saved' if state.get('email_editor_mode')=='automation' else 'campaign_saved'


def editable_document(doc):
    """Lossless editor representation; callers take their baseline afterwards."""
    from crm_html_workspace import html_document
    result=html_document(doc)
    if any(s.get('type')=='abandoned_checkout_products' for s in result.get('middle_sections',[])):
        from crm_checkout_section import editable
        result=editable(result)
    return result


def mark_content_edit(state,editor):
    """Invalidate review for authored edits; an exact undo restores its baseline.

    Call only for authored content events, never the explicit review checkbox.
    HTML, whitespace, section settings/order and every other document field are
    compared byte-for-byte; only the derived review flag is excluded.
    """
    saved=state.get(saved_key(state),{})
    doc=editor['document'];prior=saved.get('document',{})
    unchanged=editor.get('name')==saved.get('name') and {k:v for k,v in doc.items() if k!='copy_reviewed'}=={k:v for k,v in prior.items() if k!='copy_reviewed'}
    doc['copy_reviewed']=prior.get('copy_reviewed',False) if unchanged else False


def flush_automation(state,*,force=False):
    from copy import deepcopy
    from crm_store import StoreUnavailable
    editor=state.get('automation_editor');context=state.get('automation_editor_context')
    if not editor or not context:return True
    store,user=context;saved=state.get('automation_saved') or {}
    # Force means flush pending edits, never manufacture a save for a clean view.
    if editor.get('document')==saved.get('document') and editor.get('name')==saved.get('name'):return True
    try:
        updated=store.save(user,editor['name'],editor['document'],editor['id'],editor['version'])
        updated['document']=editable_document(updated['document'])
        editor.update(updated);state['automation_saved']=deepcopy(editor)
        state['campaign_save_status']='Saved';state.pop('campaign_save_error',None)
        return True
    except (ValueError,StoreUnavailable,PermissionError) as exc:
        state['campaign_save_status']='Save failed';state['campaign_save_error']=str(exc)
        return False
