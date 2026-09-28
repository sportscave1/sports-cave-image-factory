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
    if isinstance(content,dict) and content.get('format')=='campaign_blocks_v1':
        from crm_campaign_content import validate_document
        if set(content)!={'format','document'}:raise ValueError('Invalid design template.')
        validate_document(content['document']);return content
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
    """Legacy flow adapter into the same locked campaign renderer.

    Stored legacy templates/versions are preserved. This adapter resolves only the
    existing placeholders; production dispatch still requires the CRM master gate.
    """
    validate(content)
    if not safe_url(unsubscribe_url) or not safe_url(logo_url):raise ValueError('Public HTTPS logo and unsubscribe URL are required.')
    import hashlib
    from crm_campaign_content import new_document,render_campaign,settings
    from crm_email_blocks import block
    from crm_tracking import campaign_link
    if content.get('format')=='campaign_blocks_v1':
        result=render_campaign(content['document'],{**settings(),'logo':logo_url},unsubscribe_url=unsubscribe_url)
        result['unsubscribe_url']=unsubscribe_url
        return result
    def text(key):
        return re.sub(r'{{\s*(.*?)\s*}}',lambda m:str(context.get(m[1]) or ('there' if m[1]=='first_name' else '')),content[key])
    doc=new_document();doc['campaign_key']='sc_'+hashlib.sha256(str(campaign_key).encode()).hexdigest()[:32]
    cta=campaign_link(text('cta_url'),doc['campaign_key'],'b_primary',test=False)
    if not safe_url(cta):raise ValueError('Current message has no valid CTA URL.')
    doc['content'].update(subject=text('subject'),preheader=text('preview'))
    doc['blocks']=[block('heading',text=text('headline')),block('text',text=text('body'))]
    if content['product_block']:
        for product in context.get('products',[])[:12]:
            doc['blocks'].append(block('text',text=str(product.get('title',''))+' × '+str(product.get('quantity',1))+' '+str(product.get('price',''))))
    doc['blocks'].append(block('button',label=text('cta_label'),url=cta))
    # Keep resolved legacy tracking stable; the renderer must not add test UTMs.
    doc.pop('campaign_key')
    result=render_campaign(doc,{**settings(),'logo':logo_url},unsubscribe_url=unsubscribe_url)
    result['subject']=text('subject');result['unsubscribe_url']=unsubscribe_url
    return result
