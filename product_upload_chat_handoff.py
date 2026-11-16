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
    upload = build(selected, row['data']['name'], source=planned, metadata=metadata)
    black = originals['black-frame']
    black_path = core['folder_path'] + '/' + black['filename']
    black_url = ('https://www.dropbox.com/home' + quote(core['folder_path'], safe='/')
                 + '?' + urlencode({'preview': black['filename']}))
    psd = json.dumps({'name': row['data']['name'], 'upload_id': str(row['id']),
                      'source': {key: row['data']['source'][key] for key in ('id', 'rev', 'content_hash')}},
                     ensure_ascii=False)
    combined = f"""Run this Product Uploads workflow for {json.dumps(result['product_name'], ensure_ascii=False)} in order.

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
Use the selected mode and rules below. The eight-file manifest is ready only after Step 3 verifies it. Use Step 5 in place of the manual attach instruction at the end of the existing prompt.

{upload}

STEP 5 — VERIFY EDITION OPS AND ATTACH THE ORIGINAL PSD
Use the resulting Shopify product ID to verify the product has arrived through the existing Edition Ops sync. Attach the exact original PSD to that product using the Sports Cave OS connector's Add / Attach PSD workflow when supported. PSD identity: {psd}
Read the mapping back against the exact Shopify product ID and the PSD identity. Edition Ops owns edition state. Preserve edition numbers, allocations, runs, counters and history and leave Shopify's sports_cave edition metafields to the existing webhook and Edition Ops. If sync is pending, retry verification and report pending if still absent. Report each unfinished step if a required tool or platform permission is unavailable. Report success only after verifying the eight Dropbox WebPs, the Shopify upload and the exact Edition Ops PSD mapping. Return the Dropbox folder, Shopify admin link and stable product ID, and mapping result."""
    companion_id = hashlib.sha256(
        f"{row['id']}:{receipt['export_fingerprint']}".encode('utf-8')
    ).hexdigest()
    return dict(project=PROJECT, prompt=combined, companion_id=companion_id,
                automatic=bool(receipt.get('generation_receipt')))
