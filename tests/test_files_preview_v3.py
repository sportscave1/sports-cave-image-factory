"""Offline V3 boundaries: fake providers, real encryption/decoding, no secrets."""
import asyncio
import base64
import io
import json
import threading
import time
import unittest
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch

from PIL import Image
from cryptography.fernet import Fernet
from services import files_preview_cache as cache
import files_upload_api as api
from tests.test_files_window import get_request

META = {".tag":"file", "id":"id:synthetic", "rev":"r1", "name":"Artwork.jpg",
        "path_display":"/Synthetic/Artwork.jpg", "size":35*1024*1024}


class S3Error(Exception):
    def __init__(self, code):
        self.response = {"Error":{"Code":code}}


class S3:
    def __init__(self):
        self.data = {}; self.lock = threading.Lock(); self.serial = 0
    def get_object(self, Bucket, Key):
        with self.lock:
            if Key not in self.data:
                raise S3Error("NoSuchKey")
            data, etag, _ = self.data[Key]
            return {"Body":io.BytesIO(data), "ETag":etag}
    def put_object(self, Bucket, Key, Body, IfMatch=None, IfNoneMatch=None, **kwargs):
        with self.lock:
            old = self.data.get(Key)
            if (IfNoneMatch and old) or (IfMatch and (not old or old[1] != IfMatch)):
                raise S3Error("PreconditionFailed")
            self.serial += 1; etag = str(self.serial)
            self.data[Key] = (Body, etag, datetime.now(timezone.utc))
            return {"ETag":etag}
    def list_objects_v2(self, Bucket, Prefix, **kwargs):
        return {"Contents":[{"Key":k,"LastModified":v[2],"Size":len(v[0])}
                            for k,v in self.data.items() if k.startswith(Prefix)]}
    def delete_object(self, Bucket, Key):
        self.data.pop(Key, None)


class Upstream:
    def __init__(self, data):
        self.data = data; self.closed = False
    def iter_content(self, chunk_size):
        for start in range(0, len(self.data), chunk_size):
            yield self.data[start:start+chunk_size]
    def close(self):
        self.closed = True


