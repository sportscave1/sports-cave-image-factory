import ast
from pathlib import Path
import unittest
from streamlit.testing.v1 import AppTest
from sidebar_theme import SIDEBAR_CSS

ROOT=Path(__file__).resolve().parents[1]
class SidebarThemeTests(unittest.TestCase):
 def test_all_theme_selectors_are_sidebar_scoped(self):
  import re
  css=re.sub(r'/\*.*?\*/','',SIDEBAR_CSS,flags=re.S)
  for rule in css.split('}'):
   if '{' not in rule:continue
   selectors=rule.split('{')[0]
   for selector in selectors.split(','):
    self.assertTrue(selector.strip().startswith('section[data-testid="stSidebar"]'),selector)
 def test_no_extra_controls_or_route_logic_in_theme(self):
  self.assertNotIn('Collapse',SIDEBAR_CSS)
  self.assertNotIn('Build. Create.',SIDEBAR_CSS)
  self.assertNotIn('set_current_page',SIDEBAR_CSS)
 def test_child_route_active_and_refresh(self):
  at=AppTest.from_file(str(ROOT/'tests/sidebar_preview_app.py')).run()
  self.assertFalse(at.exception)
  self.assertEqual(at.session_state['route'],'CRM Campaigns')
  self.assertEqual(at.button(key='sidebar-child::CRM Campaigns').proto.type,'primary')
  at.button(key='sidebar-child::CRM Automations').click().run()
  self.assertFalse(at.exception)
  self.assertEqual(at.session_state['route'],'CRM Automations')
  at.run()
  self.assertEqual(at.button(key='sidebar-child::CRM Automations').proto.type,'primary')
  self.assertEqual(at.session_state['sidebar-open-group'],'crm')
 def test_top_level_and_parent_destinations(self):
  at=AppTest.from_file(str(ROOT/'tests/sidebar_preview_app.py')).run()
  for key,route in [('sidebar-nav::Orders','Orders'),('sidebar-nav::Prodigi','Prodigi'),('sidebar-disclosure::seo','SEO Overview'),('sidebar-disclosure::crm','CRM Campaigns')]:
   at.button(key=key).click().run()
   self.assertFalse(at.exception)
   self.assertEqual(at.session_state['route'],route)
