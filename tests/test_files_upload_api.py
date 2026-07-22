from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import files_upload_api


ROOT = Path(__file__).resolve().parents[1]
TEAM_ROOT = "/Sportscave Team Folder"


class DropboxChunkUploadManagerTests(unittest.TestCase):
    def setUp(self):
        self.manager = files_upload_api.DropboxChunkUploadManager()
        self.user = {
            "id": "user-1",
            "display_name": "Nathan",
            "email": "hello@sportscave.com.au",
        }

    def start_upload(self, *, size=10, relative_path="All Rise - Judge.psd", conflict="cancel"):
        destination = f"{TEAM_ROOT}/{relative_path}"
        resolved = {"path": destination, "mode": "add"}
        with patch.object(
            files_upload_api.dropbox_integration,
            "ensure_relative_folders",
        ), patch.object(
            files_upload_api.dropbox_integration,
            "resolve_upload_destination",
            return_value=resolved,
        ):
            return self.manager.start(
                access_token="short-lived-token",
                root_path=TEAM_ROOT,
                current_path=TEAM_ROOT,
                relative_path=relative_path,
                size=size,
                conflict=conflict,
                user=self.user,
            )

    def test_180_6_mb_psd_is_accepted_without_allocating_the_file(self):
        file_size = int(180.6 * 1024 * 1024)

        result = self.start_upload(size=file_size)

        self.assertEqual(result["size"], file_size)
        self.assertEqual(result["state"], "ready")
        self.assertEqual(result["offset"], 0)

    def test_large_upload_uses_bounded_dropbox_session_chunks(self):
        upload = self.start_upload(size=10)
        with patch.object(
            files_upload_api.dropbox_integration,
            "start_upload_session",
            return_value="session-1",
        ) as start_session, patch.object(
            files_upload_api.dropbox_integration,
            "append_upload_session",
            return_value=8,
        ) as append_session, patch.object(
            files_upload_api.dropbox_integration,
            "finish_upload_session",
            return_value={
                ".tag": "file",
                "id": "id:judge",
                "name": "All Rise - Judge.psd",
                "path_display": f"{TEAM_ROOT}/All Rise - Judge.psd",
                "size": 10,
            },
        ) as finish_session:
            first = self.manager.append(
                upload["upload_id"], upload["upload_secret"], 0, b"0123"
            )
            second = self.manager.append(
                upload["upload_id"], upload["upload_secret"], 4, b"4567"
            )
            completed = self.manager.append(
                upload["upload_id"],
                upload["upload_secret"],
                8,
                b"89",
                final=True,
            )

        start_session.assert_called_once_with("short-lived-token", b"0123")
        append_session.assert_called_once_with(
            "short-lived-token", "session-1", 4, b"4567"
        )
        finish_session.assert_called_once_with(
            "short-lived-token",
            "session-1",
            8,
            b"89",
            f"{TEAM_ROOT}/All Rise - Judge.psd",
            mode="add",
        )
        self.assertEqual(first["offset"], 4)
        self.assertEqual(second["offset"], 8)
        self.assertEqual(completed["state"], "completed")
        self.assertEqual(completed["offset"], 10)

    def test_one_request_cannot_exceed_the_memory_bounded_chunk_size(self):
        upload = self.start_upload(size=files_upload_api.FILES_UPLOAD_CHUNK_BYTES + 1)

        with self.assertRaises(files_upload_api.FilesUploadError) as caught:
            self.manager.append(
                upload["upload_id"],
                upload["upload_secret"],
                0,
                b"x" * (files_upload_api.FILES_UPLOAD_CHUNK_BYTES + 1),
            )

        self.assertEqual(caught.exception.status_code, 413)

    def test_interrupted_upload_can_retry_from_the_saved_offset(self):
        upload = self.start_upload(size=8)
        with patch.object(
            files_upload_api.dropbox_integration,
            "start_upload_session",
            side_effect=[RuntimeError("connection lost"), "session-1"],
        ) as start_session:
            with self.assertRaises(files_upload_api.FilesUploadError):
                self.manager.append(
                    upload["upload_id"], upload["upload_secret"], 0, b"0123"
                )
            failed = self.manager.status(upload["upload_id"], upload["upload_secret"])
            resumed = self.manager.append(
                upload["upload_id"], upload["upload_secret"], 0, b"0123"
            )

        self.assertEqual(failed["state"], "failed")
        self.assertEqual(failed["offset"], 0)
        self.assertEqual(resumed["offset"], 4)
        self.assertEqual(start_session.call_count, 2)

    def test_dropbox_confirmed_offset_is_used_after_an_interrupted_response(self):
        upload = self.start_upload(size=8)
        offset_error = files_upload_api.dropbox_integration.DropboxApiError(
            "incorrect_offset"
        )
        offset_error.correct_offset = 6
        with patch.object(
            files_upload_api.dropbox_integration,
            "start_upload_session",
            return_value="session-1",
        ), patch.object(
            files_upload_api.dropbox_integration,
            "append_upload_session",
            side_effect=offset_error,
        ):
            self.manager.append(
                upload["upload_id"], upload["upload_secret"], 0, b"01"
            )
            with self.assertRaises(files_upload_api.FilesUploadError) as caught:
                self.manager.append(
                    upload["upload_id"], upload["upload_secret"], 2, b"2345"
                )

        self.assertEqual(caught.exception.code, "offset_mismatch")
        self.assertEqual(caught.exception.details["offset"], 6)
        status = self.manager.status(upload["upload_id"], upload["upload_secret"])
        self.assertEqual(status["offset"], 6)
        self.assertEqual(status["state"], "uploading")

    def test_multiple_uploads_have_independent_progress_records(self):
        first = self.start_upload(size=100, relative_path="first.psd")
        second = self.start_upload(size=200, relative_path="second.psd")

        self.assertNotEqual(first["upload_id"], second["upload_id"])
        self.assertEqual(self.manager.status(first["upload_id"], first["upload_secret"])["size"], 100)
        self.assertEqual(self.manager.status(second["upload_id"], second["upload_secret"])["size"], 200)

    def test_nested_folder_upload_preserves_relative_path(self):
        relative = "Campaign/Source/All Rise - Judge.psd"
        destination = f"{TEAM_ROOT}/{relative}"
        with patch.object(
            files_upload_api.dropbox_integration,
            "ensure_relative_folders",
        ) as ensure_folders, patch.object(
            files_upload_api.dropbox_integration,
            "resolve_upload_destination",
            return_value={"path": destination, "mode": "add"},
        ):
            result = self.manager.start(
                access_token="short-lived-token",
                root_path=TEAM_ROOT,
                current_path=TEAM_ROOT,
                relative_path=relative,
                size=10,
                conflict="cancel",
                user=self.user,
            )

        ensure_folders.assert_called_once_with(
            "short-lived-token", TEAM_ROOT, "Campaign/Source"
        )
        self.assertEqual(result["relative_path"], relative)
        self.assertEqual(result["destination"], destination)

    def test_conflict_cancel_keep_both_and_replace_remain_explicit(self):
        with patch.object(
            files_upload_api.dropbox_integration,
            "resolve_upload_destination",
            return_value=None,
        ):
            with self.assertRaises(files_upload_api.FilesUploadError) as caught:
                self.manager.start(
                    access_token="short-lived-token",
                    root_path=TEAM_ROOT,
                    current_path=TEAM_ROOT,
                    relative_path="existing.psd",
                    size=10,
                    conflict="cancel",
                    user=self.user,
                )
        self.assertEqual(caught.exception.code, "name_conflict")

        for conflict, mode, suffix in (
            ("keep_both", "add", "existing (1).psd"),
            ("replace", "overwrite", "existing.psd"),
        ):
            destination = f"{TEAM_ROOT}/{suffix}"
            with self.subTest(conflict=conflict), patch.object(
                files_upload_api.dropbox_integration,
                "resolve_upload_destination",
                return_value={"path": destination, "mode": mode},
            ):
                result = self.manager.start(
                    access_token="short-lived-token",
                    root_path=TEAM_ROOT,
                    current_path=TEAM_ROOT,
                    relative_path="existing.psd",
                    size=10,
                    conflict=conflict,
                    user=self.user,
                )
                self.assertEqual(result["destination"], destination)
                self.assertEqual(result["mode"], mode)

    def test_files_permission_is_checked_before_an_upload_starts(self):
        request = SimpleNamespace(cookies={"sports_cave_auth": "signed-cookie"})
        user = {**self.user, "role": "worker", "is_active": True}
        with patch.object(
            files_upload_api.sc_auth,
            "validate_user_auth_token",
            return_value=(True, "", {"sub": "user-1"}),
        ), patch.object(
            files_upload_api.os_accounts.DEFAULT_STORE,
            "get_user",
            return_value=user,
        ), patch.object(
            files_upload_api.os_accounts,
            "can_access_page",
            return_value=False,
        ), patch.object(
            files_upload_api.sc_auth,
            "validate_auth_token",
            return_value=(False, ""),
        ):
            with self.assertRaises(files_upload_api.FilesUploadError) as caught:
                files_upload_api._request_user(request)

        self.assertEqual(caught.exception.code, "access_denied")


class FilesChunkUploaderSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        cls.component_source = (
            ROOT / "components" / "files_chunk_uploader" / "index.html"
        ).read_text(encoding="utf-8")

    def test_old_streamlit_20mb_files_limit_is_removed(self):
        config = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
        files_upload = self.app_source[
            self.app_source.index("def _render_files_chunk_uploader") : self.app_source.index(
                "\n\ndef _render_files_command_bar"
            )
        ]

        self.assertNotIn("maxUploadSize", config)
        self.assertNotIn("20MB per file", self.component_source)
        self.assertNotIn("st.file_uploader", files_upload)
        self.assertIn("Large files supported", self.component_source)

    def test_browser_sends_only_bounded_chunks_and_shows_progress_rows_immediately(self):
        self.assertIn("const CHUNK_BYTES = 8 * 1024 * 1024", self.component_source)
        self.assertIn("row.file.slice(row.uploaded, end)", self.component_source)
        self.assertIn("state.rows.push(...rows)", self.component_source)
        self.assertLess(
            self.component_source.index("state.rows.push(...rows)"),
            self.component_source.index("drainQueue()", self.component_source.index("function addFiles")),
        )
        self.assertIn("Uploading ${percent}%", self.component_source)
        self.assertIn('class="spinner"', self.component_source)
        self.assertIn("const MAX_CONCURRENT = 2", self.component_source)

    def test_failure_retry_remove_and_resume_are_present(self):
        self.assertIn("Upload failed", self.component_source)
        self.assertIn("data-retry", self.component_source)
        self.assertIn("data-remove", self.component_source)
        self.assertIn("uploadStatus(row)", self.component_source)
        self.assertIn('row.errorCode === "upload_missing"', self.component_source)

    def test_folder_upload_drag_drop_and_conflicts_remain_available(self):
        self.assertIn("webkitdirectory", self.component_source)
        self.assertIn("walkEntry", self.component_source)
        self.assertIn("relativePath", self.component_source)
        self.assertIn('value="cancel"', self.component_source)
        self.assertIn('value="keep_both"', self.component_source)
        self.assertIn('value="replace"', self.component_source)

    def test_complete_files_workspace_is_the_drop_target(self):
        self.assertIn(
            'parentDocument.querySelector(".st-key-files-explorer")',
            self.component_source,
        )
        self.assertIn(
            'workspace.addEventListener("dragenter", binding.onDragEnter)',
            self.component_source,
        )
        self.assertIn(
            'workspace.addEventListener("dragover", binding.onDragOver)',
            self.component_source,
        )
        self.assertIn(
            'workspace.addEventListener("drop", binding.onDrop)',
            self.component_source,
        )
        self.assertIn("event.preventDefault()", self.component_source)
        self.assertIn('event.dataTransfer.dropEffect = "copy"', self.component_source)
        self.assertIn("sc-files-workspace-drop-overlay", self.component_source)
        self.assertIn(
            "Drop to upload to ${currentFolderName(state.workspaceDragDestination)}",
            self.component_source,
        )

    def test_external_file_drag_uses_depth_counter_and_does_not_affect_other_pages(self):
        self.assertIn('includes("Files")', self.component_source)
        self.assertIn("state.workspaceDragDepth += 1", self.component_source)
        self.assertIn(
            "state.workspaceDragDepth = Math.max(0, state.workspaceDragDepth - 1)",
            self.component_source,
        )
        self.assertIn("if (state.workspaceDragDepth === 0) resetWorkspaceDrag()", self.component_source)
        self.assertIn("const isActive = () => (", self.component_source)
        self.assertIn(
            'parentDocument.querySelector(".st-key-files-explorer") === workspace',
            self.component_source,
        )
        self.assertIn("cleanupWorkspaceDropTarget", self.component_source)

    def test_drop_destination_is_captured_and_survives_folder_navigation(self):
        self.assertIn(
            'state.workspaceDragDestination = String(state.args.current_path || "")',
            self.component_source,
        )
        self.assertIn("destinationPath: String(destinationPath", self.component_source)
        self.assertIn("current_path: row.destinationPath", self.component_source)
        self.assertIn(
            "addFiles(await droppedItems(transfer), destination)",
            self.component_source,
        )
        self.assertIn('key="files-chunk-uploader"', self.app_source)
        self.assertNotIn(
            'key=_files_widget_key("files-chunk-uploader", current_path)',
            self.app_source,
        )

    def test_workspace_drop_reuses_folder_traversal_and_chunked_upload(self):
        self.assertIn("droppedItems(transfer)", self.component_source)
        self.assertIn("webkitGetAsEntry", self.component_source)
        self.assertIn("walkEntry", self.component_source)
        self.assertIn("relativePath", self.component_source)
        self.assertIn("row.file.slice(row.uploaded, end)", self.component_source)
        self.assertIn("const CHUNK_BYTES = 8 * 1024 * 1024", self.component_source)

    def test_files_drop_styling_is_scoped_to_the_files_list(self):
        files_css = self.app_source[
            self.app_source.index(".st-key-files-explorer") : self.app_source.index(
                ".sc-task-card"
            )
        ]
        self.assertIn(".st-key-files-details-list.sc-files-drop-active", files_css)
        self.assertIn(".sc-files-workspace-drop-overlay", files_css)
        self.assertIn("pointer-events: none", files_css)
        self.assertNotIn("body.sc-files-drop-active", files_css)

    def test_completion_invalidates_only_the_captured_destination_cache(self):
        handler = self.app_source[
            self.app_source.index("def _render_files_chunk_uploader") : self.app_source.index(
                "\n\ndef _render_files_command_bar"
            )
        ]
        self.assertIn("_files_clear_directory_cache(event_path)", handler)
        self.assertIn("path_is_within_root(event_path, root_path)", handler)
        self.assertNotIn('pop("files_directory_cache"', handler)
        self.assertIn("_files_fragment_rerun()", handler)

    def test_files_navigation_still_uses_fragment_callbacks(self):
        browser = self.app_source[
            self.app_source.index("@st.fragment\ndef _render_files_browser") : self.app_source.index(
                "\n\ndef render_files_page"
            )
        ]
        self.assertIn("@st.fragment", browser)
        self.assertIn("_files_directory_entries(access_token, current_path)", browser)
        self.assertNotIn("href=", browser)

    def test_custom_upload_routes_run_with_the_streamlit_app(self):
        server_source = (ROOT / "sports_cave_server.py").read_text(encoding="utf-8")
        api_source = (ROOT / "files_upload_api.py").read_text(encoding="utf-8")
        render_source = (ROOT / "render.yaml").read_text(encoding="utf-8")
        self.assertIn('App("app.py", routes=routes)', server_source)
        self.assertIn("python sports_cave_server.py", render_source)
        self.assertIn("record_activity_log", api_source)
        self.assertIn('"files_uploaded"', api_source)
        self.assertIn('actor=actor', api_source)


if __name__ == "__main__":
    unittest.main()
