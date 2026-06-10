from contextlib import suppress
from pathlib import Path
import json
import os
import tempfile

from dotenv import load_dotenv
import streamlit as st

import drive_storage
import image_factory


load_dotenv()


BASE_DIR = Path(__file__).resolve().parent
RUNS_DIR = BASE_DIR / "output" / "runs"
MENU_OPTIONS = [
    "Mockups",
    "Google Drive",
    "Limited Editions",
    "Product Uploads",
    "Settings",
]
APP_VERSION = "Build 2026-06-11"
DRIVE_SECTION_NAMES = {
    "mockups": "Mockups",
    "limited_editions": "Limited Editions",
    "product_uploads": "Product Uploads",
    "system_logs": "System Logs",
}
PASSWORD_ENV_KEYS = (
    "APP_PASSWORD",
    "STREAMLIT_PASSWORD",
    "SPORTS_CAVE_PASSWORD",
    "SITE_PASSWORD",
)
LEGACY_BASE_ASSET_SPECS = [
    ("black", "Black Framed"),
    ("size-guide", "Size Guide"),
    ("oak", "Oak Framed"),
    ("white", "White Framed"),
    ("unframed", "Unframed"),
]
SPORT_OPTIONS = [
    "Soccer",
    "Motorsport",
    "Basketball",
    "AFL",
    "NRL",
    "Rugby Union",
    "Cricket",
    "NFL",
    "Baseball",
    "Hockey",
    "Tennis",
    "Custom",
]
PROMPT_LABELS = {
    "01-man-cave-prompt.txt": "01 - Man Cave (Product Page)",
    "02-office-prompt.txt": "02 - Office (Product Page)",
    "03-living-room-prompt.txt": "03 - Living Room (Product Page)",
    "04-close-up-wall-prompt.txt": "04 - Close-Up Premium Wall Shot (Social)",
    "05-limited-edition-detail-prompt.txt": "05 - Limited Edition Detail Shot (Social)",
    "06-instant-experience-cover-prompt.txt": "06 - Instant Experience Cover Banner (Social)",
    "07-home-sports-bar-prompt.txt": "07 - Premium Home Sports Bar (Social)",
    "08-collector-display-room-prompt.txt": "08 - Collector Display Room (Social)",
    "09-luxury-entry-wall-prompt.txt": "09 - Luxury Entry Statement Wall (Social)",
    "10-premium-unboxing-prompt.txt": "10 - Premium Unboxing / Collector Arrival (Social)",
    "11-wall-upgrade-moment-prompt.txt": "11 - The Wall Upgrade Moment (Social)",
    "12-fireplace-feature-wall-prompt.txt": "12 - Luxury Fireplace Feature Wall (Social)",
    "13-premium-bedroom-prompt.txt": "13 - Premium Bedroom / Private Retreat (Social)",
    "14-home-gym-prompt.txt": "14 - Home Gym / Motivation Wall (Social)",
    "15-premium-gift-reveal-prompt.txt": "15 - Premium Gift Reveal Scene (Social)",
}
PRODUCT_PAGE_PROMPT_NAMES = {
    "01-man-cave-prompt.txt",
    "02-office-prompt.txt",
    "03-living-room-prompt.txt",
}


