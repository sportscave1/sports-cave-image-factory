"""Campaign-scoped manual ChatGPT helper; no editor writes or send actions."""
from copy import deepcopy
from html import escape
import json
import logging
import uuid
import streamlit as st
from crm_campaign_prompt import HELP, PURPOSES, STOCK, OFFERS, DEADLINES, EVENTS, CONFIRMED, hint, build, fingerprint


@st.fragment
def prompt_control(shop, editor, key):
    with st.container(horizontal=True,horizontal_alignment='right',gap='small',key='crm-autofill-trigger'):
        opened=st.button('Auto fill prompt',type='tertiary',key=key+'prompt_open')
        with st.popover('?',help='How Auto fill prompt works',key=key+'prompt_help'):
            st.write(HELP)
    st.html('''<style>
    .st-key-crm-autofill-trigger{gap:4px;min-height:28px;margin-top:-8px}
    .st-key-crm-autofill-trigger button{font-size:12px!important;min-height:28px!important;padding:2px 6px!important;background:transparent!important;border:0!important}
    .st-key-crm-autofill-trigger button p{font-size:12px!important}
    </style><script>(()=>{
      if(window.scPromptScrollGuard)return;window.scPromptScrollGuard=true;
      let anchor=null,wasOpen=false;
      document.addEventListener('click',event=>{
        const button=event.target.closest('.st-key-crm-autofill-trigger button');
        if(button?.textContent.trim()!=='Auto fill prompt')return;
        anchor={button,positions:[...document.querySelectorAll('[data-testid="stMain"],[data-testid="stSidebarContent"],.st-key-crm-composer-controls')].map(e=>[e,e.scrollTop,e.scrollLeft])};
      },true);
      const restore=()=>{anchor?.positions.forEach(([e,y,x])=>{if(e.isConnected){e.scrollTop=y;e.scrollLeft=x;}});};
      new MutationObserver(()=>{
        const open=!!document.querySelector('[role="dialog"] .st-key-crm-autofill-body');
        if(open===wasOpen)return;wasOpen=open;if(!anchor)return;
        restore();requestAnimationFrame(restore);
        if(!open)anchor.button?.focus({preventScroll:true});
      }).observe(document.body,{childList:true,subtree:true});
    })();</script>''',unsafe_allow_javascript=True)
    if opened:
        state=st.session_state.setdefault(key+'prompt_helper',{})
        if (state.get('ready') or {}).get('sensitive'):state.pop('ready',None)
        prompt_dialog(shop,editor,key+'prompt_helper_')


def picker(reader, kind, key):
    query=st.text_input('Search editions' if kind=='Single product' else 'Select or type a collection',key=key+'query',max_chars=150,
                        placeholder='Title, handle or SKU' if kind=='Single product' else 'Collection name')
    state=st.session_state.setdefault(key+'selection',{})
    if state.get('query')!=query:
        state.clear();state.update(query=query,offset=0,cursors=[None])
        st.session_state[key+'selected']=None
    # Opening the popup does no catalogue work. Mode/search interaction loads a
    # single bounded page. Native dialog reruns are serial; no background replies.
    try:
        if kind=='Single product':page=reader.products(query,state.get('offset',0))
        else:page=reader.collections(query,state.get('cursors',[None])[-1])
        rows=page['rows']
    except Exception as exc:
        logging.getLogger(__name__).warning('campaign_prompt_picker_unavailable type=%s',type(exc).__name__)
        st.caption('Options unavailable. Retry, or use a typed collection name.')
        rows=[];page={'more':False}
    options={r['id']:r for r in rows if r.get('id')}
    previous=st.session_state.get(key+'selected')
    if previous and previous.get('id'):options.setdefault(previous['id'],previous)
    counts={r['title']:sum(v['title']==r['title'] for v in options.values()) for r in options.values()}
    identity=st.selectbox('Select edition' if kind=='Single product' else 'Matching collections',list(options),index=None,
                          format_func=lambda i:options[i]['title']+(' · '+(options[i].get('handle') or i.rsplit('/',1)[-1]) if counts[options[i]['title']]>1 else ''),
                          key=key+'pick_'+str(state.get('offset',0))+'_'+str(len(state.get('cursors',[])))+'_'+query+'_'+str(state.get('choice_epoch',0)))
    if identity:st.session_state[key+'selected']=deepcopy(options[identity])
    if not rows:st.caption('No matching results.' if 'rows' in page else 'No cached options.')
    back=state.get('offset',0)>0 if kind=='Single product' else len(state.get('cursors',[None]))>1
    if back or page.get('more'):
        a,b=st.columns(2)
        if a.button('Previous',disabled=not back,key=key+'previous'):
            if kind=='Single product':state['offset']-=8
            else:state['cursors'].pop()
            st.rerun(scope='fragment')
        if b.button('Next',disabled=not page.get('more'),key=key+'next'):
            if kind=='Single product':state['offset']=state.get('offset',0)+8
            else:
                cursor=page.get('cursor')
                if not cursor or cursor in state['cursors']:st.error('Pagination unavailable. Retry.');return None
                state['cursors'].append(cursor)
            st.rerun(scope='fragment')
    if 'rows' not in page:st.button('Retry',key=key+'retry')
    if kind=='Collection' and query.strip():
        if st.button('Use “'+query.strip()+'”',key=key+'manual'):
            st.session_state[key+'selected']={'source':'manual','title':query.strip()}
            # Old selectbox value must not restore the former canonical identity.
            state['manual']=True
            state['choice_epoch']=state.get('choice_epoch',0)+1
            st.rerun(scope='fragment')
        elif identity:state['manual']=False
    chosen=st.session_state.get(key+'selected')
    if chosen and chosen.get('source')=='manual':st.caption('Using: '+chosen['title']+' · manual')
    return chosen


