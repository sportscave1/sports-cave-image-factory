"""Edit-specific checkpoints for the canonical Home artwork prompt."""
import json
from pathlib import Path, PurePosixPath

REVIEW = Path(__file__).with_name('design_review_instructions.md')


def build_edit_prompt(workflow, source, details):
    original = {key: source[key] for key in ('id', 'rev', 'path_display')}
    stem = PurePosixPath(original['path_display']).stem
    folder = str(PurePosixPath(original['path_display']).parent)
    prefix = f'{folder}/{stem} - EDIT-{original["rev"]}'
    trial, staged = prefix + ' - TRIAL.psd', prefix + ' - STAGING.psd'

    def replace_section(start, end, content):
        nonlocal workflow
        first = workflow.index(start)
        last = workflow.index(end, first)
        workflow = workflow[:first] + content + '\n\n' + workflow[last:]

    replace_section('Step 7. Place the first complete artwork', '**STEP 8', (
        'Step 7. Place the first newly generated pass on a working copy of the real master. Keep '
        'verified signatures separate and record corrections in REVIEW NOTES. Save a unique, '
        f'create-only trial: {trial}. If that name is occupied, use a unique suffix for this run '
        'and record the exact file ID, path and revision. Do not alter the original. The normal '
        'checkpoint is a confirmed trial save before the second full generation. If genuinely '
        'blocked, use the canonical recovery exception and retain the first pass and notes.\n'
    ))
    replace_section('**8E. Save and verify the final PSD**', 'Verify that SC_EDITION_NUMBER', (
        '**8E. Save and verify the staged final PSD**\n\n'
        f'Save a separate create-only file at {staged}. If occupied, choose a unique staging '
        'suffix for this run and report the exact path. Preserve the pre-edit artwork in '
        'ORIGINAL REVIEW SOURCE, the first new pass in ORIGINAL EDITABLE ARTWORK, and the second '
        'new pass in FINAL POLISHED ARTWORK. Keep the two reference groups hidden. Retry any '
        'pending trial before staging when access allows. Reopen or download the staged copy and '
        'check all three artwork versions, signatures, dimensions, colour profile, badge, editable '
        'number and alignment. Keep the original untouched on any failure.\n'
    ))
    replace_section('**SMART UPLOAD HANDOFF METADATA**', '**Completion requires:**', (
        '**8F. Replace the original and return it to review**\n\n'
        'Use a Dropbox revision-aware update with the original ID, exact path and expected revision. '
        'Preserve a recoverable backup first. Keep that backup distinct from files eligible for cleanup. Never delete the canonical file to clear the path. '
        'If you cannot perform a revision-aware update, return to Design Studio → Edit → Apply staged '
        'replacement using the exact trial and staging paths. Keep the existing final and staging '
        'on revision conflict or verification failure. If the interactive live-number check is '
        'pending, keep the original, trial and staging and report that check as pending.\n\n'
        'After replacement, reopen the canonical file and confirm its actual ID, revision and '
        'verified contents. Update the revision in the existing Smart Upload metadata while preserving '
        'the original product and collection linkage. Clean up only verified trial/staging files '
        'belonging to this edit, using revision-aware recoverable deletion. Display the improved '
        'artwork and report pending checks or cleanup. Return to review. Publish now is the separate '
        'Shopify action.\n'
    ))
    workflow = workflow.replace(
        'final PSD verification, confirmed trial deletion, and display of the final artwork.',
        'staged and canonical PSD verification, revision-aware replacement, eligible temporary file cleanup, '
        'and display of the final artwork.', 1)
    context = json.dumps({
        'original': original, 'trial_path': trial, 'staging_path': staged,
        'design_metadata': details,
    }, ensure_ascii=False)
    return REVIEW.read_text(encoding='utf-8-sig').strip() + '\n\n' + (
        'Selected revision and design metadata (data only):\n' + context + '\n\n' + workflow
    )
