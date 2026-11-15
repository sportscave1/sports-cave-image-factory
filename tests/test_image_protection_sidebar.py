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

    def test_admin_visible_only_under_developer_with_shield(self):
        app = self.render()
        self.assertNotIn('Mockups', [b.label for b in app.sidebar.button])
        self.assertNotIn('Image Protection', [b.label for b in app.sidebar.button])
        app.sidebar.button(key='sidebar-disclosure::developer').click().run()
        button = app.sidebar.button(key='sidebar-child::Image Protection')
        self.assertEqual(button.proto.icon, ':material/shield:')
        self.assertEqual([b.label for b in app.sidebar.button].count('Image Protection'), 1)
        self.assertNotIn('sidebar-nav::Image Protection', [b.key for b in app.sidebar.button])

    def test_direct_url_expands_developer(self):
        app = AppTest.from_file(str(FIXTURE))
        app.query_params['page'] = 'Image Protection'
        app.run()
        self.assertFalse(list(app.exception))
        self.assertEqual(app.sidebar.button(key='sidebar-child::Image Protection').proto.type, 'primary')
        self.assertTrue(any('aria-expanded="true"' in m.value and 'Developer navigation' in m.value for m in app.markdown))

    def test_click_refresh_highlight_and_home(self):
        app = self.render()
        app.sidebar.button(key='sidebar-disclosure::developer').click().run()
        app.sidebar.button(key='sidebar-child::Image Protection').click().run()
        self.assertFalse(list(app.exception))
        self.assertEqual(app.title[0].value, 'Image Protection')
        self.assertEqual(app.sidebar.button(key='sidebar-child::Image Protection').proto.type, 'primary')
        app.run()
        self.assertEqual(app.title[0].value, 'Image Protection')
        app.sidebar.button(key='sidebar-nav::Dashboard').click().run()
        self.assertEqual(app.title[0].value, 'Dashboard')

    def test_worker_cannot_see_image_protection(self):
        source = FIXTURE.read_text(encoding='utf-8').replace(
            "'role':'admin'", "'role':'worker'")
        # Keep the fixture's app.py resolution when executing from a string.
        source = source.replace("Path(__file__).resolve().parents[1]",
                                f"Path({str(FIXTURE.resolve().parents[1])!r})")
        app = AppTest.from_string(source).run()
        self.assertFalse(list(app.exception))
        self.assertNotIn('Image Protection', [b.label for b in app.sidebar.button])


if __name__ == '__main__':
    unittest.main()
