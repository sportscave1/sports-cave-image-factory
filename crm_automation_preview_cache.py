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
    from crm_smart_catalogue import enabled as smart_enabled,preview as smart_preview
    if getattr(store,'preview_trigger',None)=='abandoned' and smart_enabled(hydrated):
        hydrated=smart_preview(state,store,store.preview_shop,hydrated)
    token=digest([hydrated,cfg,identity])
    trigger=getattr(store,'preview_trigger',None)
    lifecycle=getattr(store,'email_mode',None)=='automation' and isinstance(trigger,str) and trigger!='abandoned'
    slot='_automation_lifecycle_visual_outputs' if lifecycle else '_automation_visual_outputs'
    entries=state.get(slot,{})
    cache=entries.get(token)
    if cache is None:
        message=render_production(hydrated,cfg,identity)
        from crm_recovery_links import inspect,sources,checkout_url,verify
        recovery=[url for source in sources(hydrated) for url in inspect(source).urls if checkout_url(url)]
        if recovery:verify(message,recovery[0],len(recovery))
        cache={'token':token,'html_hash':hashlib.sha256(message['html'].encode('utf-8')).hexdigest(),'message':message,'size':analyze_rendered_email(message['html'],message['text'])}
        from crm_personalisation import present
        if present(doc):cache['personalised_headers']={k:hydrated['content'][k] for k in ('subject','preheader')}
        entries={**entries,token:cache}
        if len(entries)>(16 if lifecycle else 4):entries.pop(next(iter(entries)))
        state[slot]=entries
    if lifecycle:
        # Share this exact resolved document with the visual section compiler.
        # It is display-only and never replaces authored or published content.
        cache['document']=hydrated
    return cache,label,getattr(store,'preview_warning','')
