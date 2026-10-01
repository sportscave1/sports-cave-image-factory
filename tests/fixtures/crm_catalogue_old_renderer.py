from html import escape
from decimal import Decimal
from crm_catalogue import product_issues,canonical_product_url,amount,price_label
from crm_tracking import campaign_link
def catalogue_html(section, *, campaign_key=''):
    """Compact collector cards; one validated destination for every product link.

    Tracking remains in the shared campaign_link helper. One product-level reference
    keeps image/title/CTA and plaintext identical rather than tracking each anchor
    separately. The stored product URL/facts are never modified by presentation.
    """
    cfg, products = section['settings'], section['products']
    display, cells = cfg['display'], []
    e = lambda v: escape(str(v), quote=True)
    single = cfg['columns'] == 1
    image_height, image_width = (300, 560) if single else (200, 260)
    title_size, title_line = (20, 25) if single else (18, 23)
    for p in products:
        if product_issues(p, cfg):
            continue  # Validation belongs in the editor, never in customer output.
        canonical_url = canonical_product_url(p)
        destination = campaign_link(canonical_url, campaign_key, 'product_' + p['id'].rsplit('/', 1)[-1], test=True) if campaign_key else canonical_url
        link = 'href="' + e(destination) + '" target="_blank" rel="noopener noreferrer"'
        parts = []
        if display['image']:
            # A consistent image well contains the whole artwork without cropping
            # or stretching. Clients without max-height support retain natural ratio.
            parts.append('<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr>'
                '<td align="center" valign="middle" height="' + str(image_height) + '" bgcolor="#f5f3ee" style="height:' + str(image_height) + 'px">'
                '<a ' + link + ' style="display:block;text-decoration:none">'
                '<img src="' + e(p['image']) + '" alt="' + e(p['title']) + '" width="' + str(image_width) + '" border="0" '
                'style="display:block;width:auto;max-width:100%;height:auto;max-height:' + str(image_height) + 'px;margin:0 auto;border:0">'
                '</a></td></tr></table>')
        if display['title']:
            parts.append('<p style="margin:8px 0 4px;font-family:Arial,Helvetica,sans-serif;font-weight:700;font-size:' + str(title_size) + 'px;line-height:' + str(title_line) + 'px">'
                '<a ' + link + ' style="color:#1c1c1a;text-decoration:none">' + e(p['title']) + '</a></p>')
        ed = p['edition']
        if ed:
            if display['limit']:
                parts.append('<p style="margin:0 0 5px;font-size:10px;line-height:14px;letter-spacing:1px;color:#94753c">LIMITED TO ' + str(ed['limit']) + ' WORLDWIDE</p>')
            next_available = display['next'] and ed['remaining'] > 0 and ed['next'] <= ed['limit']
            if next_available:
                parts.append('<p style="margin:0;font-size:16px;line-height:20px;font-weight:700;color:#242422">#' + format(ed['next'], '03d') + ' / ' + str(ed['limit']) + '</p>')
            status = ['NEXT AVAILABLE'] if next_available else []
            if display['remaining']:
                status.append(str(ed['remaining']) + ' REMAINING' if ed['remaining'] else 'SOLD OUT')
            if status:
                parts.append('<p style="margin:0;font-size:10px;line-height:16px;letter-spacing:.4px;color:#6b6a65">' + ' · '.join(status) + '</p>')
        if display['price']:
            price = 'From ' + e(price_label(p))
            if amount(p['compare_at']) and Decimal(p['compare_at']) > Decimal(p['price']):
                price += ' <s style="color:#85837c;font-size:11px;font-weight:400">' + e(price_label({**p, 'price':p['compare_at']})) + '</s>'
            parts.append('<p style="margin:7px 0 9px;font-size:13px;line-height:18px;font-weight:600;color:#353530">' + price + '</p>')
        if display['cta']:
            parts.append('<p style="margin:0"><a ' + link + ' style="display:inline-block;background:#171717;color:#faf8f1;border:1px solid #94753c;padding:9px 13px;font-size:11px;line-height:18px;font-weight:700;letter-spacing:.7px;text-transform:uppercase;text-decoration:none">' + e(cfg['cta']) + '</a></p>')
        cells.append('<td class="sc-stack" width="' + str(100 // cfg['columns']) + '%" valign="top" style="padding:8px 10px 16px;font-family:Arial,Helvetica,sans-serif;font-size:13px;line-height:18px">' + ''.join(parts) + '</td>')
    rows = ['<tr>' + ''.join(cells[i:i + cfg['columns']]) + '</tr>' for i in range(0, len(cells), cfg['columns'])]
    return '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;background:#fff">' + ''.join(rows) + '</table>'
