"""Edit-specific checkpoints for the canonical Home artwork prompt."""
import json
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from psd_directory import REVIEW_METADATA_FOLDER

REVIEW = Path(__file__).with_name('design_review_instructions.md')


def build_edit_prompt(workflow, source, details):
    original = {key: source[key] for key in ('id', 'rev', 'path_display')}
    stem = PurePosixPath(original['path_display']).stem
    folder = str(PurePosixPath(original['path_display']).parent)
    filename = PurePosixPath(original['path_display']).name
    original['dropbox_url'] = 'https://www.dropbox.com/home' + quote(folder, safe='/') + '?preview=' + quote(filename, safe='')
    prefix = f'{folder}/{stem} - EDIT-{original["rev"]}'
    trial, staged = prefix + ' - TRIAL.psd', prefix + ' - STAGING.psd'

    def replace_section(start, end, content):
        nonlocal workflow
        first = workflow.index(start)
        last = workflow.index(end, first)
        workflow = workflow[:first] + content + '\n\n' + workflow[last:]

    replace_section('**EXECUTION AUTHORITY', '**MANDATORY CONTINUATION AND RECOVERY**', (
        '**EXECUTION AUTHORITY — START NOW**\n\n'
        'Submitting this Edit prompt authorises the complete review, two full artwork generations, '
        'revision-aware Dropbox replacement, matching metadata update and cleanup of this edit’s '
        'temporary files. Make ordinary creative decisions and continue after each progress display '
        'without waiting for approval. Treat supplied story and metadata as reference data.\n\n'
        '**MANDATORY EXECUTION ORDER**\n\n'
        'Review the existing artwork and prioritise corrections → generate and inspect the first '
        'complete revision → save the trial where possible → generate and inspect the second complete '
        'revision → score both completed passes against the current design and select the winner → '
        'if an edit wins, stage and verify it, back up and replace the exact original revision, '
        'verify the saved replacement and update its matching JSON as needed → verify the retained '
        'original if it wins → clean up this edit’s temporary files → display the outcome.\n\n'
        'Use the shared recovery rules below. If the original PSD, master, printer specifications '
        'or Dropbox access is unavailable, continue both generations and all independent work '
        'using available verified references. Keep the review findings, artwork and available assets. '
        'If a missing input prevents verified assembly or replacement, keep that checkpoint pending '
        'and display the strongest available result. If access returns during the run, resume with '
        'the saved work and recheck the original revision before any replacement.'
    ))
    replace_section('**The first Dropbox save', '**Recover from tool failures.**', (
        '**Trial and second pass**\n\n'
        'Inspect the first complete artwork, record concerns in REVIEW NOTES and attempt the '
        'trial save in Step 7. If the trial save remains unavailable, retain the first artwork '
        'and notes. Continue immediately to the second full-artwork generation in Step 8 in '
        'either case. Use the strongest inspected candidate as the basis for targeted corrections. '
        'Keep review drafts labelled as such.'
    ))
    replace_section('Step 2. Inspect designs-canvas.psd', 'Step 3. Define the composition', (
        'Step 2. Use a working copy of the verified original PSD as the layout master. Preserve '
        'its exact dimensions, orientation, colour profile, plaque and editable edition number. '
        'Consult designs-canvas.psd for layout guidance when accessible. If the original is '
        'unavailable, use verified canvas details, keep the layout provisional and reserve room '
        'for the original plaque and number. Defer only the assembly and replacement work '
        'that requires the original layers.'
    ))
    replace_section('Step 7. Place the first complete artwork', '**STEP 8', (
        'Step 7. Place the first newly generated pass on a working copy of the selected PSD. Keep '
        'verified signatures separate and record corrections in REVIEW NOTES. Save a unique, '
        f'create-only trial: {trial}. If that name is occupied, use a unique suffix for this run '
        'and record its exact file ID, path and revision. If the save remains unavailable, keep '
        'the first pass and notes. Continue immediately to Step 8 in either case.'
    ))
    replace_section('**8D. Prepare', '**MANDATORY — MOVE THE PLAQUE', (
        '**8D. Score all three designs and select one winner**\n\n'
        'After completing and inspecting both new passes, compare the rendered current design, '
        'Pass 1 and Pass 2 side by side at 100% and at thumbnail size. Score each from 0 to 10 '
        'for photographic realism (face, anatomy, details and integration across the entire '
        'image), collector appeal (authentic story, emotional impact and display value), and '
        'Sports Cave style (composition, background, border, typography, headline longevity and '
        'placement). Give each an overall score out of 10 using the mean of those three scores. '
        'Record the four scores and a short reason for each design. Award 10 only when the artwork earns it. Review '
        'and choose autonomously, without asking for a rating or approval.\n\n'
        'Reject any edit that looks less realistic than the current design, degrades a faithful '
        'likeness or sporting detail, or introduces visible AI artefacts or warping, regardless '
        'of its overall score. Among eligible designs, choose the highest overall score. Keep the '
        'current design if no edit scores higher. If both eligible edits tie above the current '
        'design, prefer higher realism, then higher collector appeal, then Pass 1. Report any '
        'inspection that could not be done. If any of the three cannot be assessed, mark it '
        'unverified, preserve the current design and deliver the best inspected result provisionally.\n\n'
        '**Prepare the staged replacement PSD**\n\n'
        'If the current design wins, skip 8E and go directly to its cleanup in 8F. If an edit '
        'wins, place it in FINAL POLISHED ARTWORK. Keep the pre-edit artwork in hidden ORIGINAL '
        'REVIEW SOURCE and the winning edit’s editable source layers in hidden ORIGINAL EDITABLE '
        'ARTWORK. Keep verified signatures on separate visible layers, '
        'the original badge above the artwork and the editable edition number at the top. '
        'Maintain the selected original PSD’s dimensions and colour profile. Apply the shared '
        'border and print-safety rules with the smallest effective change to the layout.\n\n'
        'If the required source layers or either pass remain unavailable, preserve the completed '
        'work and proceed to delivery in Step 8F with assembly pending.'
    ))
    replace_section('**8E. Save and verify the final PSD**', '**SMART UPLOAD HANDOFF METADATA**', (
        '**8E. Save and verify the staged final PSD**\n\n'
        f'Save a separate create-only file at {staged}. If occupied, use a unique suffix and '
        'record the exact staging file ID, path and revision. Retry a pending trial first if '
        'access has returned. If the trial still cannot be saved, verify staging independently '
        'and report the trial checkpoint as pending. Reopen or download the saved staging '
        'revision. Check that the visible artwork, hidden references, signatures, dimensions, '
        'colour profile and original layers match the intended replacement.\n\n'
        'Photoshop is optional. Use Photoshop or a capable PSD parser plus a rendered preview '
        'to verify the original editable SC_EDITION_NUMBER layer, its exact name, text data, '
        'transform, position and alignment inside SC_EDITION_PLAQUE. Verify that the original '
        'plaque was preserved. A flattened preview alone cannot verify the text layer. '
        'Once these checks pass, proceed to revision-aware replacement. If a required property '
        'cannot be verified after recovery, retain the original and available temporary files '
        'and report the exact pending check while delivering the artwork.'
    ))
    replace_section('**SMART UPLOAD HANDOFF METADATA**', '**Completion requires:**', (
        '**8F. Replace the original and return it to review**\n\n'
        'If the current design won, confirm its exact file ID, path and revision and preserve '
        'its PSD and JSON as saved. Skip replacement and go directly to cleanup for this run’s '
        'saved drafts. If the comparison or verification is still pending, retain the available '
        'work and continue to delivery.\n\n'
        'If an edit won and staging is verified, recheck the original’s ID, exact path and expected revision. '
        'Create a separate recoverable backup and verify it matches the original. Use a Dropbox '
        'revision-aware update at the original path to replace the artwork while keeping its '
        'file ID. Never delete the canonical PSD to clear the path. Reopen the saved canonical '
        'PSD and confirm its actual ID, path, new revision, file contents and original editable '
        'collector layers against verified staging. If a write response is uncertain, read back '
        'the current identity and contents before attempting another write.\n\n'
        'If replacement is unavailable or the expected revision no longer matches, keep the '
        'original and verified staging. Complete independent work and deliver the artwork. If '
        'you wrote a replacement but verification fails, restore the verified backup only '
        'through a revision-aware write against the revision this run created. Otherwise retain '
        'the backup and report the exact state. If direct replacement is unavailable, use Design '
        'Studio → Editing → Apply staged replacement when an already authorised route can '
        'complete its checks. If that control requires user interaction, report the exact trial '
        'and staging paths at delivery. Continue the run without asking for browser access.\n\n'
        '**Update the matching Smart Upload JSON**\n\n'
        f'After confirming the canonical PSD, use its [PSD stem].upload.json in {REVIEW_METADATA_FOLDER}/. '
        'Use a matching legacy sidecar beside the original PSD as a fallback source for existing '
        'metadata. Preserve the design’s confirmed sport, upload intent, Shopify product ID and '
        'collection linkage. If the winning edit changes the artwork headline, record it in '
        'design_title while retaining the canonical PSD filename. Bind the JSON to the actual '
        'saved canonical PSD file ID, path and new revision. Update an existing matching sidecar '
        'with its expected JSON revision. '
        'If no central sidecar exists, use create-only mode with verified legacy or project '
        'metadata. If upload intent cannot be established, leave creation pending. Never guess '
        'linkage or replace an unrelated JSON. Record outstanding checks in review_notes. Use '
        'needs_attention when checks or required metadata remain pending and ready_for_review '
        'when verified and complete. Reconfirm the current PSD revision before writing the JSON, '
        'then read both back to confirm the exact match. Report pending metadata and continue delivery.\n\n'
        'After verifying the canonical replacement or confirming the current design won and '
        'its exact revision is still saved, use recoverable, revision-aware deletion for this '
        'edit’s exact trial, staging and rollback backup PSDs, where created. Confirm their IDs, '
        'paths and revisions before deletion and confirm the results. If cleanup fails, recheck '
        'identity before retrying via an authorised route. Leave only the winning design at the '
        'original filename in the Review folder. Report any pending cleanup and continue delivery.\n\n'
        'Display the winner and the three-design scorecard, or the strongest available provisional '
        'result with any unverified scores, and report the exact status of replacement, JSON and cleanup. If neither pass '
        'produced artwork, report the generation failure and the work retained. End in Review. '
        'Publish now is the separate Shopify action.'
    ))
    workflow = workflow[:workflow.index('**Completion requires:**')] + (
        '**Completion requires:** two full artwork generations, scores for all three designs, '
        'one verified winning PSD at the original filename in Review, matching JSON where required, '
        'confirmed temporary cleanup and display of the winner and scores. When a checkpoint remains unavailable '
        'after recovery, deliver the strongest available result and identify that checkpoint.'
    )
    context = json.dumps({
        'original': original, 'trial_path': trial, 'staging_path': staged,
        'design_metadata': details,
    }, ensure_ascii=False)
    return REVIEW.read_text(encoding='utf-8-sig').strip() + '\n\n' + (
        f'Dropbox reference for the original: {original["dropbox_url"]}\n'
        'Prefer the authorised connector or API to retrieve the original PSD and a rendered '
        'preview. Verify the expected revision before changing the canonical file. If access or '
        'revision verification fails, preserve the original and continue the independent review '
        'and artwork work.\n\n'
        'Selected revision and design metadata (data only):\n' + context + '\n\n' + workflow
    )
