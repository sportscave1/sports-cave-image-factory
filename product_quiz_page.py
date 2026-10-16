"""Developer → Product Quiz. No Shopify installation or storefront writes."""
from copy import deepcopy
import json
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
from product_quiz import DEFAULT,validate,public_product,digest
from product_quiz_store import QuizStore
from product_quiz_publish import Assets,publish,revert,sync,snippets,asset_base,verify_public


def edit_records(rows, columns, **kwargs):
    import pandas as pd
    return st.data_editor(pd.DataFrame(rows, columns=columns), **kwargs).to_dict('records')


def pairs(mapping): return [{'Value':k,'Maps to':v} for k,v in mapping.items()]


def reload_draft():
    for name in list(st.session_state):
        if name=='product-quiz-edit' or name.startswith('pq-'):
            del st.session_state[name]


def preview_html(config,products):
    """Self-contained, network-free preview with explicit synthetic commerce facts."""
    payload={'config':validate(config),'preview':{'products':products,'catalogue':{'sports':{s:'preview' for p in products for s in p['sports']}}},'manifest':{'version':digest(config)}}
    encoded=json.dumps(payload).replace('<','\\u003c')
    runtime=(Path(__file__).parent/'static/product-quiz/runtime.js').read_text(encoding='utf-8')
    return '<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0;background:#0b0b0c"><div id="quiz"></div><script>'+runtime+'</script><script>const data='+encoded+';const host=document.querySelector("#quiz");const shadow=host.attachShadow({mode:"open"});const launcher=document.createElement("button");SportsCaveQuizRuntime.mount({host,shadow,launcher,base:"",mode:"inline",...data});</script></body></html>'


