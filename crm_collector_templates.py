"""Four insertable collector designs for the existing Templates library.

No seeding, database writes, branding headers, footer or draft replacement.
"""
from html import escape
from crm_collector_images import marker,settings,COLLECTION,ACCOUNT

DESIGNS={
 'collector-welcome':('Collector Welcome','A place for the moments that matter',
   'Welcome to Sports Cave. Discover artwork that brings the sporting stories you love into your space.',
   'Explore the collection','Featured Collection'),
 'collected-artwork':('Your Collected Artwork','Your sporting story, collected',
   'Thank you for choosing Sports Cave. Visit My Collection to explore your artwork and numbered edition details. Once your certificate is available, you can access it securely in your account. Follow your order updates for the progress of your artwork.',
   'View My Collection','Actual Purchased Product'),
 'build-collection':('Build Your Collection','Another moment worth keeping',
   'Discover artwork that belongs alongside the sporting stories you love. Explore each piece for its current availability and edition details.',
   'Explore the collection','Related Products'),
 'collector-reengagement':('Collector Re-engagement','There is more to your sporting story',
   'Revisit the moments that inspired your collection, and discover another piece that speaks to you.',
   'Explore the collection','Related Products'),
}
PREFIX='builtin-collector-v1-'


def library_rows():
    return [dict(id=PREFIX+k,name=v[0],version=1,builtin=True) for k,v in DESIGNS.items()]


def source(identity, *, wording=None):
    key=identity.removeprefix(PREFIX)
    name,title,copy,cta,kind=DESIGNS[key]
    if wording:title,copy=wording
    images=marker(settings(kind,2 if key=='collected-artwork' else 1 if key=='collector-welcome' else 3))
    if key=='collector-reengagement':images=marker(settings('Actual Purchased Product',1))+images
    destination=ACCOUNT if key=='collected-artwork' else COLLECTION
    benefits=(' <table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr>'
      +''.join('<td width="33%" align="center" style="padding:16px 4px;font:11px Arial;color:#d3b779">'+icon+'<br>'+label+'</td>'
               for icon,label in [('&#9671;','Your artwork'),('&#8470;','Edition details'),('&#9635;','Secure account')])+'</tr></table>') if key=='collected-artwork' else ''
    return ('<table role="presentation" width="100%" cellspacing="0" cellpadding="0" bgcolor="#111111" '
      'style="background:#111111;border-collapse:collapse;color:#f4efe5"><tr><td style="padding:32px 24px 20px;font-family:Arial,Helvetica,sans-serif">'
      '<p style="margin:0 0 14px;color:#d3b779;font-size:11px;line-height:16px;letter-spacing:2px">THE COLLECTOR EXPERIENCE</p>'
      '<h1 style="margin:0 0 20px;font-family:Georgia,serif;font-size:30px;line-height:36px;font-weight:normal;color:#f4efe5">'+escape(title)+'</h1>'
      '<p style="margin:0;font-size:16px;line-height:26px;color:#e5dfd3">'+escape(copy)+'</p></td></tr>'
      '<tr><td>'+images+benefits+'</td></tr><tr><td align="center" style="padding:26px 20px 32px">'
      '<a href="'+destination+'" style="display:inline-block;background:#d3b779;color:#111111;padding:13px 20px;border:1px solid #d3b779;font-family:Arial,sans-serif;font-size:14px;line-height:20px;font-weight:bold;text-decoration:none">'+escape(cta)+'</a>'
      '</td></tr></table>')


def document(identity):
    from crm_campaign_content import new_document
    from crm_middle_sections import commit_middle
    doc=new_document();doc['content_mode']='HTML'
    name,title,copy,_,_=DESIGNS[identity.removeprefix(PREFIX)]
    doc['content'].update(subject=title,preheader=copy)
    commit_middle(doc,[dict(id='collector-body',type='html',visible=True,html_number=1,html=source(identity))])
    return doc
