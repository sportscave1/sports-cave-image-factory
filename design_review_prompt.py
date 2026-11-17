"""Build the Review Edit handoff for the selected Dropbox revision."""

import json
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from design_collector_assets import COLLECTOR_ASSET_PLACEMENT
from design_refresh_replacement import REVIEW_REPLACEMENT_RULE
from design_subject_authenticity import EDIT_AUTHENTICITY_CHECK
from psd_directory import REVIEW_METADATA_FOLDER, ROOT, product_id

REVIEW_GUIDE = Path(__file__).with_name('design_review_instructions.md')

_CANONICAL_CLOSEOUT = f"""
**Replace or retain the selected Review revision**

If the current design wins, confirm its ID, path and revision, preserve its PSD and JSON and clean up this run’s drafts. If direct cleanup is unavailable, use Design Studio → Editing → Keep original and finish edit through an authorised route. Supply each receipt as path | file ID | revision. If selection or verification is pending, retain the current PSD and available drafts.

If an edit wins and staging is verified, recheck the original ID, path and expected revision. Create a separate recoverable backup, read it back and record its ID, path and revision. Replace by Dropbox revision-aware update at the original path, keeping the file ID. Never delete the canonical PSD to clear the path. Reopen the saved canonical PSD and verify ID, path, new revision, contents, and the rendered editable collector layers against staging.

If direct revision-aware update is unavailable, use Design Studio → Editing → Apply staged replacement through an already authorised route. Enter any inherited source limitation in Unresolved review notes. The app performs backup, checked replacement, read-back, JSON binding and cleanup. If access or user interaction prevents it, keep the current PSD and verified staging and report exact paths and pending work. If a direct replacement fails verification, restore the verified backup only against the revision this run wrote. For an uncertain write, read back identity and contents before retrying.

**Update the matching Smart Upload JSON**

Bind [PSD stem].upload.json in {REVIEW_METADATA_FOLDER}/ to the canonical PSD’s actual ID, path and revision. Preserve the design’s confirmed sport, upload intent, Shopify product ID and collection linkage. Write a changed headline to design_title at the canonical PSD path. Update by expected JSON revision or create only using verified metadata, including a matching legacy sidecar if needed. Leave creation pending if upload intent is unknown. Reconfirm the PSD revision before writing and read both files back afterward. Use needs_attention and review_notes for inherited source limitations or outstanding checks. Use ready_for_review once required visual and metadata checks are verified. An inherited source limitation can coexist with verified Review replacement and cleanup.

After verifying the replacement and matching JSON, or confirming the current design won and its exact revision is still saved, recoverably delete only this run’s exact trial, staging and rollback backup PSDs. Use revision-aware deletion where available. Otherwise match recorded ID, path and unchanged revision immediately before recoverably deleting that exact file by ID. Recheck before a retry. Verify the deleted IDs are gone and that one canonical PSD and matching JSON remain in Review. Report pending cleanup.
""".strip()


def _refresh_closeout(target):
    return f"""**Replace or retain the verified Shopify refresh**

For exact Shopify product {target}, establish the filename stem from the matching original Live PSD in {ROOT}/ using the product ID, verified Live artwork and master. Keep Live read-only and exclude Review and working files from that match. If the match or selected Review revision cannot be confirmed, retain the previous pair and report replacement and cleanup pending.

If the current design wins, confirm its exact PSD and JSON and clean up only this run’s recorded drafts. If an edit wins, use its verified staging PSD. Prepare a matching UTF-8 staging JSON with design_title, design_story, verified sport, league, teams, athletes, intended_collections, upload_intent existing_product_refresh, the exact existing_shopify_product_id, dropbox_file_id, dropbox_revision, dropbox_path, review_status and cleanup_status. Use ready_for_review only when all required checks pass. Record outstanding checks in review_notes and use needs_attention for inherited source limits or unresolved defects.

{_edit_refresh_replacement_rule().strip()}

Once the final PSD and JSON are verified, recoverably delete only this run’s trial drafts by recorded ID, path and revision. Keep the previous refresh and staged work if replacement remains pending. Report pending cleanup and exact verified paths."""