def render_page(user,store=None):
    import os_accounts
    if not os_accounts.can_access_page(user,'Product Quiz'):
        st.error('Access not approved');return
    st.title('Product Quiz')
    st.caption('Developer · Find your edition · Manual Shopify installation')
    store=store or QuizStore()
    try: draft=store.draft();status=store.get_state('catalogue_status',{})
    except Exception:
        st.error('Quiz persistence is unavailable. Existing published embeds are independent of this editor.');return
    state_key='product-quiz-edit'
    if state_key not in st.session_state: st.session_state[state_key]=deepcopy(draft)
    editing=st.session_state[state_key];config=deepcopy(editing['config'])
    questions,matching,catalogue,appearance,publication,analytics,installation=st.tabs(['Questions & answers','Matching rules','Catalogue','Appearance','Preview & publish','Analytics','Install'])
    with questions:
        order=st.selectbox('Question order',['Sport → Subject → Preference','Sport → Preference → Subject'],index=0 if config['questions'][1]['id']=='subject' else 1)
        lookup={q['id']:q for q in config['questions']}
        config['questions']=[lookup[k] for k in (('sport','subject','preference') if order.startswith('Sport → Subject') else ('sport','preference','subject'))]
        st.caption('Choices are generated from eligible editions. Overrides rename or hide an existing choice; they never invent a catalogue match. A preference question is skipped unless it separates editions.')
        for q in config['questions']:
            with st.expander(q['id'].title(),expanded=q['id']=='sport'):
                q['enabled']=st.checkbox('Enabled',q['enabled'],key='pq-enabled-'+q['id'],disabled=q['id']=='sport')
                q['label']=st.text_input('Question',q['label'],max_chars=120,key='pq-label-'+q['id'])
                field={'sport':'sports','subject':'subjects','preference':'preferences'}[q['id']]
                values=sorted({v for p in status.get('products',[]) if p['status']=='Eligible' for v in p[field]})
                st.caption('Current catalogue choices: '+(', '.join(values) or 'Reconcile the catalogue first'))
                q['answers']=edit_records(q['answers'],['value','label','enabled'],num_rows='dynamic',key='pq-answers-'+q['id'],column_config={'value':st.column_config.TextColumn('Catalogue value'),'label':st.column_config.TextColumn('Display label'),'enabled':st.column_config.CheckboxColumn('Enabled',default=True)})
    with matching:
        config['rules']['max_results']=st.slider('Maximum editions',1,3,config['rules']['max_results'])
        config['rules']['allow_broader']=st.checkbox('Offer another preference within the selected sport and athlete/team',config['rules']['allow_broader'])
        st.caption('Explicit sport and athlete/team choices always constrain results. Featured preference only orders relevant matches. Broader preferences are labelled.')
        st.write('Canonical aliases')
        alias_rows=edit_records(pairs(config['aliases']),['Value','Maps to'],num_rows='dynamic',key='pq-aliases')
        config['aliases']={r['Value']:r['Maps to'] for r in alias_rows if r.get('Value') and r.get('Maps to')}
    with catalogue:
        st.caption('Last successful quiz sync: '+str(status.get('last_success') or 'Never')+' · Eligibility is rechecked in the shopper’s market before results.')
        if status.get('error'): st.warning(status['error'])
        rows=status.get('products',[])
        counts={s:sum(p['status']==s for p in rows) for s in ('Eligible','Needs details','Excluded')}
        st.write(' · '.join(f'{label}: {count}' for label,count in counts.items()))
        if rows: st.dataframe([{k:p.get(k) for k in ('id','title','sports','subjects','status','reason')} for p in rows],hide_index=True,use_container_width=True)
        classification=store.get_state('classification',{'aliases':{},'overrides':{}})
        if rows:
            pid=st.selectbox('Correct an edition',[p['id'] for p in rows],format_func=lambda v:next(p['title'] for p in rows if p['id']==v))
            existing=classification['overrides'].get(pid,{})
            with st.form('pq-override-'+pid):
                st.caption('Enter verified classifications only. Comma-separated lists support rivalry and multi-athlete editions. Empty fields preserve automatic classification.')
                sports=st.text_input('Sports',', '.join(existing.get('sports',[])))
                subjects=st.text_input('Athletes / teams / drivers',', '.join(existing.get('subjects',[])))
                prefs=st.text_input('Moments / eras / styles',', '.join(existing.get('preferences',[])))
                excluded=st.checkbox('Exclude from quiz',bool(existing.get('excluded')))
                reason=st.text_input('Exclusion reason',existing.get('reason',''))
                featured=st.slider('Relevant-match preference',0,3,int(existing.get('featured',0)))
                if st.form_submit_button('Save classification'):
                    override={'excluded':excluded,'reason':reason[:300],'featured':featured}
                    for k,v in (('sports',sports),('subjects',subjects),('preferences',prefs)):
                        if v.strip(): override[k]=[x.strip()[:120] for x in v.split(',') if x.strip()]
                    with store.lock():
                        latest=store.get_state('classification',{'aliases':{},'overrides':{}})
                        latest['overrides'][pid]=override;store.put_state('classification',latest)
                    st.success('Classification saved. Reconcile to update public catalogue.')
        if st.button('Reconcile catalogue from existing mirror'):
            try: sync(store,Assets());st.rerun()
            except Exception: st.error('Catalogue refresh failed; the last published catalogue remains in place.')
    with appearance:
        for name in ('title','intro'): config['appearance'][name]=st.text_input(name.title(),config['appearance'][name],max_chars=160)
        cols=st.columns(3)
        for col,name in zip(cols,('accent','background','text')): config['appearance'][name]=col.color_picker(name.title(),config['appearance'][name])
    with analytics:
        st.caption('Last 30 days · consented anonymous browser events · duplicate event IDs ignored · events retained for 90 days. No customer identity or answer text is collected.')
        if st.button('Load quiz analytics'):
            try: st.dataframe(store.report(),hide_index=True,use_container_width=True)
            except Exception: st.warning('Analytics is temporarily unavailable.')
        st.info('Starts, shown questions, answers, completions and product clicks are measured when analytics consent is available. Compare distinct sessions by question to assess drop-off. Add-to-cart, purchases and revenue attribution are unavailable in this first version. Intended purchase attribution window: 7 days, currently inactive. No incremental revenue claim is made.')
    with installation:
        st.write('Manual installation only')
        st.caption('These controls never edit a Shopify theme or create a storefront page. Snippets become installable only after approved deployment, public R2/CORS setup and a successful quiz publication.')
        st.write('Collection context mappings')
        st.caption('Map an exact existing collection handle to its verified sport. Customers can change the preselected sport.')
        mapping_rows=edit_records(pairs(config['collections']),['Value','Maps to'],num_rows='dynamic',key='pq-collections')
        config['collections']={r['Value']:r['Maps to'] for r in mapping_rows if r.get('Value') and r.get('Maps to')}
        if st.button('Verify public installation assets'):
            try:
                base=asset_base();published=verify_public(Assets())
                st.session_state['product-quiz-installation']={'base':base,'published':published}
            except Exception:
                st.session_state.pop('product-quiz-installation',None)
                st.error('Public delivery could not be verified. Check publication, CDN and CORS settings.')
        installation_state=st.session_state.get('product-quiz-installation')
        if installation_state:
            st.caption('Verified published version: '+installation_state['published']['version'])
            selected_collection=st.selectbox('Optional verified collection context',['']+list(config['collections']))
            for name,code in snippets(installation_state['base'],selected_collection).items(): st.write(name);st.code(code,language='html')
        else: st.warning('No verified published installation URL is available in this environment. No placeholder is presented as working code.')
        st.markdown('1. In Shopify → Online Store → Themes → Customize, open the desired collection template and add a **Custom Liquid** block. Paste the collection-button snippet.\n2. For the full page, manually create **Find Your Edition**, with handle `find-your-edition`. Open its page template in Customize and add the inline snippet in a Custom Liquid block.\n3. Use a dedicated page template if this quiz should appear on that page only. A Custom HTML block is suitable only if it allows scripts.\n4. Save/publish the Shopify placement yourself. Future OS publications keep the snippet stable. No email or automation changes are required.')
    with publication:
        st.caption('Draft edits do not change the live quiz. Publish creates immutable configuration/assets and switches one public pointer. Revert restores the previous working configuration.')
        st.button('Reload saved draft',on_click=reload_draft)
        if st.button('Save draft'):
            try:
                result=store.save(config,editing['revision']);st.session_state[state_key]=deepcopy(result)
                st.success('Draft saved. Published quiz unchanged.')
            except ValueError as exc: st.error(str(exc))
        eligible=[public_product(p) for p in rows if p['status']=='Eligible']
        if eligible:
            try: components.html(preview_html(config,eligible),height=720,scrolling=True)
            except ValueError as exc: st.error(str(exc))
        else: st.info('Reconcile eligible products to preview your catalogue. The standalone synthetic harness is available for local verification.')
        confirm=st.checkbox('I have reviewed this draft and its catalogue')
        if st.button('Publish quiz',disabled=not confirm):
            try:
                # Save exactly the visible configuration before publishing that same revision.
                saved=store.save(config,editing['revision']);st.session_state[state_key]=deepcopy(saved)
                assets=Assets();result=publish(store,assets,saved['config'],expected_revision=saved['revision'])
                st.success('Published version '+result['version'])
            except Exception: st.error('Publication was not confirmed. Check the published pointer before retrying; do not replace the Shopify snippet.')
        if st.button('Revert published configuration',disabled=not confirm):
            try: revert(store,Assets());st.success('Previous published configuration restored.')
            except Exception: st.error('Revert was not confirmed. Check storage availability before retrying.')
