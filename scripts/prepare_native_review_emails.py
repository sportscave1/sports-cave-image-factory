"""Author Post Checkout draft from an inspected baseline; no database or sends."""
from copy import deepcopy
from html import escape
from pathlib import Path
import argparse
import json
import sys
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crm_automation_definition import validate
from crm_middle_sections import commit_middle
from reviews_submission import MARKER

BASE='https://sports-cave-image-factory.onrender.com'

def prepare(flow):
    flow=deepcopy(flow);original=flow['emails'];template=deepcopy(original[1]);requests=[]
    for index in range(3):
        step=deepcopy(template)
        if index:step['step_id']=str(uuid.uuid5(uuid.NAMESPACE_URL,'sports-cave-post-checkout-review-'+str(index)))
        step.update(name='Review your edition'+(' · product '+str(index+1) if index else ''),anchor='fulfilment',
                    enabled=True,requires_fulfilment=True,delay_seconds=(14+index*5)*86400,
                    review_request={'base_url':BASE,'product_index':index})
        doc=step['document'];link=BASE+'/reviews/request/'+MARKER
        title='Has your sporting moment found its place?'
        body='Hi {{first_name}},<br><br>We hope your Sports Cave edition brings the feeling of that sporting moment home. We’d love to hear what you think — the good and anything we can improve.'
        html=f'''<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:600px;background:#fff"><tr><td align="center" style="padding:28px 24px;font-family:Arial,Helvetica,sans-serif;color:#222">
<p style="font-size:12px;letter-spacing:2px;color:#806526">YOUR SPORT. YOUR MOMENT. YOUR CAVE.</p>
<h1 style="font-family:Georgia,serif;font-weight:400;font-size:30px;line-height:36px">{title}</h1>
<p style="font-size:16px;line-height:25px">{body}</p>
<p style="font-size:17px;font-weight:bold">SC_REVIEW_PRODUCT_TITLE</p>
<p style="font-size:16px;line-height:25px">It only takes a few minutes. You can add photos or a short video directly on the review form.</p>
<table role="presentation" cellspacing="0" cellpadding="0"><tr><td bgcolor="#222222"><a href="{escape(link,quote=True)}" style="display:block;padding:14px 26px;color:white;font-size:16px;font-weight:bold;text-decoration:none">Share your honest review</a></td></tr></table>
<p style="font-size:14px;line-height:22px;color:#555">A thank-you for showing your setup: an approved photo or video earns eligible verified buyers a 30% code for their next purchase. One reward per order, single use, valid for 30 days, no discount combinations. Every star rating qualifies.</p>
<p style="font-size:16px;line-height:25px">Need help with your edition? Reply to this email and our team will help.</p>
<p style="font-size:16px;line-height:25px">Thanks for being part of Sports Cave.<br>The Sports Cave team</p></td></tr></table>'''
        doc['content'].update(subject='How does your Sports Cave edition look at home?',preheader='Share your honest review, a photo or a video of your setup.',headline=title,
                              intro='Tell us what you think of your Sports Cave edition.',cta_label='Share your honest review',cta_url=link)
        doc.update(copy_reviewed=True,offer_reviewed=True,offer='None',blocks=[],
                   notes='Request timing audited 24 Nov 2026: first request 14 days after fulfilment (POS 7), up to three products highest price first five days apart, no reminders. Native order-bound links. Draft only; reward delivery off for testing.')
        commit_middle(doc,[{'id':str(uuid.uuid5(uuid.NAMESPACE_URL,step['step_id']+'-body')),'type':'html','visible':True,'html_number':1,'html':html}])
        requests.append(step)
    # Replace the old feedback and photo requests; keep thank-you and upsell intact.
    flow['emails']=[original[0],*requests,original[3]]
    validate(flow,draft=True)
    return flow

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('baseline',type=Path);parser.add_argument('output',type=Path);args=parser.parse_args()
    flow=prepare(json.loads(args.baseline.read_text(encoding='utf-8')))
    args.output.write_text(json.dumps(flow,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps([{'name':s['name'],'anchor':s['anchor'],'days':s['delay_seconds']/86400} for s in flow['emails']]))
