"""Controlled sources for REAL renderer benchmarks. Never connect externally."""
from contextlib import contextmanager
from datetime import date
from pathlib import Path
import ast
import os
import time
import types
from functools import lru_cache

ROOT = Path(__file__).resolve().parents[2]


def block_external_sources():
    # A benchmark process has no need for production configuration.
    for key in list(os.environ):
        if any(word in key.upper() for word in ('DATABASE', 'SUPABASE', 'SHOPIFY', 'META_', 'IMAP', 'SMTP', 'RESEND', 'DROPBOX')):
            os.environ.pop(key, None)
    os.environ['SPORTS_CAVE_DB_PATH'] = str(ROOT / 'tmp/navigation-v5/evidence/disposable.db')
    import requests
    def denied(*args, **kwargs):
        raise RuntimeError('External I/O forbidden in navigation V5 benchmark')
    requests.sessions.Session.request = denied
    import supabase_backend
    supabase_backend.connect = denied
    import smtplib, imaplib
    smtplib.SMTP_SSL.__init__ = denied
    smtplib.SMTP.__init__ = denied
    imaplib.IMAP4_SSL.__init__ = denied
    imaplib.IMAP4.__init__ = denied


@lru_cache(maxsize=2)
def app_definitions(before=False):
    path = ROOT / ('tmp/navigation-v5/before/app.py' if before else 'app.py')
    tree = ast.parse(path.read_text(encoding='utf-8'))
    # Execute definitions, not main(), dotenv loading or application startup.
    nodes = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom,
             ast.FunctionDef, ast.ClassDef, ast.Assign, ast.AnnAssign))]
    return compile(ast.Module(body=nodes, type_ignores=[]), str(ROOT / 'app.py'), 'exec')


@lru_cache(maxsize=8)
def variant_module(name, before):
    if not before:
        import importlib
        return importlib.import_module(name)
    path = ROOT / 'tmp/navigation-v5/before' / (name + '.py')
    module = types.ModuleType('v5_before_' + name)
    module.__file__ = str(ROOT / (name + '.py'))
    exec(compile(path.read_text(encoding='utf-8'), module.__file__, 'exec'), module.__dict__)
    return module


class Sources:
    def __init__(self, state):
        self.state = state
        self.reads = state.setdefault('v5_reads', [])
        self.delay = float(os.environ.get('SC_V5_SOURCE_DELAY', '.04'))

    def read(self, name):
        started = time.perf_counter()
        time.sleep(self.delay)
        self.reads.append({'name': name,
            'ms': (time.perf_counter() - started) * 1000})

    def schema(self):
        self.read('database.schema')
        return {'configured': True, 'ready': True}

    def connect(self):
        return FakeConnection(self)


class FakeConnection:
    def __init__(self, source):
        self.source = source
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def cursor(self):
        return FakeCursor(self.source)


class FakeCursor:
    def __init__(self, source):
        self.source = source
        self.sql = ''
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def execute(self, sql, params=()):
        self.sql = ' '.join(sql.split())
        if not self.sql.upper().startswith('SELECT'):
            raise AssertionError('Benchmark permits SELECT only')
        self.source.read('database.data')
    def fetchone(self):
        if 'html_snapshot' in self.sql or 'FROM activity_report_archives' in self.sql:
            return {'id': 'v5-archive', 'report_date': str(date.today()),
                'html_snapshot': '<p>Controlled staff report</p>', 'text_snapshot': 'Staff report',
                'csv_content': 'Staff,Actions\nTest,3', 'subject': 'Controlled report',
                'status': 'sent', 'report_summary': {}, 'csv_filename': 'fixture.csv'}
        return {}
    def fetchall(self):
        if 'FROM activity_report_archives' in self.sql:
            return [self.fetchone()]
        return []


