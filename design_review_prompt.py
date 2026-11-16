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
        'revision → select the strongest faithful improvement → save and verify the staged PSD → '
        'back up and replace the exact original revision → verify the saved replacement → update '
        'its matching JSON as needed → clean up this edit’s temporary files → display the outcome.\n\n'
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
        '**8D. Prepare the staged replacement PSD**\n\n'
        'Place the strongest inspected improvement in FINAL POLISHED ARTWORK. Keep the pre-edit '
        'artwork in hidden ORIGINAL REVIEW SOURCE and the first new pass in hidden ORIGINAL EDITABLE '
        'ARTWORK, even if either reference informs the visible version. Preserve other useful '
        'versions in separate hidden groups. Keep verified signatures on separate visible layers, '
        'the original badge above the artwork and the editable edition number at the top. '
        'Maintain the selected original PSD’s dimensions and colour profile. Apply the shared '
        'border and print-safety rules with the smallest effective change to the layout.\n\n'
        'If the required source layers or either pass remain unavailable, preserve the completed '
        'work and proceed to delivery in Step 8F with assembly pending. If the review finds that '
        'neither pass improves the original, preserve the original in Review and display the '
        'strongest candidate with the reason it was not applied.'
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
        'With staging verified, recheck the original’s ID, exact path and expected revision. '
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
        'collection linkage. Bind the JSON to the actual saved canonical PSD file ID, path and '
        'new revision. Update an existing matching sidecar with its expected JSON revision. '
        'If no central sidecar exists, use create-only mode with verified legacy or project '
        'metadata. If upload intent cannot be established, leave creation pending. Never guess '
        'linkage or replace an unrelated JSON. Record outstanding checks in review_notes. Use '
        'needs_attention when checks or required metadata remain pending and ready_for_review '
        'when verified and complete. Reconfirm the current PSD revision before writing the JSON, '
        'then read both back to confirm the exact match. Report pending metadata and continue delivery.\n\n'
        'After the canonical replacement is verified, use recoverable, revision-aware deletion '
        'for this edit’s exact trial and staging files only. Confirm their IDs, paths and '
        'revisions before deletion and confirm the results. Keep the backup. If cleanup is '
        'pending, report it without delaying delivery.\n\n'
        'Always display the strongest inspected artwork, or the strongest available provisional '
        'result, and report the exact status of replacement, JSON and cleanup. If neither pass '
        'produced artwork, report the generation failure and the work retained. End in Review. '
        'Publish now is the separate Shopify action.'
    ))
    workflow = workflow[:workflow.index('**Completion requires:**')] + (
        '**Completion requires:** two full artwork generations, a confirmed trial and staging save, '
        'verified revision-aware replacement in Review, matching JSON where required, confirmed '
        'temporary cleanup and display of the final artwork. When a checkpoint remains unavailable '
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
