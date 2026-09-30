"""Actionable preflight diagnostics from the same resolved outgoing sections."""
from html.parser import HTMLParser
from urllib.parse import urlsplit
from crm_campaign_html import import_html, email_image_url


def image_reference(value):
    # Never echo query strings, credentials, private hosts, or embedded data.
    from crm_tracking import public_https
    if not public_https(value):
        return '[missing or non-public HTTPS image]'
    p = urlsplit(value)
    return p.hostname + '/…/' + p.path.rsplit('/', 1)[-1][:100]


def html_issues(source, label):
    issues = []
    class Images(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag != 'img': return
            attrs = dict(attrs); src = attrs.get('src') or ''
            ref = image_reference(src)
            if not email_image_url(src):
                issues.append(label + ' · Unsupported image URL: ' + ref + '. Use a durable public HTTPS JPEG/PNG.')
            if not (attrs.get('alt') or '').strip():
                issues.append(label + ' · Missing meaningful ALT text: ' + ref)
    Images().feed(source)
    from crm_campaign_html import TEMPLATE_LINK_TOKENS
    for check, passed in import_html(source, template_links=TEMPLATE_LINK_TOKENS if label.startswith('Footer ') else ())[2].items():
        if not passed and check in ('HTML contains only safe email markup', 'CTA label and HTTPS URL valid'):
            issues.append(label + ' · ' + check)
    return issues


def document_issues(doc, cfg):
    from crm_campaign_sections import with_email_defaults
    from crm_middle_sections import middle_sections
    from crm_catalogue import product_issues
    resolved = with_email_defaults(doc, cfg)
    issues = []
    for section in middle_sections(resolved):
        if not section['visible']: continue
        label = section['type'].title() + ' [' + section['id'] + ']'
        if section['type'] == 'catalogue':
            if not section['products']:
                issues.append(label + ' · No products selected. Add products or hide this section.')
            for product in section['products']:
                for problem in product_issues(product, section['settings']):
                    issues.append(label + ' · ' + product['title'][:120] + ': ' + problem + ' Refresh catalogue before testing.')
        else:
            issues.extend(html_issues(section['html'], label))
    for kind, source in resolved.get('html_sections', {}).items():
        issues.extend(html_issues(source, kind.title() + ' [locked system section]'))
    return issues


def preflight_error(checks):
    failed = [k for k, passed in checks['test'].items() if not passed]
    return 'Complete before testing: ' + '; '.join(failed) + ''.join('\n• ' + issue for issue in checks.get('issues', []))