def install_email_sources(page, state, source):
    from tests.email_v2_fixtures import MailboxFixture, CONFIG, fixture_smtp
    from support_email_workspace import Workspace
    from support_email_compose import default_settings
    import support_email_store as store
    import support_email_smtp as smtp
    class Mailbox(MailboxFixture):
        def discover_folders(self):
            source.read('imap.folders')
            return super().discover_folders()
        def list_headers(self, *args, **kwargs):
            source.read('imap.headers')
            return super().list_headers(*args, **kwargs)
        def read_message(self, *args, **kwargs):
            source.read('imap.body')
            return super().read_message(*args, **kwargs)
    mailbox = state.setdefault('v5_mailbox', Mailbox(30))
    def settings(*args):
        source.read('database.email-settings')
        return default_settings(), None
    store.load_email_settings = settings
    store.load_metadata = lambda *args: {}
    store.load_orders = lambda *args: []
    store.load_assignees = lambda *args: []
    store.audit = lambda *args, **kwargs: None
    page.load_configuration = lambda: CONFIG
    page.load_smtp_configuration = lambda: smtp.SMTPConfiguration(password='fixture-only')
    page.Workspace = lambda inner, user, config, smtp_config: Workspace(inner, user,
        config, smtp_config, imap=mailbox, smtp=fixture_smtp(), registry=smtp.SendRegistry())
    return CONFIG


def install_reporting_sources(page, reports, source):
    from unittest.mock import Mock
    import daily_activity_reporting as daily
    import sports_cave_dashboard as dashboard
    page.reporting_store = reports
    reports._backend = lambda: Mock(is_configured=lambda: True, connect=source.connect)
    # Keep backend identity stable for the scope check.
    backend = reports._backend()
    reports._backend = lambda: backend
    reports.schema_status = source.schema
    daily.collect_report_snapshot = lambda **kwargs: {'report_date': str(date.today()),
        'summary': {'total_actions': 3, 'staff_with_activity': 1, 'active_staff_count': 1,
            'daily_execution_completed': 2, 'daily_execution_outstanding': 0, 'attention_count': 0},
        'staff': [], 'attention': [], 'social_media': {}}
    # Controlled empty data, not replacement renderer functions.
    dashboard.list_daily_execution_history_page = lambda *a, **k: {'rows': [], 'has_next': False, 'has_previous': False}
    dashboard.build_reporting_staff_week_snapshot = lambda *a, **k: {'staff_rows': [], 'details': []}
    dashboard.list_human_work_entries_page = lambda *a, **k: {'rows': [], 'has_next': False, 'has_previous': False}
    dashboard.load_twelve_week_progress = lambda *a, **k: {'weeks': [], 'months': []}


def install_operational_sources(state, source):
    """Keep Orders and Edition Ops renderers/fragments; replace their read boundary."""
    from types import SimpleNamespace
    from copy import deepcopy
    import orders_page as orders
    import edition_ops as editions
    rows = state.setdefault('v5_order_rows', [dict(order=f'#SC{3000+i}',
        shopify_order_id=str(3000+i), shopify_line_item_id=str(6000+i),
        allocation_index=1, edition_number=i+1, edition_total=100,
        customer=f'Synthetic Collector {i}', product=f'Synthetic Artwork {i}',
        variant='Black / 60 x 90 cm', shipping='Standard',
        processed_at='2026-10-08T10:00:00Z', prodigi_status='') for i in range(50)])
    def order_read(search='', limit=50):
        source.read('database.orders')
        return {'rows': orders._filter_rows(rows, search) if search else deepcopy(rows),
            'source': 'controlled', 'order_count': 50, 'search': search}
    def marker(**kwargs):
        source.read('database.orders-marker')
        return {'marker': 'v5-controlled-v1'}
    orders._configured_supabase_backend = lambda: SimpleNamespace(orders_visibility_marker=marker)
    orders._read_orders_snapshot = order_read
    editions._configured_supabase_backend = lambda: SimpleNamespace()
    products = state.setdefault('v5_edition_rows', [editions._normalise_row(dict(
        edition_product_id=str(i+1), shopify_product_gid=f'gid://shopify/Product/{i+1}',
        edition_run_id=f'00000000-0000-0000-0000-{i+1:012d}', run_status='active',
        product_title=f'Synthetic Artwork {i+1:03d}', handle=f'artwork-{i+1}',
        edition_label='Original Edition', edition_enabled=True, edition_total=100,
        edition_next_number=10, edition_sold_count=9, edition_remaining=91)) for i in range(100)])
    def edition_read():
        source.read('database.editions')
        return {'rows': deepcopy(products), 'original_rows': deepcopy(products),
            'source': 'controlled', 'cached': False}
    editions._load_snapshot = edition_read
    editions._write_snapshot = lambda *a, **k: None
