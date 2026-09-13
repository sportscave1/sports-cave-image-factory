"""Bounded server-side read model using existing Sports Cave reporting tables."""
from contextlib import contextmanager
from datetime import date
import hashlib
import json
import time

import supabase_backend as backend
from meta_review_analysis import normalize_metrics


@contextmanager
def cursor(write=False):
    with backend.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout='8000ms'")
            if not write:
                cur.execute('SET TRANSACTION READ ONLY')
            yield cur
        if write:
            conn.commit()


def load_history(account_id, since=None, until=None):
    """No Meta I/O, no schema writes. Raise on oversized history instead of truncating silently."""
    result = {}
    with cursor() as cur:
        for key, table in (('accounts', 'meta_ad_accounts'), ('campaigns', 'meta_campaigns'),
                           ('adsets', 'meta_adsets'), ('ads', 'meta_ads'), ('creatives', 'meta_creatives')):
            cur.execute(f'SELECT * FROM {table} WHERE account_id=%s LIMIT 10001', (account_id,))
            result[key] = cur.fetchall()
            if len(result[key]) > 10000:
                raise ValueError('Reporting object limit reached. Use a dedicated account or increase the reviewed limit.')
        for key, table in (('daily', 'meta_ad_insights_daily'), ('assets', 'meta_review_asset_daily')):
            cur.execute(f'SELECT * FROM {table} WHERE account_id=%s AND date BETWEEN %s AND %s ORDER BY date LIMIT 100001',
                        (account_id, since or date(2000, 1, 1), until or date.today()))
            result[key] = cur.fetchall()
            if len(result[key]) > 100000:
                raise ValueError('Too much stored history for one view. Choose a shorter date range.')
        cur.execute('SELECT * FROM ads_product_mapping LIMIT 10001')
        result['mapping'] = cur.fetchall()
        cur.execute('SELECT ad_id,creative_id,raw,observed_at FROM meta_review_creative_observations WHERE account_id=%s ORDER BY observed_at DESC LIMIT 10001', (account_id,))
        result['observations'] = cur.fetchall()
        cur.execute("SELECT * FROM ads_sync_logs WHERE source='meta_review' AND context->>'account_id'=%s ORDER BY started_at DESC LIMIT 20", (account_id,))
        result['logs'] = cur.fetchall()
        cur.execute("SELECT * FROM ads_action_log WHERE action_type IN ('meta_review_selection','meta_review_handoff') AND context->>'account_id'=%s ORDER BY created_at DESC LIMIT 100", (account_id,))
        result['selections'] = cur.fetchall()
    return result


def log_start(account_id, range_label):
    with cursor(True) as cur:
        cur.execute("INSERT INTO ads_sync_logs(source,sync_type,date_range,context) VALUES ('meta_review','manual',%s,%s::jsonb) RETURNING id",
                    (range_label, json.dumps({'account_id': account_id})))
        return cur.fetchone()['id']


def log_failure(log_id, error):
    with cursor(True) as cur:
        cur.execute("UPDATE ads_sync_logs SET status='error',finished_at=now(),error_message=%s WHERE id=%s",
                    (error, log_id))


class WriteBatch:
    """Bounded multi-row INSERTs; no per-insight database round trip."""
    def __init__(self, cur, seconds=90):
        self.cur=cur
        self.groups={}
        self.deadline=time.monotonic()+seconds

    def add(self,sql,args,key_indexes):
        group=self.groups.setdefault(sql,{})
        group[tuple(args[index] for index in key_indexes)]=list(args)

    def flush(self):
        for sql,group in self.groups.items():
            prefix,body=sql.split(' VALUES ',1)
            values,suffix=body.split(' ON CONFLICT ',1)
            rows=list(group.values())
            for offset in range(0,len(rows),100):
                if time.monotonic()>=self.deadline:
                    raise ValueError('Reporting save time limit reached. Retry a smaller range; previous history was retained.')
                chunk=rows[offset:offset+100]
                combined=prefix+' VALUES '+','.join([values]*len(chunk))+' ON CONFLICT '+suffix
                self.cur.execute(combined,[value for row in chunk for value in row])


