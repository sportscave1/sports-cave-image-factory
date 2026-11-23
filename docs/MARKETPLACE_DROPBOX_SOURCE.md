# Marketplace source in Dropbox — 22 November 2026

Task `20261122-f7e43342`, owner `codex-marketplace-dropbox-01a1f6fa-20261122`.

The user requested a minimal Marketplace folder in the existing Dropbox account,
website uploads saved there, and all details/media available in the OS approval
queue. The Dropbox connector root and team-folder contents were reviewed. No
Marketplace folder existed. The authorised destination was created and verified:

- `/Sportscave Team Folder/Marketplace`
- Folder ID `id:u1tYiAa2O-AAAAAAAAC4Qg`
- Connector namespace path `ns:14717189651//Marketplace`

No existing folders/files were moved or deleted and no shared links were created.
The new folder inherits the existing team's access. Its creation is reversible
through Dropbox's normal recoverable deletion if the owner later requests it.

## Minimal layout

```
Marketplace/
  broncos-collector-jersey--<listing UUID>/
    photo-1.webp
    photo-2.webp
    video.mp4       # only when supplied
    listing.json
```

Up to four photographs use the same flat folder. There are no per-customer,
date, status, video or photo subfolders. Folder names use the item title and a
server-generated UUID; contact details do not appear in names.

## Source and approval

The existing OS Dropbox OAuth connection is reused, with a bounded token cache
and Team Space namespace. The backend checks access to the exact created folder
ID rather than assuming an unrelated Dropbox account with a similar path.
There are no new credentials, provider permissions or environment variables.

Seller photos/video are validated and optimised in memory/temp storage, then
uploaded directly to Dropbox. The final `listing.json` records every entered
detail, asking price, postage, private contact, consent, media receipts and item
reference. It is written last, after every media upload is acknowledged.

The existing private runtime-state table holds the searchable moderation index
and a snapshot of the submitted facts; new photo/video bytes are not stored in
the database or R2. The approval view verifies the pinned Dropbox listing record
against the index, shows the seller/details/prices and reads previews from
Dropbox. It includes an owner-only source-folder link and a read-only storage
connection check under Website & publish.

Public product pages retain their Sports Cave image/video URLs. Every media
request checks approval, then proxies the exact Dropbox file ID and revision.
IDs, source paths, credentials and Dropbox URLs are absent from public pages and
responses. Videos support bounded streaming and byte ranges. Withdrawal blocks
further public media requests and preserves the owner's source files. Preview
images/video are inline data URLs in the authenticated OS session, avoiding
shared Streamlit media-server URLs for pending submissions.

Editing a Dropbox file does not silently change an approved listing: delivery
and review pin the received revision and verify recorded details/digests.
Updating published content must go through the marketplace review workflow.
Older database photographs and private R2 videos remain readable, preserving
existing listings without an automatic migration or destructive cleanup.

## Failure behaviour

An incomplete Dropbox upload never enters the normal approval queue or returns
success. A database failure after Dropbox receives the complete submission
returns an error and preserves its files/manifest for recovery; it never deletes
received customer files to compensate. No success is claimed for an uncertain
save. Partial private folders may remain after interrupted uploads. No automatic
deletion, retention job or automatic import of arbitrary Dropbox folders is added.

## Verification and release

`python -B scripts/test_marketplace.py` runs with the existing credential-free
environment allowlist. Synthetic Dropbox SDK/HTTP transport exercises folder
creation, complete manifests, failure paths, approval, private previews, pinned
revisions, photo/video delivery and withdrawal. No real customer data or
production upload is used in development tests.

Also run `node tests/marketplace_gallery.cjs`, `git diff --check`,
`python -B scripts/validate_render_topology.py` and Studio Verify. The primary
Render service remains `sports-cave-os` / `srv-d8kl4on7f7vs73dvavv0`; no Blueprint,
infrastructure, schema or unrelated Dropbox settings are changed.

The folder exists in Dropbox. The user explicitly approved the GitHub/Render
release in this chat on 22 November 2026 after reviewing the 71 passing tests.
Folder creation alone does not switch the live website's upload storage.
After release, verify the existing server connection
from OS Marketplace → Website & publish → Submission storage, plus public routes.
