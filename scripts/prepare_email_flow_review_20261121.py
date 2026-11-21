"""Prepare authored flow definitions offline; never connect, enqueue or send."""
from copy import deepcopy
from html import escape
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from crm_automation_definition import validate

BASE=ROOT/'docs/automation-review-baseline-20261121.json'
SHARED=ROOT/'docs/email-shared-defaults-20261121.json'
OUT=ROOT/'docs/automation-review-proposed-20261121.json'
SHOP='https://www.sportscaveshop.com'
FINDER=SHOP+'/collections/all-sports-wall-art'
ACCOUNT='https://account.sportscaveshop.com/pages/019ef355-648a-7996-8977-897320e5ffd7'


def source(headline,body,label='',url=''):
    button=('''<table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center"><tr><td align="center" bgcolor="#222222"><a href="'''+escape(url,quote=True)+'''" style="display:block;padding:12px 24px;font-family:Arial,Helvetica,sans-serif;font-size:16px;line-height:24px;font-weight:700;color:#FFFFFF;text-decoration:none">'''+escape(label)+'''</a></td></tr></table>''') if label else ''
    paragraphs=''.join('<p style="margin:0 0 18px;font-family:Arial,Helvetica,sans-serif;font-size:16px;line-height:25px;color:#222222">'+escape(p)+'</p>' for p in body.split('\n\n'))
    return '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" bgcolor="#FFFFFF" style="width:100%;max-width:600px;border-collapse:collapse;background:#FFFFFF"><tr><td align="center" style="padding:28px 20px 24px"><h1 style="margin:0 0 20px;font-family:Georgia,Times New Roman,serif;font-size:30px;line-height:36px;font-weight:400;color:#222222">'+escape(headline)+'</h1>'+paragraphs+button+'</td></tr></table>'


def rewrite(step,shared,subject,preview,headline,body,*,cta='',url='',smart=False,count=2):
    result=deepcopy(step);doc=result['document'];old=doc['middle_sections']
    doc['content']={k:'' for k in doc['content']}
    doc['content'].update(subject=subject,preheader=preview,headline=headline,intro=body,cta_label=cta,cta_url=url)
    html=source(headline,body,cta,url)
    doc.update(content_mode='HTML',custom_html=html,html_sections=deepcopy(shared),blocks=[],
               tags=list(dict.fromkeys([*doc.get('tags',[]),'email-light-v1'])),
               copy_reviewed=True,offer='None',offer_reviewed=True,smart_hours=24)
    doc.pop('recovery_discount',None);doc.pop('discount_association_version',None)
    doc['notes']='Reviewed against the Sports Cave Email Growth Plan. Short, light design. Verified customer signals drive optional Smart recommendations; no anonymous quiz-to-email identity join. No unverified scarcity or discount promise.'
    sections=[dict(id='html-1',type='html',visible=True,html_number=1,css_version=1,html=html)]
    if smart:
        catalogue=next((deepcopy(s) for s in old if s['type']=='catalogue'),
                       dict(id='lifecycle-recommendations',type='catalogue',visible=True,products=[],settings={}))
        catalogue.update(visible=True,products=[])
        catalogue['settings']={'headline':'','subtext':'','columns':2,'smart':True,'smart_count':count,
          'display':{'image':True,'title':True,'limit':True,'next':False,'remaining':False,'price':False,'cta':True},
          'cta':'Claim Your Edition'}
        sections.append(catalogue)
    doc['middle_sections']=sections
    return result


