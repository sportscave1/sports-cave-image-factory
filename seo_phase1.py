"""Phase 1 adapters. No scheduler, publishing client or production migration."""
from copy import deepcopy
from datetime import date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import os
from dataclasses import replace
from zoneinfo import ZoneInfo
import seo_workspace as workspace
import seo_navigation as nav
import analytics_navigation as anav
import analytics_contracts as contracts

CLOSED = {'Dismissed', 'Done'}
TYPES = ('Content', 'Product / collection', 'Technical fix', 'Internal links', 'Other')
STATUSES = ('Open', 'In progress', 'Deferred', 'Ready for review', 'Done', 'Dismissed')

def local_mode():
    # Explicit development boundary; a configured database never opts into remote writes.
    return os.environ.get('SEO_PHASE1_MODE', 'local') != 'shared'

def store_for_workspace():
    if local_mode():
        return workspace.LocalSEOStore(Path(__file__).parent / '.local' / 'seo-phase1.json')
    return workspace.default_store()

def destination(route):
    return {
        nav.SEO_KEYWORDS_ROUTE: (nav.SEO_ANALYTICS_ROUTE, 'Queries'),
        nav.SEO_LANDING_PAGES_ROUTE: (nav.SEO_ANALYTICS_ROUTE, 'Pages'),
        nav.SEO_MAPPING_ROUTE: (nav.SEO_ANALYTICS_ROUTE, 'Mappings'),
        nav.SEO_OPPORTUNITIES_ROUTE: (nav.SEO_PLAN_ROUTE, None),
        nav.SEO_HEALTH_ROUTE: (nav.SEO_PLAN_ROUTE, 'Technical fix'),
        nav.SEO_BLOG_ROUTE: (nav.SEO_REVIEW_ROUTE, 'Blog projects'),
        anav.ANALYTICS_OVERVIEW_ROUTE: (nav.SEO_ANALYTICS_ROUTE, 'Channels'),
        anav.ANALYTICS_TRAFFIC_ROUTE: (nav.SEO_ANALYTICS_ROUTE, 'Channels'),
        anav.ANALYTICS_PAGES_ROUTE: (nav.SEO_ANALYTICS_ROUTE, 'Engagement'),
        anav.ANALYTICS_ECOMMERCE_ROUTE: (nav.SEO_ANALYTICS_ROUTE, 'Ecommerce'),
        anav.ANALYTICS_REALTIME_ROUTE: (nav.SEO_ANALYTICS_ROUTE, 'Realtime'),
    }.get(route, (route, None))

def event(state, action, target='', *, source='SEO', status='Saved', detail=None):
    return workspace.upsert_record(state, 'workspace_events', {
        'action': action, 'target': target, 'source': source, 'status': status,
        'detail': detail or {}, 'time': workspace.utc_now(),
    })

def create_task(state, *, title, target='', query='', work_type='Content', intent='improve', evidence=None, context=None, actor=None):
    # Keep URL identity intact, including meaningful query parameters. Query intent is distinct.
    from seo_technical_audit import normalize_url
    identity = json.dumps([normalize_url(target) or target.strip(), query.strip().casefold(), work_type, intent], ensure_ascii=False)
    fingerprint = sha256(identity.encode()).hexdigest()
    for row in state.get('plan_items', []):
        if row.get('fingerprint') == fingerprint and row.get('status') not in CLOSED:
            return row, False
    row = workspace.upsert_record(state, 'plan_items', {
        'title': title, 'target': target, 'query': query, 'work_type': work_type,
        'intent': intent, 'fingerprint': fingerprint, 'status': 'Open', 'priority': 'Medium',
        'reason': (evidence or {}).get('explanation') or 'Manually selected for review',
        'evidence': deepcopy(evidence or {}), 'context': deepcopy(context or {}),
        'observed_at': workspace.utc_now(),
    }, actor=actor)
    event(state, 'Task change', row['id'], detail={'change': 'created', 'title': title})
    return row, True

def update_task(state, task, changes, actor=None):
    row = workspace.upsert_record(state, 'plan_items', {**task, **changes}, record_id=task['id'], actor=actor)
    event(state, 'Task change', task['id'], detail=changes)
    return row

