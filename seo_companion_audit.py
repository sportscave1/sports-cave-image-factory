"""Read-only, bounded public-storefront audits for the SEO Companion queue."""
from collections import deque
from html.parser import HTMLParser
import posixpath
import re
import time
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit
import xml.etree.ElementTree as ET

from seo_technical_audit import StorefrontCrawler, RequestBudgetExceeded, audit_html

ORIGIN = 'https://www.sportscaveshop.com'
AGENT = 'SportsCaveSEOCompanion'
MAX_PAGES = 200
MAX_REQUESTS = 240
MAX_SECONDS = 600


def public_url(value, base=ORIGIN):
    parsed = urlsplit(urljoin(base, str(value or '').strip()))
    try:
        valid = (parsed.scheme == 'https' and parsed.hostname in {'www.sportscaveshop.com', 'sportscaveshop.com'}
                 and not parsed.username and not parsed.password and parsed.port in (None, 443))
    except ValueError:
        valid = False
    if not valid:
        raise ValueError('Only public Sports Cave HTTPS URLs are allowed.')
    path = parsed.path or '/'
    safety_path = posixpath.normpath(unquote(unquote(path)).replace('\\', '/'))
    if any(safety_path == prefix or safety_path.startswith(prefix + '/') for prefix in
           ('/admin', '/account', '/cart', '/checkout', '/checkouts', '/apps', '/search', '/password')):
        raise ValueError('Private and transactional storefront paths are excluded.')
    return urlunsplit(('https', 'www.sportscaveshop.com', path, parsed.query, ''))


def page_key(value):
    parsed = urlsplit(public_url(value))
    return parsed.path.rstrip('/') or '/'


def source_url(value):
    try:
        parsed = urlsplit(public_url(value))
    except ValueError:
        return ''
    path = parsed.path
    parts = [part for part in path.split('/') if part]
    in_scope = (not parts or parts in (['collections'], ['blogs'])
                or len(parts) == 2 and parts[0] in ('collections', 'pages')
                or 2 <= len(parts) <= 3 and parts[0] == 'blogs')
    if parsed.query or not in_scope:
        return ''
    return public_url(value)


class Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.current = [], None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a':
            if self.current:
                self.links.append(self.current)
            self.current = {'href': attrs.get('href', ''), 'anchor': ''}
        elif tag == 'img' and self.current:
            self.current['anchor'] += ' ' + attrs.get('alt', '')

    def handle_data(self, data):
        if self.current:
            self.current['anchor'] += data[:500]

    def handle_endtag(self, tag):
        if tag == 'a' and self.current:
            self.current['anchor'] = ' '.join(self.current['anchor'].split())[:300]
            self.links.append(self.current)
            self.current = None


class Robots:
    """Match scoped groups, wildcards and longest rules; allow wins equal-length ties."""
    def __init__(self, lines):
        self.groups = []
        agents, rules, directives = [], [], False
        for line in [*lines, 'user-agent: __end__']:
            text = line.split('#', 1)[0].strip()
            if ':' not in text:
                continue
            field, value = (part.strip() for part in text.split(':', 1))
            field = field.lower()
            if field == 'user-agent':
                if agents and directives:
                    self.groups.append((agents, rules))
                    agents, rules, directives = [], [], False
                agents.append(value.lower())
            elif agents:
                directives = True
                if field in ('allow', 'disallow') and value:
                    rules.append((value, field == 'allow'))
        if agents and rules:
            self.groups.append((agents, rules))

    def can_fetch(self, agent, url):
        path = urlsplit(url).path or '/'
        if urlsplit(url).query:
            path += '?' + urlsplit(url).query
        path = unquote(path)
        groups = [(max((len(a) if a != '*' else 0 for a in agents if a == '*' or a in agent.lower()), default=-1), rules)
                  for agents, rules in self.groups]
        specificity = max((score for score, _ in groups), default=-1)
        matches = []
        for score, rules in groups:
            if score != specificity or score < 0:
                continue
            for pattern, allow in rules:
                pattern = unquote(pattern)
                expression = re.escape(pattern).replace(r'\*', '.*')
                if pattern.endswith('$'):
                    expression = expression[:-2] + '$'
                if re.match(expression, path):
                    matches.append((len(pattern.replace('*', '').rstrip('$')), allow))
        return max(matches, default=(0, True))[1]


