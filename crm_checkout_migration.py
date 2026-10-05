"""Lossless, editable-draft migration of the known checkout insertion marker.

Published documents are never written here. Ambiguous Liquid remains subject to
the historical preview compatibility renderer and strict publication checks.
"""
from copy import deepcopy
import hashlib
import re
from html.parser import HTMLParser
from crm_checkout_styles import MARKER, count


def migrate(doc):
    result=deepcopy(doc)
    sections=result.get('middle_sections')
    if not isinstance(sections,list) or count(result)!=1:return result
    if any(s.get('type')=='abandoned_checkout_products' for s in sections):return result
    targets=[s for s in sections if s.get('type')=='html' and s.get('visible') and MARKER in s.get('html','')]
    if len(targets)!=1 or any(re.search(r'\{\{|\{%',s.get('html','')) for s in sections):return result
    target=targets[0];before,after=target['html'].split(MARKER)
    class Insertion(HTMLParser):
        found=0
        def handle_comment(self,value):
            if value=='SC_ABANDONED_CHECKOUT':self.found+=1
    insertion=Insertion();insertion.feed(target['html'])
    if insertion.found!=1:return result
    key='checkout-migration-'+hashlib.sha256(target['id'].encode()).hexdigest()[:20]
    if any(s['id'] in (key,key+'-after') for s in sections):return result
    number=max(s.get('html_number',0) for s in sections)+1
    if number>10000 or len(sections)>18:return result
    index=sections.index(target);target['html']=before
    sections[index+1:index+1]=[
        {'id':key,'type':'abandoned_checkout_products','visible':True},
        {'id':key+'-after','type':'html','visible':True,'html_number':number,'html':after}]
    result['custom_html']=next((s['html'] for s in sections if s.get('html_number')==1),'')
    return result


def join_fragments(doc):
    """Restore original nesting before the shared sanitizer balances HTML.

Only an adjacent migrated before/native/after triple is joined. The editable
document retains its native block; this operates on the rendering copy only.
"""
    sections=doc.get('middle_sections',[]);index=1
    while index<len(sections)-1:
        before,block,after=sections[index-1:index+2]
        if (block['id'].startswith('checkout-migration-') and
            after['id']==block['id']+'-after' and block.get('type')=='image' and
            before.get('type')=='html' and after.get('type')=='html' and
            before.get('visible') and after.get('visible')):
            before['html']+=(block['html'] if block.get('visible') else '')+after['html']
            del sections[index:index+2]
        else:index+=1
    if 'middle_sections' in doc:
        doc['custom_html']=next((s['html'] for s in sections if s.get('html_number')==1),'')
    return doc


def migrate_flow(flow):
    result=deepcopy(flow)
    if result.get('trigger')=='abandoned':
        for step in result.get('emails',[]):step['document']=migrate(step['document'])
    return result