st.set_page_config(
    page_title="Sports Cave Image Factory",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_styles():
    st.markdown(
        """
        <style>
        [data-testid="stAppViewContainer"] {
            background: #f7f4ee;
        }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #111315 0%, #1b1d21 100%);
        }

        [data-testid="stSidebar"] * {
            color: #f6f1e7;
        }

        div[data-testid="stRadio"] label p {
            font-weight: 600;
        }

        .sc-shell-card {
            background: rgba(255, 252, 246, 0.94);
            border: 1px solid #e5dbc6;
            border-radius: 18px;
            padding: 1rem 1.15rem;
        }

        .sc-muted {
            color: #6b675f;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def init_session_state():
    if "selected_page" not in st.session_state:
        st.session_state.selected_page = "Mockups"

    if "product_name" not in st.session_state:
        st.session_state.product_name = ""

    if "last_uploaded_file_name" not in st.session_state:
        st.session_state.last_uploaded_file_name = None

    if "last_autofilled_product_name" not in st.session_state:
        st.session_state.last_autofilled_product_name = ""

    if "last_generation_result" not in st.session_state:
        st.session_state.last_generation_result = None


def get_local_recent_runs(limit=5):
    if not RUNS_DIR.exists():
        return []

    return sorted(
        [path for path in RUNS_DIR.iterdir() if path.is_dir()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[:limit]


def get_recent_runs(limit=5):
    if drive_storage.is_drive_configured():
        try:
            recent_drive_runs = drive_storage.list_recent_drive_runs(limit=limit)
            if recent_drive_runs:
                return recent_drive_runs
        except Exception:
            pass

    return [
        {"name": path.name, "source": "local", "path": path}
        for path in get_local_recent_runs(limit=limit)
    ]


def get_product_name_from_upload(uploaded_file):
    if uploaded_file is None:
        return ""

    return Path(uploaded_file.name).stem.strip()


def load_run_metadata(run_dir):
    run_dir = Path(run_dir)
    manifest_path = run_dir / "manifest.json"
    metadata = {}

    if manifest_path.exists():
        try:
            metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            metadata = {}

    metadata["run_dir"] = str(run_dir)
    metadata["run_name"] = run_dir.name
    metadata["product_name"] = metadata.get("product_name", run_dir.name)
    metadata["sport_category"] = metadata.get("sport_category", "")
    metadata["product_slug"] = metadata.get("product_slug", run_dir.name)
    metadata["shopify_uploads_dir"] = str(run_dir / "shopify-uploads")
    metadata["shopify_uploads_html_path"] = str(run_dir / "shopify-uploads" / "index.html")
    metadata["prompt_dir"] = str(run_dir / "chatgpt-prompts")
    return metadata


def get_product_upload_prompt(metadata, update_existing=False):
    product_name = metadata.get("product_name", "")
    sport_category = metadata.get("sport_category", "")
    product_handle = metadata.get("product_slug", "")
    image_folder = metadata.get("shopify_uploads_dir", "shopify-uploads")
    action = "update the existing Shopify product" if update_existing else "create a new Shopify product"
    action_phrase = "Update the existing product with these new images, replacing the old media." if update_existing else "Create the product from scratch and assign the images correctly."

    upload_instructions = (
        "Attach every file from the Shopify uploads folder to ChatGPT when prompted. "
        "Also attach or reference the Shopify HTML preview file so ChatGPT can see the intended image order and labels."
    )

    if update_existing:
        upload_instructions = (
            "Attach every file from the Shopify uploads folder to ChatGPT and use them to replace the existing product images. "
            "Keep the product handle the same and ensure the old media is replaced with the new files."
        )

    header = (
        "You are a Shopify upload specialist working through ChatGPT. "
        f"Use the image files from the Shopify uploads folder and the product details below to {action}. "
        "Copy the prompt exactly and attach the uploaded images when ChatGPT asks."
    )

    csv_header = (
        "Handle,Title,Body (HTML),Vendor,Product Category,Type,Tags,Published,"
        "Option1 Name,Option1 Value,Variant SKU,Variant Grams,Variant Inventory Tracker,"
        "Variant Inventory Policy,Variant Fulfillment Service,Variant Price,Variant Compare At Price,"
        "Variant Requires Shipping,Variant Taxable,Image Src,Image Position,Image Alt Text,Status"
    )

    prompt = f"""
{header}

Product name: {product_name}
Sport category: {sport_category}
Product handle: {product_handle}

Important Shopify CSV columns to use when importing or updating a product:
{csv_header}

Use the images from the Shopify uploads folder and the HTML preview file at {metadata.get('shopify_uploads_html_path')}.
{upload_instructions}
{action_phrase}

Instructions:
- If this is a new product, create it with the provided handle and assign the uploaded images to the correct variant positions.
- If updating an existing product, keep the product handle the same and replace the current product images with the new uploaded images.
- Ensure all image filenames are copied into ChatGPT and attached in the order needed for Shopify.
- Do not create duplicate products when updating existing items.
- Use the CSV header structure above to generate the import data or the Shopify product upload request.

If you are not using a CSV file, make sure the same values are included in the Shopify product fields. Copy the full prompt and paste it into ChatGPT, then attach all Shopify preview images so ChatGPT can complete the product creation or update workflow.
"""
    return prompt.strip()


def get_sport_category(selected_option, custom_value):
    if selected_option == "Custom":
        return custom_value.strip()

    return selected_option.strip()


def normalize_asset(asset):
    defaults = {
        "key": None,
        "label": "Image",
        "review_path": None,
        "webp_path": None,
        "jpg_path": None,
        "include_in_zip": True,
        "asset_group": "generated",
        "prompt_filename": None,
        "export_to_shopify": True,
        "export_to_socials": True,
    }
    normalized = defaults.copy()
    normalized.update(asset or {})
    return normalized


def ensure_result_assets(result):
    assets = [normalize_asset(asset) for asset in result.get("assets", [])]
    if assets:
        result["assets"] = assets
        return result

    review_paths = result.get("review_paths", [])
    webp_paths = result.get("webp_paths", [])
    jpg_paths = result.get("jpg_paths", [])
    legacy_assets = []

    for index, (asset_key, asset_label) in enumerate(LEGACY_BASE_ASSET_SPECS):
        if index >= len(review_paths) and index >= len(webp_paths) and index >= len(jpg_paths):
            continue

        review_path = review_paths[index] if index < len(review_paths) else None
        webp_path = webp_paths[index] if index < len(webp_paths) else None
        jpg_path = jpg_paths[index] if index < len(jpg_paths) else None
        legacy_assets.append(
            normalize_asset(
                image_factory.build_asset_record(
                    key=asset_key,
                    label=asset_label,
                    review_path=review_path,
                    webp_path=webp_path,
                    jpg_path=jpg_path,
                )
            )
        )

    result["assets"] = legacy_assets
    return result


def normalize_generation_result(result):
    defaults = {
        "product_name": None,
        "sport_category": None,
        "created_at": None,
        "product_slug": None,
        "sport_slug": None,
        "run_dir": None,
        "review_dir": None,
        "webp_dir": None,
        "jpg_dir": None,
        "zip_dir": None,
        "zip_path": None,
        "social_zip_path": None,
        "prompt_zip_path": None,
        "complete_zip_path": None,
        "black_framed_webp_path": None,
        "black_framed_jpg_path": None,
        "prompt_dir": None,
        "prompt_paths": [],
        "review_paths": [],
        "webp_paths": [],
        "jpg_paths": [],
        "shopify_uploads_dir": None,
        "socials_dir": None,
        "shopify_uploads_html_path": None,
        "assets": [],
        "lifestyle_mockup_paths": {},
        "lifestyle_pack_error": None,
        "manifest_path": None,
        "uploaded_files": [],
        "drive_root_id": None,
        "drive_root_url": None,
        "drive_run_id": None,
        "drive_run_url": None,
        "drive_sync_enabled": False,
        "drive_sync_error": None,
        "drive_sync_message": None,
    }
    normalized = defaults.copy()
    normalized.update(result or {})
    normalized = ensure_result_assets(normalized)
    return normalized


def get_asset_checkbox_key(run_dir, asset_key):
    return f"include-asset::{run_dir}::{asset_key}"


def get_lifestyle_asset_key(prompt_filename):
    return f"lifestyle::{prompt_filename}"


def get_prompt_label(prompt_path):
    prompt_name = Path(prompt_path).name
    return PROMPT_LABELS.get(prompt_name, prompt_name)


def is_product_page_prompt(prompt_path):
    return Path(prompt_path).name in PRODUCT_PAGE_PROMPT_NAMES


def render_download_button(label, file_path, mime, key):
    if not file_path:
        return

    file_path = Path(file_path)
    if not file_path.exists():
        return

    st.download_button(
        label=label,
        data=file_path.read_bytes(),
        file_name=file_path.name,
        mime=mime,
        key=key,
        use_container_width=True,
    )


def prime_asset_selection_state(result):
    if not result["run_dir"]:
        return

    for asset in result["assets"]:
        state_key = get_asset_checkbox_key(result["run_dir"], asset["key"])
        if state_key not in st.session_state:
            st.session_state[state_key] = asset["include_in_zip"]


def upsert_result_asset(result, asset_record):
    result = normalize_generation_result(result)
    normalized_asset = normalize_asset(asset_record)

    for index, existing_asset in enumerate(result["assets"]):
        if existing_asset["key"] == normalized_asset["key"]:
            merged_asset = existing_asset.copy()
            merged_asset.update(normalized_asset)
            result["assets"][index] = normalize_asset(merged_asset)
            return result

    result["assets"].append(normalized_asset)
    return result


def write_local_manifest(result, uploaded_files=None):
    result = normalize_generation_result(result)
    if not result["run_dir"]:
        return None

    manifest_path = Path(result["run_dir"]) / "manifest.json"
    manifest_data = {}

    if manifest_path.exists():
        with manifest_path.open("r", encoding="utf-8") as file_handle:
            manifest_data = json.load(file_handle)

    manifest_data.update(
        {
            "product_name": result["product_name"],
            "product_slug": result["product_slug"],
            "sport_category": result["sport_category"],
            "created_at": result["created_at"],
            "local_run_path": str(Path(result["run_dir"]).resolve()),
            "drive_folder_id": result["drive_run_id"],
            "drive_folder_link": result["drive_run_url"],
            "uploaded_files": uploaded_files
            if uploaded_files is not None
            else manifest_data.get("uploaded_files", []),
        }
    )

    manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
    result["manifest_path"] = manifest_path
    return manifest_path


def ensure_drive_sections():
    root_folder_id = drive_storage.get_root_folder_id()
    if not root_folder_id:
        raise drive_storage.DriveStorageError(
            "GOOGLE_DRIVE_ROOT_FOLDER_ID is missing."
        )

    section_ids = {}
    for key, folder_name in DRIVE_SECTION_NAMES.items():
        section_ids[key] = drive_storage.ensure_drive_folder(root_folder_id, folder_name)

    return section_ids


def sync_result_to_google_drive(result):
    result = normalize_generation_result(result)
    write_local_manifest(result)

    if not result["run_dir"]:
        return result

    if not drive_storage.is_drive_configured():
        result["drive_sync_enabled"] = False
        result["drive_sync_error"] = None
        result["drive_sync_message"] = (
            "Google Drive is not configured. Files were saved locally only."
        )
        return result

    try:
        section_ids = ensure_drive_sections()
        upload_info = drive_storage.upload_folder_to_drive(
            result["run_dir"],
            section_ids["mockups"],
        )
        manifest_data = drive_storage.create_or_update_manifest(
            result["run_dir"],
            upload_info["folder_id"],
            upload_info["uploaded_files"],
        )
        result["drive_sync_enabled"] = True
        result["drive_root_id"] = drive_storage.get_root_folder_id()
        result["drive_root_url"] = drive_storage.get_drive_folder_link(result["drive_root_id"])
        result["drive_run_id"] = upload_info["folder_id"]
        result["drive_run_url"] = upload_info["folder_link"]
        result["uploaded_files"] = manifest_data.get("uploaded_files", upload_info["uploaded_files"])
        result["drive_sync_error"] = None
        result["drive_sync_message"] = "Saved to Google Drive"
        write_local_manifest(result, uploaded_files=result["uploaded_files"])
    except Exception as error:
        result["drive_sync_enabled"] = True
        result["drive_sync_error"] = str(error)
        result["drive_sync_message"] = None

    return result


def rebuild_result_artifacts(result):
    result = normalize_generation_result(result)

    if not result["run_dir"] or not result["product_slug"]:
        return result

    run_dir = Path(result["run_dir"])
    zip_dir = run_dir / "zip"
    image_factory.reset_directory_contents(zip_dir)

    export_dirs = image_factory.rebuild_export_folders(
        run_dir,
        result["assets"],
        product_name=result.get("product_name", ""),
        sport_category=result.get("sport_category", ""),
    )
    result["zip_dir"] = zip_dir
    result["shopify_uploads_dir"] = export_dirs["shopify_uploads_dir"]
    result["shopify_uploads_html_path"] = export_dirs.get("shopify_uploads_html_path")
    result["socials_dir"] = export_dirs["socials_dir"]
    result["zip_path"] = None
    result["social_zip_path"] = None
    result["prompt_zip_path"] = None

    result["complete_zip_path"] = image_factory.create_complete_pack_zip(
        zip_dir,
        result["product_slug"],
        assets=result["assets"],
    )
    write_local_manifest(result)
    return result


def apply_asset_selection_from_session(result):
    result = normalize_generation_result(result)
    prime_asset_selection_state(result)

    selections_changed = False

    for asset in result["assets"]:
        state_key = get_asset_checkbox_key(result["run_dir"], asset["key"])
        selected = bool(st.session_state.get(state_key, asset["include_in_zip"]))
        if selected != asset["include_in_zip"]:
            asset["include_in_zip"] = selected
            selections_changed = True

    if selections_changed:
        result = rebuild_result_artifacts(result)
        result = sync_result_to_google_drive(result)
        st.session_state.last_generation_result = result

    return result


def build_lifestyle_asset(prompt_path, saved_paths):
    prompt_filename = Path(prompt_path).name
    is_product_page_asset = image_factory.is_product_page_prompt_filename(prompt_filename)
    return image_factory.build_asset_record(
        key=get_lifestyle_asset_key(prompt_filename),
        label=get_prompt_label(prompt_path),
        review_path=saved_paths.get("jpg_path") or saved_paths.get("webp_path"),
        webp_path=saved_paths.get("webp_path"),
        jpg_path=saved_paths.get("jpg_path"),
        include_in_zip=True,
        asset_group="lifestyle",
        prompt_filename=prompt_filename,
        export_to_shopify=is_product_page_asset,
        export_to_socials=True,
    )


def save_uploaded_lifestyle_result(result, prompt_path, uploaded_file):
    result = normalize_generation_result(result)

    saved_paths = image_factory.save_lifestyle_mockup(
        run_dir=result["run_dir"],
        product_slug=result["product_slug"],
        sport_slug=result["sport_slug"],
        prompt_filename=Path(prompt_path).name,
        image_bytes=uploaded_file.getvalue(),
    )

    prompt_filename = Path(prompt_path).name
    result["lifestyle_mockup_paths"][prompt_filename] = saved_paths
    result = upsert_result_asset(result, build_lifestyle_asset(prompt_path, saved_paths))

    state_key = get_asset_checkbox_key(result["run_dir"], get_lifestyle_asset_key(prompt_filename))
    if state_key not in st.session_state:
        st.session_state[state_key] = True

    result["lifestyle_pack_error"] = None
    result = rebuild_result_artifacts(result)
    return sync_result_to_google_drive(result)


def render_asset_selection_controls(result):
    result = normalize_generation_result(result)

    if not result["assets"]:
        return result

    included_count = sum(1 for asset in result["assets"] if asset["include_in_zip"])
    st.subheader("ZIP Image Selection")
    st.caption(
        f"{included_count} of {len(result['assets'])} images are currently included. "
        "Untick any image to leave it out of the ZIP downloads."
    )

    return result


def render_generated_previews(result):
    st.subheader("Generated Previews")
    preview_cols = st.columns(2)
    base_assets = [asset for asset in result["assets"] if asset["asset_group"] == "generated"]

    for index, asset in enumerate(base_assets):
        with preview_cols[index % 2]:
            checkbox_key = get_asset_checkbox_key(result["run_dir"], asset["key"])
            st.checkbox("Include in ZIP", key=checkbox_key)

            preview_path = asset["review_path"] or asset["webp_path"] or asset["jpg_path"]
            if preview_path and Path(preview_path).exists():
                st.image(str(preview_path), caption=asset["label"], width="stretch")
                st.caption(Path(preview_path).name)


def render_prompt_cards(result, prompt_paths, heading):
    if not prompt_paths:
        return

    st.subheader(heading)
    cols = st.columns(3)

    for index, prompt_path in enumerate(prompt_paths):
        with cols[index % 3]:
            st.markdown(f"**{get_prompt_label(prompt_path)}**")
            with st.expander("View Prompt"):
                st.code(prompt_path.read_text(encoding="utf-8"), language=None)

            prompt_name = prompt_path.name
            saved_lifestyle_paths = result["lifestyle_mockup_paths"].get(prompt_name)

            if saved_lifestyle_paths:
                saved_webp_path = saved_lifestyle_paths.get("webp_path")
                saved_jpg_path = saved_lifestyle_paths.get("jpg_path")
                asset_key = get_lifestyle_asset_key(prompt_name)
                checkbox_key = get_asset_checkbox_key(result["run_dir"], asset_key)

                preview_path = saved_webp_path or saved_jpg_path
                if preview_path and Path(preview_path).exists():
                    st.checkbox("Include in ZIP", key=checkbox_key)
                    st.image(
                        str(preview_path),
                        caption=Path(preview_path).name,
                        width="stretch",
                    )

            uploaded_lifestyle_image = st.file_uploader(
                "Upload image from ChatGPT",
                type=["png", "jpg", "jpeg", "webp"],
                key=f"lifestyle-upload::{result['run_dir']}::{prompt_name}",
                help="Upload the finished ChatGPT lifestyle image here.",
            )

            if st.button(
                "Add To ZIP",
                key=f"save-lifestyle::{result['run_dir']}::{prompt_name}",
                use_container_width=True,
            ):
                if uploaded_lifestyle_image is None:
                    st.warning("Upload the generated lifestyle image first.")
                else:
                    try:
                        updated_result = save_uploaded_lifestyle_result(
                            result,
                            prompt_path,
                            uploaded_lifestyle_image,
                        )
                        st.session_state.last_generation_result = updated_result
                        st.rerun()
                    except Exception as error:
                        st.error("Could not save the lifestyle image for this prompt.")
                        st.exception(error)


def render_downloads(result):
    render_download_button(
        "Download ZIP",
        result["complete_zip_path"],
        "application/zip",
        key=f"download-complete::{result['run_dir']}",
    )


def render_generation_result(result):
    result = apply_asset_selection_from_session(result)
    result = render_asset_selection_controls(result)
    st.success("Images generated successfully.")

    if result["run_dir"]:
        st.caption(f"Local run folder: `{result['run_dir']}`")

    render_downloads(result)

    if result["drive_run_url"]:
        st.success("Saved to Google Drive")
        st.markdown(f"[Open Google Drive run folder]({result['drive_run_url']})")
    elif result["drive_sync_error"]:
        st.warning(
            "Google Drive upload failed, but the local ZIP downloads are still ready. "
            f"{result['drive_sync_error']}"
        )
    else:
        st.info("Google Drive is not configured. Files were saved locally only.")

    if result["shopify_uploads_dir"]:
        with suppress(FileNotFoundError):
            st.caption(
                f"{len(list(Path(result['shopify_uploads_dir']).glob('*.webp')))} WEBP files ready for Shopify uploads."
            )

    if result["socials_dir"]:
        with suppress(FileNotFoundError):
            st.caption(
                f"{len(list(Path(result['socials_dir']).glob('*.jpg')))} JPG files ready for socials."
            )

    render_generated_previews(result)

    if result["lifestyle_pack_error"]:
        st.warning(
            "The base image set was created, but the prompt pack could not be prepared for this run: "
            f"{result['lifestyle_pack_error']}"
        )

    prompt_paths = [
        Path(prompt_path)
        for prompt_path in result["prompt_paths"]
        if Path(prompt_path).exists()
    ]

    if prompt_paths:
        st.info(
            "Use the prompts below for ChatGPT lifestyle images, then upload the finished images back into the matching cards."
        )
        product_page_prompts = [path for path in prompt_paths if is_product_page_prompt(path)]
        social_prompts = [path for path in prompt_paths if not is_product_page_prompt(path)]

        render_prompt_cards(
            result,
            product_page_prompts,
            "Product Page Lifestyle Mockups",
        )
        render_prompt_cards(
            result,
            social_prompts,
            "Social Lifestyle Mockups",
        )
    else:
        st.caption("Generate a new run to create the ChatGPT lifestyle prompt pack.")


def render_recent_runs_sidebar():
    recent_runs = get_recent_runs(limit=5)
    if not recent_runs:
        return

    st.sidebar.divider()
    st.sidebar.subheader("Recent Runs")
    for run_entry in recent_runs:
        if run_entry.get("url"):
            st.sidebar.markdown(f"[{run_entry['name']}]({run_entry['url']})")
        else:
            st.sidebar.caption(run_entry["name"])


def render_sidebar():
    st.sidebar.title("Sports Cave")
    st.sidebar.caption("Image Factory")
    st.sidebar.caption(APP_VERSION)
    st.sidebar.radio(
        "Navigation",
        MENU_OPTIONS,
        key="selected_page",
        label_visibility="collapsed",
    )

    if st.session_state.selected_page == "Mockups":
        st.sidebar.divider()
        st.sidebar.subheader("How It Works")
        st.sidebar.write("1. Upload the finished artwork file.")
        st.sidebar.write("2. Enter the product name.")
        st.sidebar.write("3. Choose the sport category.")
        st.sidebar.write("4. Click Generate Images.")
        st.sidebar.write("5. Tick only the images you want in the ZIP.")
        st.sidebar.write("6. Add any ChatGPT lifestyle images below.")

    st.sidebar.divider()
    st.sidebar.subheader("Storage")
    if drive_storage.is_drive_configured():
        root_folder_id = drive_storage.get_root_folder_id()
        st.sidebar.caption("Google Drive configured: Yes")
        st.sidebar.caption(f"Root folder ID: `{root_folder_id}`")
        st.sidebar.markdown(
            f"[Open root folder]({drive_storage.get_drive_folder_link(root_folder_id)})"
        )
    else:
        st.sidebar.caption("Google Drive configured: No")
        st.sidebar.caption("Local output is active until Drive is configured.")

    render_recent_runs_sidebar()


def render_mockups_page():
    st.title("Sports Cave Image Factory")
    st.caption(
        "Upload one finished artwork, generate the base images, then download one ZIP or add ChatGPT lifestyle images."
    )

    uploaded_file = st.file_uploader(
        "Upload finished Sports Cave artwork",
        type=["jpg", "jpeg", "png", "webp"],
        help="Upload the final flattened artwork that should appear in every mockup.",
    )

    autofill_product_name = get_product_name_from_upload(uploaded_file)

    if uploaded_file is not None and uploaded_file.name != st.session_state.last_uploaded_file_name:
        if (
            not st.session_state.product_name.strip()
            or st.session_state.product_name == st.session_state.last_autofilled_product_name
        ):
            st.session_state.product_name = autofill_product_name

        st.session_state.last_uploaded_file_name = uploaded_file.name
        st.session_state.last_autofilled_product_name = autofill_product_name

    elif uploaded_file is None and st.session_state.last_uploaded_file_name is not None:
        if st.session_state.product_name == st.session_state.last_autofilled_product_name:
            st.session_state.product_name = ""

        st.session_state.last_uploaded_file_name = None
        st.session_state.last_autofilled_product_name = ""

    product_name = st.text_input(
        "Product name",
        key="product_name",
        placeholder="Example: Arsenal The Wait Is Over",
    )

    sport_option = st.selectbox(
        "Sport category",
        options=SPORT_OPTIONS,
        index=0,
    )

    custom_sport = ""
    if sport_option == "Custom":
        custom_sport = st.text_input(
            "Custom sport category",
            placeholder="Example: Formula 1",
        )

    generate_clicked = st.button("Generate Images", type="primary")

    if uploaded_file is not None:
        st.subheader("Uploaded Artwork")
        st.image(uploaded_file, caption=uploaded_file.name, width="stretch")

    if generate_clicked:
        sport_category = get_sport_category(sport_option, custom_sport)

        if uploaded_file is None:
            st.error("Please upload an artwork image first.")
        elif not product_name.strip():
            st.error("Please enter a product name.")
        elif not sport_category:
            st.error("Please enter a sport category.")
        else:
            with st.spinner("Generating Sports Cave product images..."):
                temp_artwork_path = None
                suffix = Path(uploaded_file.name).suffix or ".jpg"

                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                        temp_file.write(uploaded_file.getbuffer())
                        temp_artwork_path = Path(temp_file.name)

                    result = image_factory.generate_product_images(
                        product_name=product_name,
                        sport_category=sport_category,
                        artwork_file_path=temp_artwork_path,
                        base_dir=BASE_DIR,
                    )
                except Exception as error:
                    st.error("Something went wrong while generating the image assets.")
                    st.exception(error)
                    result = None
                finally:
                    if temp_artwork_path is not None:
                        with suppress(FileNotFoundError, PermissionError):
                            temp_artwork_path.unlink()

                if result is not None:
                    try:
                        result = rebuild_result_artifacts(result)
                    except Exception as error:
                        st.error("Something went wrong while preparing the download package.")
                        st.exception(error)

                    result = sync_result_to_google_drive(result)
                    st.session_state.last_generation_result = result

    if st.session_state.last_generation_result is not None:
        render_generation_result(st.session_state.last_generation_result)


def render_product_uploads_page():
    st.title("Product Uploads")
    st.caption(
        "Use the Shopify upload assets created by a finished run to push a new product or update an existing product in Shopify through ChatGPT."
    )

    st.info(
        "This page is an instructional prompt generator. It provides the exact text you need to copy into ChatGPT, attach the Shopify upload images and HTML preview, and then execute the new-product or update-product workflow in ChatGPT."
    )

    st.markdown(
        "- `New Shopify product` will generate a prompt for creating a brand new product in Shopify.\n"
        "- `Update existing product` will generate a prompt for replacing the images on an existing Shopify product.\n"
        "- If you already have a `shopify-uploads` folder and HTML preview, attach those files in ChatGPT when prompted."
    )

    runs = get_local_recent_runs(limit=10)
    metadata = None

    if runs:
        run_names = [run.name for run in runs]
        selected_run_name = st.selectbox("Choose a recent run", run_names)
        selected_run = next((run for run in runs if run.name == selected_run_name), None)

        if selected_run is not None:
            metadata = load_run_metadata(selected_run)
            st.markdown(f"**Run:** {metadata['run_name']}")
            st.markdown(f"**Product:** {metadata.get('product_name', 'Unknown')}")
            st.markdown(f"**Sport category:** {metadata.get('sport_category', 'Unknown')}")
        else:
            st.warning("Select a run above to load the Shopify upload prompt and image preview.")
    else:
        st.warning(
            "No local run folders were found in output/runs. You can still use this page as a prompt generator for ChatGPT if you already have Shopify upload assets elsewhere."
        )

    if metadata is None:
        metadata = {
            "run_name": "example-run",
            "product_name": "Example Product",
            "sport_category": "Example Sport",
            "product_slug": "example-product",
            "shopify_uploads_dir": "shopify-uploads",
            "shopify_uploads_html_path": "shopify-uploads/index.html",
        }
    shopify_uploads_dir = Path(metadata["shopify_uploads_dir"])
    shopify_html_path = Path(metadata["shopify_uploads_html_path"])

    if shopify_uploads_dir.exists():
        upload_files = sorted(shopify_uploads_dir.glob("*.webp"))
        st.write(f"{len(upload_files)} Shopify upload images found.")

        if shopify_html_path.exists():
            st.download_button(
                "Download Shopify HTML preview",
                shopify_html_path.read_bytes(),
                file_name="shopify-uploads-preview.html",
                mime="text/html",
            )
        else:
            st.warning("Shopify HTML preview is not available yet. Generate or rebuild the run to create it.")

        if upload_files:
            st.write("**Shopify upload image files:**")
            for upload_file in upload_files:
                st.write(f"- {upload_file.name}")
    else:
        st.info(
            "No local shopify-uploads folder was found for this run. If you already have the folder and HTML preview elsewhere, attach them in ChatGPT as described below."
        )

    st.divider()
    st.write(
        "Use the two buttons below to reveal the ChatGPT prompt text. Attach the Shopify upload images and copy the prompt into ChatGPT."
    )

    new_prompt_key = f"show_new_prompt::{metadata['run_name']}"
    existing_prompt_key = f"show_existing_prompt::{metadata['run_name']}"

    if new_prompt_key not in st.session_state:
        st.session_state[new_prompt_key] = False
    if existing_prompt_key not in st.session_state:
        st.session_state[existing_prompt_key] = False

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Show prompt for NEW Shopify product", key=f"new-prompt-button::{metadata['run_name']}"):
            st.session_state[new_prompt_key] = True
            st.session_state[existing_prompt_key] = False

    with col2:
        if st.button("Show prompt for UPDATE existing product", key=f"update-prompt-button::{metadata['run_name']}"):
            st.session_state[existing_prompt_key] = True
            st.session_state[new_prompt_key] = False

    if st.session_state[new_prompt_key]:
        st.subheader("New Product Prompt")
        st.code(get_product_upload_prompt(metadata, update_existing=False), language=None)

    if st.session_state[existing_prompt_key]:
        st.subheader("Update Existing Product Prompt")
        st.code(get_product_upload_prompt(metadata, update_existing=True), language=None)


def test_google_drive_connection():
    section_ids = ensure_drive_sections()
    test_dir = BASE_DIR / "output" / "_drive_test"
    test_dir.mkdir(parents=True, exist_ok=True)
    test_file = test_dir / "google-drive-connection-test.txt"
    test_file.write_text("Sports Cave Image Factory connection test", encoding="utf-8")

    try:
        return drive_storage.upload_file_to_drive(
            test_file,
            section_ids["system_logs"],
            mime_type="text/plain",
        )
    finally:
        with suppress(FileNotFoundError, PermissionError):
            test_file.unlink()


def render_google_drive_page():
    st.title("Google Drive")
    st.caption("OAuth refresh-token Drive storage for Sports Cave runs.")

    root_folder_id = drive_storage.get_root_folder_id()
    drive_configured = drive_storage.is_drive_configured()

    if drive_configured:
        st.success("Status: Connected")
    else:
        st.info("Status: Not connected")

    st.write(f"Root folder ID: `{root_folder_id or 'Not set'}`")
    if root_folder_id:
        st.markdown(
            f"[Open root folder]({drive_storage.get_drive_folder_link(root_folder_id)})"
        )

    if st.button("Test Google Drive Connection", type="primary", disabled=not drive_configured):
        try:
            uploaded_test_file = test_google_drive_connection()
            st.success("Google Drive connection test succeeded.")
            st.markdown(f"[Open uploaded test file]({uploaded_test_file['drive_link']})")
        except Exception as error:
            st.error(f"Google Drive connection test failed: {error}")

    st.subheader("Recent Drive Runs")
    if drive_configured:
        try:
            recent_runs = drive_storage.list_recent_drive_runs(limit=20)
        except Exception as error:
            st.warning(f"Could not load recent Drive runs: {error}")
            recent_runs = []
    else:
        recent_runs = []

    if recent_runs:
        for run_entry in recent_runs:
            st.markdown(f"- [{run_entry['name']}]({run_entry['url']})")
    else:
        st.caption("No Drive runs found yet.")


def get_password_protection_status():
    for env_key in PASSWORD_ENV_KEYS:
        if os.getenv(env_key):
            return "Enabled"

    return "Managed outside app or not detected"


def render_settings_page():
    st.title("Settings")
    st.caption("Current app and environment status.")

    st.write(f"**Password protection:** {get_password_protection_status()}")
    st.write(f"**Google Drive configured:** {'Yes' if drive_storage.is_drive_configured() else 'No'}")
    st.write(f"**Root folder ID present:** {'Yes' if drive_storage.get_root_folder_id() else 'No'}")
    st.write(f"**OAuth client ID present:** {'Yes' if os.getenv('GOOGLE_OAUTH_CLIENT_ID') else 'No'}")
    st.write(f"**OAuth client secret present:** {'Yes' if os.getenv('GOOGLE_OAUTH_CLIENT_SECRET') else 'No'}")
    st.write(f"**OAuth refresh token present:** {'Yes' if os.getenv('GOOGLE_OAUTH_REFRESH_TOKEN') else 'No'}")
    st.write(f"**Output folder path:** `{RUNS_DIR}`")
    st.write(f"**App version:** {APP_VERSION}")


def render_placeholder_page(title, body):
    st.title(title)
    st.caption(body)


def main():
    inject_styles()
    init_session_state()
    render_sidebar()

    current_page = st.session_state.selected_page
    if current_page == "Google Drive":
        render_google_drive_page()
    elif current_page == "Limited Editions":
        render_placeholder_page("Limited Editions", "Limited edition tracking will live here.")
    elif current_page == "Product Uploads":
        render_product_uploads_page()
    elif current_page == "Settings":
        render_settings_page()
    else:
        render_mockups_page()


main()