class PublicCrawler(StorefrontCrawler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session.headers['User-Agent'] = AGENT + '/1.0 (Sports Cave public link audit)'

    def _request_once(self, method, url, **kwargs):
        if method not in ('GET', 'HEAD'):
            raise ValueError('SEO Companion is read-only.')
        return super()._request_once(method, public_url(url), **kwargs)


def audit(job, *, crawler, progress=lambda value: None, stopped=lambda: False,
          clock=time.monotonic, max_pages=MAX_PAGES, max_seconds=MAX_SECONDS):
    """Never infer absence beyond the checked HTML scope; never write to Shopify."""
    started = clock()
    targets = list(dict.fromkeys(public_url(url) for url in job.get('targets', [])))[:3]
    result = {'checked_at': job.get('started_at'), 'scope': 'Public server-rendered homepage, navigation, collections, blog and editorial HTML; target URLs from the daily report.',
              'targets': [], 'pages': [], 'links': [], 'proposals': [], 'gaps': [],
              'coverage_complete': False, 'storefront_changes': 0, 'report_date': job['date']}
    response = crawler.fetch_page(ORIGIN + '/robots.txt')
    if response.status_code == 404:
        robots = Robots([])
        result['gaps'].append('robots.txt returned 404; no published rules were available.')
    elif response.status_code != 200:
        raise RuntimeError('robots.txt could not be verified; crawl was not started.')
    else:
        robots = Robots(response.text.splitlines())
    queue = deque([ORIGIN + '/', ORIGIN + '/collections', ORIGIN + '/collections/v8-supercars-wall-art'])
    maps = deque([ORIGIN + '/sitemap.xml'])
    visited_maps, discovered = set(), set(queue)
    while maps and len(visited_maps) < 10:
        if stopped():
            raise InterruptedError('Companion stopped; audit can be retried.')
        url = maps.popleft()
        if url in visited_maps:
            continue
        visited_maps.add(url)
        try:
            fetched = crawler.fetch_page(url)
            if fetched.status_code != 200 or len(fetched.text) > 10_000_000:
                raise ValueError('Sitemap unavailable or too large')
            xml = ET.fromstring(fetched.text)
            # Shopify embeds image:loc below image:image. Only entry-level loc
            # elements identify sitemap files or storefront pages.
            for node in (child for entry in xml for child in entry):
                if node.tag.rsplit('}', 1)[-1] != 'loc' or not node.text:
                    continue
                candidate = public_url(node.text)
                if xml.tag.rsplit('}', 1)[-1] == 'sitemapindex':
                    # Product inventory is unnecessary for an inbound editorial-link audit.
                    if '/sitemap_products_' not in candidate:
                        maps.append(candidate)
                elif source_url(candidate) and candidate not in discovered:
                    queue.append(candidate)
                    discovered.add(candidate)
        except (ValueError, ET.ParseError, OSError, RuntimeError) as error:
            result['gaps'].append('Sitemap could not be read: ' + url)
        finally:
            crawler._page_cache.pop(url, None)
    if maps:
        result['gaps'].append('Sitemap discovery reached its ten-file limit.')
    progress({'stage': 'auditing', 'sources_discovered': len(discovered), 'pages_checked': 0})
    for target in targets:
        if stopped():
            raise InterruptedError('Companion stopped.')
        if not robots.can_fetch(AGENT, target):
            result['gaps'].append('robots.txt excluded target: ' + target)
            result['targets'].append({'url': target, 'status': None, 'findings': []})
            continue
        try:
            response = crawler.fetch_page(target)
            final = public_url(response.url)
            result['targets'].append({'url': target, 'status': response.status_code, 'final_url': final,
                'findings': audit_html(target, status_code=response.status_code, headers=response.headers,
                                       html_text=response.text[:2_000_000], final_url=final)})
        except Exception as error:
            result['targets'].append({'url': target, 'status': None, 'findings': []})
            result['gaps'].append('Target could not be checked: ' + target + ' (' + type(error).__name__ + ')')
    target_keys = {page_key(url): url for url in targets}
    seen, link_ids = set(), set()
    while queue and len(result['pages']) < max_pages and clock() - started < max_seconds:
        if stopped():
            raise InterruptedError('Companion stopped.')
        url = queue.popleft()
        if url in seen:
            continue
        seen.add(url)
        if not robots.can_fetch(AGENT, url):
            result['gaps'].append('robots.txt excluded source: ' + url)
            continue
        try:
            response = crawler.fetch_page(url)
            final = public_url(response.url)
            result['pages'].append({'url': url, 'status': response.status_code, 'final_url': final})
            if response.status_code != 200:
                result['gaps'].append('Source returned HTTP ' + str(response.status_code) + ': ' + url)
                continue
            if len(response.text) > 2_000_000:
                result['gaps'].append('HTML was truncated at two million characters: ' + url)
            parser = Links()
            parser.feed(response.text[:2_000_000])
            for link in parser.links:
                try:
                    destination = public_url(link['href'], final)
                except ValueError:
                    continue
                source = source_url(destination)
                if source and source not in discovered and len(discovered) < 2000:
                    discovered.add(source)
                    queue.append(source)
                key = (url, destination, link['anchor'])
                if page_key(destination) in target_keys and key not in link_ids:
                    link_ids.add(key)
                    if len(result['links']) < 500:
                        result['links'].append({'source_url': url, 'anchor': link['anchor'],
                                                'href': link['href'][:1200], 'target_url': destination})
            if len(result['pages']) % 5 == 0:
                progress({'stage': 'auditing', 'pages_checked': len(result['pages']),
                          'sources_discovered': len(discovered), 'matching_links': len(result['links'])})
        except RequestBudgetExceeded:
            queue.appendleft(url)
            result['gaps'].append('Storefront request budget reached.')
            break
        except Exception as error:
            result['gaps'].append('Source could not be checked: ' + url + ' (' + type(error).__name__ + ')')
        finally:
            crawler._page_cache.pop(url, None)
    result['remaining_sources'] = len(queue)
    result['sources_discovered'] = len(discovered)
    result['coverage_complete'] = not queue and not result['gaps']
    if queue:
        result['gaps'].append('Crawl stopped at the page, request or time limit; remaining sources are not checked.')
    if len(discovered) >= 2000 or len(result['links']) >= 500:
        result['gaps'].append('Discovery or link-evidence storage limit reached; results are partial.')
        result['coverage_complete'] = False
    result['gaps'] = list(dict.fromkeys(result['gaps']))[:250]
    result['requests'] = crawler.stats['total_storefront_requests']
    result['duration_seconds'] = round(clock() - started, 1)
    result['proposals'] = proposals(result)
    result['limitations'] = 'No JavaScript-only links, private content, external backlinks, Shopify admin inventory, AU checkout availability or permanent-retirement decision was verified. No storefront write or outreach was performed.'
    result['deferred_work'] = 'This executor checks public HTML, technical observations and inbound links. Keyword research and copy/outreach drafting remain in the daily ChatGPT report; Shopify/admin checks and proposed live edits await review and implementation.'
    return result


def proposals(result):
    fixes = []
    for target in result['targets']:
        links = [r for r in result['links'] if page_key(r['target_url']) == page_key(target['url'])]
        if target['status'] in (404, 410):
            for link in links[:50]:
                fixes.append({'kind': 'broken_internal_link', **link, 'before': link['href'],
                    'proposed_after': 'Remove this buying link, or replace it with an equivalent, available edition after owner confirmation.',
                    'verification_required': 'Confirm retirement and an equivalent replacement, preserve collector facts and anchor intent, then verify HTTP 200, canonical and AU availability. A broad collection redirect is not assumed equivalent.'})
            fixes.append({'kind': 'retirement_review', 'target_url': target['url'],
                'before': 'HTTP ' + str(target['status']) + '; ' + str(len(links)) + ' matching link occurrences in checked HTML.',
                'proposed_after': 'Confirm permanent retirement. Keep the absent-page response if no equivalent replacement exists; propose a redirect only to a verified equivalent edition. No internal link edit is proposed where none was observed.',
                'verification_required': 'Check Shopify status/availability and Search Console/external entry URLs. Absence of links applies only to the recorded crawl scope.'})
        elif target['status'] is None:
            fixes.append({'kind': 'verification_gap', 'target_url': target['url'], 'before': 'Fetch not verified',
                'proposed_after': 'Resolve the recorded fetch or robots restriction and recheck before changing content.',
                'verification_required': 'Successful permitted public fetch; do not infer a broken page from a timeout.'})
    for i, fix in enumerate(fixes):
        fix['id'] = str(i + 1)
        fix['review_status'] = 'Awaiting review'
    return fixes
