import ast
from contextlib import ExitStack, redirect_stdout
import io
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

import run_migrations


class MigrationConnections(unittest.TestCase):
    def test_every_migration_connection_disables_preparation(self):
        tree = ast.parse(Path(run_migrations.__file__).read_text(encoding='utf-8'))
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute)
                 and isinstance(node.func.value, ast.Name)
                 and node.func.value.id == 'psycopg' and node.func.attr == 'connect']
        self.assertEqual(len(calls), 6)
        for call in calls:
            with self.subTest(line=call.lineno):
                keywords = {keyword.arg: keyword.value for keyword in call.keywords}
                self.assertIn('prepare_threshold', keywords)
                self.assertIsInstance(keywords['prepare_threshold'], ast.Constant)
                self.assertIsNone(keywords['prepare_threshold'].value)

    def deployment(self, post_commit_issues=None):
        connections = [MagicMock(), MagicMock()]
        for conn in connections:
            conn.__enter__.return_value = conn
            conn.cursor.return_value.__enter__.return_value.fetchone.return_value = {'count': 0}
        with ExitStack() as stack:
            stack.enter_context(redirect_stdout(io.StringIO()))
            stack.enter_context(patch.object(run_migrations, 'get_database_url', return_value=('fixture', 'DATABASE_URL')))
            connect = stack.enter_context(patch.object(run_migrations.psycopg, 'connect', side_effect=connections))
            stack.enter_context(patch.object(run_migrations.manual_certificate_schema, 'schema_issues', return_value=[]))
            stack.enter_context(patch.object(run_migrations.crm_schema, 'schema_issues', return_value=[]))
            stack.enter_context(patch.object(run_migrations.support_email_schema, 'schema_issues', side_effect=[[], post_commit_issues or []]))
            if post_commit_issues:
                with self.assertRaisesRegex(RuntimeError, 'Post-commit deployment verification failed'):
                    run_migrations.run_deployment_migrations()
            else:
                run_migrations.run_deployment_migrations()
        self.assertEqual(connect.call_count, 2)
        for call in connect.call_args_list:
            self.assertIn('prepare_threshold', call.kwargs)
            self.assertIsNone(call.kwargs['prepare_threshold'])
            self.assertEqual(call.kwargs['connect_timeout'], 15)
        self.assertEqual(connect.call_args_list[1].kwargs['options'], '-c default_transaction_read_only=on')
        connections[0].commit.assert_called_once()

    def test_deployment_and_post_commit_connections(self):
        self.deployment()

    def test_post_commit_schema_failure_still_fails_closed(self):
        self.deployment(['missing required support email column'])

    def test_shared_verifier_remains_read_only_and_fail_closed(self):
        conn = MagicMock()
        with patch.object(run_migrations, 'get_database_url', return_value=('fixture', 'DATABASE_URL')), \
             patch.object(run_migrations.psycopg, 'connect', return_value=conn) as connect, \
             redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(SystemExit, 'incompatible'):
                run_migrations._verify_schema(issue_loader=lambda cur: ['missing column'],
                                              ready_message='ready', failure_message='incompatible')
        self.assertIsNone(connect.call_args.kwargs['prepare_threshold'])
        self.assertTrue(connect.call_args.kwargs['autocommit'])
        self.assertEqual(connect.call_args.kwargs['options'], '-c default_transaction_read_only=on')
