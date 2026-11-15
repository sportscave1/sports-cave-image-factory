"""Isolated loopback PostgreSQL fixtures. Never reads application credentials."""
from contextlib import ExitStack, contextmanager
from uuid import uuid4
from unittest.mock import patch

import psycopg
from psycopg.rows import dict_row
import supabase_backend as backend
import sports_cave_dashboard as dashboard

USER = {"id": "design-v4-test", "username": "fixture", "display_name": "Fixture User",
        "role": "admin", "is_active": True, "page_permissions": []}


def connect():
    return psycopg.connect(host="127.0.0.1", port=55492, user="design_v4_test",
                           dbname="postgres", row_factory=dict_row,
                           options="-c search_path=design_v4_fixture -c statement_timeout=15000")


@contextmanager
def local_backend():
    with ExitStack() as stack:
        stack.enter_context(patch.object(backend, "connect", connect))
        stack.enter_context(patch.object(backend, "is_configured", return_value=True))
        stack.enter_context(patch.object(dashboard, "get_supabase_backend", return_value=backend))
        yield


def initialize():
    with connect() as conn:
        conn.execute("CREATE SCHEMA IF NOT EXISTS design_v4_fixture")
    with local_backend(), patch.object(backend, "_DASHBOARD_SCHEMA_READY", False), patch.object(backend, "_SCHEMA_READY", False):
        backend.ensure_dashboard_schema()


def seed(title, *, section=dashboard.DESIGN_TASK_GROUP, status="open", sport="Motorsport"):
    task_id = str(uuid4())
    metadata = {"design_details": {"design_title": title, "sport": sport,
                "principal_subject_one": "Fixture Driver", "season_era": "1980",
                "event_moment": "Fixture championship", "priority": "High"},
                "artwork_file": "unchanged-fixture-artwork.png", "shopify_product_id": "fixture-product"}
    with connect() as conn:
        conn.execute("""INSERT INTO dashboard_tasks(id,title,section,status,design_style,metadata)
                     VALUES (%s,%s,%s,%s,'motorsport_driver_car',%s::jsonb)""",
                     (task_id, title, section, status, backend.json_dumps(metadata)))
    dashboard.clear_task_cache()
    return task_id