def scan(state, rows, context, actor=None):
    import seo_metrics
    created = 0
    evaluated=list(rows[:500])
    for row in evaluated:
        # Rules are opportunity signals, not a diagnosis or a content-type generator.
        impressions = number(row.get('impressions'))
        ctr, position = number(row.get('ctr')), number(row.get('average_position'))
        if impressions is None or impressions < 100 or not ((ctr is not None and ctr < Decimal('.02')) or (position is not None and 11 <= position <= 20)):
            continue
        query = str(row.get('query') or '')
        if not query:
            continue
        target = row.get('page') or row.get('current_page') or ''
        evidence = {**row, **seo_metrics.opportunity_score(row), 'source': 'GSC'}
        evidence['explanation'] = 'At least 100 impressions; CTR below 2% or position 11–20. Review intent and existing page before choosing a change.'
        _, added = create_task(state, title=f'Review search opportunity: {query}', target=target,
            query=query, work_type='Other', intent='search-opportunity', evidence=evidence, context=context, actor=actor)
        created += int(added)
    event(state, 'Opportunity scan', source='GSC', status='Completed', detail={'rows_evaluated': len(evaluated), 'rows_available':len(rows), 'tasks_created': created, 'context': context})
    return created

def number(value):
    return None if value is None or value == '' else Decimal(str(value))

def gsc_totals(rows):
    if not rows:
        return {'clicks': None, 'impressions': None, 'ctr': None}
    clicks = sum((number(r['clicks']) for r in rows), Decimal(0))
    impressions = sum((number(r['impressions']) for r in rows), Decimal(0))
    return {'clicks': clicks, 'impressions': impressions, 'ctr': clicks / impressions if impressions else None}

def ga4_contract(scope, dimensions=()):
    filters = () if scope == 'All channels' else (('sessionDefaultChannelGroup', 'EXACT', 'Organic Search'),)
    if scope == 'Google organic':
        filters += (('sessionSource', 'EXACT', 'google'),)
    return contracts.GA4ReportContract('seo_phase1_' + '_'.join(dimensions), scope, 'SEO Analytics', tuple(dimensions),
        ('sessions', 'ecommercePurchases', 'purchaseRevenue'), 'session / attributed event', (), 25000,
        'GA4 property currency; attributed purchase revenue', filters=filters)

def filters_for_ga4(market, device):
    result = []
    if market != 'All markets':
        result.append(('countryId', 'EXACT', {'Australia':'AU', 'United States':'US', 'United Kingdom':'GB'}[market]))
    if device != 'All devices':
        result.append(('deviceCategory', 'EXACT', device.lower()))
    return tuple(result)

def period(days=28, *, through=None, today=None):
    today = today or datetime.now(ZoneInfo('America/Los_Angeles')).date()
    end = min(date.fromisoformat(str(through)) if through else today - timedelta(days=3), today - timedelta(days=3))
    return end - timedelta(days=days-1), end

def revision(record):
    return sha256(json.dumps(record, sort_keys=True, default=str).encode()).hexdigest()

def review_decision(state, record, decision, actor=None):
    saved = workspace.upsert_record(state, 'review_decisions', {'target': record['id'], 'revision': revision(record), 'decision': decision}, actor=actor)
    event(state, 'Review decision', record['id'], detail=saved)
    return saved

def valid_decision(state, record):
    matches = [r for r in state.get('review_decisions', []) if r['target'] == record['id'] and r['revision'] == revision(record)]
    return matches[-1]['decision'] if matches else 'Needs review'


class LocalBlogProjects:
    """Existing Blog v2 project interface, persisted beside the local Plan."""
    is_local = True
    def __init__(self, store):
        self.store = store
    def list_projects(self, *, owner_id='', include_all=False, limit=50):
        return [r for r in self.store.load()['blog_projects'] if include_all or r.get('owner_id') == owner_id][:limit]
    def save_project(self, project):
        state = self.store.load()
        row = workspace.upsert_record(state, 'blog_projects', project, record_id=project.get('project_id',''))
        row['project_id'] = row['id']
        self.store.save(state)
        return row
    def list_shopify_targets(self, limit=500):
        return self.store.load()['target_library'][:limit]
    def record_event(self, project_id, *, actor_id, actor_name, action_type, idempotency_key, metadata=None):
        state = self.store.load()
        if any(r.get('event_key') == project_id + ':' + idempotency_key for r in state['workspace_events']):
            return False
        saved = event(state, 'Draft/proposal change', project_id, detail={'action': action_type, **(metadata or {})})
        saved['event_key'] = project_id + ':' + idempotency_key
        self.store.save(state)
        return True


