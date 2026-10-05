"""Visual-only checkout recovery. Never imported by the live delivery boundary."""
from copy import deepcopy
import re
from crm_abandoned_checkout import BLOCK,block_html,hydrate,dynamic

TOKENS=re.compile(r'\{%.*?%\}|\{\{.*?\}\}',re.S)
CHECKOUT=re.compile(r'\babandoned_checkout\b|\bcheckout\.(?:line_items|url|products)|\bitem\.(?:product_title|variant_title|image_url|quantity|price)',re.I)


def legacy(doc):
    return any((CHECKOUT.search(source) and re.search(r'\{[\{%]',source)) or 'SC_ABANDONED_CHECKOUT' in source for source in sources(doc))


def sources(doc):
    return [s.get('html','') for s in doc.get('middle_sections',[])]+[doc.get('custom_html','')]


def needs_checkout(doc):return dynamic(doc) or legacy(doc)


def sample(doc):
    """Use already selected product facts if present; never fetch or invent prices."""
    item={'title':'Your selected edition','variant':'Large · Black Frame','quantity':1,'image':'','amount':None,'currency':''}
    for section in doc.get('middle_sections',[]):
        if section.get('type')!='catalogue':continue
        for product in section.get('products',[]):
            from crm_campaign_html import email_image_url
            item.update(title=product.get('title') or item['title'],image=email_image_url(product.get('image','')))
            from crm_abandoned_checkout import money
            try:
                amount,currency=money({'amount':product.get('price'),'currencyCode':product.get('currency','')})
                item.update(amount=str(amount),currency=currency)
            except ValueError:pass
            break
        if section.get('products'):break
    return {'preview_only':True,'label':'Sample abandoned checkout','recovery_url':'','items':[item]}


def legacy_html(source,markup):
    """Replace recognized cart loops, not the surrounding authored HTML."""
    def clear(value):
        return re.sub(r'\{[\{%][^<>\n]*(?=<|\n|$)','',TOKENS.sub('',value))
    found=bool((CHECKOUT.search(source) and re.search(r'\{[\{%]',source)) or 'SC_ABANDONED_CHECKOUT' in source)
    if not found:return clear(source),False
    stack=[];ranges=[]
    for token in TOKENS.finditer(source):
        if not token.group().startswith('{%'):continue
        body=token.group()[2:-2].strip();kind=body.split()[0] if body else ''
        if kind in ('for','if','unless'):stack.append((kind,token.start(),token.end(),body,None))
        elif kind in ('else','elsif') and stack:
            if stack[-1][4] is None:stack[-1]=(*stack[-1][:4],token.start())
        elif kind in ('endfor','endif','endunless') and stack and stack[-1][0]==kind[3:]:
            opener=stack.pop()
            if opener[0]=='for' and (CHECKOUT.search(opener[3]) or CHECKOUT.search(source[opener[2]:token.start()])):
                ranges.append((opener[1],token.end(),markup))
            elif opener[0] in ('if','unless') and CHECKOUT.search(opener[3]):
                # Keep the authored true branch. Its cart loop is substituted below.
                if opener[4] is not None:ranges.append((opener[4],token.start(),''))
    # Ignore inner replacements when an enclosing cart loop is already replaced.
    selected=[]
    for start,end,value in sorted(ranges,key=lambda r:(r[0],-r[1])):
        if not any(a<=start and end<=b for a,b,_ in selected):selected.append((start,end,value))
    inserted=any(value==markup for _,_,value in selected)
    for start,end,value in sorted(selected,reverse=True):source=source[:start]+value+source[end:]
    source,count=re.subn(r'<!--\s*SC_ABANDONED_CHECKOUT\s*-->|SC_ABANDONED_CHECKOUT',lambda _:markup,source)
    inserted|=bool(count)
    # Old recovery anchors/images are dynamic content, never retain their unresolved URLs.
    source=re.sub(r'<a\b[^>]*href\s*=\s*[\"\'][^\"\']*\{\{\s*(?:abandoned_checkout|checkout)\.url.*?</a\s*>','',source,flags=re.I|re.S)
    source=re.sub(r'<img\b[^>]*(?:\{\{|\{%)[^>]*>','',source,flags=re.I|re.S)
    source=clear(source)
    if not inserted:source+=markup
    return source,True


def document(doc,data,*,test=False,preview_warnings=None):
    """Render-copy substitution; authored sections/IDs and saved content stay intact."""
    from crm_checkout_migration import migrate
    result=migrate(doc);warning=False;markup=block_html(data,test=test)
    for section in result.get('middle_sections',[]):
        if section.get('type') in ('html','image'):
            section['html'],detected=legacy_html(section['html'],markup);warning|=detected
    if 'middle_sections' in result:
        # Compatibility mirror must follow the substituted source, never render twice.
        result['custom_html']=next((s['html'] for s in result['middle_sections'] if s.get('html_number')==1),'')
    else:result['custom_html'],warning=legacy_html(result.get('custom_html',''),markup)
    return hydrate(result,data,test=test,preview=True,preview_warnings=preview_warnings),warning
