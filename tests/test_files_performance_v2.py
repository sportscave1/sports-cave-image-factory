"""Offline behavioural contracts for Files V2; no provider credentials or original artwork."""
import asyncio
import json
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import files_upload_api as api
from tests.test_files_window import get_request

ROOT = "/Synthetic Files"
USER = {"id":"test-worker", "role":"worker", "is_active":True, "page_permissions":["files"]}
CONTEXT = {"access_token":"synthetic", "root_path":ROOT}

class FilesPerformanceV2Tests(unittest.TestCase):
    def setUp(self):
        api.invalidate_directory_cache()
        api._PREVIEW_CACHE.clear()
        api._DIRECTORY_PAGE_RESULTS.clear()
        self.auth = patch.object(api, "_request_user", return_value=USER)
        self.context = patch.object(api, "_dropbox_context", return_value=CONTEXT)
        self.auth_mock = self.auth.start(); self.context.start()
        self.addCleanup(self.auth.stop); self.addCleanup(self.context.stop)

    def preview(self, path="Artwork.jpg", representation="screen"):
        return asyncio.run(api.image_preview(get_request("/api/files-image-preview", dict(path=path, representation=representation))))

    def test_screen_representations_never_download_originals_and_reuse_bytes(self):
        with patch.object(api.dropbox_integration,"get_thumbnail_bytes",return_value=b"small-jpeg") as thumbnail, patch.object(api.dropbox_integration,"get_file_response") as original:
            for extension in ["jpg","png","webp","psd"]:
                for _ in range(2):
                    response = self.preview("Artwork."+extension)
                    self.assertEqual(response.status_code,200)
                    self.assertEqual(response.body,b"small-jpeg")
                    self.assertEqual(response.headers["cache-control"],"private, no-store")
            self.assertEqual(thumbnail.call_count,4)
            self.assertEqual(self.auth_mock.call_count,8)
            original.assert_not_called()
            self.assertEqual(thumbnail.call_args.kwargs["size"],"w1024h768")

    def test_unsupported_preview_never_falls_back_to_original(self):
        with patch.object(api.dropbox_integration,"get_thumbnail_bytes",side_effect=api.FilesUploadError("Unavailable",status_code=404)), patch.object(api.dropbox_integration,"get_file_response") as original:
            self.assertEqual(self.preview().status_code,404)
            original.assert_not_called()

    def test_permission_is_checked_even_after_cache_hit(self):
        with patch.object(api.dropbox_integration,"get_thumbnail_bytes",return_value=b"jpg"):
            self.assertEqual(self.preview().status_code,200)
            self.auth_mock.side_effect=api.FilesUploadError("Denied",status_code=403)
            self.assertEqual(self.preview().status_code,403)

    def test_cache_is_scoped_to_user_connection_revision_and_size(self):
        with patch.object(api.dropbox_integration,"get_thumbnail_bytes",return_value=b"jpg") as thumbnail:
            for user,token,rev,size in [("a","t","r","w256h256"),("b","t","r","w256h256"),("a","u","r","w256h256"),("a","t","s","w256h256"),("a","t","r","w1024h768")]:
                api._preview_bytes(token,ROOT+"/a.jpg",user_id=user,revision=rev,size=size)
            self.assertEqual(thumbnail.call_count,5)

    def test_concurrent_previews_are_single_flight_and_invalidation_works(self):
        def thumbnail(*args,**kwargs): time.sleep(.04); return b"jpg"
        with patch.object(api.dropbox_integration,"get_thumbnail_bytes",side_effect=thumbnail) as fetch:
            with ThreadPoolExecutor(max_workers=6) as pool:
                results=list(pool.map(lambda _:api._preview_bytes("t",ROOT+"/a.jpg",user_id="u"),range(6)))
            self.assertEqual(results,[b"jpg"]*6);self.assertEqual(fetch.call_count,1)
            api.invalidate_thumbnail_cache(ROOT+"/a.jpg")
            api._preview_bytes("t",ROOT+"/a.jpg",user_id="u")
            self.assertEqual(fetch.call_count,2)

    def test_mutation_during_preview_does_not_repopulate_cache(self):
        def thumbnail(*args,**kwargs):
            api.invalidate_thumbnail_cache(ROOT+"/a.jpg");return b"jpg"
        with patch.object(api.dropbox_integration,"get_thumbnail_bytes",side_effect=thumbnail):
            api._preview_bytes("t",ROOT+"/a.jpg",user_id="u")
            self.assertFalse(api._PREVIEW_CACHE)

    def test_preview_cache_has_byte_budget(self):
        with patch.object(api,"FILES_PREVIEW_CACHE_BYTES",8),patch.object(api.dropbox_integration,"get_thumbnail_bytes",return_value=b"1234"):
            for i in range(5):api._preview_bytes("t",ROOT+f"/{i}.jpg",user_id="u")
            self.assertLessEqual(sum(len(value[1]) for value in api._PREVIEW_CACHE.values()),8)

    def test_precise_id_lookup_has_no_listing_or_download(self):
        metadata={"id":"id:saved", "rev":"r1", ".tag":"file", "name":"Saved.jpg", "path_display":ROOT+"/Saved.jpg", "size":35000000}
        with patch.object(api.dropbox_integration,"psd_open_metadata",return_value=metadata) as lookup,patch.object(api.dropbox_integration,"list_folder") as listing,patch.object(api.dropbox_integration,"get_file_response") as download:
            response=asyncio.run(api.resolve_files_item(get_request("/api/files-resolve",{"id":"id:saved","rev":"r1"})))
            self.assertEqual(response.status_code,200)
            self.assertEqual(json.loads(response.body)["item"]["id"],"id:saved")
            lookup.assert_called_once_with("synthetic","id:saved",include_preview=False)
            listing.assert_not_called();download.assert_not_called()
            metadata["rev"]="r2"
            self.assertEqual(asyncio.run(api.resolve_files_item(get_request("/api/files-resolve",{"id":"id:saved","rev":"r1"}))).status_code,409)
            metadata["path_display"]="/Outside/Saved.jpg"
            self.assertEqual(asyncio.run(api.resolve_files_item(get_request("/api/files-resolve",{"id":"id:saved"}))).status_code,403)

    def test_paginated_single_flight_replay_does_not_duplicate_entries(self):
        def listing(*args,**kwargs):
            time.sleep(.04)
            return {"entries":[{"id":"id:a","name":"a"}], "cursor":"cursor", "has_more":True}
        with patch.object(api.dropbox_integration,"list_folder_page",side_effect=listing) as fetch:
            with ThreadPoolExecutor(max_workers=4) as pool:
                pages=list(pool.map(lambda _:api._directory_page("t",ROOT,root_path=ROOT,user_id="u",limit=100),range(4)))
            self.assertEqual(fetch.call_count,1)
            self.assertEqual(len({page["page_token"] for page in pages}),1)
            token=pages[0]["page_token"]
            page=api._directory_page("t",ROOT,root_path=ROOT,user_id="u",page_token=token,limit=100)
            api.invalidate_directory_cache(ROOT+"/Unrelated")
            replay=api._directory_page("t",ROOT,root_path=ROOT,user_id="u",page_token=token,limit=100)
            self.assertEqual(page,replay);self.assertEqual(fetch.call_count,2)
            with self.assertRaises(api.FilesUploadError):api._directory_page("t",ROOT,root_path=ROOT,user_id="other",page_token=token,limit=100)

    def test_mutation_during_listing_does_not_cache_obsolete_page(self):
        def listing(*args,**kwargs):
            api.invalidate_directory_cache(ROOT)
            return {"entries":[{"id":"id:old"}],"has_more":False}
        with patch.object(api.dropbox_integration,"list_folder_page",side_effect=listing):
            with self.assertRaises(api.FilesUploadError):api._directory_page("t",ROOT,root_path=ROOT,user_id="u",limit=100)
            self.assertFalse(api._DIRECTORY_CACHE)

    def test_cold_connection_is_single_flight(self):
        self.context.stop(); api._DROPBOX_CONTEXT.clear()
        def resolve():time.sleep(.04);return {"access_token":"synthetic"}
        with patch.object(api.dropbox_integration,"resolve_server_auth",side_effect=resolve) as auth,patch.object(api.dropbox_integration,"find_team_folder",return_value=ROOT) as root:
            with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(lambda _:api._dropbox_context(),range(4)))
            self.assertEqual(auth.call_count,1);self.assertEqual(root.call_count,1)
        api._DROPBOX_CONTEXT.clear()

    def test_non_auth_listing_error_does_not_refresh_connection_or_repeat_request(self):
        with patch.object(api,"_directory_page",side_effect=api.FilesUploadError("Expired page",status_code=409)) as listing,patch.object(api,"_dropbox_context",return_value=CONTEXT) as context:
            response=asyncio.run(api.list_files(get_request("/api/files-list",{"path":ROOT,"page_size":"100"})))
            self.assertEqual(response.status_code,409);self.assertEqual(listing.call_count,1)
            context.assert_called_once_with()
        with patch.object(api,"_directory_page",side_effect=api.dropbox_integration.DropboxApiError("Missing folder")) as listing,patch.object(api,"_dropbox_context",return_value=CONTEXT) as context:
            asyncio.run(api.list_files(get_request("/api/files-list",{"path":ROOT,"page_size":"100"})))
            self.assertEqual(listing.call_count,1);context.assert_called_once_with()

    def test_auth_error_refreshes_connection_once(self):
        AuthError=type("AuthError",(Exception,),{})
        page={"entries":[],"has_more":False,"complete":True}
        with patch.object(api,"_directory_page",side_effect=[AuthError(),page]) as listing,patch.object(api,"_dropbox_context",return_value=CONTEXT) as context:
            response=asyncio.run(api.list_files(get_request("/api/files-list",{"path":ROOT,"page_size":"100"})))
            self.assertEqual(response.status_code,200);self.assertEqual(listing.call_count,2)
            self.assertEqual(context.call_args_list[-1].kwargs,{"force":True})
            self.assertIn("auth;dur=",response.headers["server-timing"])

    def test_unavailable_thumbnails_do_not_retry_on_every_scroll(self):
        with patch.object(api.dropbox_integration,"get_thumbnail_bytes",side_effect=api.FilesUploadError("Unavailable",status_code=404)) as thumbnail:
            self.assertEqual(self.preview().status_code,404)
            self.assertEqual(self.preview().status_code,404)
            self.assertEqual(thumbnail.call_count,1)

    def test_explicit_original_transfer_seeds_preview_without_another_download(self):
        import io
        from PIL import Image
        from tests.test_files_window import response_bytes
        original=io.BytesIO();Image.new("RGB",(1800,1200),(40,80,130)).save(original,"JPEG",quality=95)
        content=original.getvalue()
        content += bytes(35 * 1024 * 1024 - len(content))
        class Upstream:
            def iter_content(self,chunk_size):
                for start in range(0,len(content),chunk_size):yield content[start:start+chunk_size]
            def close(self):pass
        with patch.object(api.dropbox_integration,"get_file_response",return_value=({"size":len(content),"rev":"r1"},Upstream())) as download,patch.object(api.dropbox_integration,"get_thumbnail_bytes",side_effect=AssertionError("No extra provider request")):
            response=asyncio.run(api.image_preview(get_request("/api/files-image-preview",{"path":"Large.jpg","original":"1"})))
            self.assertEqual(asyncio.run(response_bytes(response)),content)
            self.assertEqual(download.call_count,1)
            preview=api._preview_bytes("synthetic",ROOT+"/Large.jpg",user_id=USER["id"],revision="r1")
            with Image.open(io.BytesIO(preview)) as image:
                self.assertLessEqual(image.width,1024);self.assertLessEqual(image.height,768)
            self.assertLess(len(preview),len(content))
            api.invalidate_thumbnail_cache(ROOT+"/Large.jpg")
            self.assertFalse(api._PREVIEW_CACHE)

    def test_incomplete_original_transfer_never_seeds_a_preview(self):
        class Upstream:
            def iter_content(self,chunk_size):yield b"partial"
            def close(self):pass
        self.assertEqual(b"".join(api._stream_original_with_preview(Upstream(),access_token="synthetic",user_id="u",path=ROOT+"/x.jpg",metadata={"size":100,"rev":"r"})),b"partial")
        self.assertFalse(api._PREVIEW_CACHE)

    def test_saturated_decoder_does_not_hold_up_original_transfer(self):
        class Upstream:
            def iter_content(self,chunk_size):yield b"original"
            def close(self):pass
        api._PREVIEW_DECODE_SLOT.acquire()
        try:
            self.assertEqual(b"".join(api._stream_original_with_preview(Upstream(),access_token="synthetic",user_id="u",path=ROOT+"/x.jpg",metadata={"size":8,"rev":"r"})),b"original")
            self.assertFalse(api._PREVIEW_CACHE)
        finally:api._PREVIEW_DECODE_SLOT.release()
