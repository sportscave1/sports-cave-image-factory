# Automatic ad collection (Companion 1.5)

New Ads Add to queue and Design Studio Publish + Ad share the same delivery
worker. Manual Submit is unchanged. Only Meta Instant Experience is supported.

The queued prompt requests `ad_copy.csv`, `collector-hallway.jpg`,
`architectural-wall.jpg` and `man-cave.jpg`, followed by `SC_AD_READY: <job-id>`.
The marker is advisory: actual readiness requires all four files, valid copy,
distinct original JPEG covers, verified catalog membership and valid targeting.
The current CSV format stays unchanged; no Dropbox URLs need to be pasted.

The extension locates attachments only after the exact queued user prompt and
before the next user turn. Each file is pinned to its assistant response ID.
It invokes ChatGPT's native download, waits for the browser's completed-download
signal, reads the authenticated original and transfers it to the paired OS API.
Only ChatGPT/blob and OpenAI artifact hosts are accepted. The download must have
the expected name and a matching ChatGPT referrer; ambiguous downloads wait.
Download journal entries survive an extension worker restart. Expired links are
requested again. Failed transfers remain visible in the queue detail.

The API validates paired-device authentication, requester access, job/chat/response
identity, size, CSV schema and original image dimensions. A shared queue lease
serializes transfer and posting. Files are saved in the existing job-specific
Dropbox destination, with hash, size, ID and revision receipts. An occupied slot
with different contents is preserved and reported. Partial imports remain saved.
Posting checks the recorded file revisions and uses the existing deterministic
submission ID and durable Meta Posting job. Ads remain paused for review.

Automatic targeting reuses the smart relevance ranking and verifies that the
chosen product set actually contains the advertised product. An explicit set
takes priority. Audiences prefer product/team identity matches among relevant
market-compatible candidates; sport/league candidates precede Broad fallback.
Wrong-country saved audiences and lookalikes are excluded. Explicit audience
choices, including Broad, are preserved. Ties are stable by ID; no unverified
performance ranking is inferred. Selections are persisted and revalidated before
submission. Missing membership stops the job while retaining its imported files.

Developer → Companion Queues → Ads provides **Resume import** for a prepared,
unsubmitted job with its original chat. It never generates the prompt again.
**View imported ad draft** displays the saved images/copy and lets an administrator
correct targeting after failure, then resume. Once a Posting ID exists, use its
existing Posting receipt to recover rather than creating another campaign.

## Edge setup and limits

Install/reload the bundled Companion 1.5.0 extension in the paired Edge profile;
accept its downloads/artifact-host permissions. Existing open ChatGPT tabs must
be reloaded once so the new collector content script is present. Keep Edge open,
ChatGPT signed in and the computer awake. Disable the browser's “ask where to
save each file” setting for unattended native downloads. Ad chats open inactive
and are marked non-discardable during collection; no foreground tab is required.
This does not run while Edge is closed, Windows sleeps, or ChatGPT needs sign-in.

ChatGPT DOM and download behavior can change. Offline Edge fixtures cover the
current attachment contract; authenticated production acceptance is still needed
after the server and extension are upgraded. Never test using live ads or customer
data in development previews. No live Meta publication is part of offline tests.
