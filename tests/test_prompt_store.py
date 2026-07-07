import unittest
from unittest.mock import patch

import prompt_store


class FakeSupabaseBackend:
    class SupabaseNotConfigured(RuntimeError):
        pass

    def __init__(self, configured=True):
        self.configured = configured
        self.records = {}
        self.versions = []

    def is_configured(self):
        return self.configured

    def ensure_prompt_template_schema(self):
        if not self.configured:
            raise self.SupabaseNotConfigured("Not configured")

    def get_prompt_template(self, prompt_key):
        return self.records.get(prompt_key)

    def upsert_prompt_template(self, prompt_key, **kwargs):
        old = self.records.get(prompt_key)
        if old and old.get("prompt_text") != kwargs["prompt_text"]:
            self.versions.append((prompt_key, old.get("prompt_text"), kwargs["prompt_text"]))
        record = {
            "prompt_key": prompt_key,
            "prompt_name": kwargs.get("prompt_name"),
            "module": kwargs.get("module"),
            "prompt_text": kwargs.get("prompt_text"),
            "source": kwargs.get("source"),
            "updated_by": kwargs.get("updated_by"),
        }
        self.records[prompt_key] = record
        return record


class PromptStoreTests(unittest.TestCase):
    def tearDown(self):
        prompt_store.clear_prompt_cache()

    def test_missing_supabase_uses_default_and_warns_not_persisted(self):
        backend = FakeSupabaseBackend(configured=False)
        with patch.object(prompt_store, "_supabase_backend", return_value=backend):
            prompt_store.clear_prompt_cache()
            record = prompt_store.load_prompt("product-upload::new", "Default prompt")

        self.assertEqual(record["text"], "Default prompt")
        self.assertFalse(record["persisted"])
        self.assertEqual(record["source_label"], "Not persisted — Supabase unavailable")

    def test_first_load_seeds_default_to_supabase(self):
        backend = FakeSupabaseBackend()
        with patch.object(prompt_store, "_supabase_backend", return_value=backend):
            prompt_store.clear_prompt_cache()
            record = prompt_store.load_prompt(
                "product-upload::new",
                "Default prompt",
                prompt_name="New Product",
                module="product_uploads",
            )

        self.assertTrue(record["persisted"])
        self.assertEqual(record["text"], "Default prompt")
        self.assertEqual(backend.records["product-upload::new"]["prompt_text"], "Default prompt")

    def test_save_prompt_requires_supabase_success(self):
        backend = FakeSupabaseBackend()
        with patch.object(prompt_store, "_supabase_backend", return_value=backend):
            prompt_store.clear_prompt_cache()
            prompt_store.save_prompt("product-upload::new", "New Product", "Edited prompt")

        self.assertEqual(backend.records["product-upload::new"]["prompt_text"], "Edited prompt")

    def test_save_prompt_fails_when_supabase_unavailable(self):
        backend = FakeSupabaseBackend(configured=False)
        with patch.object(prompt_store, "_supabase_backend", return_value=backend):
            prompt_store.clear_prompt_cache()
            with self.assertRaises(RuntimeError):
                prompt_store.save_prompt("product-upload::new", "New Product", "Edited prompt")


if __name__ == "__main__":
    unittest.main()
