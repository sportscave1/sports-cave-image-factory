"""Actionable preflight diagnostics from the same resolved outgoing sections."""
from html.parser import HTMLParser
from urllib.parse import urlsplit
import re
from crm_campaign_html import import_html, email_image_url


class CampaignValidationError(ValueError):
    """Expected authoring state, kept structured across the send boundary."""
    def __init__(self, checks):
        self.checks = checks
        super().__init__('Campaign content needs attention before testing.')


def structured_issues(doc, cfg):
    from crm_campaign_sections import with_email_defaults
    from crm_middle_sections import middle_sections
    from crm_catalogue import product_issues
    resolved = with_email_defaults(doc, cfg)
    sections = middle_sections(resolved) + [dict(id=kind, type=kind, visible=True, html=source)
        for kind, source in resolved.get('html_sections', {}).items()]
    result = []
    for section in sections:
        if not section['visible']: continue
        kind = section['type']
        label = ('HTML Section '+str(section['html_number']) if kind=='html' else
                 'System '+kind.title() if kind in ('header','footer') else kind.title())
        base = dict(section_id=section['id'], section_type=kind, display_label=label,
                    editable=kind not in ('header','footer'))
        def add(issue_type, message, count=1, **extra):
            result.append(dict(base, issue_type=issue_type, message=message, count=count, **extra))
        if kind == 'catalogue':
            if not section['products']:
                add('empty_catalogue','No products selected. Add products or hide this section.')
            for product in section['products']:
                problems=product_issues(product,section['settings'])
                if problems:add('catalogue_facts',product['title'][:120]+': '+ ' '.join(problems)+' Refresh catalogue.')
            continue
        images=[]
        class Images(HTMLParser):
            def handle_starttag(self, tag, attrs):
                if tag=='img':images.append(dict(attrs))
        Images().feed(section['html'])
        bad_url=[];bad_alt=[];affected=set()
        for index, image in enumerate(images):
            src=image.get('src') or ''
            detail={'image':index+1,'asset_reference':image_reference(src)}
            if not email_image_url(src):bad_url.append(detail);affected.add(index)
            if not (image.get('alt') or '').strip():bad_alt.append(detail);affected.add(index)
        if bad_url:add('image_source','missing or unsupported image URLs',len(bad_url),assets=bad_url,image_count=len(affected))
        if bad_alt:add('image_alt','missing ALT texts',len(bad_alt),assets=bad_alt,image_count=len(affected))
        from crm_campaign_html import TEMPLATE_LINK_TOKENS
        checks=import_html(section['html'],template_links=TEMPLATE_LINK_TOKENS if kind=='footer' else ())[2]
        if not checks['HTML contains only safe email markup']:add('markup','Unsafe or malformed HTML. Review this section.')
        if not checks['CTA label and HTTPS URL valid']:add('link','Link needs a public HTTPS destination.')
    return result


def issue_groups(checks):
    groups={}
    for issue in checks.get('section_issues',[]):
        group=groups.setdefault(issue['section_id'],dict(section_id=issue['section_id'],display_label=issue['display_label'],
            editable=issue['editable'],image_count=0,messages=[]))
        group['image_count']=max(group['image_count'],issue.get('image_count',0))
        message=(str(issue['count'])+' '+issue['message']) if issue['issue_type'] in ('image_source','image_alt') else issue['message']
        if message not in group['messages']:group['messages'].append(message)
    return list(groups.values())


def image_reference(value):
    # Never echo query strings, credentials, private hosts, or embedded data.
    from crm_tracking import public_https
    if re.fullmatch(r'ICON_URL_[A-Z_]{1,40}',value):return value+' (placeholder)'
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
