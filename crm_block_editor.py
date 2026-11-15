"""Small sortable component; events are validated against the current draft order."""
from copy import deepcopy
from pathlib import Path
from crm_email_blocks import KINDS, block, duplicate_block, validate_blocks


def apply_event(blocks, event):
    validate_blocks(blocks)
    if not isinstance(event,dict) or event.get('base')!=[b['id'] for b in blocks]:
        raise ValueError('The block list changed. Try the action again.')
    result=deepcopy(blocks);kind=event.get('type');selected=event.get('id')
    if kind=='order':
        ids=event.get('ids')
        if not isinstance(ids,list) or len(ids)!=len(result) or set(ids)!={b['id'] for b in result}:raise ValueError('Invalid block order.')
        lookup={b['id']:b for b in result};result=[lookup[i] for i in ids]
    elif kind=='add':
        index=event.get('index')
        if event.get('kind') not in KINDS or type(index) is not int or not 0<=index<=len(result):raise ValueError('Invalid new block.')
        new=block(event['kind']);result.insert(index,new);selected=new['id']
    elif kind in ('select','copy','delete'):
        if selected not in [b['id'] for b in result]:raise ValueError('Unknown block.')
        index=next(i for i,b in enumerate(result) if b['id']==selected)
        if kind=='copy':
            new=duplicate_block(result[index]);result.insert(index+1,new);selected=new['id']
        if kind=='delete':result.pop(index);selected=None
    else:raise ValueError('Unknown block action.')
    validate_blocks(result)
    return result,selected


def sortable(doc,key):
    import streamlit as st
    import streamlit.components.v1 as components
    component=components.declare_component('crm_sortable_blocks_v2',path=str(Path(__file__).parent/'components'/'crm_blocks'))
    blocks=doc.setdefault('blocks',[])
    selected=st.session_state.get(key+'selected')
    event=component(blocks=blocks,kinds=list(KINDS),selected=selected,key=key+'sortable',default=None)
    if event and event.get('event')!=st.session_state.get(key+'handled'):
        st.session_state[key+'handled']=event.get('event')
        try:
            doc['blocks'],selected=apply_event(blocks,event)
            st.session_state[key+'selected']=selected
            if event.get('type')!='select':doc['copy_reviewed']=False;st.session_state[key+'review']=False
            st.rerun()
        except ValueError as exc:st.warning(str(exc))
    return next((i for i,b in enumerate(blocks) if b['id']==selected),0)
