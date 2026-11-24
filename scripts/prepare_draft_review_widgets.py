"""Prepare only the existing OS duplicate's review asset; never publish a theme."""
import argparse
import json
from html import escape
from pathlib import Path


def text(value):
    return escape(value).replace('{','&#123;').replace('}','&#125;')


def prepare(source):
    methods=(Path(__file__).resolve().parents[1]/'shopify/reviews/draft-review-methods.js').read_text(encoding='utf-8')
    body=methods.split('class DraftReviewMethods {',1)[1].rsplit('}',1)[0]
    start=min(source.index('  async nativeFeed('),source.index('  async nativePage('))
    end=source.index('  renderMedia() {',start)
    result=source[:start]+body+'\n'+source[end:]
    result=result.replace("first.full.includes('__1777871865832-ultimatemancavedecor__')", "review.id === '813945ea-267e-4f52-ab71-3a2c528ce98f' || first.full.includes('__1777871865832-ultimatemancavedecor__')")
    result=result.replace("this.querySelector('[data-review-form-host]').replaceChildren(frame);", """const status = node('p', '', 'Loading review form…');
        status.setAttribute('role', 'status');
        const fallback = node('a', '', 'Open review form in a new tab');
        fallback.href = url.href; fallback.target = '_blank'; fallback.rel = 'noopener noreferrer';
        fallback.style.cssText = 'display:block;color:inherit;margin:0 0 12px;text-decoration:underline';
        frame.addEventListener('load', () => { status.hidden = true; }, {once:true});
        this.querySelector('[data-review-form-host]').replaceChildren(status, fallback, frame);""")
    return result


def preview(feeds):
    sections=[]
    for country in ('US','AU'):
        rows=list(feeds[country]['featured'])
        priority=['d69b0463-04bc-412c-948a-1636353b3528','013c8326-eeb9-41c0-8a3a-07ee648bcf2a','f0a533af-ce9f-4114-845d-dc003032c337','82212abb-7957-46ff-a819-fea0c3ab6e5e','3cea26d2-792c-42c7-a283-48e1d8cf5c54']
        if country=='US':rows.sort(key=lambda r:priority.index(r['legacy_id']) if r['legacy_id'] in priority else 6)
        else:
            selected=[next((r for r in rows if r['legacy_id']==identity),None) for identity in ['4c91276a-636b-4eae-944a-d9912d65900e','013c8326-eeb9-41c0-8a3a-07ee648bcf2a']]
            rows=[r for r in rows if r not in selected];rows[2:2]=[r for r in selected if r]
        cards=[]
        for index,row in enumerate(rows[:4]):
            image=row['media'][0];rating=max(1,min(5,int(row['rating'])))
            thumbnail='sc-reviews__thumbnail'+(' sc-reviews__thumbnail--rivals' if row['legacy_id']=='4c91276a-636b-4eae-944a-d9912d65900e' else '')
            loading='{% if eager %}eager{% else %}lazy{% endif %}' if index==0 else 'lazy'
            cards.append('<article class="sc-reviews__card"><div class="'+thumbnail+'"><img src="'+escape(image['thumbnail_url'],quote=True)+'" srcset="'+escape(image['thumbnail_url'],quote=True)+' 320w, '+escape(image.get('carousel_url',image['thumbnail_url']),quote=True)+' 640w" sizes="(max-width:767px) 82vw,340px" alt="" loading="'+loading+'" decoding="async" width="'+str(image['width'])+'" height="'+str(image['height'])+'"></div><div class="sc-reviews__card-copy"><span class="sc-reviews__stars" role="img" aria-label="'+str(rating)+' out of 5 stars">'+'★'*rating+'☆'*(5-rating)+'</span>'+('<strong class="sc-reviews__title">'+text(row['title'])+'</strong>' if row['title'] else '')+'<p class="sc-reviews__body">'+text(row['body'])+'</p><div class="sc-reviews__credit"><strong class="sc-reviews__name">'+text(row['reviewer_name'])+'</strong>'+('<span class="sc-reviews__verified"><span class="sc-reviews__tick" aria-hidden="true">✓</span>Verified buyer</span>' if row.get('source_verified') or row.get('verified_purchase') else '')+'</div></div></article>')
        sections.append('\n'.join(cards))
    return '{% doc %}\nInitial OS review cards with Dropbox WebP sources.\n@param {string} country - Visitor country\n@param {boolean} eager - Prioritise the first visible image\n{% enddoc %}\n{% if country == \'US\' %}\n'+sections[0]+'\n{% else %}\n'+sections[1]+'\n{% endif %}\n'


def header_preview(feed):
    summary=feed['summary'];count=int(summary['count']);rating=f"{float(summary['average'] or 0):.2f}"
    share=100*float(rating)/5
    score='<p class="sc-reviews__summary" data-review-summary data-value="'+rating+'/'+str(count)+'"><span class="sc-reviews__summary-star" aria-hidden="true">★★★★★<span class="sc-reviews__summary-fill" style="inline-size:'+str(share)+'%">★★★★★</span></span><strong>'+rating+' / 5</strong>'+str(count)+' reviews</p>'
    histogram='<ul class="sc-reviews__histogram" data-review-histogram aria-label="Rating breakdown">'
    for stars,frequency in feed['histogram']:
        histogram+='<li><span class="sc-reviews__histogram-stars" aria-label="'+str(stars)+' stars">'+'★'*stars+'☆'*(5-stars)+'</span><span class="sc-reviews__histogram-bar" aria-hidden="true" style="--share:'+str(100*frequency/count if count else 0)+'%"></span><span>'+str(frequency)+'</span></li>'
    return '{% doc %}\nLast-known OS review totals, refreshed by the native feed.\n@param {string} part - Summary or histogram\n{% enddoc %}\n{% if part == \'summary\' %}'+score+'{% else %}'+histogram+'</ul>{% endif %}\n'


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--feeds',type=Path)
    args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(prepare(args.source.read_text(encoding='utf-8')),encoding='utf-8')
    if args.feeds:
        feeds=json.loads(args.feeds.read_text(encoding='utf-8'))
        destination=args.output.parent.parent/'snippets/sc-review-os-preview.liquid'
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_text(preview(feeds),encoding='utf-8')
        (destination.parent/'sc-review-os-header.liquid').write_text(header_preview(feeds['AU']),encoding='utf-8')
