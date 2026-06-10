from contextlib import suppress
import base64
import importlib
from pathlib import Path
import tempfile

import streamlit as st
import streamlit.components.v1 as components

import image_factory as image_factory_module


image_factory = importlib.reload(image_factory_module)


BASE_DIR = Path(__file__).resolve().parent
RUNS_DIR = BASE_DIR / "output" / "runs"

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


def get_recent_runs(limit=5):
    if not RUNS_DIR.exists():
        return []

    return sorted(
        [path for path in RUNS_DIR.iterdir() if path.is_dir()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[:limit]


def get_sport_category(selected_option, custom_value):
    if selected_option == "Custom":
        return custom_value.strip()

    return selected_option.strip()


def get_product_name_from_upload(uploaded_file):
    if uploaded_file is None:
        return ""

    return Path(uploaded_file.name).stem.strip()


def render_download_button(label, file_path, mime):
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
    )


def get_prompt_label(prompt_path):
    prompt_name = Path(prompt_path).name
    return PROMPT_LABELS.get(prompt_name, prompt_name)


def render_copy_prompt_control(prompt_text, prompt_name):
    encoded_prompt = base64.b64encode(prompt_text.encode("utf-8")).decode("ascii")
    button_id = f"copy-prompt-{prompt_name.replace('.', '-').replace('_', '-')}"

    components.html(
        f"""
        <button
            id="{button_id}"
            style="
                width: 100%;
                height: 40px;
                border: 1px solid #d0d7de;
                border-radius: 10px;
                background: #ffffff;
                color: #1f2937;
                font-size: 14px;
                font-family: sans-serif;
                font-weight: 600;
                cursor: pointer;
            "
            onclick="
                const text = atob('{encoded_prompt}');
                navigator.clipboard.writeText(text).then(() => {{
                    const btn = document.getElementById('{button_id}');
                    const original = btn.innerHTML;
                    btn.innerHTML = 'Copied';
                    setTimeout(() => btn.innerHTML = original, 1200);
                }});
            "
        >
            Copy Prompt
        </button>
        """,
        height=46,
    )


def is_product_page_prompt(prompt_path):
    return Path(prompt_path).name in PRODUCT_PAGE_PROMPT_NAMES


def save_uploaded_lifestyle_result(result, prompt_path, uploaded_file):
    result = normalize_generation_result(result)

    saved_paths = image_factory.save_lifestyle_mockup(
        run_dir=result["run_dir"],
        product_slug=result["product_slug"],
        sport_slug=result["sport_slug"],
        prompt_filename=Path(prompt_path).name,
        image_bytes=uploaded_file.getvalue(),
    )

    result["lifestyle_mockup_paths"][Path(prompt_path).name] = saved_paths

    prompt_dir = Path(result["prompt_dir"]) if result["prompt_dir"] else None
    webp_dir = Path(result["run_dir"]) / "webp"
    jpg_dir = Path(result["run_dir"]) / "jpg"
    zip_path = image_factory.create_complete_pack_zip(
        Path(result["run_dir"]) / "zip",
        result["product_slug"],
        webp_dir,
        jpg_dir,
        prompt_dir,
    )
    result["zip_path"] = zip_path
    result["complete_zip_path"] = zip_path
    result["lifestyle_pack_error"] = None

    return result


def normalize_generation_result(result):
    defaults = {
        "complete_zip_path": None,
        "zip_path": None,
        "prompt_zip_path": None,
        "black_framed_webp_path": None,
        "black_framed_jpg_path": None,
        "prompt_paths": [],
        "review_paths": [],
        "run_dir": None,
        "product_slug": None,
        "sport_slug": None,
        "prompt_dir": None,
        "jpg_dir": None,
        "jpg_paths": [],
        "lifestyle_mockup_paths": {},
        "lifestyle_pack_error": None,
    }
    normalized = defaults.copy()
    normalized.update(result)
    return normalized


def render_prompt_cards(result, prompt_paths, heading):
    if not prompt_paths:
        return

    st.subheader(heading)
    cols = st.columns(3)

    for index, prompt_path in enumerate(prompt_paths):
        with cols[index % 3]:
            st.markdown(f"**{get_prompt_label(prompt_path)}**")
            render_copy_prompt_control(prompt_path.read_text(encoding="utf-8"), prompt_path.name)

            prompt_name = prompt_path.name
            saved_lifestyle_paths = result["lifestyle_mockup_paths"].get(prompt_name)

            if saved_lifestyle_paths:
                if isinstance(saved_lifestyle_paths, dict):
                    saved_webp_path = saved_lifestyle_paths.get("webp_path")
                    saved_jpg_path = saved_lifestyle_paths.get("jpg_path")
                else:
                    saved_webp_path = saved_lifestyle_paths
                    saved_jpg_path = None

                if saved_webp_path and Path(saved_webp_path).exists():
                    st.image(
                        str(saved_webp_path),
                        caption=Path(saved_webp_path).name,
                        use_container_width=True,
                    )
                    if saved_jpg_path:
                        st.caption(
                            f"Included in ZIP as {Path(saved_webp_path).name} and {Path(saved_jpg_path).name}"
                        )

            uploaded_lifestyle_image = st.file_uploader(
                "Upload image from ChatGPT",
                type=["png", "jpg", "jpeg", "webp"],
                key=f"lifestyle-upload::{result['run_dir']}::{prompt_name}",
                help="Upload the ChatGPT generation here and it will be added into the final ZIP.",
            )

            if st.button(
                "Add To ZIP",
                key=f"save-lifestyle::{result['run_dir']}::{prompt_name}",
                use_container_width=True,
            ):
                if uploaded_lifestyle_image is None:
                    st.warning("Upload or paste the generated lifestyle image first.")
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


def render_generation_result(result):
    result = normalize_generation_result(result)
    package_zip_path = result["complete_zip_path"] or result["zip_path"]
    st.success("Images generated successfully.")

    if package_zip_path:
        render_download_button(
            "Download Complete Package ZIP",
            package_zip_path,
            "application/zip",
        )

    if result["run_dir"]:
        st.info(f"Saved output folder: {result['run_dir']}")

    st.subheader("Generated Previews")
    preview_cols = st.columns(2)

    for index, preview_path in enumerate(result["review_paths"]):
        with preview_cols[index % 2]:
            st.image(
                str(preview_path),
                caption=Path(preview_path).name,
                use_container_width=True,
            )

    if result["lifestyle_pack_error"]:
        st.warning(
            "The Shopify image set was created, but the lifestyle prompt pack could not be prepared for this run: "
            f"{result['lifestyle_pack_error']}"
        )

    prompt_paths = [
        Path(prompt_path)
        for prompt_path in result["prompt_paths"]
        if Path(prompt_path).exists()
    ]

    if prompt_paths:
        st.info(
            "At the bottom you can copy each prompt, upload the finished ChatGPT image into the little plus box, and it will be added into the final ZIP. "
            "The ZIP includes shopify-uploads, social-media, and chatgpt-prompts folders."
        )
        st.markdown(
            """
            1. Download the ZIP and use `chatgpt-prompts/00-upload-this-black-framed-reference.webp` as the reference in ChatGPT.
            2. Use Man Cave, Office, and Living Room for Product Page lifestyle images.
            3. Use the rest of the prompts for Socials.
            4. Upload each finished ChatGPT image back into its matching box below.
            5. Download the ZIP again when you are done to get the updated package.
            """
        )

        product_page_prompts = [path for path in prompt_paths if is_product_page_prompt(path)]
        social_prompts = [path for path in prompt_paths if not is_product_page_prompt(path)]

        render_prompt_cards(result, product_page_prompts, "Product Page Lifestyle Mockups")
        render_prompt_cards(result, social_prompts, "Social Lifestyle Mockups")
    else:
        st.caption("Generate a new run to create the optional ChatGPT lifestyle prompt pack.")


st.set_page_config(
    page_title="Sports Cave Image Factory",
    layout="wide",
)

if "product_name" not in st.session_state:
    st.session_state.product_name = ""

if "last_uploaded_file_name" not in st.session_state:
    st.session_state.last_uploaded_file_name = None

if "last_autofilled_product_name" not in st.session_state:
    st.session_state.last_autofilled_product_name = ""

if "last_generation_result" not in st.session_state:
    st.session_state.last_generation_result = None

with st.sidebar:
    st.header("How It Works")
    st.write("1. Upload the finished artwork file.")
    st.write("2. Enter the product name.")
    st.write("3. Choose the sport category.")
    st.write("4. Click Generate Images.")
    st.write("5. Review the previews, add any ChatGPT lifestyle images below, and download the final ZIP.")

    recent_runs = get_recent_runs()

    if recent_runs:
        st.divider()
        st.subheader("Recent Jobs")
        for run_path in recent_runs:
            st.caption(run_path.name)

st.title("Sports Cave Image Factory")
st.caption(
    "Upload one finished artwork, generate the base images, then add any ChatGPT lifestyle images into one final ZIP package."
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
    help="This fills from the uploaded filename without the file extension, and you can still change it.",
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
    st.image(uploaded_file, caption=uploaded_file.name, use_container_width=True)

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
                st.session_state.last_generation_result = result

            except Exception as error:
                st.error("Something went wrong.")
                st.exception(error)
            finally:
                if temp_artwork_path is not None:
                    with suppress(FileNotFoundError, PermissionError):
                        temp_artwork_path.unlink()

if st.session_state.last_generation_result is not None:
    render_generation_result(st.session_state.last_generation_result)
