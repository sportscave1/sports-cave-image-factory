"""Shorten existing Post Checkout drafts without changing timing or publications."""
from copy import deepcopy
from html import escape
import uuid
from crm_middle_sections import commit_middle
from crm_automation_definition import validate
from reviews_submission import MARKER
BASE='https://sports-cave-image-factory.onrender.com'

def polish(flow):
 result=deepcopy(flow)
 for index,step in enumerate(result['emails']):
  doc=step['document'];review=bool(step.get('review_request'))
  if review:
   titles=['How does it look at home?','Another edition. Your story.','Show us your setup.']
   slot=step['review_request']['product_index'];title=titles[slot]
   subject=['How does your Sports Cave edition look?','What do you think of this edition?','Your sporting moment, on your wall'][slot]
   intro='Hi {{first_name}},<br>Tell us what you think of your edition. Add a photo or video on the same form.'
   extra='<p style="font-size:17px;font-weight:600">SC_REVIEW_PRODUCT_TITLE</p>'
   link=BASE+'/reviews/request/'+MARKER;label='Write a review'
   reward='<p style="font-size:14px;line-height:21px;color:#555">Approved photo or video? Eligible buyers get 30% off next time. Any star rating.</p><p style="font-size:12px;line-height:18px;color:#666">One code per order. Single use. Valid 30 days. No stacking.</p>'
  elif index==0:
   title='A great addition to your cave.';subject='Thanks for choosing Sports Cave'
   intro='Thanks for choosing Sports Cave, {{first_name}}.<br>When your edition arrives, find your certificate in your account. Need help? Just reply.'
   extra='';link='https://account.sportscaveshop.com/pages/019ef355-648a-7996-8977-897320e5ffd7';label='View your collection';reward=''
  else:
   title='Make it a pair.';subject='What belongs beside your edition?'
   intro='Your next sporting moment is waiting. Find an edition to sit beside your favourite.'
   extra='';link='https://www.sportscaveshop.com/collections/all-sports-wall-art';label='Explore editions';reward=''
  button=('<p><a href="'+escape(link,quote=True)+'" style="display:inline-block;background:#d4a54c;color:#171717;padding:14px 28px;border-radius:6px;text-decoration:none;font-weight:700">'+label+'</a></p>') if link else ''
  html='<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="center" style="padding:28px 24px;font-family:Arial,Helvetica,sans-serif;color:#222;background:#fff"><p style="font-size:11px;letter-spacing:2px;color:#806526">YOUR SPORT. YOUR MOMENT. YOUR CAVE.</p><h1 style="font-family:Georgia,serif;font-size:30px;line-height:36px;font-weight:400">'+title+'</h1><p style="font-size:16px;line-height:24px">'+intro+'</p>'+extra+button+reward+'<p style="font-size:14px;line-height:21px">The Sports Cave team</p></td></tr></table>'
  doc['content'].update(subject=subject,headline=title,intro=intro.replace('<br>',' '),preheader='Share your review, photo or video.' if review else 'Your sport. Your moment. Your cave.',cta_label=label,cta_url=link,body='',secondary='',ps='')
  preserved=[x for x in doc.get('middle_sections',[]) if x.get('type')!='html']
  commit_middle(doc,[{'id':str(uuid.uuid5(uuid.NAMESPACE_URL,step['step_id']+'-short-copy')),'type':'html','visible':True,'html_number':1,'html':html},*preserved])
  doc['copy_reviewed']=True
 validate(result,draft=True)
 return result
