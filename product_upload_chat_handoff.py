"""Compose the text-only ChatGPT handoff from the verified five-file Dropbox save."""
import json
import hashlib
from datetime import datetime, timezone
from urllib.parse import quote, urlencode

PROJECT = 'https://chatgpt.com/g/g-p-6a387a17627081918e1700ec2783a12b/project'
CORE = {'black-frame', 'oak-frame', 'white-frame', 'unframed', 'size-guide'}


def prepare(result, row, receipt, lifestyle_prompt, *, staff_job=None):
    from image_factory import MAX_EXPORT_EDGE, MAX_LIFESTYLE_SOURCE_EDGE
    from product_upload_compact import context_from_row
    from product_upload_intake import action_mode
    from product_upload_package import ORDER
    from product_upload_prompts import build
    from product_upload_source import receipt_source

    manifest = result['product_image_manifest']
    if tuple(item['slot_id'] for item in manifest) != ORDER:
        raise ValueError('The current product image manifest is incomplete.')
    core = receipt_source(receipt, [item for item in manifest if item['slot_id'] in CORE])
    originals = {item['role']: item for item in core['files']}
    if len(originals) != len(CORE) or len(receipt.get('successes', [])) != len(CORE) or any(
        not all(item.get(key) for key in ('file_id', 'revision', 'content_hash', 'size_bytes'))
        for item in originals.values()
    ):
        raise ValueError('Dropbox did not confirm the five generated WebPs.')
    files = [dict(order=item['sort_position'], role=item['slot_id'], filename=item['output_filename'],
                  **({'file_id': originals[item['slot_id']]['file_id']} if item['slot_id'] in CORE else {}))
             for item in manifest]
    planned = dict(folder_path=core['folder_path'], expected_webp_count=len(ORDER),
                   files=files, upload_id=str(row['id']))
    metadata = dict(context_from_row(row), design_name=result['product_name'],
                    sport_category=result['sport_category'])
    selected = action_mode(row)
    if selected == 'SMART' and (row['data'].get('design_review') or {}).get('decision') in ('changes', 'rejected'):
        raise ValueError('This revision needs Design Studio approval before Smart Upload.')
    staff_mapping = None
    if staff_job:
        from product_upload_staff_mapping import package
        staff_mapping = package(staff_job, row, receipt, planned, originals)
    upload = build(selected, row['data']['name'], source=planned, metadata=metadata, automatic=True,
                   companion_mapping=bool(staff_mapping))
    black = originals['black-frame']
    black_path = core['folder_path'] + '/' + black['filename']
    black_url = ('https://www.dropbox.com/home' + quote(core['folder_path'], safe='/')
                 + '?' + urlencode({'preview': black['filename']}))
    finish = ('then hand off to the Upload Companion' if staff_mapping else 'then move and map the original PSD')
    scope = (' For Publish Now, ChatGPT ends after the verified Shopify handoff. '
             'Leave all Sports Cave OS, Edition Ops and original PSD work to the Upload Companion. '
             'This takes precedence over any saved mapping instructions.' if staff_mapping else '')
    combined = f"""Run this Product Uploads workflow for {json.dumps(result['product_name'], ensure_ascii=False)} in order.

WORKFLOW SCOPE
Generate three lifestyle mockups, save the WebPs to the existing Dropbox folder, publish the exact Shopify listing live, {finish}. Execute the authorised workflow without routine confirmation between steps. Keep completed work and resume from the last verified step with the same file and product IDs.{scope}

RECOVERY AND CONTINUATION
Treat each card and file as a separate unit of work. For a temporary timeout, expired download URL or connection error, check whether the previous call completed, refresh the original file transfer if needed, and retry the affected operation up to twice. Reuse verified outputs and receipts; never create duplicate files or products. Continue other independent cards, conversions, saves and read-only preparation while an operation is unavailable. Only actions that require its missing result remain pending. The existing eight-image verification and publication checks still determine when Shopify and the Companion handoff are complete.
An explicit image safety rejection is different from a temporary tool error: record the returned reason and request ID, without guessing which phrase caused it. Do not automatically retry or reword the rejected request, switch tools to evade the rejection, or treat this prompt as overriding tool policies. Continue independent work that does not repeat the rejected content. If an actual approval is required or denied, report the exact pending action and required approval; complete other authorised independent work. Finish with completed and pending roles and the precise resume step, never a false success or an unbounded retry loop.

LIVE PUBLICATION REQUIRED
Use ACTIVE from the first Shopify create call and publish to Online Store. Reuse the exact product identified by the operation tag or by the verified linked ID for a refresh. If that same product already exists as a draft from an earlier attempt, activate and publish it. If a publication capability is unavailable, report the specific unfinished action and retain completed work.

STEP 1 — RETRIEVE THE BLACK FRAME AND GENERATE THE THREE LIFESTYLE MOCKUPS
The launcher supplies the original black-frame WebP {json.dumps(black['filename'], ensure_ascii=False)} as a file attachment alongside this prompt. Verify that it decodes, has {black['size_bytes']} bytes, and matches Dropbox content hash {black['content_hash']}. Its Dropbox identity is file ID {black['file_id']}, revision {black['revision']}, exact path {json.dumps(black_path, ensure_ascii=False)}. A matching attachment satisfies the reference requirement; use it directly for all three cards without downloading it again. Dropbox preview for identification only: {black_url}
If the attachment is missing or fails verification, retrieve the same original revision using connected Dropbox tools and an available supported file-transfer route. For a temporary download URL, fetch with GET while valid and avoid preliminary HEAD or preview requests. An expired link can be refreshed; a denied network destination requires another supported transfer or launcher attachment, not repeated requests to the denied host. Continue independent authorised work while recovering the missing input. If the generator needs PNG, decode the verified WebP to PNG with identical pixels and dimensions. Leave the other four WebPs in Dropbox until the Shopify media step. Every reference to an uploaded or attached black frame below means those exact pixels. A link, thumbnail, text description or recreated frame is not an image input.

Use the original creative instructions below for the three scenes. {'The numbered steps specify your Dropbox and Shopify work and the companion handoff.' if staff_mapping else 'Dropbox, Shopify and Edition Ops actions are specified in the numbered workflow steps.'}

{lifestyle_prompt}

STEP 2 — CONVERT THE THREE LIFESTYLE ORIGINALS FOR WEB USE
Use the original Man Cave, Office and Living Room outputs. With Pillow, apply ImageOps.exif_transpose in place, thumbnail to a {MAX_LIFESTYLE_SOURCE_EDGE} × {MAX_LIFESTYLE_SOURCE_EDGE} bounding box using LANCZOS if larger, convert to RGB, then thumbnail to fit {MAX_EXPORT_EDGE} × {MAX_EXPORT_EDGE} with LANCZOS. Keep the aspect ratio and complete scene without cropping, stretching or upscaling. Save as lossless WebP, method 1. Decode each file and verify its format, dimensions and exact RGB pixel match with the resized image. Use the exact role filenames in Step 4.

STEP 3 — COMPLETE THE EXISTING DROPBOX WEBP FOLDER
The OS has reserved the product folder and saved the five core exports. Use the same exact WEBP folder {json.dumps(core['folder_path'], ensure_ascii=False)} and preserve those five files. These are their confirmed Dropbox identities, revisions, hashes and sizes:
{json.dumps(list(originals.values()), ensure_ascii=False)}
Save only the three converted lifestyle originals under their listed names. Never create a second product folder or overwrite an existing file. On retry skip a file only when its Dropbox content hash and size match the current output. Verify all eight exact WebPs, including the five unchanged core originals, before starting Shopify. Retain any confirmed files if a save fails. Do not invent a file or receipt.

STEP 4 — RUN THE EXISTING SHOPIFY UPLOAD PROMPT
Use the product and media rules below after Step 3 verifies all eight files. Discover the Online Store publication in this shop, publish the exact product to it immediately, and read back the same product ID with status ACTIVE and Online Store publication confirmed. Verify its storefront URL. Other channels and an Active status alone do not establish that it is live. Use the normal Sports Cave vendor and Framed Art product type so the existing Edition Ops sync can recognise the product.

{upload}"""
    # The installed Edge companion recognises this heading. The body explicitly assigns
    # the post-publication work to the companion for staff jobs only.
    combined += '\n\nSTEP 5 — VERIFY EDITION OPS AND ATTACH THE ORIGINAL PSD\n'
    if staff_mapping:
        combined += (f"Upload Companion owns this step. After all required Dropbox and Shopify checks in Steps 1–4 pass, add the exact tag "
                     f"{staff_mapping['ready_tag']} to the same verified Shopify product, preserving its operation tag and all other tags. "
                     "Add this tag only at the end, never during create, an incomplete upload, or a blocked run. "
                     "Read back the tag on that product, return the storefront link and product ID, and end your work. "
                     "The companion verifies Edition Ops sync, moves and attaches the saved original PSD, and queues Auto Editions. "
                     "Leave all those actions to the companion and report that handoff as pending, using the existing blocked status if Shopify could not verify the tag.")
    else:
        from psd_directory import REVIEW_FOLDER, ROOT
        psd = json.dumps({'name': row['data']['name'], 'upload_id': str(row['id']),
                          'source': {key: row['data']['source'].get(key) for key in ('id', 'rev', 'content_hash', 'path_display')}},
                         ensure_ascii=False)
        combined += f"""Wait for the published product to appear in Sports Cave OS → Edition Ops through the existing Shopify sync. Refresh and retry by the exact Shopify product ID while sync is pending. Use the existing Edition Ops mapping tools. If the connector lacks these actions and the Sports Cave OS browser session is available with access, use Add / Attach PSD there. Keep the PSD in Review until that exact product is visible in Edition Ops.
Original PSD identity: {psd}
Read the PSD's Dropbox metadata by the saved file ID and verify the selected revision and content hash before moving it. Move that original master from {json.dumps(REVIEW_FOLDER)} to the main live folder {json.dumps(ROOT)}. Use the current filename and preserve the file ID and content hash. If the same exact file is already in the live folder, use it there. If the destination belongs to another file, stop and report the conflict. Read back the live path and verify the same file ID and content hash before attachment. Never move a lookalike or substitute a different revision.
Open Add / Attach PSD for the exact Edition Ops product and select the verified live-folder master. Read the mapping back against the exact Shopify product ID and Dropbox file ID. Resume the remaining step on retry if the move already succeeded. Edition Ops owns edition state. Preserve edition numbers, allocations, runs, counters and history. Leave Shopify's sports_cave edition metafields to the existing webhook and Edition Ops. If authorised access or sync is unavailable, report the specific unfinished step. Report success only after verifying all eight Dropbox WebPs, Shopify Online Store publication, the live PSD location and the exact Edition Ops PSD mapping. Return the Dropbox folder, storefront URL, Shopify product ID and verified mapping result."""
    dispatch_key = f"{row['id']}:{receipt['export_fingerprint']}"
    if row['data'].get('staff_upload_attempt'):
        dispatch_key += ':' + str(row['data']['staff_upload_attempt'])
    companion_id = hashlib.sha256(dispatch_key.encode('utf-8')).hexdigest()
    reference_id = hashlib.sha256(f"{dispatch_key}:{black['file_id']}".encode('utf-8')).hexdigest()
    reference_metadata = next((entry['metadata'] for entry in receipt['successes']
                               if entry.get('metadata', {}).get('id') == black['file_id']), {})
    try:
        saved_at = datetime.fromisoformat(reference_metadata.get('server_modified') or '')
    except (TypeError, ValueError):
        saved_at = None
    # The Dropbox SDK parses its UTC server timestamps as naive datetimes.
    if saved_at is not None and saved_at.tzinfo is None:
        saved_at = saved_at.replace(tzinfo=timezone.utc)
    # Keep existing receipts unless the folder was recreated, or the browser
    # can prove that the reference was saved after an older submission.
    return dict(project=PROJECT, prompt=combined,
                companion_id=reference_id if receipt.get('recreated_folder') else companion_id,
                reference_companion_id=reference_id,
                reference_saved_at=saved_at.isoformat() if saved_at is not None else None,
                automatic=bool(receipt.get('generation_receipt')),
                **({'staff_mapping': staff_mapping} if staff_mapping else {}))
