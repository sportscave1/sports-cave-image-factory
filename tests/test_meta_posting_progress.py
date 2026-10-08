import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest


class ProgressViewTests(unittest.TestCase):
    def test_submission_immediate_progress_and_url_restoration(self):
        path = Path(__file__).with_name('meta_posting_progress_fixture.py')
        app = AppTest.from_file(str(path), default_timeout=20).run()
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertIn('Creating your Meta ads', [item.value for item in app.subheader])
        identity = app.query_params['meta_posting_job']
        restored = AppTest.from_file(str(path), default_timeout=20)
        restored.query_params['meta_posting_job'] = identity
        restored.run()
        self.assertFalse(restored.exception)
        self.assertIn('Creating your Meta ads', [item.value for item in restored.subheader])
        app.button[1].click().run()  # Release the test-only service gate.


if __name__ == '__main__': unittest.main()
