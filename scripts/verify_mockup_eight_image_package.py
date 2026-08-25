"""Local-only eight-image Mockup workflow simulation."""

import json
import sys
import tempfile
import zipfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import image_factory


def main():
    with tempfile.TemporaryDirectory(prefix="sports-cave-eight-image-check-") as temp_dir:
        run_dir = Path(temp_dir)
        sources_dir = run_dir / "distinct-test-images"
        sources_dir.mkdir()
        assets = []
        for index, spec in enumerate(image_factory.PRODUCT_IMAGE_SLOT_SPECS, start=1):
            source_path = sources_dir / f"slot-{index}.webp"
            image = Image.new(
                "RGB",
                (64, 64),
                color=((index * 29) % 255, (index * 53) % 255, (index * 83) % 255),
            )
            image.save(source_path, format="WEBP", quality=90)
            image.close()
            assets.append(
                image_factory.build_asset_record(
                    key=spec["asset_key"],
                    label=spec["display_label"],
                    webp_path=source_path,
                    asset_group="lifestyle" if spec.get("prompt_filename") else "generated",
                    zip_group=spec["zip_group"],
                    prompt_filename=spec.get("prompt_filename"),
                    export_to_shopify=True,
                    export_to_socials=False,
                )
            )

        manifest = image_factory.build_product_image_manifest(
            assets,
            product_slug="manual-eight-image-check",
            sport_slug="cricket",
        )
        readiness = image_factory.product_image_readiness(manifest)
        image_factory.require_complete_product_image_manifest(manifest)
        export = image_factory.rebuild_export_folders(
            run_dir,
            assets,
            product_name="Manual Eight Image Check",
            sport_category="Cricket",
            product_slug="manual-eight-image-check",
            sport_slug="cricket",
            product_image_manifest=manifest,
        )
        ordered_assets = image_factory.order_assets_by_product_manifest(assets, manifest)
        outgoing_manifest = image_factory.build_asset_zip_manifest(
            ordered_assets,
            include_content_hash=False,
        )
        zip_dir = run_dir / "zip"
        zip_dir.mkdir()
        zip_path = image_factory.create_complete_pack_zip(
            zip_dir,
            "manual-eight-image-check",
            assets=ordered_assets,
        )
        with zipfile.ZipFile(zip_path) as archive:
            zip_names = archive.namelist()
        output_names = [path.name for path in Path(export["shopify_uploads_dir"]).glob("*.webp")]
        shopify_images = image_factory.build_shopify_draft_image_payload(manifest)

        expected_names = [entry["output_filename"] for entry in manifest]
        assert readiness == {
            "ready_count": 8,
            "required_count": 8,
            "complete": True,
            "missing_labels": [],
        }
        assert zip_names == [f"WEBP/{name}" for name in expected_names]
        assert set(output_names) == set(expected_names)
        assert [entry["filename"] for entry in shopify_images] == expected_names
        assert [entry["archive_name"] for entry in outgoing_manifest] == zip_names

        print(
            json.dumps(
                {
                    "readiness": readiness,
                    "ordered_slots": [entry["slot_id"] for entry in manifest],
                    "zip_entries": zip_names,
                    "output_entries": expected_names,
                    "dropbox_upload_entries": [entry["archive_name"] for entry in outgoing_manifest],
                    "shopify_draft_images": [
                        {"position": entry["position"], "slot_id": entry["slot_id"], "filename": entry["filename"]}
                        for entry in shopify_images
                    ],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
