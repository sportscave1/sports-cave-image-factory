from copy import deepcopy
import json
from pathlib import Path
import re
import tempfile
import unittest

import seo_workspace as seo


ROOT = Path(__file__).resolve().parents[1]


class LegacyCitationFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_text = (ROOT / "data" / "seo_citations_legacy_v1.json").read_text(encoding="utf-8")
        cls.fixture = json.loads(cls.fixture_text)
        cls.records = cls.fixture["records"]

    def test_expected_source_and_unique_counts(self):
        self.assertEqual(self.fixture["source_rows"], 259)
        self.assertEqual(self.fixture["source_live"], 257)
        self.assertEqual(self.fixture["source_pending"], 2)
        self.assertEqual(self.fixture["duplicate_rows_merged"], 6)
        self.assertEqual(self.fixture["invalid_rows"], 0)
        self.assertEqual(len(self.records), 253)
        self.assertEqual(sum(row["status"] == "Live" for row in self.records), 251)

    def test_pending_records_are_not_completed(self):
        pending = {row["platform"]: row for row in self.records if row["status"] == "Pending Verification"}
        self.assertEqual(set(pending), {"Folkd", "RateYourMusic"})
        for row in pending.values():
            self.assertIsNone(row["date_completed"])
            self.assertEqual(row["date_started"], "2026-01-14")

    def test_duplicate_profile_groups_merge_to_one_record_each(self):
        for url in (
            "https://bio.site/sportscave",
            "https://campsite.bio/sports_cave",
            "https://paragraph.com/@sportscave",
            "https://solo.to/sportscaveshop",
        ):
            canonical = seo.canonical_profile_url(url)
            self.assertEqual(sum(row["canonical_profile_url"] == canonical for row in self.records), 1)

    def test_email_addresses_are_not_in_fixture_or_record_keys(self):
        self.assertIsNone(re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", self.fixture_text, re.I))
        self.assertFalse(any("email" in key.casefold() for row in self.records for key in row))

    def test_dates_plain_text_links_and_stable_ids(self):
        tumblr = next(row for row in self.records if row["platform"] == "Tumblr")
        self.assertEqual(tumblr["date_completed"], "2025-01-01")
        adobe = next(row for row in self.records if row["platform"] == "Adobe")
        self.assertEqual(adobe["website_displayed"], "Yes")
        self.assertEqual(adobe["website_link_type"], "Plain Text")
        self.assertEqual(adobe["notes"], "Website displayed as plain text; link is not clickable.")
        reparsed = seo.parse_legacy_citation_tracker(
            "| Platform Name | Signup URL | Profile URL | Username / Handle | Email Used | Status | Link Displayed? | Logo Uploaded? | Notes | Date Completed |\n"
            "|---|---|---|---|---|---|---|---|---|---|\n"
            "| Test\\|Site | [Join](https://EXAMPLE.com:443/signup?a=1\\&b=2) | [Profile\\|One](https://Example.com/User_Name/) | name\\_one | secret@example.test | Live | Yes | No | Profile live | 01-01-25 |\n"
        )
        row = reparsed["records"][0]
        self.assertEqual(row["platform"], "Test|Site")
        self.assertEqual(row["signup_url"], "https://EXAMPLE.com:443/signup?a=1&b=2")
        self.assertEqual(row["profile_url"], "https://Example.com/User_Name/")
        self.assertEqual(row["canonical_profile_url"], "https://example.com/User_Name")
        self.assertEqual(row["date_completed"], "2025-01-01")
        self.assertNotIn("email", json.dumps(row).casefold())

    def test_import_is_idempotent_and_preserves_manual_fields(self):
        fixture = deepcopy(self.fixture)
        first_record = fixture["records"][0]
        state = seo.default_state()
        state["citations"] = [{
            "id": "manual-id",
            "platform": "Manual platform name",
            "profile_url": first_record["profile_url"],
            "canonical_profile_url": first_record["canonical_profile_url"],
            "status": "Live",
            "owner": "Nathan",
            "notes": "Manually reviewed note",
            "reviewed_at": "2026-08-01",
            "archived_at": "",
        }]
        imported, summary = seo.apply_legacy_citation_import(state, fixture)
        self.assertEqual(summary["records_created"], 252)
        self.assertEqual(summary["existing_records_updated"], 1)
        merged = next(row for row in imported["citations"] if row["id"] == "manual-id")
        self.assertEqual(merged["owner"], "Nathan")
        self.assertEqual(merged["notes"], "Manually reviewed note")
        repeated, repeated_summary = seo.apply_legacy_citation_import(imported, fixture)
        self.assertIsNone(repeated_summary)
        self.assertEqual(len(repeated["citations"]), 253)

    def test_store_restart_creates_no_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "seo.json"
            first_store = seo.LocalSEOStore(path)
            first = first_store.load()
            second_store = seo.LocalSEOStore(path)
            second = second_store.load()
            self.assertEqual(len(first["citations"]), 253)
            self.assertEqual(len(second["citations"]), 253)
            self.assertEqual(len({row["canonical_profile_url"] for row in second["citations"]}), 253)
            self.assertIsNone(second_store.consume_import_summary())

    def test_kpis_filters_and_pagination_derive_from_records(self):
        state, _ = seo.apply_legacy_citation_import(seo.default_state(), deepcopy(self.fixture))
        counts = seo.citation_status_counts(state)
        self.assertEqual(counts["Live"], 251)
        self.assertEqual(counts["Pending Verification"], 2)
        pending = seo.filter_citations(state["citations"], status="Pending Verification")
        self.assertEqual({row["platform"] for row in pending}, {"Folkd", "RateYourMusic"})
        searched = seo.filter_citations(state["citations"], search="Tumblr")
        self.assertEqual([row["platform"] for row in searched], ["Tumblr"])
        page = seo.paginate_records(state["citations"], page=2, page_size=25)
        self.assertEqual(len(page["rows"]), 25)
        self.assertEqual(page["total"], 253)
        self.assertEqual(page["page_count"], 11)

    def test_activity_summary_is_single_idempotent_and_email_free(self):
        source = (ROOT / "seo_page.py").read_text(encoding="utf-8")
        self.assertIn('event_key=f"seo-import:{seo.LEGACY_CITATION_IMPORT_VERSION}"', source)
        self.assertIn("source_rows_processed", source)
        self.assertIn("records_created", source)
        self.assertIn("existing_records_updated", source)
        self.assertIn("duplicate_rows_merged", source)
        self.assertIn("records_skipped", source)
        self.assertNotIn("Email Used", source)


if __name__ == "__main__":
    unittest.main()
