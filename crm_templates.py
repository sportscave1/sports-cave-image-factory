"""Marketing templates only; support signatures are deliberately not imported."""
import re
from html import escape
from crm_logic import safe_url,utm

LOGO_PATH = '/app/static/branding/sports-cave-os-icon-192-v2.png'
FIELDS = ('subject','preview','headline','body','cta_label','cta_url','product_block','footer')
PLACEHOLDERS={'first_name','checkout_url','order_name','store_url'}

def seeds():
    items=[('abandoned_1','Abandoned Checkout 1','Your collection is waiting','Your next piece is still here.','Return to your checkout','{{checkout_url}}'),
      ('abandoned_2','Abandoned Checkout 2','Still thinking it over?','Take another look at the piece you chose.','View your selection','{{checkout_url}}'),
      ('abandoned_3','Abandoned Checkout 3','One more look','Real fans remember this. Own the moment.','Return to checkout','{{checkout_url}}'),
      ('welcome_1','Welcome 1','Welcome to Sports Cave','A place for collectors and the moments that matter.','Explore the collection','{{store_url}}'),
      ('welcome_2','Welcome 2','Find your defining moment','Discover sports art made for the fans who know.','Find your sport','{{store_url}}'),
      ('welcome_3','Welcome 3','Build your collection','Choose the sporting moments you want to live with.','Explore Sports Cave','{{store_url}}'),
      ('post_purchase','Post Purchase','Thank you for collecting with us','We hope your Sports Cave piece brings that moment home.','Explore the collection','{{store_url}}'),
      ('win_back','Win Back','Your next collector piece','It has been a while. See what is new at Sports Cave.','See the collection','{{store_url}}'),
      ('product_launch','Product Launch','A new moment to collect','Discover our latest sports art release.','Explore the release','{{store_url}}')]
    return [dict(template_key=k,name=n,kind='Campaign' if k=='product_launch' else 'Automation',content={
        'subject':s,'preview':b,'headline':s,'body':'Hi {{first_name}},\n\n'+b,
        'cta_label':cta,'cta_url':url,'product_block':k.startswith('abandoned'),
        'footer':'Sports Cave · Limited Edition Sports Art'}) for k,n,s,b,cta,url in items]

def validate(content):
    if set(content)!=set(FIELDS):raise ValueError('Template fields are incomplete.')
    for key,value in content.items():
        if key=='product_block':
            if not isinstance(value,bool):raise ValueError('Product block must be on or off.')
            continue
        if not isinstance(value,str) or len(value)>10000:raise ValueError('Template text is too long.')
        for token in re.findall(r'{{\s*(.*?)\s*}}',value):
            if token not in PLACEHOLDERS:raise ValueError('Unknown template placeholder.')
    if not content['subject'].strip() or not content['headline'].strip():raise ValueError('Subject and headline are required.')
    if '\n' in content['subject'] or '\r' in content['subject']:raise ValueError('Subject must be one line.')
    if content['cta_url'] not in ('{{checkout_url}}','{{store_url}}') and not safe_url(content['cta_url']):raise ValueError('CTA must use HTTPS or a supported URL placeholder.')
    return content

def render(content,context,unsubscribe_url,logo_url,campaign_key):
    validate(content)
    if not safe_url(unsubscribe_url) or not safe_url(logo_url):raise ValueError('Public HTTPS logo and unsubscribe URL are required.')
    def text(key):
        return re.sub(r'{{\s*(.*?)\s*}}',lambda m:str(context.get(m[1]) or ('there' if m[1]=='first_name' else '')),content[key])
    subject=text('subject');body=text('body');cta=utm(text('cta_url'),campaign_key)
    if not cta:raise ValueError('Current message has no valid CTA URL.')
    product_html=[];product_text=[]
    if content['product_block']:
        for p in context.get('products',[])[:12]:
            title=str(p.get('title',''));qty=str(p.get('quantity',1));price=str(p.get('price',''))
            product_html.append('<tr><td style="padding:10px 0;border-bottom:1px solid #dedad0">'+escape(title)+' × '+escape(qty)+' <span style="color:#777">'+escape(price)+'</span></td></tr>')
            product_text.append(f'{title} × {qty} {price}'.strip())
    html='''<!doctype html><html><body style="margin:0;background:#f7f5ef;color:#171717;font-family:Arial,sans-serif">
+<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="center" style="padding:28px 14px">
+<table role="presentation" width="560" cellspacing="0" cellpadding="0" style="width:100%;max-width:560px;background:white">
+<tr><td style="padding:22px;background:#111"><img alt="Sports Cave" width="48" height="48" src="'''.replace('\n+','\n')+escape(logo_url,quote=True)+'''"></td></tr>
+<tr><td style="padding:28px"><div style="display:none;max-height:0;overflow:hidden">'''.replace('\n+','\n')+escape(text('preview'))+'''</div><h1 style="font-size:25px;margin:0 0 20px">'''+escape(text('headline'))+'''</h1><div style="font-size:15px;line-height:1.65">'''+escape(body).replace('\n','<br>')+'''</div><table role="presentation" width="100%">'''+''.join(product_html)+'''</table><p style="margin:26px 0"><a style="display:inline-block;background:#171717;color:#fff;padding:13px 20px;text-decoration:none;border-bottom:2px solid #b29454" href="'''+escape(cta,quote=True)+'''">'''+escape(text('cta_label'))+'''</a></p><div style="border-top:1px solid #dedad0;padding-top:18px;font-size:11px;color:#777">'''+escape(text('footer'))+'''<br><a style="color:#777" href="'''+escape(unsubscribe_url,quote=True)+'''">Unsubscribe</a></div></td></tr></table></td></tr></table></body></html>'''
    plain='\n\n'.join([text('headline'),body,'\n'.join(product_text),text('cta_label')+': '+cta,text('footer'),'Unsubscribe: '+unsubscribe_url])
    return {'subject':subject,'html':html,'text':plain,'unsubscribe_url':unsubscribe_url}
