import inspect
import unittest
from unittest import mock

import social_media_catalog
import social_media_creator
import social_media_workspace


def package():
    return social_media_creator.build_content_package(
        {
            "scheduled_date": "2026-07-31",
            "content_focus": "Product",
            "product_title": "Senna Collector's Edition",
            "product_handle": "senna-collector-s-edition",
            "product_url": "https://sportscaveshop.com/products/senna",
            "market": "Australia",
            "sport": "Motorsport",
            "format": "Static feed post",
            "series": "WALL WORTHY",
            "platforms": ["Instagram", "Facebook"],
            "objective": "Product click",
            "funnel_stage": "Warm",
            "hook": "Some moments never leave you.",
            "cta": "See the complete edition.",
            "rights_status": "Approved",
        }
    )


class FakeUpload:
    def __init__(self, name, data):
        self.name = name
        self._data = data

    def getvalue(self):
        return self._data


class SocialOutputSaveTests(unittest.TestCase):
    def test_partial_save_writes_both_text_files_with_replace(self):
        calls = []

        def upload_stream(access_token, path, stream, *, size, conflict):
            calls.append(
                {
                    "token": access_token,
                    "path": path,
                    "data": stream.read(),
                    "size": size,
                    "conflict": conflict,
                }
            )
            return {"path_display": path}

        with (
            mock.patch.object(
                social_media_workspace.dropbox_integration,
                "ensure_folder_path",
            ) as ensure_folder,
            mock.patch.object(
                social_media_workspace.dropbox_integration,
                "upload_stream",
                side_effect=upload_stream,
            ),
        ):
            saved = social_media_workspace.save_social_output(
                "token",
                "/Sportscave Team Folder",
                package(),
                uploads=(),
            )

        self.assertEqual(
            [call["path"].rsplit("/", 1)[-1] for call in calls],
            ["Brief.txt", "Social Copy.txt"],
        )
        self.assertTrue(all(call["conflict"] == "replace" for call in calls))
        self.assertTrue(all(b"\r\n" in call["data"] for call in calls))
        self.assertTrue(saved["relative_folder"].startswith("04_OUTPUT/social-media/"))
        ensure_folder.assert_called_once()

    def test_ordered_assets_use_short_stable_master_filenames(self):
        calls = []

        def upload_stream(_access_token, path, stream, *, size, conflict):
            calls.append((path, stream.read(), size, conflict))
            return {"path_display": path}

        uploads = (
            FakeUpload("Original First Image.PNG", b"first"),
            FakeUpload("Second Video.MP4", b"second"),
        )
        with (
            mock.patch.object(
                social_media_workspace.dropbox_integration,
                "ensure_folder_path",
            ),
            mock.patch.object(
                social_media_workspace.dropbox_integration,
                "upload_stream",
                side_effect=upload_stream,
            ),
        ):
            social_media_workspace.save_social_output(
                "token",
                "/Sportscave Team Folder",
                package(),
                uploads,
            )

        asset_names = [path.rsplit("/", 1)[-1] for path, _data, _size, _mode in calls[2:]]
        self.assertEqual(
            asset_names,
            [
                "senna-collector-s-edition__static-feed-post__master__01.png",
                "senna-collector-s-edition__static-feed-post__master__02.mp4",
            ],
        )
        self.assertTrue(all(mode == "replace" for _path, _data, _size, mode in calls))

    def test_files_and_ai_reels_navigation_reuse_existing_routes(self):
        files_source = inspect.getsource(social_media_workspace._open_files_folder)
        reels_source = inspect.getsource(social_media_workspace._open_ai_reels)

        self.assertIn('st.query_params["files_path"] = clean_path', files_source)
        self.assertIn('st.session_state["files_browser_path"]', files_source)
        self.assertIn("social_media.AI_REELS_ROUTE", reels_source)
        self.assertIn('st.session_state["smrs_final_product_handle"]', reels_source)

    def test_weekly_priority_offer_and_restrictions_prefill_create(self):
        prefill = social_media_workspace._plan_prefill(
            "ONLY 100",
            "Feed carousel",
            "Only 100. Then it retires.",
            {
                "hero_products": ["Senna Collector's Edition"],
                "priority_market": "Australia",
                "approved_offer": "Verified free shipping",
                "restrictions": "Do not invent a live edition count.",
            },
        )

        self.assertEqual(prefill["offer"], "Verified free shipping")
        self.assertEqual(
            prefill["restrictions"],
            "Do not invent a live edition count.",
        )


class SocialCatalogueTests(unittest.TestCase):
    def test_catalogue_product_preserves_protected_identity_and_url(self):
        product = social_media_catalog._clean_product(
            {
                "shopify_product_id": "gid://shopify/Product/123",
                "product_title": "Senna Collector's Edition",
                "shopify_handle": "senna-collector-s-edition",
                "online_store_url": "https://sportscaveshop.com/products/senna",
                "featured_image_url": "https://cdn.example.test/senna.jpg",
                "product_type": "Motorsport Wall Art",
                "collections": ["Motorsport", "Best Sellers"],
            }
        )

        self.assertEqual(product["id"], "gid://shopify/Product/123")
        self.assertEqual(product["title"], "Senna Collector's Edition")
        self.assertEqual(product["handle"], "senna-collector-s-edition")
        self.assertEqual(
            product["url"],
            "https://sportscaveshop.com/products/senna",
        )
        self.assertEqual(
            product["image_url"],
            "https://cdn.example.test/senna.jpg",
        )

    def test_collection_options_are_derived_without_duplicate_labels(self):
        options = social_media_catalog.collection_options(
            [
                {
                    "collections": ("Motorsport Wall Art", "Best Sellers"),
                    "product_type": "Wall Art",
                },
                {
                    "collections": ("Best Sellers",),
                    "product_type": "Wall Art",
                },
            ]
        )

        self.assertEqual(
            options,
            ("Best Sellers", "Motorsport Wall Art", "Wall Art"),
        )


if __name__ == "__main__":
    unittest.main()
