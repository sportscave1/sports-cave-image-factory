"""Presentation-only cleanup of historical Ads setup instructions."""
import re
from ads_meta_contract import META_AD_URL_PARAMETERS


def creation_instructions(text):
    text = str(text or '')
    # The persisted prompt/CSV and Posting contract remain unchanged. Old drafts
    # pass through the same presentation boundary as newly generated prompts.
    text = re.sub(r'META URL PARAMETERS\s*\n\s*For every Meta ad created from this prompt,.*?Do not rewrite, localise, encode, shorten, remove, or add to these URL parameters\.', '', text, flags=re.S)
    text = re.sub(r'(?m)^\d+\. Under URL parameters, use:\s*\n\s*' + re.escape(META_AD_URL_PARAMETERS) + r'\s*\n', '', text)
    text = re.sub(r'(?mi)^.*(?:The exact URL parameters are used:|The URL parameters field uses|URL parameters use exactly:|Paste this into the Meta URL parameters field for every ad\.).*\n?', '', text)
    text = text.replace(', and ' + META_AD_URL_PARAMETERS, '').replace(' and ' + META_AD_URL_PARAMETERS, '')
    text = text.replace(' and URL parameters', '').replace('URL parameters, ', '')
    return text
