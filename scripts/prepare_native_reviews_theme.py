"""Patch a pulled duplicate only. No Shopify writes or theme publication."""
from pathlib import Path
import argparse
import json
import re

ROOT=Path(__file__).resolve().parents[1]

def prepare(folder):
    changed=[]
    for path in [*folder.glob('templates/*.json'),folder/'config/settings_data.json']:
        text=path.read_text(encoding='utf-8');data=json.loads(re.sub(r'/\*.*?\*/','',text,flags=re.S))
        def walk(node):
            if isinstance(node,dict):
                blocks=node.get('blocks')
                if isinstance(blocks,dict):
                    removed={k for k,b in blocks.items() if 'shopify://apps/judge-me-reviews/' in b.get('type','')}
                    for k in removed:del blocks[k]
                    if isinstance(node.get('block_order'),list):node['block_order']=[k for k in node['block_order'] if k not in removed]
                for k,v in list(node.items()):
                    if isinstance(v,str):node[k]=v.replace('shop.metafields.judgeme.all_reviews_count','209')
                    else:walk(v)
            elif isinstance(node,list):
                for v in node:walk(v)
        before=json.dumps(data);walk(data)
        if json.dumps(data)!=before:
            path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');changed.append(str(path.relative_to(folder)).replace('\\','/'))
    for path in folder.glob('snippets/*.liquid'):
        text=path.read_text(encoding='utf-8');new=text.replace('shop.metafields.judgeme.all_reviews_count','209')
        if new!=text:path.write_text(new,encoding='utf-8');changed.append(str(path.relative_to(folder)).replace('\\','/'))
    path=folder/'assets/sc-customer-reviews.js';text=path.read_text(encoding='utf-8')
    # Keep all original card, gallery, histogram, dialog and responsive styling.
    start=text.index("        const original = this.directory()?.querySelector('.jdgm-write-rev-link');",text.index("button.matches('[data-review-write]')"))
    end=text.index('\n      }\n    }\n',start)
    text=text[:start]+'''        const url = new URL('https://sports-cave-image-factory.onrender.com/reviews/write');
        if (this.dataset.product) url.searchParams.set('product', this.dataset.product);
        if (!this.formDialog) { window.location.assign(url.href); return; }
        const frame = document.createElement('iframe');
        frame.title = 'Write your Sports Cave review'; frame.src = url.href;
        frame.style.cssText = 'display:block;width:100%;height:65dvh;border:0';
        this.querySelector('[data-review-form-host]').replaceChildren(frame);
        this.formDialog.showModal();
        this.querySelector('[data-review-form-close]').focus({preventScroll:true});'''+text[end:]
    start=text.index("        const original = this.directory()?.querySelector('.jdgm-write-rev-link[aria-expanded=\"true\"]');")
    end=text.index("        this.querySelector('[data-review-write]').focus",start)
    text=text[:start]+"        this.querySelector('[data-review-form-host]')?.replaceChildren();\n"+text[end:]
    start=text.index('    // Judge.me remains available');end=text.index('    if (!this.nativeStarted)',start)
    text=text[:start]+'''    const invitation = this.querySelector('[data-review-invitation]');
    if (invitation) invitation.hidden = false;
    const button = this.querySelector('[data-review-write]');
    if (button) button.hidden = false;
'''+text[end:]
    text+='''
// Refresh the existing title badges from OS without changing their markup or CSS.
fetch('https://sports-cave-image-factory.onrender.com/reviews/public?summary=1')
 .then(r => { if (!r.ok) throw Error(); return r.json(); })
 .then(({summary}) => {
   if (!summary?.count) return;
   document.querySelectorAll('.scx-review-text').forEach(target => {
     const rating=target.querySelector('strong'); if (rating) rating.textContent=Number(summary.average).toFixed(1);
     const last=target.querySelector('span:last-child'); if (last) last.textContent=`${summary.count} reviews`;
   });
 }).catch(() => {});
'''
    path.write_text(text,encoding='utf-8');changed.append('assets/sc-customer-reviews.js')
    path=folder/'sections/sc-customer-reviews.liquid';text=path.read_text(encoding='utf-8')
    text=text.replace('  data-shop=', '  data-product="{{ product.id }}"\n  data-shop=',1)
    text=text.replace('      {% for block in section.blocks %}', '      {% for block in section.blocks %}')
    path.write_text(text,encoding='utf-8');changed.append('sections/sc-customer-reviews.liquid')
    return sorted(set(changed))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('folder',type=Path);args=parser.parse_args()
    print(json.dumps(prepare(args.folder),indent=2))
