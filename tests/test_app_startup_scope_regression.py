import ast
import builtins
import inspect
import time
import unittest
from contextlib import ExitStack, nullcontext
from unittest import mock

import app


STARTUP_ROUTES = (
    "Dashboard",
    "Orders",
    "Prodigi",
    "Edition Ops",
    "Mockups",
    "Product Uploads",
    "Design Studio",
    "Ads",
    "Analytics",
    "SEO",
    "Reporting",
    "Accounts & Access",
)


class AppStartupScopeRegressionTests(unittest.TestCase):
    def run_main_route(self, route):
        state = {
            "sports_cave_authenticated": True,
            "sports_cave_auth_checked_at": time.monotonic(),
            "sports_cave_admin_setup_required": False,
        }
        renderer = mock.Mock()
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(app.st, "session_state", state))
            stack.enter_context(mock.patch.object(app, "init_session_state"))
            stack.enter_context(mock.patch.object(app, "inject_styles"))
            stack.enter_context(mock.patch.object(app, "is_app_authenticated", return_value=True))
            stack.enter_context(mock.patch.object(app, "current_os_user", return_value={"id": "startup-test"}))
            stack.enter_context(mock.patch.object(app, "set_activity_actor"))
            stack.enter_context(mock.patch.object(app, "_dropbox_oauth_pending", return_value=False))
            stack.enter_context(mock.patch.object(app, "get_current_page", side_effect=(route, route)))
            stack.enter_context(mock.patch.object(app, "get_components_module", return_value=object()))
            stack.enter_context(mock.patch.object(app, "asset_data_uri", return_value="data:image/webp;base64,test"))
            stack.enter_context(mock.patch.object(app.top_bar, "render_top_bar"))
            stack.enter_context(mock.patch.object(app.top_bar, "render_planner_data_refresh_bridge"))
            stack.enter_context(mock.patch.object(app.top_bar, "render_navigation_complete"))
            stack.enter_context(mock.patch.object(app, "render_sidebar"))
            stack.enter_context(mock.patch.object(app, "apply_global_search_context"))
            stack.enter_context(mock.patch.object(app, "ensure_current_page_access", return_value=True))
            stack.enter_context(mock.patch.object(app, "page_uses_local_database", return_value=False))
            stack.enter_context(mock.patch.object(app, "render_selected_page", renderer))
            stack.enter_context(mock.patch.object(app, "_finish_navigation_transition"))
            stack.enter_context(mock.patch.object(app, "log_startup_stage"))
            stack.enter_context(mock.patch.object(app, "log_app_memory"))
            stack.enter_context(mock.patch.object(app, "safe_startup_print"))
            app.main()
        renderer.assert_called_once_with(route)

    def test_fresh_authenticated_home_session_does_not_need_mockup_state(self):
        self.run_main_route("Dashboard")

    def test_all_primary_routes_reach_only_the_selected_page_renderer(self):
        for route in STARTUP_ROUTES:
            with self.subTest(route=route):
                self.run_main_route(route)

    def test_every_selected_groups_use_has_an_explicit_owner(self):
        module = ast.parse(inspect.getsource(app))
        selected_group_scopes = []
        for node in ast.walk(module):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            uses_selected_groups = any(
                isinstance(child, ast.Name)
                and child.id == "selected_groups"
                and isinstance(child.ctx, ast.Load)
                for child in ast.walk(node)
            )
            if not uses_selected_groups:
                continue
            argument_names = {argument.arg for argument in node.args.args}
            assigned_names = {
                child.id
                for child in ast.walk(node)
                if isinstance(child, ast.Name)
                and child.id == "selected_groups"
                and isinstance(child.ctx, ast.Store)
            }
            self.assertTrue(
                "selected_groups" in argument_names or "selected_groups" in assigned_names,
                f"{node.name} reads selected_groups without owning or receiving it",
            )
            selected_group_scopes.append(node.name)
        self.assertIn("render_final_zip_download", selected_group_scopes)
        self.assertNotIn("main", selected_group_scopes)

    def test_main_has_no_names_loaded_outside_local_or_module_scope(self):
        module = ast.parse(inspect.getsource(app))
        main_node = next(
            node for node in module.body
            if isinstance(node, ast.FunctionDef) and node.name == "main"
        )
        module_names = set(dir(builtins))
        for node in module.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                module_names.add(node.name)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                module_names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                module_names.update(
                    child.id
                    for target in targets
                    for child in ast.walk(target)
                    if isinstance(child, ast.Name)
                )

        local_names = {argument.arg for argument in main_node.args.args}
        local_names.update(
            node.id
            for node in ast.walk(main_node)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
        )
        local_names.update(
            node.name
            for node in ast.walk(main_node)
            if isinstance(node, ast.ExceptHandler) and node.name
        )
        loaded_names = {
            node.id
            for node in ast.walk(main_node)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
        }
        unresolved = loaded_names - local_names - module_names
        self.assertEqual(set(), unresolved)

    def test_mockup_export_with_no_selected_groups_is_a_safe_no_op(self):
        result = {
            "run_dir": "fresh-mockup-run",
            "product_image_readiness": {
                "complete": False,
                "missing_labels": ["Man Cave", "Office", "Living Room"],
            },
        }
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(app, "normalize_generation_result", return_value=result))
            stack.enter_context(mock.patch.object(app.st, "subheader"))
            stack.enter_context(mock.patch.object(app.st, "caption"))
            stack.enter_context(
                mock.patch.object(
                    app.st,
                    "columns",
                    return_value=[nullcontext() for _ in app.MOCKUPS_ZIP_GROUP_OPTIONS],
                )
            )
            stack.enter_context(mock.patch.object(app.st, "checkbox", return_value=False))
            warning = stack.enter_context(mock.patch.object(app.st, "warning"))
            button = stack.enter_context(mock.patch.object(app.st, "button"))
            app.render_final_zip_download(result)

        warning.assert_called_once_with("Select at least one image group to save or download.")
        self.assertTrue(button.call_args.kwargs["disabled"])

    def test_incomplete_package_allows_only_a_deliberate_partial_group(self):
        result = {
            "run_dir": "partial-mockup-run",
            "assets": [],
            "product_image_manifest": [],
            "product_image_readiness": {
                "complete": False,
                "missing_labels": ["Man Cave", "Office", "Living Room"],
            },
        }

        def render_with_selections(selections):
            factory = mock.Mock()
            factory.order_assets_by_product_manifest.return_value = []
            storage = mock.Mock()
            storage.dropbox_selected_manifest.return_value = []
            with ExitStack() as stack:
                stack.enter_context(mock.patch.object(app, "normalize_generation_result", return_value=result))
                stack.enter_context(mock.patch.object(app.st, "subheader"))
                stack.enter_context(mock.patch.object(app.st, "caption"))
                stack.enter_context(
                    mock.patch.object(
                        app.st,
                        "columns",
                        return_value=[nullcontext() for _ in app.MOCKUPS_ZIP_GROUP_OPTIONS],
                    )
                )
                stack.enter_context(mock.patch.object(app.st, "checkbox", side_effect=selections))
                warning = stack.enter_context(mock.patch.object(app.st, "warning"))
                stack.enter_context(mock.patch.object(app.st, "button"))
                stack.enter_context(mock.patch.object(app, "result_is_dropbox_backed", return_value=True))
                stack.enter_context(mock.patch.object(app, "image_factory", factory))
                stack.enter_context(mock.patch.object(app, "mockup_storage", storage))
                app.render_final_zip_download(result)
                return [str(call.args[0]) for call in warning.call_args_list]

        partial_warnings = render_with_selections([True, False, False])
        self.assertNotIn("The complete product package is not ready", " ".join(partial_warnings))
        self.assertIn("No Dropbox files are available", " ".join(partial_warnings))

        complete_package_warnings = render_with_selections([True, False, True])
        self.assertIn("The complete product package is not ready", " ".join(complete_package_warnings))


if __name__ == "__main__":
    unittest.main()