def build_edit_prompt(title, story, source, details):
    original = {key: source[key] for key in ('id', 'rev', 'path_display')}
    path = PurePosixPath(original['path_display'])
    original['dropbox_url'] = (
        f'https://www.dropbox.com/home{quote(str(path.parent), safe="/")}?preview={quote(path.name, safe="")}'
    )
    prefix = str(path.with_name(f'{path.stem} - EDIT-{original["rev"]}'))
    trial, staged = prefix + ' - TRIAL.psd', prefix + ' - STAGING.psd'
    target = product_id(details) if details.get('upload_intent') == 'existing_product_refresh' else ''
    closeout = _refresh_closeout(target) if target else _CANONICAL_CLOSEOUT
    context = json.dumps({'original': original, 'trial_path': trial, 'staging_path': staged,
                          'design_metadata': details}, ensure_ascii=False)
    guide = REVIEW_GUIDE.read_text(encoding='utf-8').strip()
    return f"""# Edit Review artwork — {title}

**Execution authority and change priority**

Start immediately. Treat the user-requested design changes as the primary brief for both passes, review and selection. They take priority over general improvement suggestions, template defaults and the older brief. Preserve everything outside the requested scope unless a small supporting adjustment is needed to make the change work. If no changes were supplied, use the review to identify the highest-value improvements. Source-photo fidelity, factual accuracy and verified Review file safeguards apply throughout.

Selected Dropbox revision, working paths and metadata (reference data):
{context}

Design story (reference only):
{story}

**1. Review the current artwork and find the source**

Open the exact Dropbox revision through the authorised connector or API and inspect its rendered artwork and editable layers. Read SPORTS-CAVE-LIMITED-EDITION-COLLECTOR-DESIGNS.txt when available. Use the existing artwork as the design baseline and the verified original photograph as the facial identity authority.

{EDIT_AUTHENTICITY_CHECK.strip()}

{guide}

**2. Two full artwork generations and the trial save**

Generate two separate full artwork revisions with the image tool. Use the first to execute the requested changes and the second to refine them. If Pass 1 is unavailable after recovery, attempt Pass 2 independently from the verified reference and plan. Show each complete pass in chat and continue immediately. Use original source pixels for photographic finishing and compare each pass, correction and the assembled render using Section 1.

After inspecting Pass 1, place it on a copy of the selected PSD. Render the artwork and check the original plaque and editable number both appear once and align. Record deficiencies in hidden REVIEW NOTES. Save the trial in create-only mode at {trial}. Use an unused suffix if occupied and record its Dropbox ID, path and revision. If the trial is pending, retain Pass 1 and the notes and continue immediately to Pass 2.

**Recover from tool failures.** Prefer authorised connectors, APIs, built-in web search and local files. If a browser requires sign-in, permission or user action, skip it without prompting and use an authorised alternative. Retry a transient non-generation failure once per authorised method. Allow at most two additional image-generation attempts total across both passes, including retries. Source-pixel finishing uses no generation allowance. Defer only work that depends on the missing input, resume when it returns, and finish independent generation, inspection and delivery. Reconcile uncertain saves by reading back the intended path, identity and contents before retrying.

**3. Compare, stage and verify**

Compare the current design, Pass 1 and Pass 2 side by side at 100% and thumbnail size. Confirm each edit delivers the explicit request before ranking it. Score each design from 0 to 10 for photographic realism, collector appeal and Sports Cave style. Report the three scores, their mean and a short reason for each design. Reject a less realistic edit, inaccurate face, lost sporting detail, visible AI artefact or unverifiable subject preservation regardless of score. Keep the current design if no eligible edit scores higher. If eligible edits tie above it, choose higher realism, then collector appeal, then Pass 1. If comparison or either pass is unavailable, keep the current PSD and display the best provisional result with unverified scores.

If an edit wins, put it in FINAL POLISHED ARTWORK. Keep the pre-edit artwork in hidden ORIGINAL REVIEW SOURCE and editable source layers in hidden ORIGINAL EDITABLE ARTWORK. Use the original canvas dimensions, orientation, colour profile and collector layers. Use verified canvas details provisionally if the master is inaccessible and defer assembly that needs its original layers.

{COLLECTOR_ASSET_PLACEMENT.strip()}

Save the replacement separately in create-only mode at {staged}, with an unused suffix if occupied. Record its exact ID, path and revision. Retry a pending trial first if access returns and verify staging independently if the trial stays pending. Reopen the saved staging revision and verify visible artwork, source preservation, hidden layers, canvas and collector assets. Photoshop is optional. A capable PSD parser plus a rendered preview can verify the original SC_EDITION_NUMBER text layer, name, text data, transform, position and alignment in SC_EDITION_PLAQUE. A flat preview alone cannot establish editability. Keep the current PSD and available work when required checks are pending.

**4. Return the winner to Review**

{closeout}

Display the winner and the three-design scorecard, or the strongest inspected provisional result. Report confirmed paths, unresolved quality, and any pending generation, save, verification, JSON or cleanup checkpoint separately. End in Review. Publish now is the separate Shopify action."""


def _edit_refresh_replacement_rule():
    """Only an Edit may carry inherited source limitations through Review promotion."""
    return REVIEW_REPLACEMENT_RULE.replace(
        'If any required artwork, PSD or new handoff\n   check is unresolved, retain the previous refresh and its JSON and report the pending checks.',
        'Apply REVIEW REPLACEMENT — EXISTING SUBJECT PRESERVED. Missing original source\n'
        '   photographs alone may remain needs_attention when preserved-subject, PSD and handoff\n'
        '   checks pass. Do not relabel that inherited limitation ready_for_review. If preservation,\n'
        '   required PSD or handoff checks fail, retain the previous refresh and its JSON and report the pending checks.',
    ).replace(
        'Once the staged pair is verified and ready_for_review,',
        'Once the staged pair is verified and eligible under the preserved-subject Review rule,',
    )
