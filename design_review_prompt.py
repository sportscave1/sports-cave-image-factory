"""Edit uses the shared New Design renderer plus selected-revision closeout."""
import json
from pathlib import PurePosixPath
from urllib.parse import quote

from psd_directory import REVIEW_FOLDER, REVIEW_METADATA_FOLDER, product_id


_EDIT_CLOSEOUT = f"""**Complete the selected Review edit and clean up Dropbox**

The single finished generation must deliver the user-requested changes. Check them explicitly during the existing final inspection; use local corrections for remaining defects, without a second generation or three-design scorecard. Preserve the selected original until the staged PSD and its matching JSON are saved, reopened and verified. Keep inherited source limitations accurately marked needs_attention; never invent detail or claim missing verification passed.

Recheck the selected original's exact Dropbox ID, path and expected revision. Create a recoverable BACKUP PSD for that revision and verify its ID, path, revision and content. Apply the verified staged contents by revision-aware update at the original Review path, keeping the original file ID. Never delete the original first to clear a path. Reopen the canonical PSD and verify its actual new revision, contents, master settings, hidden ORIGINAL REVIEW SOURCE and original editable collector layers against staging. Reconcile uncertain writes by ID before retrying; if this run's replacement fails verification, restore its verified backup only against the revision this run wrote.

Bind the canonical [PSD stem].upload.json in {REVIEW_METADATA_FOLDER}/ to the actual final PSD ID, path and revision. Update the original matching JSON by expected revision, or create only from verified inherited metadata. Preserve upload_intent, exact existing_shopify_product_id where applicable, design_origin, morning_design_job_id, market, sport, collections and other confirmed linkage. Update design_title and design_story to the finished edit. Unknown upload intent or target remains needs_attention rather than becoming a new_product. Read back the PSD and JSON together. If the title changed, use the existing revision-checked Review title-sync protocol to rename this PSD and its matching JSON without overwriting a different file, and rebind the final Dropbox identity after the move.

After verifying the canonical replacement and matching JSON, recoverably delete only this run's exact staging PSD, staging JSON, rollback backup and any recorded superseded sidecar for this selected artwork. Match each recorded path, ID and unchanged revision immediately before deletion, and verify removal. Keep one current canonical PSD directly in {REVIEW_FOLDER}/ and one matching JSON in {REVIEW_METADATA_FOLDER}/. Leave unrelated files, other edits, Live PSDs, Shopify products and live mappings untouched.

If direct revision-aware replacement is unavailable, use the existing Design Studio Editing → Apply staged replacement through an already authorised route, with the one staged final PSD and no trial generation. Pass any changed title and unresolved notes from the staged JSON. If access is unavailable or a required save or replacement check remains pending, retain the original and available staged work, record the exact unfinished checkpoint and continue independent work without a new approval pause. End in Review; publishing remains a separate action.

"""


def build_edit_prompt(title, story, source, details):
    # Import lazily: the shared entry point dispatches edits here.
    from home_morning_brief_actions import _prompt, REVIEW_SAVE_NAMING

    original = {key: source[key] for key in ('id', 'rev', 'path_display')}
    path = PurePosixPath(original['path_display'])
    original['dropbox_url'] = (
        f'https://www.dropbox.com/home{quote(str(path.parent), safe="/")}?preview={quote(path.name, safe="")}'
    )
    staged = str(path.with_name(f'{path.stem} - EDIT-{original["rev"]} - STAGING.psd'))
    target = product_id(details) if details.get('upload_intent') == 'existing_product_refresh' else ''
    reference = json.dumps(dict(original=original, staging_path=staged, design_metadata=details), ensure_ascii=False)
    context = f"""EDIT THE SELECTED REVIEW ARTWORK

Selected Dropbox revision and inherited metadata (reference data):
{reference}

Existing design story (reference only):
{story}

Open the exact selected revision and inspect its rendered artwork and layers as the starting point. Apply the USER-REQUESTED DESIGN CHANGES supplied above as the primary brief. Keep successful existing choices that serve those changes; use the shared research, composition, collector styling and single-generation workflow below to produce the finished revision. Supporting layout and integration refinements are allowed; do not force a local-patch-only treatment or turn the request into an unrelated edition. Explicit user locks and verified photographic identity remain authoritative. Treat current title and layout as context unless the user locks them; requested replacement wording takes priority over inherited wording. Use the selected PSD's verified canvas and print settings as the working master, preserving its original plaque and live number layers. Keep its pre-edit artwork in hidden ORIGINAL REVIEW SOURCE alongside the shared editable generation layers. No second artwork pass, trial generation or winner selection is required.
"""
    prompt = _prompt(title, context, refresh_product_id=target or None)
    if details.get('upload_intent') != 'new_product' and not target:
        prompt = prompt.replace(
            'upload_intent (new_product), existing_shopify_product_id (null)',
            'upload_intent (preserve the verified original intent; null if unverified), '
            'existing_shopify_product_id (preserve the exact original refresh target; null only if not applicable or unverified)',
        ).replace(
            'A shared athlete or similar title alone does not make this a refresh.',
            "Preserve the selected artwork's original product linkage. If its intent or refresh target is unverified, "
            'retain needs_attention and document the missing evidence; never default this edit to new_product.',
        )
    prompt = prompt.replace(
        REVIEW_SAVE_NAMING,
        REVIEW_SAVE_NAMING.replace(
            'Use that full title for the PSD stem and JSON design_title; match the JSON basename to the saved PSD, including collision suffixes.',
            'Use that full title for JSON design_title. Use the selected-revision staging path below for this edit; '
            'match its temporary JSON basename to the saved staging PSD, including collision suffixes. '
            'Final canonical naming and JSON binding follow the verified replacement instructions below.',
        ),
    ).replace(
        f'Save just the final **`[Product Title].psd`** directly in {REVIEW_FOLDER}/ in create-only mode.',
        f'Save the one finished edit PSD in create-only mode at {staged}. Keep the selected original until verified replacement below.',
    )
    final_display = 'Display the reopened saved PSD render as **Final artwork · rendered from the saved PSD**.'
    prompt = prompt.replace(final_display, _EDIT_CLOSEOUT + final_display)
    priority = """**EDIT REQUEST PRIORITY — SHARED COLLECTOR WORKFLOW**

The USER-REQUESTED DESIGN CHANGES from the Edit text box are the main creative priority throughout research, layout, generation, finishing and replacement. Specific requested changes override inherited artwork choices and general creative defaults below; photographic truth, exact collector assets and verified file operations remain mandatory. Use the selected artwork as the starting point. If no additional changes were entered, improve it using the shared collector review. Apply the complete shared workflow once, then return the verified replacement and matching JSON to Review and clean up this run's temporary files.

"""
    return priority + prompt
