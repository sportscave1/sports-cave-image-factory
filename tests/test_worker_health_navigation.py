from pathlib import Path
from streamlit.testing.v1 import AppTest
import navigation_runtime,os_accounts

ROOT=Path(__file__).parents[1]

def test_developer_default_order_and_active_collapse():
    page=AppTest.from_file(str(ROOT/'tests/worker_health_nav_fixture.py'),default_timeout=15).run()
    assert not page.exception
    page.button(key='sidebar-disclosure::developer').click().run()
    assert not page.exception and page.session_state['route']=='Worker Health'
    assert page.button(key='sidebar-child::Worker Health').proto.type=='primary'
    # Keep original owner-only Dev Mode as a separate-tab native link.
    links=page.get('link_button');assert any('Developer%20Studio' in x.proto.url and 'dev_mode=1' in x.proto.url for x in links)
    page.button(key='sidebar-disclosure::developer').click().run()
    assert not page.exception and page.session_state['route']=='Worker Health'
    assert not any(x.key=='sidebar-child::Worker Health' for x in page.button)
    page.button(key='sidebar-disclosure::developer').click().run()
    assert page.button(key='sidebar-child::Worker Health')
    assert navigation_runtime.active_disclosure_group('Worker Health')=='developer'

def test_worker_health_cannot_be_assigned_to_staff_or_replace_owner_dev_mode(monkeypatch):
    admin=dict(role='admin',is_active=True,email='admin@fixture.invalid')
    staff=dict(role='va',is_active=True,page_permissions=['worker_health','developer_studio'])
    assert os_accounts.can_access_page(admin,'Worker Health')
    assert not os_accounts.can_access_page(staff,'Worker Health')
    assert not os_accounts.can_access_page(staff,'Developer Studio')
    assert not os_accounts.PAGE_BY_KEY['worker_health']['worker_assignable']
    assert 'worker_health' not in (ROOT/'orders_page.py').read_text(encoding='utf-8')