def _upsert(cur, table, values, keys):
    # Table/column identifiers are internal constants; values always parameterized.
    fields = list(values)
    placeholders = ['%s::jsonb' if isinstance(values[k], (dict, list)) else '%s' for k in fields]
    args = [json.dumps(values[k], default=str) if isinstance(values[k], (dict, list)) else values[k] for k in fields]
    updates = ','.join(f'{key}=EXCLUDED.{key}' for key in fields if key not in keys)
    if table != 'meta_review_asset_daily':
        updates += ',updated_at=now(),synced_at=now()'
    else:
        updates += ',synced_at=now()'
    statement=f"INSERT INTO {table} ({','.join(fields)}) VALUES ({','.join(placeholders)}) ON CONFLICT ({','.join(keys)}) DO UPDATE SET {updates}"
    if isinstance(cur,WriteBatch):
        cur.add(statement,args,[fields.index(key) for key in keys])
    else:
        cur.execute(statement,args)


def save_sync(payload, log_id):
    """One transaction for base reporting, asset rows and successful sync marker."""
    aid = payload['account_id']
    with cursor(True) as cur:
        cur.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', ('meta-review:' + aid,))
        cur.execute("SELECT EXISTS(SELECT 1 FROM ads_sync_logs newer JOIN ads_sync_logs current ON current.id=%s WHERE newer.source='meta_review' AND newer.status='success' AND newer.context->>'account_id'=%s AND newer.started_at>current.started_at) AS superseded", (log_id,aid))
        if (cur.fetchone() or {}).get('superseded') is True:
            raise ValueError('A newer Meta sync already completed. Refresh history instead of overwriting it with this older run.')
        batch=WriteBatch(cur)
        account = payload['account']
        _upsert(batch, 'meta_ad_accounts', {'account_id': aid, 'name': account.get('name'), 'currency': account.get('currency'),
            'timezone_name': account.get('timezone_name'), 'raw': account}, ('account_id',))
        for plural, singular in (('campaigns', 'campaign'), ('adsets', 'adset'), ('ads', 'ad')):
            for row in payload[plural]:
                values = {singular+'_id': str(row['id']), 'account_id': aid, singular+'_name': row.get('name'),
                          'status': row.get('status'), 'effective_status': row.get('effective_status'), 'raw': row}
                values.update(meta_created_at=row.get('created_time'),meta_updated_at=row.get('updated_time'))
                if singular == 'campaign':
                    values['objective'] = row.get('objective')
                if singular != 'campaign':
                    values['campaign_id'] = row.get('campaign_id')
                if singular == 'ad':
                    values['adset_id'] = row.get('adset_id')
                    creative = row.get('creative') or {}
                    values['creative_id'] = creative.get('id')
                    if creative.get('id'):
                        digest = hashlib.sha256(json.dumps(creative,sort_keys=True,default=str).encode()).hexdigest()
                        batch.add('INSERT INTO meta_review_creative_observations(account_id,ad_id,creative_id,content_hash,raw) VALUES (%s,%s,%s,%s,%s::jsonb) ON CONFLICT DO NOTHING',
                                    (aid,row['id'],creative['id'],digest,json.dumps(creative)),[0,1,3])
                        # Reuse the established extraction for compatibility with Creative Refresh history.
                        fields = backend._extract_creative_fields(creative)
                        _upsert(batch, 'meta_creatives', {'creative_id': creative['id'], 'ad_id': row['id'],
                            'account_id': aid, 'name': creative.get('name'), 'thumbnail_url': creative.get('thumbnail_url'),
                            'raw': creative, **fields}, ('creative_id',))
                _upsert(batch, 'meta_'+plural, values, (singular+'_id',))
        admap = {str(a['id']): a for a in payload['ads']}
        for raw in payload['daily']:
            m = normalize_metrics(raw)
            values = {key: raw.get(key) for key in ('campaign_id','campaign_name','adset_id','adset_name','ad_id','ad_name')}
            values.update(date=raw['date_start'], account_id=aid, country='', placement='',
                          raw={**raw, '_review_creative': (admap.get(str(raw['ad_id'])) or {}).get('creative'),
                               '_review_note': 'Creative observed at sync; Meta does not provide historical serving combinations.'})
            for field in ('spend','impressions','clicks','inline_link_clicks','reach','frequency','cpc','cpm','purchases','purchase_value','roas','add_to_cart'):
                values[field] = m.get(field)
            values.update(ctr=m['click_ctr'], cost_per_purchase=m['cpa'], initiate_checkout=m['checkout'])
            _upsert(batch, 'meta_ad_insights_daily', values, ('date','ad_id','country','placement'))
        for row in payload['assets']:
            _upsert(batch, 'meta_review_asset_daily', {**row, 'account_id': aid}, ('account_id','ad_id','date','breakdown','asset_key'))
        batch.flush()
        counts = {key: len(payload[key]) for key in ('campaigns','adsets','ads','daily','assets')}
        counts['creatives']=len({str((ad.get('creative') or {}).get('id')) for ad in payload['ads'] if (ad.get('creative') or {}).get('id')})
        counts['accounts']=1
        cur.execute("UPDATE ads_sync_logs SET finished_at=now(),status='success',rows_fetched=%s,rows_upserted=%s,context=%s::jsonb WHERE id=%s",
                    (sum(counts.values()), sum(counts.values()), json.dumps({'account_id': aid, 'counts': counts,
                     'warnings': payload['warnings'], 'api_version': payload['api_version']}), log_id))
    return counts


