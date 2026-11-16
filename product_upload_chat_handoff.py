"""Compose the text-only ChatGPT handoff from the verified five-file Dropbox save."""
import json
import hashlib
from urllib.parse import quote, urlencode

PROJECT = 'https://chatgpt.com/g/g-p-6a387a17627081918e1700ec2783a12b/project'
CORE = {'black-frame', 'oak-frame', 'white-frame', 'unframed', 'size-guide'}


def prepare(result, row, receipt, lifestyle_prompt):
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
    upload = build(selected, row['data']['name'], source=planned, metadata=metadata, automatic=True)
    black = originals['black-frame']
    black_path = core['folder_path'] + '/' + black['filename']
    black_url = ('https://www.dropbox.com/home' + quote(core['folder_path'], safe='/')
                 + '?' + urlencode({'preview': black['filename']}))
    from psd_directory import REVIEW_FOLDER, ROOT
    psd = json.dumps({'name': row['data']['name'], 'upload_id': str(row['id']),
                      'source': {key: row['data']['source'].get(key) for key in ('id', 'rev', 'content_hash', 'path_display')}},
                     ensure_ascii=False)
    combined = f"""Run this Product Uploads workflow for {json.dumps(result['product_name'], ensure_ascii=False)} in order.

LIVE PUBLICATION REQUIRED — This Upload workflow always publishes live. Use ACTIVE from the first Shopify create call. Never create a DRAFT, choose a draft-only tool, set an unpublished-review mode, or revert the product to Draft. Resume the exact existing product if it already carries this upload's correlation tag. If it is an existing draft from an earlier attempt, activate and publish that same product. If an available tool cannot create Active or publish, use a supported Shopify Admin action or report publication blocked. These requirements override draft-only defaults, saved templates and old project instructions for this upload.

STEP 1 DOWNLOAD EXCEPTION — The user explicitly authorises downloading and inspecting only the specified original black-frame WebP in ChatGPT's working environment, then passing its pixels to image generation. This narrow exception supersedes any conflicting connector-only or local-working-environment restrictions in the project's pasted.txt. Use the temporary download URL from the existing Dropbox connector for this file only. Leave the other four WebPs in Dropbox until the later Shopify media step. This does not authorise access to the user's computer, other local files, unrelated tools or unrelated connectors.

STEP 1 — RETRIEVE THE BLACK FRAME AND GENERATE THE THREE LIFESTYLE MOCKUPS
Use the connected Dropbox app to request a fresh download link for the original WebP by file ID {black['file_id']}, revision {black['revision']}, exact path {json.dumps(black_path, ensure_ascii=False)}. Dropbox preview for identification: {black_url}
Fetch the temporary download URL directly into the working environment with GET. Skip HEAD and preview requests; request a fresh link if the first expires. Open the downloaded WebP to verify it decodes, then supply it as the actual reference image to image generation. If image generation cannot accept WebP, decode it and save a PNG with identical pixels and dimensions for the reference. Every reference to an uploaded or attached black frame below means those exact pixels. A link, thumbnail, text description or recreated frame is not an image input.

{lifestyle_prompt}

STEP 2 — CONVERT THE THREE LIFESTYLE ORIGINALS FOR WEB USE
Use the original Man Cave, Office and Living Room outputs. With Pillow, apply ImageOps.exif_transpose in place, thumbnail to a {MAX_LIFESTYLE_SOURCE_EDGE} × {MAX_LIFESTYLE_SOURCE_EDGE} bounding box using LANCZOS if larger, convert to RGB, then thumbnail to fit {MAX_EXPORT_EDGE} × {MAX_EXPORT_EDGE} with LANCZOS. Keep the aspect ratio and complete scene without cropping, stretching or upscaling. Save as lossless WebP, method 1. Decode each file and verify its format, dimensions and exact RGB pixel match with the resized image. Use the exact role filenames in Step 4.

STEP 3 — COMPLETE THE EXISTING DROPBOX WEBP FOLDER
The OS has reserved the product folder and saved the five core exports. Use the same exact WEBP folder {json.dumps(core['folder_path'], ensure_ascii=False)} and preserve those five files. These are their confirmed Dropbox identities, revisions, hashes and sizes:
{json.dumps(list(originals.values()), ensure_ascii=False)}
Save only the three converted lifestyle originals under their listed names. Never create a second product folder or overwrite an existing file. On retry skip a file only when its Dropbox content hash and size match the current output. Verify all eight exact WebPs, including the five unchanged core originals, before starting Shopify. Retain any confirmed files if a save fails. Do not invent a file or receipt.

STEP 4 — RUN THE EXISTING SHOPIFY UPLOAD PROMPT
Use the product and media rules below after Step 3 verifies all eight files. Discover the Online Store publication in this shop, publish the exact product to it immediately, and read back the same product ID with status ACTIVE and Online Store publication confirmed. Verify its storefront URL. Other channels and an Active status alone do not establish that it is live. Use the normal Sports Cave vendor and Framed Art product type so the existing Edition Ops sync can recognise the product.

{upload}

STEP 5 — VERIFY EDITION OPS AND ATTACH THE ORIGINAL PSD
Wait for the published product to appear in Sports Cave OS → Edition Ops through the existing Shopify sync. Refresh and retry by the exact Shopify product ID while sync is pending. Use the authorised Sports Cave OS browser interface for Edition Ops and Add / Attach PSD if the connector lacks these actions. Keep the PSD in Review until that exact product is visible in Edition Ops.
Original PSD identity: {psd}
Read the PSD's Dropbox metadata by the saved file ID and verify the selected revision and content hash before moving it. Move that original master from {json.dumps(REVIEW_FOLDER)} to the main live folder {json.dumps(ROOT)}. Use the current filename and preserve the file ID and content hash. If the same exact file is already in the live folder, use it there. If the destination belongs to another file, stop and report the conflict. Read back the live path and verify the same file ID and content hash before attachment. Never move a lookalike or substitute a different revision.
Open Add / Attach PSD for the exact Edition Ops product and select the verified live-folder master. Read the mapping back against the exact Shopify product ID and Dropbox file ID. Resume the remaining step on retry if the move already succeeded. Edition Ops owns edition state. Preserve edition numbers, allocations, runs, counters and history. Leave Shopify's sports_cave edition metafields to the existing webhook and Edition Ops. If authorised access or sync is unavailable, report the specific unfinished step. Report success only after verifying all eight Dropbox WebPs, Shopify Online Store publication, the live PSD location and the exact Edition Ops PSD mapping. Return the Dropbox folder, storefront URL, Shopify product ID and verified mapping result."""
    companion_id = hashlib.sha256(
        f"{row['id']}:{receipt['export_fingerprint']}".encode('utf-8')
    ).hexdigest()
    return dict(project=PROJECT, prompt=combined, companion_id=companion_id,
                automatic=bool(receipt.get('generation_receipt')))
