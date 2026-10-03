"""Session-only automation visual output; never a live delivery decision."""
import hashlib
import json


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest()


def output(state,store,doc,cfg,identity=None):
    from crm_email_size import render_production,analyze_rendered_email
    # render_settings already carries defaults; don't read them twice per render.
    if 'email_defaults' not in cfg:cfg={**cfg,'email_defaults':store.default_sections(cfg)}
    hydrated,label=store.preview_document(doc)
    token=digest([hydrated,cfg,identity])
    cache=state.get('_automation_visual_output')
    if not cache or cache['token']!=token:
        message=render_production(hydrated,cfg,identity)
        cache={'token':token,'message':message,'size':analyze_rendered_email(message['html'],message['text'])}
        state['_automation_visual_output']=cache
    return cache,label,getattr(store,'preview_warning','')
