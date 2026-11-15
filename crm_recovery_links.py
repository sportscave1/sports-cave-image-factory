"""One recipient-owned destination, shared by authored and native recovery actions.

This module performs no network requests and cannot create checkouts. The live
caller supplies the engine's freshly verified checkout, never editor state.
"""
from copy import deepcopy
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlsplit
import re

TOKEN = 'SC_CHECKOUT_RECOVERY_URL'


def sources(doc):
    if 'middle_sections' in doc:
        return [s.get('html', '') for s in doc['middle_sections'] if s.get('visible')]
    return [doc.get('custom_html', '')]


def present(doc):
    return any(TOKEN in s for s in sources(doc))


def pasted(doc):
    return any(checkout_url(u) for s in sources(doc) for u in inspect(s).urls)


def checkout_url(value):
    from crm_tracking import public_https
    return public_https(value) and bool(re.search(r'/checkouts?/', urlsplit(value).path))


def destination(data, discount=None):
    original = (data or {}).get('recovery_url', '')
    if not checkout_url(original):
        raise ValueError('Verified original checkout recovery URL unavailable. No email was sent.')
    if discount:
        if discount.get('original_url') != original or not discount.get('url'):
            raise ValueError('Discount checkout identity mismatch. Revalidate before sending.')
        # The existing discount verifier owns eligibility and URL construction.
        return discount['url']
    return original


class Links(HTMLParser):
    def __init__(self, url=None, disabled=False):
        super().__init__(convert_charrefs=False)
        self.url, self.disabled = url, disabled
        self.parts, self.anchors, self.urls = [], [], []
        self.action_content = []
        self.current_action = None
        self.visibility = []

    @property
    def actions(self): return sum(self.action_content)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        hidden=bool(self.visibility and self.visibility[-1][1]) or bool(re.search(r'(?:display\s*:\s*none|visibility\s*:\s*hidden)',values.get('style') or '',re.I))
        if tag not in ('img','br','hr','meta','link','input'):self.visibility.append((tag,hidden))
        if tag == 'a':
            if self.anchors: raise ValueError('Nested email links are not supported. Use one action per image or button.')
            href = values.get('href', '')
            recovery = href == TOKEN or (self.disabled and checkout_url(href))
            if recovery:
                self.current_action = len(self.action_content)
                self.action_content.append(False)
                if self.disabled: tag = 'span'; values.pop('href', None); values.pop('target', None)
                elif self.url is not None: values['href'] = self.url
            self.anchors.append(tag)
            if tag == 'a': self.urls.append(values.get('href', ''))
        if tag == 'img' and not hidden and self.current_action is not None and values.get('src') and values.get('alt'):
            self.action_content[self.current_action] = True
        for key, value in values.items():
            if TOKEN in (value or '') and not (tag == 'a' and key == 'href' and value == TOKEN):
                raise ValueError('Use SC_CHECKOUT_RECOVERY_URL as the complete link destination.')
        self.parts.append('<' + tag + ''.join(' ' + k + '="' + escape(v or '', quote=True) + '"' for k, v in values.items()) + '>')

    def handle_endtag(self, tag):
        for i in range(len(self.visibility)-1,-1,-1):
            if self.visibility[i][0]==tag:del self.visibility[i:];break
        if tag == 'a' and self.anchors:
            tag = self.anchors.pop(); self.current_action = None
        self.parts.append('</' + tag + '>')

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in ('img', 'br', 'hr', 'meta', 'link', 'input'): self.handle_endtag(tag)

    def handle_data(self, data):
        if TOKEN in data: raise ValueError('Recovery placeholders belong in link destinations, not visible copy.')
        if data.strip() and self.current_action is not None and not (self.visibility and self.visibility[-1][1]): self.action_content[self.current_action] = True
        self.parts.append(data)

    def handle_entityref(self, name): self.parts.append('&' + name + ';')
    def handle_charref(self, name): self.parts.append('&#' + name + ';')
    def handle_comment(self, data): self.parts.append('<!--' + data + '-->')


def inspect(source):
    parser = Links(); parser.feed(source); parser.close()
    return parser


def resolve(doc, data=None, *, test=False, offline=False):
    result = deepcopy(doc)
    disabled = test or offline or bool((data or {}).get('preview_only'))
    url = None if disabled or not present(doc) else destination(data)
    def replace(source):
        parser = Links(url, disabled); parser.feed(source); parser.close()
        return ''.join(parser.parts)
    if 'middle_sections' in result:
        for s in result['middle_sections']:
            if s.get('type') in ('html', 'image'):
                s['html'] = replace(s['html']) if s['visible'] else ''
        result['custom_html'] = next((s['html'] for s in result['middle_sections'] if s.get('html_number') == 1), '')
    else: result['custom_html'] = replace(result.get('custom_html', ''))
    return result


def verify(message, url, expected):
    """Run after the shared sanitizer/tracker; no alternate checkout can escape."""
    parser = inspect(message['html'])
    recovery = [v for v in parser.urls if checkout_url(v)]
    if expected < 1 or len(recovery) != expected or any(v != url for v in recovery):
        raise ValueError('Recovery link verification failed after rendering. No email was sent.')
    if TOKEN in message['html'] or TOKEN in message['text']:
        raise ValueError('Unresolved checkout recovery link. No email was sent.')
