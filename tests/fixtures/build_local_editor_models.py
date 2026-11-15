"""Generate shared server/browser composition fixtures without external I/O."""
import json
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch,Mock
from crm_local_preview import model
from crm_middle_sections import commit_middle,render_middle
from crm_checkout_elements import element,KINDS
from crm_checkout_preview import document as hydrate
from crm_recovery_discount import substitute
from tests.test_crm_campaign_sections import sectioned
from tests.test_crm_send_flow import CFG
from tests.test_crm_abandoned_checkout import checkout
from crm_abandoned_checkout import context
from tests.test_crm_modular_catalogue import catalogue_doc
from tests.test_crm_discount_editor_v2 import add

def build():
    data=context(checkout(items=2));cases=[]
    for i,item in enumerate(data['items']):item.update(product_id=f'gid://shopify/Product/{i+1}',product_url=f'https://www.sportscaveshop.com/products/art-{i+1}')
    images=[{'url':f'https://cdn.shopify.com/lifestyle-{n}.jpg'} for n in range(1,5)]
    sections=[element(k,text='Fresh copy',action='none',size=21,align='left',color='#123456',image_url='https://cdn.shopify.com/photo.png') for k in KINDS]
    for count in (1,2,3,4,5,6):
        catalogue=catalogue_doc()['middle_sections'][-1]
        catalogue['products']=[{**deepcopy(catalogue['products'][i%2]),'id':f'gid://shopify/Product/{i+1}'} for i in range(count)]
        catalogue['settings'].update(headline='Featured art',subtext='A new collection',cta='Explore')
        sections.append(catalogue)
    sections += [dict(id='long-html',type='html',html_number=1,visible=True,html='<p>Safe <strong>copy</strong></p>'*300),dict(id='custom-image',type='image',visible=True,html='<img src="https://cdn.shopify.com/photo.png" alt="Art" width="600">')]
    offer_doc=sectioned();sections.append(add(offer_doc))
    from crm_lifestyle_images import source as lifestyle
    from crm_frame_banner_template import source as banner
    sections.extend(dict(id='template-'+str(i),type='image',visible=True,html=source) for i,source in enumerate([lifestyle(2),lifestyle(3),lifestyle(4),banner()]))
    for index,section in enumerate(sections):
        section['id']='fixture-'+str(index)
        doc=sectioned();commit_middle(doc,[section])
        if section['type']=='discount':doc['recovery_discount']=deepcopy(section['offer'])
        with patch('streamlit.session_state',{'_automation_checkout_pin':{'last_good':data}}),patch('requests.sessions.Session.request',side_effect=AssertionError('Network forbidden')),patch('crm_lifestyle_images.gallery',return_value=images),patch('crm_frame_banner_assets.prepare',return_value='https://cdn.shopify.com/frame.png'):
            seed=model(doc,CFG,Mock(email_mode='automation'))
            expected=render_middle(hydrate(substitute(doc),data,test=True)[0])[0]
        seed['resolved']={} # Exercise the incremental path, not its warm seed.
        cases.append(dict(section=section,model=seed,expected=expected))
    doc=sectioned();add(doc);section=doc['middle_sections'][0]
    section['html']='<p>Offer: {{discount_code}} / {{discount_value}}</p>'
    commit_middle(doc,doc['middle_sections'])
    with patch('streamlit.session_state',{}):seed=model(doc,CFG)
    cases.append(dict(section=section,sections=doc['middle_sections'],model=seed,expected=substitute(doc)['custom_html'],sibling_offer=True))
    Path('tmp/local-editor-models.json').write_text(json.dumps(cases,default=str),encoding='utf8')
    print('Generated',len(cases),'composition cases')

if __name__=='__main__':build()
