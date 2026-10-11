"""Compact image configuration inside the existing composer."""
from copy import deepcopy
import json
import uuid
import streamlit as st
from crm_collector_images import SOURCES,MARKER,marker,settings,validate


def control(doc,key,shop,store):
    # No visual or behavioural change to Abandoned Cart or other composers.
    if getattr(store,'preview_trigger',None) not in ('welcome','post_purchase','win_back'):return
    from crm_middle_sections import middle_sections,commit_middle
    from crm_catalogue import Catalogue
    parts=middle_sections(doc)
    choices={}
    for part in parts:
        for index,match in enumerate(MARKER.finditer(part.get('html',''))):
            choices[part['id']+':'+str(index)]=(part,index,json.loads(bytes.fromhex(match[1]).decode()))
    with st.container(key='crm-personalise-image'),st.expander('Personalise Image',icon=':material/image:'):
        chosen=st.selectbox('Image block',['new',*choices],format_func=lambda x:'Add image block' if x=='new' else (choices[x][0].get('name') or 'Image')+' · '+str(choices[x][1]+1),key=key+'collector_block')
        original=choices[chosen][2] if chosen!='new' else settings()
        widget=key+'collector_'+chosen+'_'
        source=st.selectbox('Source',SOURCES,index=SOURCES.index(original['source']),key=widget+'source')
        cfg=deepcopy(original);cfg['source']=source
        if source not in ('No Image','Static Selected Image'):
            cfg['count']=st.selectbox('Products',list(range(1,3 if source=='Actual Purchased Product' else 4)),index=min(original['count'],2 if source=='Actual Purchased Product' else 3)-1,key=widget+'count')
        if source=='Static Selected Image':
            cfg['image']=st.text_input('Selected image URL',original['image'],key=widget+'image')
            cfg['alt']=st.text_input('Image description',original['alt'],key=widget+'alt')
        elif source not in ('No Image','Actual Purchased Product'):
            catalogue=Catalogue(shop,connect=store.connect,edition_reader=lambda **_:[])
            query=st.text_input('Find artwork',key=widget+'query')
            if st.button('Search artwork',key=widget+'search'):
                try:st.session_state[widget+'results']=catalogue.search(query)['rows']
                except Exception:st.warning('Catalogue unavailable. Existing selection is retained.')
            rows=st.session_state.get(widget+'results',[])
            labels={p['id']:p['title'] for p in rows}
            for identity in original['product_ids']:labels.setdefault(identity,'Selected artwork '+identity.rsplit('/',1)[-1])
            cfg['product_ids']=st.multiselect('Approved artwork',list(labels),default=original['product_ids'],format_func=lambda i:labels[i],max_selections=12,key=widget+'products')
            if st.button('Choose collection',key=widget+'load_collections'):
                try:st.session_state[widget+'collections']=catalogue.collections()['rows']
                except Exception:st.warning('Collections unavailable. Existing selection is retained.')
            collections={r['id']:r['title'] for r in st.session_state.get(widget+'collections',[])}
            if original['collection_id']:collections.setdefault(original['collection_id'],'Selected collection')
            cfg['collection_id']=st.selectbox('Approved collection',['',*collections],index=(['',*collections].index(original['collection_id'])),format_func=lambda i:collections.get(i,'No collection selected'),key=widget+'collection')
            if source=='Verified Bestsellers':st.caption('Requires a collection. Uses its current Shopify best-selling order, filtered for availability and relevance.')
            elif source=='Verified New Releases':st.caption('Only verified products created within the last 30 days are eligible.')
            st.caption('Owned, unavailable and unrelated artworks are excluded. With no approved selection or known preference, only the collection link remains.')
        if st.button('Apply image settings',key=widget+'apply',type='primary'):
            try:
                encoded=marker(validate(cfg));updated=deepcopy(parts)
                if chosen=='new':updated.append(dict(id=uuid.uuid4().hex,type='image',name='Personalised artwork',visible=True,html=encoded))
                else:
                    part,index,_=choices[chosen];target=next(p for p in updated if p['id']==part['id'])
                    matches=list(MARKER.finditer(target['html']));match=matches[index]
                    target['html']=target['html'][:match.start()]+encoded+target['html'][match.end():]
                commit_middle(doc,updated)
                from crm_section_ui import rerun_editor
                rerun_editor()
            except ValueError as exc:st.warning(str(exc))
