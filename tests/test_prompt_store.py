import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import prompt_store


class PromptStoreTests(unittest.TestCase):
    def test_prompt_override_persists_and_replaces_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "prompt_overrides.json"
            with patch.object(prompt_store, "PROMPT_OVERRIDES_PATH", store_path):
                self.assertEqual(prompt_store.get_prompt("product-upload::new", "Default prompt"), "Default prompt")

                prompt_store.save_prompt("product-upload::new", "New Product", "Edited prompt")

                self.assertEqual(prompt_store.get_prompt("product-upload::new", "Default prompt"), "Edited prompt")
                payload = json.loads(store_path.read_text(encoding="utf-8"))
                self.assertEqual(payload["prompts"]["product-upload::new"]["title"], "New Product")
                self.assertEqual(payload["prompts"]["product-upload::new"]["text"], "Edited prompt")


if __name__ == "__main__":
    unittest.main()
