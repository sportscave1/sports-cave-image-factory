"""Home shell must render without Planner bootstrap or Files backend work."""
import ast
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import home_daily_planner
import daily_planner

ROOT = Path(__file__).resolve().parents[1]

class HomeShellLazyTests(unittest.TestCase):
    def test_summary_is_markup_only_and_greeting_is_escaped(self):
        st = Mock()
        with patch.object(home_daily_planner, 'compact_planner_config', side_effect=AssertionError('bootstrap')), patch.object(home_daily_planner, '_component_source', side_effect=AssertionError('UI loaded')):
            for hour, expected in [(4,'Good night'),(5,'Good morning'),(11,'Good morning'),(12,'Good afternoon'),(16,'Good afternoon'),(17,'Good night')]:
                home_daily_planner.render_status(st, {'role':'admin','display_name':'<Nathan>'}, datetime(2026,9,30,hour))
                markup=st.markdown.call_args.args[0]
                self.assertIn(expected + ', &lt;Nathan&gt;', markup)
                self.assertIn('type="button" hidden', markup)
                self.assertNotIn("Today's Plan",markup)
                self.assertNotIn('iframe',markup)
        home_daily_planner.render_status(st, {'role':'worker','display_name':'Worker'}, datetime.now())
        self.assertNotIn('id="sc-home-active-planner"',st.markdown.call_args.args[0])

    def test_real_home_render_never_mounts_planner_or_files(self):
        source=(ROOT/'app.py').read_text(encoding='utf-8')
        tree=ast.parse(source)
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='render_lightweight_dashboard_page')
        from contextlib import nullcontext
        namespace={'time':SimpleNamespace(perf_counter=lambda:0),'current_os_user':lambda:{'role':'admin'},
          'account_local_now':lambda user:datetime.now(),'sports_sales_calendar':SimpleNamespace(sydney_date=lambda now:now.date()),
          'sports_cave_dashboard':SimpleNamespace(load_calendar_events=lambda:[]),
          'st':SimpleNamespace(container=lambda **kwargs:nullcontext()),'home_daily_planner':SimpleNamespace(render_status=Mock()),
          'render_active_upcoming_events':Mock(),'render_home_weekly_work':Mock(),'safe_startup_print':Mock()}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'app.py','exec'),namespace)
        namespace[node.name]()
        namespace['home_daily_planner'].render_status.assert_called_once()
        namespace['render_home_weekly_work'].assert_called_once()
        sidebar=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='render_sidebar')
        self.assertNotIn('files_window_launcher',ast.get_source_segment(source,sidebar))
        self.assertNotIn('files-window-launcher-slot',source)

    def test_planner_document_read_is_lazy(self):
        daily_planner._client_source.cache_clear()
        with patch.object(Path,'read_text',return_value='planner document') as read:
            self.assertEqual(daily_planner._client_source(),'planner document')
            self.assertEqual(daily_planner._client_source(),'planner document')
            read.assert_called_once()
        daily_planner._client_source.cache_clear()

if __name__=='__main__':unittest.main()