def copy_result(value):
    # Native click has already revalidated context and fresh ledger facts. No
    # draft mutation. Clipboard denial reveals read-only selectable text.
    payload=json.dumps(value,ensure_ascii=True).replace('<','\\u003c')
    st.html('''<div id="crm-prompt-copy-result" role="status">Copying…</div>
    <textarea id="crm-prompt-copy-fallback" aria-label="Manual copy prompt" readonly hidden style="width:100%;height:120px"></textarea>
    <script>(()=>{const text='''+payload+''';
      const status=document.getElementById('crm-prompt-copy-result');
      const fallback=document.getElementById('crm-prompt-copy-fallback');
      const fail=()=>{status.textContent='Clipboard unavailable. Select and copy the text below.';fallback.hidden=false;fallback.value=text;};
      if(!navigator.clipboard?.writeText){fail();return;}
      navigator.clipboard.writeText(text).then(()=>{status.textContent='Copied';}).catch(fail);
    })();</script>'''.replace('<script>','<script>/* '+uuid.uuid4().hex+' */'),unsafe_allow_javascript=True)


@st.dialog('Auto fill prompt',width='small',on_dismiss='ignore')
def prompt_dialog(shop,editor,key):
    # Native dialog supplies focus containment, Escape and X. No page rerun.
    state=st.session_state.setdefault(key.rstrip('_'),{})
    st.html('''<style>
    [role="dialog"]:has(.st-key-crm-autofill-body){width:min(490px,calc(100vw - 32px));max-height:calc(100dvh - 96px);overflow:auto;margin:16px auto!important;box-sizing:border-box}
    .st-key-crm-autofill-body,.st-key-crm-autofill-body [data-testid="stVerticalBlock"]{gap:6px!important}
    .st-key-crm-autofill-body label p{font-size:13px}
    .st-key-crm-autofill-body button{min-height:30px}
    .st-key-crm-autofill-body button[kind="primary"]{background:#242424;border-color:#242424;color:#fff}
    .st-key-crm-autofill-body button[kind="segmented_controlActive"]{color:#242424;border-color:#b49450;background:#f2eddf}
    .st-key-crm-autofill-body button:focus-visible,.st-key-crm-autofill-body input:focus-visible{outline:2px solid #b49450;outline-offset:2px}
    </style>''')
    with st.container(key='crm-autofill-body'):
        kind=st.segmented_control('What are you promoting?',('Single product','Collection'),key=key+'kind')
        if kind!=state.get('kind'):
            state.pop('ready',None);state['kind']=kind
            # Keep per-mode widget state, but no implicit cross-target facts.
        from crm_prompt_readers import PromptReader
        target=None;reader=None
        if kind:
            reader=PromptReader(shop)
            target=picker(reader,kind,key+kind)
        purpose=st.selectbox('What type of email is this?',PURPOSES,index=None,key=key+'purpose',placeholder='Choose an email type')
        edition_id=None
        if kind=='Collection' and (purpose in STOCK or purpose=='Availability / waitlist update'):
            st.caption('Select one qualifying edition in this collection. No collection-wide stock claim.')
            edition=picker(reader,'Single product',key+'collectionedition')
            edition_id=(edition or {}).get('id')
        required=purpose in OFFERS|DEADLINES|EVENTS|CONFIRMED or purpose=='Other / custom'
        notes=st.text_area('Details to include'+(' (required)' if required else ''),height=68,max_chars=1200,
                           placeholder=hint(purpose),key=key+'details')
        inputs={'kind':kind,'target':target,'purpose':purpose,'details':notes,'edition_id':edition_id}
        stamp=fingerprint(inputs,editor['document'])
        if state.get('input_stamp')!=stamp:
            state.pop('ready',None);state.pop('error',None);state['input_stamp']=stamp
        if st.button('Submit',key=key+'submit',type='primary'):
            state.pop('error',None)
            try:
                state['ready']=build(inputs,editor['document'],reader)
            except ValueError as exc:
                state.pop('ready',None);state['error']=str(exc)
            except Exception as exc:
                state.pop('ready',None);state['error']='Public context unavailable. Retry Submit.'
                logging.getLogger(__name__).warning('campaign_prompt_context_unavailable type=%s',type(exc).__name__)
        if state.get('error'):
            st.caption(state['error'])
            if state['error'].startswith('Sold out is not low stock'):
                def switch_to_availability():
                    st.session_state[key+'purpose']='Availability / waitlist update'
                st.button('Use Availability / waitlist update',key=key+'sold_out_switch',on_click=switch_to_availability)
        ready=state.get('ready')
        if ready:st.caption('Prompt ready')
        if st.button('Copy prompt',key=key+'copy',disabled=not ready):
            try:
                # Fresh authoritative recheck, no invented stock TTL. If facts
                # changed, invalidate and require an explicit new Submit.
                current=build(inputs,editor['document'],reader)
                old=deepcopy(ready['context']);new=deepcopy(current['context'])
                for context in (old,new):(context['target'].get('edition') or {}).pop('observed_at',None)
                if old!=new:raise ValueError('Context changed. Submit again before copying.')
                copy_result(current['prompt'])
            except ValueError as exc:
                state.pop('ready',None);state['error']=str(exc);st.rerun(scope='fragment')
            except Exception:
                state.pop('ready',None);state['error']='Unable to recheck facts. Submit again.';st.rerun(scope='fragment')
        if state.get('ready'):
            with st.expander('View prompt'):st.code(state['ready']['prompt'],language=None)
    interaction_bridge()