def save_selection(context, actor='sports_cave_os', action='meta_review_selection'):
    if action not in ('meta_review_selection', 'meta_review_handoff'):
        raise ValueError('Invalid internal decision action.')
    with cursor(True) as cur:
        cur.execute('INSERT INTO ads_action_log(action_type,status,summary,context,created_by) VALUES (%s,%s,%s,%s::jsonb,%s) RETURNING id',
                    (action, 'saved', 'Meta Review internal creative selection', json.dumps(context, default=str), actor))
        return cur.fetchone()['id']


def load_preferences(account_id):
    """Optional Sports Cave decisions only; never read campaign/reporting snapshots."""
    with cursor() as cur:
        cur.execute("SELECT * FROM ads_action_log WHERE action_type IN ('meta_review_selection','meta_review_handoff') AND context->>'account_id'=%s ORDER BY created_at DESC LIMIT 100", (account_id,))
        selections = cur.fetchall()
        cur.execute('SELECT * FROM ads_product_mapping LIMIT 10001')
        return {'selections': selections, 'mapping': cur.fetchall()}


def load_handoff(token, account_id):
    """Opaque link lookup, constrained to the configured account and handoff type."""
    import re
    if not re.fullmatch(r'[a-f0-9]{32}',str(token)):
        raise ValueError('Invalid saved winner reference.')
    with cursor() as cur:
        cur.execute("SELECT context FROM ads_action_log WHERE action_type='meta_review_handoff' AND context->>'handoff_token'=%s AND context->>'account_id'=%s ORDER BY created_at DESC LIMIT 1",(token,str(account_id).removeprefix('act_')))
        row=cur.fetchone()
    if not row: raise ValueError('Saved winner reference is unavailable for this account.')
    return row['context']


def save_media(data, content_type):
    if not data or len(data) > 8*1024*1024:
        raise ValueError('Winner image is empty or exceeds 8 MiB.')
    digest = hashlib.sha256(data).hexdigest()
    with cursor(True) as cur:
        cur.execute('INSERT INTO meta_review_media(sha256,content_type,data) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING', (digest, content_type, data))
    return digest


def load_media(digest):
    with cursor() as cur:
        cur.execute('SELECT data,content_type FROM meta_review_media WHERE sha256=%s', (digest,))
        row = cur.fetchone()
        return (bytes(row['data']), row['content_type']) if row else (None, None)
