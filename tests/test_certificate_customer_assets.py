import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import certificate_engine as engine
import certificate_job


class CustomerAssetTests(unittest.TestCase):
    def record(self):
        return dict(order_name="#TEST1", shopify_order_id="gid://shopify/Order/1",
                    line_item_id="gid://shopify/LineItem/2", edition_number=7,
                    edition_total=100, handle="test", product_title="Test Artwork",
                    certificate_id="TEST-CERT", certificate_pdf_url="https://cdn.example/original.pdf",
                    status="Ready")

    def test_existing_pdf_gets_current_template_images_and_retry_is_noop(self):
        record = self.record()
        with tempfile.TemporaryDirectory() as tmp, patch("shopify_sync.upload_image_to_shopify_files") as upload:
            upload.side_effect = lambda path, **kw: dict(file_id="gid://shopify/MediaImage/1", url="https://cdn.example/" + Path(path).name)
            repaired = engine.ensure_certificate_customer_assets(record, output_dir=tmp)
            self.assertEqual(upload.call_count, 2)
            from PIL import Image
            with Image.open(repaired["local_print_jpg_path"]) as image:
                self.assertEqual(image.size, (3508, 2480))
            self.assertEqual(repaired["certificate_pdf_url"], record["certificate_pdf_url"])
            engine.ensure_certificate_customer_assets(repaired, output_dir=tmp)
            self.assertEqual(upload.call_count, 2)

    def test_partial_upload_retains_success_for_retry(self):
        with tempfile.TemporaryDirectory() as tmp, patch("shopify_sync.upload_image_to_shopify_files") as upload:
            upload.side_effect = [dict(file_id="print-id", url="https://cdn.example/print.jpg"), RuntimeError("preview unavailable")]
            partial = engine.ensure_certificate_customer_assets(self.record(), output_dir=tmp, require_complete=False)
            self.assertEqual(partial["asset_sync_status"], "partial")
            self.assertTrue(partial["certificate_print_jpg_url"])
            upload.reset_mock(side_effect=True)
            upload.return_value = dict(file_id="preview-id", url="https://cdn.example/preview.webp")
            repaired = engine.ensure_certificate_customer_assets(partial, output_dir=tmp)
            self.assertEqual(upload.call_count, 1)
            self.assertEqual(repaired["asset_sync_status"], "ready")

    def test_save_merges_missing_assets_without_replacing_pdf_or_sibling(self):
        existing = self.record()
        sibling = {**existing, "line_item_id": "gid://shopify/LineItem/3", "edition_number": 8}
        proposed = {**existing, "certificate_pdf_url": "https://cdn.example/replacement.pdf",
                    "certificate_print_jpg_url": "https://cdn.example/print.jpg",
                    "certificate_preview_image_url": "https://cdn.example/preview.webp"}
        with patch.object(engine, "read_order_certificate_state", return_value=dict(certificates=[existing, sibling], compare_digest="digest")), patch.object(engine, "persist_certificate_record_to_supabase", return_value={"ok": True}) as persist, patch.object(engine, "_sync_order_certificate_records", return_value={"ok": True}) as sync:
            result = engine.save_certificate_record_to_order(proposed, ensure_schema_first=False)
        self.assertTrue(result["saved"])
        self.assertEqual(result["record"]["certificate_pdf_url"], existing["certificate_pdf_url"])
        self.assertIn(sibling, sync.call_args.args[1])
        self.assertEqual(sync.call_args.kwargs["compare_digest"], "digest")
        self.assertFalse(persist.call_args.kwargs["ensure_schema_first"])

    def test_prebuilt_pdf_upload_still_generates_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "certificate.pdf"
            pdf.write_bytes(b"%PDF-test")
            record = {**self.record(), "local_pdf_path": str(pdf)}
            with patch("shopify_sync.upload_pdf_to_shopify_files", return_value=dict(file_id="pdf-id", url=record["certificate_pdf_url"])), patch.object(engine, "ensure_certificate_customer_assets", side_effect=lambda r, **kw: {**r, "asset_sync_status": "ready"}) as ensure:
                engine.upload_generated_certificate_record(record)
            ensure.assert_called_once()

    def test_orders_retry_repairs_existing_instead_of_skipping_images(self):
        record = self.record()
        row = {**record, "edition_order_id": "1", "shopify_line_item_id": record["line_item_id"]}
        repaired = {**record, "asset_sync_status": "ready"}
        with patch("shopify_sync.get_config", return_value={"configured": True}), patch("supabase_backend.generate_certificate_for_edition_order", return_value=""), patch.object(certificate_job, "_existing_uploaded_certificate", return_value=record), patch.object(engine, "ensure_certificate_customer_assets", return_value=repaired) as ensure, patch.object(engine, "save_certificate_record_to_order", return_value={"metafields_synced": True, "record": repaired}) as save, patch.object(engine, "upload_generated_certificate_record") as pdf_upload:
            result = certificate_job.run_certificate_job(row, upload=True)
        self.assertTrue(result["ok"])
        ensure.assert_called_once()
        save.assert_called_once()
        pdf_upload.assert_not_called()


if __name__ == "__main__":
    unittest.main()