class LocalResearch:
    def __init__(self, evidence=None):
        self.evidence = evidence or {}
    def reporting_context(self):
        return {'available': bool(self.evidence), 'status': 'local_evidence', 'through_date': self.evidence.get('context',{}).get('end',''), 'gsc_site_url':'', 'watermark':''}
    def query_page(self, *args, **kwargs):
        rows = self.evidence.get('rows',[])
        return {'rows': rows[:kwargs.get('limit',25)], 'total':len(rows)}
    def overview_base(self, *args, **kwargs):
        return {}
    def landing_pages(self, *args, **kwargs):
        return {'rows':[], 'total':0}


def saved_health(reader):
    return reader._query_all('technical', """SELECT canonical_url, source, severity, issue_summary,
        correction_steps, status, checked_at FROM seo_technical_url_audits_v2
        WHERE workspace_key=%s ORDER BY last_seen_at DESC LIMIT 500""", ('sports-cave',))


def import_health(state, findings, actor=None):
    count = 0
    for row in findings:
        if str(row.get('status','')).casefold() in {'resolved','dismissed','fixed'}:
            continue
        _, added = create_task(state, title=row.get('issue_summary') or 'Review technical finding',
            target=row.get('canonical_url',''), work_type='Technical fix',
            intent=str(row.get('source','')) + ':' + str(row.get('issue_summary','')),
            evidence=row, context={'source':'Saved technical audit','observed_at':row.get('checked_at')},actor=actor)
        count += int(added)
    return count


def import_saved_work(state, *, tasks=(), recommendations=(), actor=None):
    """Thin references preserve source IDs; source workflows remain the owners of execution."""
    added = 0
    sources = [('growth_task', r) for r in tasks] + [('recommendation',r) for r in recommendations]
    sources += [('draft', r) for r in state.get('blog_records',[]) if not r.get('archived_at')]
    sources += [('link_plan', r) for r in state.get('link_plans',[]) if not r.get('archived_at')]
    for source, item in sources:
        ref = source + ':' + str(item['id'])
        if any(r.get('source_ref') == ref or (source=='draft' and r.get('draft_id')==item['id']) for r in state['plan_items']):
            continue
        row, created = create_task(state, title=item.get('title') or item.get('article_title') or item.get('recommended_action') or item.get('source_blog') or 'Review saved work',
            target=item.get('target_page') or item.get('target_url') or item.get('recommended_page') or item.get('current_page') or '',
            query=item.get('target_keyword') or item.get('primary_keyword') or '',
            work_type='Content' if source=='draft' else 'Internal links' if source=='link_plan' else 'Other',
            intent=ref, evidence=item, actor=actor)
        row['source_ref'] = ref
        row['admin_only'] = source=='growth_task' and item.get('status') not in {'approved','assigned','in_progress','completed','measuring','measured'}
        if source=='draft': row['draft_id'] = item['id']
        added += int(created)
    return added


def read_saved_events(backend, *, actor_id='', admin=False):
    """Read existing streams independently, without schema preparation or write calls."""
    events, errors = [], []
    streams = (
        ('SEO audit', "SELECT id, created_at, event_type AS action, source, reason AS target, new_value AS detail FROM audit_logs WHERE (source ILIKE '%%seo%%' OR event_type ILIKE '%%seo%%') AND (%s OR new_value->'metadata'->>'actor_id'=%s) ORDER BY created_at DESC LIMIT 200", (admin,actor_id)),
        ('Data sync', "SELECT id, created_at, source, status, property_identifier AS target, error_summary, rows_received, completed_at FROM seo_sync_runs WHERE workspace_key=%s ORDER BY created_at DESC LIMIT 100", ('sports-cave',)),
        ('Blog project', "SELECT e.id, e.created_at, e.action_type AS action, e.project_id AS target, e.safe_metadata AS detail FROM seo_blog_project_events_v2 e JOIN seo_blog_projects_v2 p ON p.project_id=e.project_id WHERE p.workspace_key=%s AND (%s OR p.owner_id=%s) ORDER BY e.created_at DESC LIMIT 100", ('sports-cave',admin,actor_id)),
    )
    for source, sql, params in streams:
        try:
            with backend.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql,params)
                    rows=list(cur.fetchall())
            for row in rows:
                events.append({'id':source+':'+str(row['id']), 'time':str(row.get('created_at') or ''),
                    'action':'Data refresh' if source=='Data sync' else 'Draft/proposal change' if source=='Blog project' else row.get('action') or 'SEO activity',
                    'source':row.get('source') or source, 'target':row.get('target') or '',
                    'status':row.get('status') or (row.get('detail') or {}).get('status') or 'Recorded', 'detail':workspace._json_safe(row)})
        except Exception:
            errors.append(source)
    return events, errors