def interaction_bridge():
    st.html('''<script>(()=>{
      const root=document.querySelector('[role="dialog"] .st-key-crm-autofill-body');if(!root)return;
      // Mark edits immediately; server fingerprint validation is authoritative.
      root.querySelectorAll('input,textarea').forEach(input=>{
        if(input.dataset.promptBound)return;input.dataset.promptBound='1';
        input.addEventListener('input',()=>{
          root.querySelectorAll('button').forEach(b=>{if(b.textContent.trim()==='Copy prompt')b.disabled=true;});
          root.querySelectorAll('p').forEach(p=>{if(p.textContent.trim()==='Prompt ready')p.hidden=true;});
          const copied=root.querySelector('#crm-prompt-copy-result');if(copied)copied.hidden=true;
          if(!['Search editions','Select or type a collection'].includes(input.getAttribute('aria-label')))return;
          clearTimeout(input.promptTimer);input.promptTimer=setTimeout(()=>{
            if(input.isConnected&&document.activeElement===input){
              const start=input.selectionStart,end=input.selectionEnd;
              input.blur(); // Existing Streamlit text-input commit; never submits a form.
              requestAnimationFrame(()=>{if(input.isConnected){input.focus({preventScroll:true});input.setSelectionRange(start,end);}});
            }
          },250);
        });
      });
      if(!root.dataset.returnFocus){root.dataset.returnFocus='1';
        const observer=new MutationObserver(()=>{if(!root.isConnected){observer.disconnect();
          document.querySelector('.st-key-crm-autofill-trigger button')?.focus({preventScroll:true});}});
        observer.observe(document.body,{childList:true,subtree:true});
      }
    })();</script>'''.replace('<script>','<script>/* '+uuid.uuid4().hex+' */'),unsafe_allow_javascript=True)


def field_feedback():
    st.html('''<script>(()=>{
      const panel=document.querySelector('.st-key-crm-composer-controls');if(!panel)return;
      for(const [name,max,range] of [['Subject',60,'30–45 characters; at most 60 or 9 words'],['Preview text',89,'50–85 characters; at most 89']]){
        const input=panel.querySelector('input[aria-label="'+name+'"]');if(!input)continue;
        const label=panel.querySelector('label[for="'+input.id+'"]');if(!label)continue;
        let count=label.querySelector('.prompt-count');if(!count){count=document.createElement('span');count.className='prompt-count';label.append(count);}
        count.title=range+' recommended. Existing field limits are unchanged.';count.style.cssText='margin-left:auto;font-size:11px;color:#777;white-space:nowrap';
        const update=()=>{const n=Array.from(input.value).length;count.textContent=n+' / '+max+(n>max?' · advisory':'');};
        update();requestAnimationFrame(update);
        if(!input.dataset.promptCount){input.dataset.promptCount='1';input.addEventListener('input',update);
          new MutationObserver(update).observe(input,{attributes:true,attributeFilter:['value']});}
      }
    })();</script>''',unsafe_allow_javascript=True)
