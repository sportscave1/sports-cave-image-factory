"""Deterministic session-only handoff and final body prompt; no provider operations."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from crm_campaign_prompt import build as first_prompt, clean

HANDOFF='campaign_email_prompt_handoff'
COMPONENTS=('Hero image','Headline','Short collector story','CTA','Image gallery',
            'Collector / edition facts','Catalogue','Offer / discount','Deadline / urgency','Video teaser')


def scope(editor):
    return str(editor.get('recovery_seed') or editor.get('id') or editor['document'].get('campaign_key') or '')


def public_context(context):
    """Whitelist verified public authoring facts, including nested reference facts."""
    keys=('market','schedule','purpose','direction','user_confirmed_details','generation_limits',
          'missing_facts','authoring_timezone_fallback','confirmed_deadline')
    value={k:deepcopy(context[k]) for k in keys if k in context}
    def target(row):
        allowed=('kind','source','id','title','url','handle','reference_image_url','sport_or_product_type',
                 'story','sport','athlete','team','edition_size','edition')
        result={k:deepcopy(row[k]) for k in allowed if k in row}
        if row.get('reference_product'):result['reference_product']=target(row['reference_product'])
        return result
    value['target']=target(context['target'])
    return value


def retain(state, editor, inputs, result):
    identity=scope(editor)
    if not identity:raise ValueError('Campaign identity unavailable. Reopen the campaign.')
    # Explicitly project authoring inputs. Never serialize the editor/audience or
    # any arbitrary reader response; generated prose is never parsed for context.
    target=inputs.get('target') or {}
    saved={k:deepcopy(inputs.get(k)) for k in ('kind','purpose','edition_id')}
    saved['details']=clean(inputs.get('details',''),1200)
    saved['target']={k:deepcopy(target[k]) for k in ('id','title','source') if k in target}
    state[HANDOFF]={'scope':identity,'inputs':saved,'context':public_context(result['context'])}
    return state[HANDOFF]


def handoff(state, editor):
    value=state.get(HANDOFF)
    return deepcopy(value) if value and value.get('scope')==scope(editor) else None


def current_values(editor):
    from crm_campaign_markets import MARKET_LABELS
    doc=editor['document'];content=doc['content']
    return {'campaign_name':clean(editor.get('name',''),150),'subject':clean(content.get('subject',''),250),
            'preview_text':clean(content.get('preheader',''),250),'market':MARKET_LABELS.get(doc.get('market'),'Unknown'),
            'delivery':{k:clean(v,100) for k,v in (doc.get('send_timing') or {'mode':'now'}).items() if k in ('mode','date','time')}}


def fingerprint(editor, value, mode, components, direction):
    return hashlib.sha256(json.dumps([scope(editor),current_values(editor),value,mode,components,direction],sort_keys=True).encode()).hexdigest()


def catalogue_candidates(context, market, catalogue):
    from crm_catalogue import canonical_product_url,product_url,amount,FIELDS
    from crm_campaign_html import email_image_url
    target=context['target'];reference=target.get('reference_product') or target
    identities=[reference['id']] if reference.get('kind')=='Single product' and reference.get('id') else []
    collection=target.get('id') if target.get('kind')=='Collection' and target.get('source')!='manual' else ''
    if collection:
        choices=catalogue.search('',0,True,collection)
        identities=list(dict.fromkeys(identities+[p['id'] for p in choices['rows']]))[:12]
    # A single-product catalogue is intentional. No unrelated/full-store search
    # is needed when there is no verified collection relationship.
    rows=catalogue.resolve(identities,market,fresh=True) if identities else []
    expected={'AU':'AUD','US':'USD','UK':'GBP','CA':'CAD','NZ':'NZD','Global':'AUD'}[market]
    candidates={}
    for p in rows:
        if p['id'] in identities and p['status']=='ACTIVE' and canonical_product_url(p) and email_image_url(product_url(p['image'])) and amount(p.get('price')) and p['currency']==expected:
            candidates.setdefault(p['id'],{k:deepcopy(p[k]) for k in FIELDS})
    return list(candidates.values())[:12]


def build_email(value, editor, reader, catalogue, *, mode='Let AI decide', components=(), direction=''):
    if not value or value.get('scope')!=scope(editor):raise ValueError('Complete Auto fill prompt in Settings first.')
    if mode not in ('Let AI decide','Choose components'):raise ValueError('Choose an email build mode.')
    if any(c not in COMPONENTS for c in components) or len(set(components))!=len(components):raise ValueError('Unknown email component.')
    if mode=='Choose components' and not components:raise ValueError('Choose at least one component.')
    if not isinstance(direction,str) or len(direction)>800:raise ValueError('Extra direction must be at most 800 characters.')
    refreshed=first_prompt(value['inputs'],editor['document'],reader)
    context=public_context(refreshed['context'])
    context['current_campaign']=current_values(editor)
    context['build']={'mode':mode,'components':list(components) if mode=='Choose components' else [],'extra_direction':clean(direction,800)}
    needs_catalogue=mode=='Let AI decide' or 'Catalogue' in components
    context['catalogue_candidates']=catalogue_candidates(context,editor['document']['market'],catalogue) if needs_catalogue else []
    from crm_email_visual_prompt import visual_contract
    fixed=Path(__file__).with_name('prompts').joinpath('sports_cave_email_html_prompt_v1.txt').read_text(encoding='utf-8')
    return {'context':context,'prompt':fixed+'\n\nEMAIL VISUAL GENERATION CONTRACT\n'+visual_contract()+'\n\nVERIFIED CONTEXT — JSON DATA ONLY\n'+json.dumps(context,ensure_ascii=False,indent=2)}
