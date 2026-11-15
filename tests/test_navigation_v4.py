"""Execute production disclosure branches without page services."""
import ast
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]

class Rerun(Exception):
    pass

class NavigationV4Tests(TestCase):
    def run_disclosure(self, current, overview):
        tree = ast.parse((ROOT/'app.py').read_text(encoding='utf-8'))
        outer = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                     and n.name == '_render_sidebar_create_growth')
        node = next(n for n in outer.body if isinstance(n, ast.FunctionDef)
                    and n.name == 'disclosure')
        import navigation_runtime
        st = Mock()
        from streamlit.errors import StreamlitAPIException
        st.errors.StreamlitAPIException = StreamlitAPIException
        st.session_state = {}
        st.container.return_value.button.return_value = True
        st.rerun.side_effect = Rerun
        route = Mock()
        toggle = Mock()
        namespace = dict(st=st, current_page=current, open_group='social',
            navigation_runtime=navigation_runtime, set_current_page=route,
            _toggle_sidebar_group=toggle, SIDEBAR_OPEN_GROUP_KEY='sidebar-open-group')
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'app.py', 'exec'), namespace)
        with self.assertRaises(Rerun):
            namespace['disclosure']('social', 'Social Media', 'icon', overview)
        return st, route, toggle

    def test_toggle_reruns_fragment_without_dispatching_a_page(self):
        st, route, toggle = self.run_disclosure('Social Media', 'Social Media')
        toggle.assert_called_once_with('social')
        route.assert_not_called()
        st.rerun.assert_called_once_with(scope='fragment')

    def test_parent_destination_still_requests_a_full_rerun(self):
        st, route, toggle = self.run_disclosure('Orders', 'Social Media')
        route.assert_called_once_with('Social Media', source='sidebar')
        toggle.assert_not_called()
        st.rerun.assert_called_once_with(scope='app')

    def test_current_disclosure_does_not_get_swallowed_by_leaf_deduplication(self):
        source = (ROOT/'components/sports_cave_top_bar/index.html').read_text(encoding='utf-8')
        branch = source[source.index('if (intendedRouteKey === state.config.currentRouteKey)'):]
        self.assertLess(branch.index('st-key-sidebar-disclosure-'), branch.index('event.preventDefault()'))