def main():
    rows=json.loads(BASE.read_text(encoding='utf-8'))
    shared={r['key'].removeprefix('email_default_'):r['value']['html'] for r in json.loads(SHARED.read_text(encoding='utf-8'))}
    for row in rows:
        flow=row['draft'];emails=flow['emails'];name=row['name']
        if name=='Abandoned Checkout':continue
        if name=='Welcome Series':
            specs=[
              ('Your sporting story starts here','Find a moment that means something to you.','Your sport. Your memories. Your wall.',
               'Hi {{first_name}},\n\nSome moments stay with you. The roar. The rivalry. The athlete you grew up watching.\n\nWelcome to Sports Cave. Explore the editions below, or let the finder help you choose.',0,True,'Find your next edition',FINDER),
              ('A moment worth keeping','Bring back the feeling. Explore the story behind each edition.','More than a moment.',
               'The play you replay. The hero you backed. The memory that still gives you chills.\n\nFind an edition that brings it all back. Explore its story and verified edition details on the product page.',1,True,'',''),
              ('Your space. Your sport. Your edition.','Compare the frame details, or reply for help choosing.','Make room for your moment.',
               'Big statement or a quiet corner? Choose the size and finish that feel right for your space.\n\nExplore the frame details, or reply with your wall size. We will help you choose.',3,False,'See sizes and frames',SHOP+'/pages/frame-specifications'),
              ('Which moment belongs on your wall?','Two editions to explore. A real person to help you choose.','Find the one that feels like yours.',
               'Still finding your favourite? Explore the editions below.\n\nTorn between two legends? Reply with your sport or athlete. We will help you find your match.',6,True,'','')]
            new=[]
            for i,(subject,preview,heading,body,day,smart,cta,url) in enumerate(specs):
                step=deepcopy(emails[min(i,len(emails)-1)])
                if i==3:step['step_id']='aab73be5-2a11-5b9a-b3e9-ae2f86b3c12e'
                step=rewrite(step,shared,subject,preview,heading,body,cta=cta,url=url,smart=smart)
                step.update(name=('Welcome and discovery','The sporting memory','Size and frame help','Your next edition')[i],enabled=True,anchor='subscription',delay_seconds=day*86400)
                new.append(step)
            flow['emails']=new;flow['exit_on_purchase']=True
        elif name=='Post Checkout':
            first=rewrite(emails[0],shared,'Your sporting moment is coming home','Thank you for choosing Sports Cave. Your collector details are inside.','A moment worth keeping.',
              'Hi {{first_name}},\n\nThank you for choosing Sports Cave. We are glad this sporting story will be part of your home.\n\nWhen your edition arrives, follow the packing-slip instructions to access your certificate in your Sports Cave account.\n\nAny questions? Just reply.',cta='View your collection',url=ACCOUNT)
            first.update(name='Thank you and collector access',anchor='payment',delay_seconds=10800)
            review=rewrite(emails[1],shared,'How does your edition feel at home?','Tell us honestly. If anything is not right, we are here to help.','Has your moment found its place?',
              'Hi {{first_name}},\n\nWe hope your edition brings that sporting feeling back every time you see it.\n\nTell us what you think, good or bad. If anything is not right, reply and we will help.',cta='Share honest feedback',url=SHOP+'/pages/reviews')
            review.update(name='Honest feedback',anchor='delivery',delay_seconds=7*86400,requires_fulfilment=True)
            photo=rewrite(emails[1],shared,'Show us your sporting corner','We would love to see your setup. Sharing is always your choice.','Your edition. Your space.',
              'Every collector makes an edition their own. We would love to see yours.\n\nReply with a photo if you would like to share your setup. We will ask before featuring your space.',cta='Share your setup',url=SHOP+'/pages/contact')
            photo.update(step_id='90f0f54e-d03a-5a1e-bf48-43b70573062a',name='Share your setup',enabled=True,anchor='delivery',delay_seconds=14*86400,requires_fulfilment=True)
            collect=rewrite(emails[2],shared,'Another chapter for your collection','Explore editions that complement the sporting story you already own.','One memory leads to another.',
              'Your collection tells your story. What comes next?\n\nExplore a complementary edition from the sports you love. If you are building a pair, reply and we will help you choose.',smart=True)
            collect.update(name='Complement your collection',anchor='delivery',delay_seconds=45*86400,requires_fulfilment=True)
            flow['emails']=[first,review,photo,collect]
            flow['fulfilment_fallback_days']=None
        elif name=='Win Back':
            copy=[
              ('A new chapter for your collection','Discover relevant new editions, at your own pace.','Still your sport. A new story.',
               'Some sporting moments never leave you. Others are still waiting to be discovered.\n\nExplore the latest available editions from the sports you love. Find a story that belongs alongside yours.'),
              ('Which legend comes next for you?','A small selection to explore, with help whenever you need it.','Your next sporting chapter.',
               'A collection grows one meaningful piece at a time.\n\nSee what speaks to you now. Want help finding a companion for your edition? Reply with your favourite sport or athlete.'),
              ('A sporting memory worth revisiting','Discover editions at your own pace.','The feeling stays with you.',
               'The heroes. The rivalries. The moments you still talk about.\n\nWhenever you are ready, explore the collection and find a sporting story that feels like yours.'),
              ('Keep the moments that move you','Choose the editions and updates that matter to you.','Your sport. On your terms.',
               'There is no rush to find the right edition.\n\nExplore when the moment feels right, or use the unsubscribe link below if these updates are no longer for you.')]
            flow['emails']=[rewrite(step,shared,*spec,smart=True) for step,spec in zip(emails,copy)]
            for i,step in enumerate(flow['emails']):step['enabled']=i<2
        validate(flow,draft=False)
    OUT.write_text(json.dumps(rows,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    from crm_personalisation import render as personalise
    from crm_campaign_content import render_campaign
    from tests.test_crm_modular_catalogue import catalogue_doc
    from tests.test_crm_send_flow import CFG
    preview_dir=ROOT/'tmp/automation-review'
    preview_dir.mkdir(parents=True,exist_ok=True)
    specimens=catalogue_doc()['middle_sections'][-1]['products']
    for row in rows:
        if row['name']=='Abandoned Checkout':continue
        for index,step in enumerate(row['draft']['emails']):
            doc=deepcopy(step['document'])
            for section in doc['middle_sections']:
                if section['type']!='catalogue':continue
                section['settings']['smart']=False
                section['products']=[]
                for i,finish in enumerate(('black','oak')):
                    sample=deepcopy(specimens[0])
                    sample.update(id='gid://shopify/Product/'+str(i+1),
                      title='Sample '+finish+' frame - layout preview',
                      url='https://example.test/products/sample-'+finish,
                      image='https://cdn.shopify.com/s/files/1/0722/2332/6515/files/'+finish+'-frame-swatch.webp?v=1761953957')
                    section['products'].append(sample)
            doc=personalise(doc,{'first_name':'Collector'},trigger=row['draft']['trigger'])
            message=render_campaign(doc,CFG)
            if len(message['html'].encode())>=80000:raise ValueError('Preview exceeds the plan HTML budget')
            slug=row['name'].lower().replace(' ','-')+'-'+str(index+1)
            (preview_dir/(slug+'.html')).write_text(message['html'],encoding='utf-8')
            words=len(step['document']['content']['intro'].split())
            if words>90:raise ValueError('Body copy is too long')
    for row in rows:
        for e in row['draft']['emails']:
            if row['name']=='Abandoned Checkout':continue
            print(row['name'],e['name'],e['delay_seconds'],e['anchor'],'enabled='+str(e['enabled']),e['document']['content']['subject'])


if __name__=='__main__':main()
