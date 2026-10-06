"""Render the actual app sidebar helpers, rather than testing registry strings."""
from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest


FIXTURE = Path(__file__).with_name('sidebar_preview_app.py')


class ImageProtectionSidebarTests(unittest.TestCase):
    def render(self):
        app = AppTest.from_file(str(FIXTURE)).run()
        self.assertFalse(list(app.exception))
        return app

    def test_admin_visible_first_level_order_and_shield(self):
        app = self.render()
        labels = [button.label for button in app.sidebar.button
                  if not str(button.key).startswith(('sidebar-history::', 'sidebar-child::'))]
        start = labels.index('Reviews')
        self.assertEqual(labels[start:start + 5],
                         ['Reviews', 'Email', 'Image Protection', 'Reporting', 'Accounts & Access'])
        button = app.sidebar.button(key='sidebar-nav::Image Protection')
        self.assertEqual(button.proto.icon, ':material/shield:')
        self.assertEqual(labels.count('Image Protection'), 1)

    def test_click_refresh_highlight_and_home(self):
        app = self.render()
        app.sidebar.button(key='sidebar-nav::Image Protection').click().run()
        self.assertFalse(list(app.exception))
        self.assertEqual(app.title[0].value, 'Image Protection')
        self.assertEqual(app.sidebar.button(key='sidebar-nav::Image Protection').proto.type, 'primary')
        app.run()
        self.assertEqual(app.title[0].value, 'Image Protection')
        app.sidebar.button(key='sidebar-nav::Dashboard').click().run()
        self.assertEqual(app.title[0].value, 'Dashboard')

    def test_worker_cannot_see_image_protection(self):
        source = FIXTURE.read_text(encoding='utf-8').replace(
            "'role':'admin'", "'role':'worker'")
        # Keep the fixture's app.py resolution when executing from a string.
        source = source.replace("Path(__file__).resolve().parents[1]", repr(str(FIXTURE.resolve().parents[1])) + ' and Path(' + repr(str(FIXTURE.resolve().parents[1])) + ')')
        app = AppTest.from_string(source).run()
        self.assertFalse(list(app.exception))
        self.assertNotIn('Image Protection', [b.label for b in app.sidebar.button])


if __name__ == '__main__':
    unittest.main()
