"""Independent checkout HTML copies in the shared middle-section document."""
from copy import deepcopy
import uuid
from crm_checkout_styles import MARKER
from crm_middle_sections import middle_sections,commit_middle


def insert(store,doc,event=None):
    from crm_checkout_template import load,validate
    from crm_middle_sections import apply_event
    proposed=deepcopy(doc)
    # Flush pending source edits before inserting the fetched master.
    if event:
        apply_event(proposed,{**event,'type':'order','ids':event['base']})
    html=validate(load(store)['html'])
    sections=middle_sections(proposed)
    if len(sections)==1 and sections[0]['type']=='html' and not sections[0]['html'].strip():sections=[]
    sections.append(dict(id=uuid.uuid4().hex,type='html',name='Abandoned Checkout',visible=True,
        html_number=max((s.get('html_number',0) for s in sections),default=0)+1,html=html))
    proposed['content_mode']='HTML';commit_middle(proposed,sections)
    from crm_campaign_content import validate_document
    proposed['copy_reviewed']=False;validate_document(proposed);doc.update(proposed)


def editable(doc):
    """Upgrade only an editor's draft copy; never touch published versions/history."""
    result=deepcopy(doc);sections=middle_sections(result);index=0
    while index<len(sections):
        block=sections[index]
        if block['type']!='abandoned_checkout_products':index+=1;continue
        if (0<index<len(sections)-1 and sections[index-1]['type']=='html' and
            sections[index+1]['type']=='html' and
            all(s['visible']==block['visible'] for s in sections[index-1:index+2])):
            before,_,after=sections[index-1:index+2]
            before['html']+=MARKER+after['html'];before.setdefault('name','Abandoned Checkout')
            del sections[index:index+2]
        else:
            block.update(type='html',name=block.get('name','Abandoned Checkout'),html=MARKER,
                html_number=max((s.get('html_number',0) for s in sections),default=0)+1)
            index+=1
    commit_middle(result,sections)
    return result
