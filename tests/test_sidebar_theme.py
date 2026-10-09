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
  css=re.sub(r'@media[^{}]+\{', '', css)
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
  at=AppTest.from_file(str(ROOT/'tests/sidebar_preview_app.py'), default_timeout=15).run()
  self.assertFalse(at.exception)
  self.assertEqual(at.session_state['route'],'CRM Campaigns')
  self.assertEqual(at.button(key='sidebar-child::CRM Campaigns').proto.type,'primary')
  at.button(key='sidebar-child::CRM Automations').click().run()
  self.assertFalse(at.exception)
  self.assertEqual(at.session_state['route'],'CRM Automations')
  at.run()
  self.assertEqual(at.button(key='sidebar-child::CRM Automations').proto.type,'primary')
  self.assertEqual(at.session_state['sidebar-open-group'],'email')
 def test_top_level_and_parent_destinations(self):
  at=AppTest.from_file(str(ROOT/'tests/sidebar_preview_app.py'), default_timeout=15).run()
  for key,route in [('sidebar-nav::Orders','Orders'),('sidebar-nav::Prodigi','Prodigi'),('sidebar-disclosure::seo','SEO Overview'),('sidebar-disclosure::email','Email')]:
   at.button(key=key).click().run()
   self.assertFalse(at.exception)
   self.assertEqual(at.session_state['route'],route)

 def test_compact_labels_badges_and_touch_targets(self):
  self.assertIn('--sc-sidebar-width:244px',SIDEBAR_CSS)
  self.assertIn('font-size:14px',SIDEBAR_CSS)
  self.assertIn('white-space:normal',SIDEBAR_CSS)
  self.assertNotIn('text-overflow:ellipsis',SIDEBAR_CSS)
  self.assertIn('padding-right:72px',SIDEBAR_CSS)
  self.assertIn('min-height:44px',SIDEBAR_CSS)
 def test_topbar_measures_width_without_minimum_gutter(self):
  source=(ROOT/'components/sports_cave_top_bar/index.html').read_text(encoding='utf-8')
  self.assertIn('--sc-sidebar-width: 244px',source)
  self.assertNotIn('Math.max(width, 240)',source)
  self.assertIn('getPropertyValue("--sc-sidebar-width") !== value',source)
