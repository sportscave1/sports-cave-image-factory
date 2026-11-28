"""Shared PSD eligibility without loading the Streamlit gallery."""
from product_upload_dropbox import REVIEW, approved, within
from design_review_metadata import is_working_file


def final_psd(entry):
    return bool(approved(entry) and within(entry['path_display'], REVIEW)
                and entry.get('rev')
                and not is_working_file(entry['name']))
