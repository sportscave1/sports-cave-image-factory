"""Post Ad only: compact desktop controls, with a single-column mobile fallback."""
CSS = """<style>
[data-testid="stMain"]:has(.st-key-post-ad-workspace) .block-container {
  padding-top:calc(var(--sc-topbar-height, 3rem) + .55rem)!important;
}
.st-key-post-ad-workspace {color:#252522; background:#faf9f6;}
.st-key-post-ad-workspace [data-testid="stVerticalBlock"] {gap:.45rem;}
.st-key-post-ad-workspace h1 {font-size:1.55rem; padding:.1rem 0 .25rem;}
.st-key-post-ad-workspace h3 {font-size:1.05rem; padding:.3rem 0 .1rem;}
.st-key-post-ad-workspace h4 {font-size:.95rem; padding:.2rem 0;}
.st-key-post-ad-workspace [data-testid="stWidgetLabel"] p {font-size:.82rem;}
.st-key-post-ad-workspace [data-testid="stTextInputRootElement"],
.st-key-post-ad-workspace [data-baseweb="select"] > div {min-height:34px; border-radius:5px;}
.st-key-post-ad-workspace button {min-height:32px; border-radius:5px; box-shadow:none;}
.st-key-post-ad-workspace button[kind="primary"] {background:#b9974c; border-color:#a98a42; color:#171713;}
.st-key-post-ad-workspace button[kind="segmented_controlActive"] {background:#efe6d1; border-color:#b9974c; color:#443719;}
.st-key-post-ad-workspace [data-testid="stVerticalBlockBorderWrapper"] {border-radius:6px; box-shadow:none;}
.st-key-post-ad-workspace [data-testid="stFileUploaderDropzone"] {
  min-height:44px; padding:.3rem .6rem; border:1px solid #deddd7; border-radius:5px;
}
.st-key-post-ad-workspace [data-testid="stFileUploaderDropzone"] svg {display:none;}
.st-key-post-ad-workspace [data-testid="stFileUploaderDropzoneInstructions"] {gap:.15rem;}
.st-key-post-ad-workspace [data-testid="stFileUploaderDropzoneInstructions"] span {font-size:.8rem;}
.st-key-post-ad-workspace [data-testid="stFileUploaderDropzoneInstructions"] small {font-size:.7rem;}
.st-key-post-ad-workspace [data-testid="stImage"] img {max-height:110px; width:auto; object-fit:contain;}
.st-key-post-ad-workspace [data-testid="stAlert"] {padding:.45rem .7rem;}
.st-key-post-ad-workspace .posting-review-grid {display:grid; grid-template-columns:1fr 1fr; gap:.35rem 1rem; font-size:.85rem;}
@media(max-width:700px) {
 .st-key-post-ad-workspace .posting-review-grid {grid-template-columns:1fr;}
 .st-key-post-ad-workspace [data-testid="stHorizontalBlock"] {flex-wrap:wrap;}
 .st-key-post-ad-workspace [data-testid="stColumn"] {min-width:100%;}
}
</style>"""
