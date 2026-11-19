"""Pure text assembly for manual prompt testing. No AI client or network calls."""
import json
import re
from urllib.parse import urlsplit

WORKFLOWS = {'Design': ('New design', 'Refresh', 'Edit design'), 'Upload': ('Upload',), 'Ads': ('Ads',)}


def build_prompt(text, workflow, item):
    """Preserve the entire draft and apply only known product placeholders."""
    context = dict(item.get('context') or {})
    title = item.get('title', '').strip()
    url = context.get('product_url') or context.get('url') or ''
    if urlsplit(title).scheme in ('http', 'https'):
        url, title = title, context.get('title') or ''
    if not url and context.get('handle'):
        url = 'https://www.sportscaveshop.com/products/' + context['handle']
    values = {k: str(v) for k, v in context.items()
              if v is not None and isinstance(v, (str, int, float)) and str(v)}
    if title:
        values.update(product_name=title, product_title=title, title=title)
    if url:
        values.update(product_url=url, product_page_url=url)
    if context.get('details'):
        values['product_details'] = context['details']
    values = {k.lower(): v for k, v in values.items()}
    # One substitution pass: values containing braces are never interpreted again.
    applied = re.sub(r'\{\{([A-Za-z_][\w]*)\}\}|(?<!\{)\{([A-Za-z_][\w]*)\}(?!\})',
                     lambda m: values.get((m[1] or m[2]).lower(), m[0]), text)
    lines = ['WORKFLOW: ' + workflow, 'PRODUCT / DESIGN TO APPLY']
    if title:
        lines.append('Product name: ' + title)
    if url:
        lines.append('Product URL: ' + url)
    if context:
        lines.append('Product details / selected suggestion:\n' + json.dumps(context, ensure_ascii=False, indent=2, default=str))
    lines.append('Apply the following full prompt to this product/design. Use the supplied context for matching placeholders; do not invent missing facts.')
    return '\n\n'.join(lines) + '\n\nFULL PROMPT\n\n' + applied
