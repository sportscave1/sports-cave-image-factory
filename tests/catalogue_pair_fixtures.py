"""Offline fixtures through the actual final email renderer; no delivery or app startup."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from crm_campaign_content import render_campaign
from crm_campaign_html import CSS, TAGS
from crm_catalogue import catalogue_html
from tests.test_crm_premium_catalogue import PremiumCatalogueTests
from tests.test_crm_modular_catalogue import catalogue_doc


def fixtures():
    cases=[]
    for count in range(1,13):
        section=PremiumCatalogueTests().section(count)
        for i,p in enumerate(section['products']):
            p['title']=('Champion Print' if i%4!=1 else 'Championship winning collector artwork celebrating an unforgettable sporting victory in a premium framed edition')
            p['image']='https://cdn.shopify.com/fixture-'+str(i%2)+'.png'
        section['settings']['cta']='Explore this artwork'
        doc=catalogue_doc();doc['middle_sections']=[section];doc['custom_html']=''
        cases.append(dict(name=str(count),section=section,html=render_campaign(doc)['html']))
    for mode in ('missing','toggles','unbroken'):
        section=deepcopy(cases[3]['section'])
        if mode=='missing':
            section['products'][0]['edition']=None
            section['products'][2]['edition']['remaining']=None
            section['products'][0]['compare_at']=''
        if mode=='toggles':section['settings']['display'].update(image=False,price=False,cta=False,limit=False)
        if mode=='unbroken':
            section['products'][1]['title']='Collector'+('W'*180)
            section['settings']['cta']='Discover this extraordinary championship collectors edition'
        doc=catalogue_doc();doc['middle_sections']=[section];doc['custom_html']=''
        cases.append(dict(name=mode,section=section,html=render_campaign(doc)['html']))
    return dict(cases=cases,tags=sorted(TAGS),css=sorted(CSS))

if __name__=='__main__':
    Path(sys.argv[1]).write_text(json.dumps(fixtures()),encoding='utf-8')
