"""Lightweight wrapper for the existing copy iframe; preflight precedes copying."""
from functools import lru_cache
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).parent / 'ui_components' / 'prompt_copy'


@lru_cache(maxsize=1)
def clipboard_script():
    return ROOT.joinpath('clipboard.js').read_text(encoding='utf-8')


def copy_prompt(prompt, key, *, label='Copy prompt', revalidate=None, success='✓ Prompt copied'):
    component=components.declare_component('crm_prompt_copy',path=str(ROOT))
    state=st.session_state.setdefault(key+'state',{})
    event=component(prompt_text=state.get('prepared','') if revalidate else (prompt or ''),
        label=label,success_label=success,disabled=not bool(prompt),compact=True,
        validation_mode=bool(revalidate),response_id=state.get('response_id'),
        default=None,key=key)
    if not isinstance(event,dict):return None
    if event.get('type')=='prepare' and event.get('event')!=state.get('handled'):
        state['handled']=event['event']
        state['prepared']=revalidate()
        state['response_id']=event['event']
        st.rerun(scope='fragment')
    if event.get('type') in ('copied','failed'):
        state.pop('response_id',None);state.pop('prepared',None)
        return event['type']
    return None