class PreviewV3Tests(unittest.TestCase):
    def setUp(self):
        cache._fast.clear()
        cache._failed.clear()
        self.s3 = S3()
        env = patch.dict("os.environ", {"FILES_PREVIEW_BUCKET":"synthetic-private",
            "FILES_PREVIEW_NAMESPACE":"synthetic", "FILES_PREVIEW_PRIVATE_BUCKET_CONFIRMED":"1",
            "FILES_PREVIEW_ENCRYPTION_KEY":Fernet.generate_key().decode()})
        env.start(); self.addCleanup(env.stop)
        client = patch("services.r2_storage.get_r2_client", return_value=self.s3)
        client.start(); self.addCleanup(client.stop)
        self.store = cache.Store()

    def request(self, representation="screen", **kwargs):
        return cache.request_preview("test-token", META["path_display"], root="/Synthetic",
            user_id=kwargs.get("user_id", "worker"), revision=kwargs.get("rev", "r1"), representation=representation)

    def test_config_requires_explicit_private_storage_and_namespace(self):
        self.assertTrue(cache.configured())
        for setting in ["FILES_PREVIEW_BUCKET", "FILES_PREVIEW_NAMESPACE", "FILES_PREVIEW_ENCRYPTION_KEY", "FILES_PREVIEW_PRIVATE_BUCKET_CONFIRMED"]:
            with patch.dict("os.environ", {setting:""}):
                self.assertFalse(cache.configured())

    def test_encrypted_persistent_bundle_survives_new_store(self):
        value = {"assets":{"screen":base64.b64encode(b"private-artwork").decode()}, "expires":time.time()+60}
        self.store.write("assets/test", value)
        self.assertNotIn(b"private-artwork", next(iter(self.s3.data.values()))[0])
        self.assertEqual(cache.Store().read("assets/test"), value)
        with patch.dict("os.environ", {"FILES_PREVIEW_ENCRYPTION_KEY":Fernet.generate_key().decode()}):
            with self.assertRaises(Exception):
                cache.Store().read("assets/test")

    def test_identity_is_revision_user_root_and_version_scoped(self):
        original = cache.asset_key("worker", "/Synthetic", META)
        for user, root, meta in [("another", "/Synthetic", META), ("worker", "/Other", META),
                                  ("worker", "/Synthetic", {**META,"rev":"r2"}), ("worker", "/Synthetic", {**META,"id":"id:other"})]:
            self.assertNotEqual(cache.asset_key(user,root,meta), original)
        with self.assertRaises(cache.PreviewError): cache.asset_key("", "/Synthetic", META)

    def test_metadata_is_checked_before_every_cached_read(self):
        key = cache.asset_key("worker", "/Synthetic", META)
        self.store.write(key, {"assets":{"screen":base64.b64encode(b"jpeg").decode()}, "expires":time.time()+60})
        with patch.object(cache.dbx,"get_file_metadata",return_value=META) as metadata:
            self.assertEqual(self.request()[0], b"jpeg")
            self.assertEqual(self.request()[0], b"jpeg")
            self.assertEqual(metadata.call_count,2)
        with patch.object(cache.dbx,"get_file_metadata",return_value={**META,"rev":"r2"}):
            with self.assertRaises(cache.PreviewError) as result: self.request()
            self.assertEqual(result.exception.status,409)
        with patch.object(cache.dbx,"get_file_metadata",side_effect=RuntimeError("revoked")):
            with self.assertRaises(RuntimeError): self.request()

    def test_moved_or_missing_file_is_not_served(self):
        for meta in [{**META,"path_display":"/Other/Artwork.jpg"},{**META,".tag":"folder"},{**META,"rev":""}]:
            with patch.object(cache.dbx,"get_file_metadata",return_value=meta):
                with self.assertRaises(cache.PreviewError): self.request()

    def test_thumbnail_miss_does_not_queue_original_preparation(self):
        key=cache.asset_key("worker","/Synthetic",META)
        with patch.object(cache.dbx,"get_file_metadata",return_value=META), patch.object(cache,"_provider_preview",return_value=b"small-jpeg") as provider, patch.object(cache._pool,"submit") as submit:
            try:
                self.assertEqual(self.request("small")[0], b"small-jpeg")
                self.assertFalse(submit.call_args.args[5], "Grid preparation must forbid original retrieval")
                self.assertEqual(provider.call_args.args[-1], "w256h256")
            finally:
                with cache._lock: cache._pending.discard(key)
                cache._slots.release()

    def test_pending_requests_are_deduplicated(self):
        key = cache.asset_key("worker", "/Synthetic", META)
        with patch.object(cache.dbx,"get_file_metadata",return_value=META), patch.object(cache,"_provider_preview",side_effect=cache.PreviewError("Unavailable")), patch.object(cache._pool,"submit") as submit:
            try:
                for _ in range(10): self.assertIsNone(self.request()[0])
                self.assertEqual(submit.call_count,1)
            finally:
                with cache._lock: cache._pending.discard(key)
                cache._slots.release()

    def test_existing_provider_preview_is_immediate_and_not_requested_twice(self):
        key=cache.asset_key("worker","/Synthetic",META)
        with patch.object(cache.dbx,"get_file_metadata",return_value=META) as metadata, patch.object(cache,"_provider_preview",return_value=b"small-jpeg") as provider, patch.object(cache._pool,"submit") as submit:
            try:
                self.assertEqual(self.request()[0],b"small-jpeg")
                self.assertEqual(self.request()[0],b"small-jpeg")
                self.assertEqual(provider.call_count,1)
                self.assertEqual(metadata.call_count,2)
                self.assertEqual(submit.call_args.args[-4:],(b"small-jpeg",True,2048,False))
            finally:
                with cache._lock: cache._pending.discard(key)
                cache._slots.release()

    def test_cross_process_lease_and_stale_release_fence(self):
        first = self.store.lease()
        self.assertIsNotNone(first); self.assertIsNone(cache.Store().lease())
        self.store.release(first)
        second = cache.Store().lease()
        with self.assertRaises(S3Error): self.store.release(first)
        self.assertIsNone(self.store.lease())
        self.store.release(second)

    def test_storage_failure_stops_automatic_repeat_downloads(self):
        key=cache.asset_key("worker","/Synthetic",META)
        with patch.object(cache,"prepare",return_value={"screen":"anBlZw==","small":"anBlZw=="}) as prepare, patch.object(self.store,"write",side_effect=RuntimeError("storage unavailable")), patch.object(cache.dbx,"get_file_metadata",return_value=META):
            cache._slots.acquire(); cache._job(self.store,key,"test-token",META,True)
            with self.assertRaises(cache.PreviewError) as result: self.request()
            self.assertEqual(result.exception.status,503)
            self.assertEqual(prepare.call_count,1)

    def test_cleanup_bounded_and_preserves_other_storage(self):
        for index in range(cache.MAX_OBJECTS+3):
            self.store.write("assets/old-version/"+str(index), {"expires":time.time()+60})
        self.s3.put_object(Bucket="synthetic", Key="unrelated-artwork", Body=b"keep")
        self.store.cleanup()
        self.assertEqual(len([k for k in self.s3.data if k.startswith(self.store.prefix)]),cache.MAX_OBJECTS-1)
        self.assertIn("unrelated-artwork",self.s3.data)

    def raster(self):
        output=io.BytesIO(); Image.new("RGB",(4000,3000),(25,80,140)).save(output,"JPEG")
        return output.getvalue()

    def test_large_jpg_prepared_once_without_original_in_asset(self):
        payload=self.raster(); payload+=b"\0"*(META["size"]-len(payload))
        upstream=Upstream(payload)
        with patch.object(cache.dbx,"team_space_client",side_effect=RuntimeError("no thumbnail")), patch.object(cache,"_download_source",return_value=(META,upstream)) as download:
            value=cache.prepare("test-token",META,True)
            self.assertEqual(download.call_count,1); self.assertTrue(upstream.closed)
        self.assertLess(sum(len(v) for v in value.values()),100_000)
        for name,bounds in [("screen",(1600,1200)),("small",(256,256))]:
            with Image.open(io.BytesIO(base64.b64decode(value[name]))) as image:
                self.assertLessEqual(image.width,bounds[0]); self.assertLessEqual(image.height,bounds[1])

    def test_psd_and_unselected_raster_never_download_original(self):
        with patch.object(cache.dbx,"team_space_client",side_effect=RuntimeError("no thumbnail")), patch.object(cache,"_download_source") as download:
            for meta,allowed in [({**META,"name":"Master.psd","size":300*1024*1024},True),(META,False),({**META,"size":cache.MAX_SOURCE+1},True)]:
                with self.assertRaises(cache.PreviewError): cache.prepare("test-token",meta,allowed)
            download.assert_not_called()

    def test_provider_psd_representation_is_pinned_and_closed(self):
        upstream=Upstream(self.raster()); client=Mock(); client.files_get_thumbnail.return_value=(META,upstream)
        with patch.object(cache.dbx,"team_space_client",return_value=client), patch.object(cache.dbx,"_metadata_to_dict",side_effect=lambda m:m), patch.object(cache,"_download_source") as original:
            self.assertIn("screen",cache.prepare("test-token",{**META,"name":"Master.psd"},True))
            original.assert_not_called(); self.assertTrue(upstream.closed)

    def test_wrong_revision_in_transfer_fails_closed(self):
        upstream=Upstream(self.raster())
        with patch.object(cache.dbx,"team_space_client",side_effect=RuntimeError("no thumbnail")), patch.object(cache,"_download_source",return_value=({**META,"rev":"other"},upstream)):
            with self.assertRaises(cache.PreviewError): cache.prepare("test-token",META,True)
            self.assertTrue(upstream.closed)

    def test_api_permission_denial_never_reads_storage(self):
        with patch.object(api,"_request_user",side_effect=api.FilesUploadError("Denied",status_code=403)), patch.object(cache,"request_preview") as preview:
            response=asyncio.run(api.image_preview(get_request("/api/files-image-preview",{"path":"Artwork.jpg","representation":"screen"})))
            self.assertEqual(response.status_code,403); preview.assert_not_called()

    def test_api_pending_has_honest_status_and_private_headers(self):
        with patch.object(api,"_request_user",return_value={"id":"worker"}), patch.object(api,"_dropbox_context",return_value={"access_token":"test-token","root_path":"/Synthetic"}), patch.object(cache,"request_preview",return_value=(None,"metadata;dur=5, storage;dur=2")):
            response=asyncio.run(api.image_preview(get_request("/api/files-image-preview",{"path":"Artwork.jpg","representation":"screen"})))
            self.assertEqual(response.status_code,202)
            self.assertEqual(response.headers["cache-control"],"private, no-store")
            self.assertEqual(response.headers["retry-after"],"1")
            self.assertIn("metadata;dur=5",response.headers["server-timing"])

    def test_persistent_worker_reuse_and_safe_fixture_benchmark(self):
        payload=self.raster(); payload+=b"\0"*(META["size"]-len(payload))
        key=cache.asset_key("worker","/Synthetic",META)
        with patch.object(cache.dbx,"team_space_client",side_effect=RuntimeError("unsupported thumbnail")), patch.object(cache,"_download_source",side_effect=lambda *args:(META,Upstream(payload))) as download, patch.object(cache.dbx,"get_file_metadata",return_value=META) as metadata:
            cache._slots.acquire()
            start=time.perf_counter(); cache._job(self.store,key,"test-token",META,True)
            preparation_ms=(time.perf_counter()-start)*1000
            # A different process/store sees the persisted bytes and does not download again.
            cache._slots.acquire(); cache._job(cache.Store(),key,"test-token",META,True)
            samples=[]
            for _ in range(20):
                start=time.perf_counter(); content,timing=self.request()
                samples.append((time.perf_counter()-start)*1000)
            self.assertEqual(download.call_count,1)
            self.assertEqual(metadata.call_count,20)
            self.assertLess(len(content),100_000)
        samples.sort()
        result={"environment":"synthetic in-memory Dropbox/R2; actual Pillow and Fernet; zero provider network latency",
                "source_bytes":len(payload),"screen_bytes":len(content),"encrypted_bundle_bytes":len(self.s3.data[self.store.prefix+key][0]),
                "one_time_preparation_ms":preparation_ms,"warm_ms":{"p50":samples[10],"p95":samples[18],"samples":samples},
                "original_downloads":1,"warm_source_metadata_requests":20,"warm_original_downloads":0}
        Path("test-results").mkdir(exist_ok=True)
        Path("test-results/files-preview-v3-pipeline.json").write_text(json.dumps(result,indent=2),encoding="utf8")
