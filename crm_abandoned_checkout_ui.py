from crm_abandoned_checkout import dynamic,preview_context,apply_template,TEMPLATE

def live_control(store,editor,key,cfg):
    import streamlit as st
    if st.button('Live preview',key=key+'live_preview'):
        if dynamic(editor['document']):preview_context(st.session_state,store.preview_shop,refresh=True)
        live_dialog(store,editor['document'],key,cfg)


def live_dialog(store,doc,key,cfg):
    import streamlit as st
    @st.dialog('Live preview',width='large')
    def show():
        automation_canvas(doc,cfg,key+'live_',store,live=True)
    show()


def automation_canvas(doc,cfg,key,store,*,live=False):
    if live:_live_canvas(doc,cfg,key,store)
    elif dynamic(doc):_dynamic_canvas(doc,cfg,key,store)
    else:
        from crm_html_workspace import _campaign_canvas
        _campaign_canvas(doc,cfg,key,store)


import streamlit as st


@st.fragment(run_every='3s')
def _dynamic_canvas(doc,cfg,key,store):
    from crm_html_workspace import _composer_canvas
    from crm_email_editor_context import current
    editor=current(st.session_state,{})
    _composer_canvas(editor.get('document',doc),cfg,key,store)


@st.fragment(run_every='3s')
def _live_canvas(doc,cfg,key,store):
    from crm_html_workspace import _composer_canvas
    _composer_canvas(doc,cfg,key,store,live=True)


def template_control(editor,key):
    import streamlit as st
    context_pair=st.session_state.get('automation_editor_context')
    if not context_pair:return
    store,_=context_pair
    if store.flow(editor['id'])['config']['draft']['trigger']!='abandoned':return
    st.markdown('**'+TEMPLATE+'**')
    if st.button('Use Abandoned Checkout template',key=key+'checkout_template'):
        apply_template(editor['document']);st.rerun()
