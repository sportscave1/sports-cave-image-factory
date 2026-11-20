"""Private founding-seller register, stored as one batch per Sydney date."""
import re
import unicodedata
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit
from zoneinfo import ZoneInfo

from marketplace_store import MarketplaceStore, PREFIX, lock, put, read

SYDNEY = ZoneInfo('Australia/Sydney')
FIELDS = ('seller', 'category', 'item', 'source_url', 'contact_url', 'contact_basis')
SHARED = {'facebook.com', 'instagram.com', 'linktr.ee', 'etsy.com', 'ebay.com.au',
          'linkedin.com', 'forms.gle', 'docs.google.com', 'linktree.com', 'gmail.com'}


def clean(row):
    if not isinstance(row, dict):
        raise ValueError('Supply a seller record.')
    result = {}
    for field in FIELDS:
        value = row.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > 1200:
            raise ValueError('Missing or invalid ' + field)
        result[field] = value.strip()
    for field in ('source_url', 'contact_url'):
        url = urlsplit(result[field])
        if url.scheme != 'https' or not url.hostname or '.' not in url.hostname or url.username or url.password:
            raise ValueError('Supply a direct HTTPS link for ' + field)
    return result


def keys(row):
    name = unicodedata.normalize('NFKC', row['seller']).casefold()
    result = {'name:' + re.sub(r'[\W_]+', '', name)}
    for field in ('source_url', 'contact_url'):
        url = urlsplit(row[field])
        host = url.hostname.lower().removeprefix('www.')
        path = url.path.rstrip('/').casefold()
        query = urlencode(sorted((k, v) for k, v in parse_qsl(url.query)
                                 if not k.lower().startswith('utm_') and k not in ('fbclid', 'gclid')))
        shared = any(host == site or host.endswith('.' + site) for site in SHARED)
        if field == 'contact_url':
            result.add('url:' + host + path + ('?' + query if query else ''))
            if not shared:
                result.add('domain:' + host)
        elif shared and host.endswith(('facebook.com', 'instagram.com')):
            result.add('url:' + host + path + ('?' + query if query else ''))
    return result


class OutreachStore(MarketplaceStore):
    def _batches(self, conn):
        return [r['value'] for r in conn.execute(
            'SELECT value FROM crm_runtime_state WHERE key LIKE %s ORDER BY key DESC',
            (PREFIX + 'outreach:day:%',)).fetchall()]

    def history(self):
        with self.db() as conn:
            return self._batches(conn)

    def history_page(self, offset):
        if type(offset) is not int or offset < 0:
            raise ValueError('Supply a non-negative history offset.')
        rows = [dict(row, date=batch['date']) for batch in self.history() for row in batch['sellers']]
        return {'sellers': rows[offset:offset + 50],
                'next_offset': offset + 50 if len(rows) > offset + 50 else None}

    def submit(self, edition):
        today = datetime.now(SYDNEY).date().isoformat()
        if not isinstance(edition, dict) or edition.get('date') != today:
            raise ValueError('Supply the current Sydney date.')
        rows = edition.get('sellers')
        if not isinstance(rows, list) or len(rows) > 20:
            raise ValueError('Supply up to 20 seller records.')
        candidates = [clean(row) for row in rows]
        with self.db() as conn:
            lock(conn, 'outreach')
            key = 'outreach:day:' + today
            batch = read(conn, key, {'date': today, 'sellers': []})
            seen = {identity for day in self._batches(conn) for row in day['sellers']
                    for identity in keys(row)}
            for row in candidates:
                identities = keys(row)
                if len(batch['sellers']) < 20 and seen.isdisjoint(identities):
                    batch['sellers'].append(row)
                    seen.update(identities)
            put(conn, key, batch)
        return batch


def render(st, connect=None):
    batches = OutreachStore(connect).history()
    today = datetime.now(SYDNEY).date().isoformat()
    rows = [dict(Date=b['date'], Seller=r['seller'], Category=r['category'], Item=r['item'],
                 Contact=r['contact_url'], Source=r['source_url'], **{'Contact basis': r['contact_basis']})
            for b in batches for r in b['sellers']]
    links = {k: st.column_config.LinkColumn(k, display_text=label)
             for k, label in [('Contact', 'Message seller'), ('Source', 'View source')]}
    st.subheader('Today’s outreach')
    current = [r for r in rows if r['Date'] == today]
    if current:
        st.dataframe(current, column_config=links, hide_index=True)
    else:
        st.info('No new sellers recorded for today.')
    st.subheader('All sellers')
    if rows:
        st.dataframe(rows, column_config=links, hide_index=True)
    else:
        st.caption('New sellers will appear here after the first delivery.')
