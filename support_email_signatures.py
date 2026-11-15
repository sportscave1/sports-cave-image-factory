"""Sports Cave signature profiles and the existing official inline brand asset."""
import base64
from functools import lru_cache
from html import escape
from pathlib import Path

LOGO_CID = "sports-cave-signature-logo@sportscaveshop.com"
LOGO_ASSET = "sports-cave-os-icon-192-v2"
LOGO_PATH = Path(__file__).resolve().parent / "static" / "branding" / f"{LOGO_ASSET}.png"
EMAIL = "hello@sportscaveshop.com"
WEBSITE = "https://www.sportscaveshop.com"
TAGLINE = "Limited Edition Sports Art · Built for the Fans Who Know."
# Keep the existing database preference key; only its customer-facing profile changes.
PROFILES = {"nathan": ("Nathan", "Nathan Baker", "Founder"),
            "reina": ("Maria", "Maria", "Customer Support"),
            "company": ("Company Default", "Sports Cave", "Customer Support")}


@lru_cache(maxsize=1)
def logo_bytes():
    return LOGO_PATH.read_bytes()


@lru_cache(maxsize=1)
def logo_data_uri():
    """Browser preview only. Outgoing MIME and settings storage use CID, never this URI."""
    return "data:image/png;base64," + base64.b64encode(logo_bytes()).decode("ascii")


def profile(key):
    label, name, role = PROFILES[key]
    name, role = escape(name), escape(role)
    company_line = '' if key == 'company' else '<div style="padding:5px 0 2px 0;font-size:13px;line-height:18px;font-weight:bold;color:#222222;">Sports Cave</div>'
    markup = f'''<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="520" style="width:100%;max-width:520px;border-collapse:collapse;font-family:Arial,Helvetica,sans-serif;color:#333333;">
<tr><td colspan="2" style="padding:0 0 14px 0;font-size:14px;line-height:20px;">Kind regards,</td></tr>
<tr><td width="74" valign="top" style="width:74px;padding:3px 16px 0 0;border-right:2px solid #AA8B49;">
<img src="cid:{LOGO_CID}" alt="Sports Cave" width="56" height="56" style="display:block;width:56px;height:56px;border:0;"></td>
<td valign="top" style="padding:0 0 0 16px;">
<div style="font-size:17px;line-height:22px;font-weight:bold;color:#111111;">{name}</div>
<div style="font-size:12px;line-height:18px;color:#94753C;">{role}</div>
{company_line}
<div style="font-size:12px;line-height:18px;"><a href="mailto:{EMAIL}" style="color:#444444;text-decoration:none;">{EMAIL}</a></div>
<div style="font-size:12px;line-height:18px;"><a href="{WEBSITE}" style="color:#444444;text-decoration:none;">sportscaveshop.com</a></div>
</td></tr>
<tr><td colspan="2" style="padding:12px 0 0 0;"><div style="border-top:1px solid #E5E0D5;padding:9px 0 0 0;font-size:10px;line-height:16px;letter-spacing:0.8px;color:#82765D;">{escape(TAGLINE.upper())}</div></td></tr>
</table>'''
    company_text = '' if key == 'company' else '\nSports Cave'
    plain = f"Kind regards,\n\n{PROFILES[key][1]}\n{PROFILES[key][2]}{company_text}\n{EMAIL}\nsportscaveshop.com\n\n{TAGLINE}"
    return {"id": "maria" if key == "reina" else key, "version": 2, "label": label,
            "display_name": PROFILES[key][1], "role": PROFILES[key][2], "email": EMAIL,
            "website": WEBSITE, "tagline": TAGLINE, "logo_asset": LOGO_ASSET,
            "html": markup, "text": plain}


def defaults():
    return {key: profile(key) for key in PROFILES}
