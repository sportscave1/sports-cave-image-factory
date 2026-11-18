# Ads queue controls and quick add

Companion 1.5.1 extends the existing automatic Instant Experience flow.

- The header Ads popup has compact, isolated text styles and per-job Play,
  Cancel and Delete buttons. The Developer Companion Ads tab has the same actions
  for waiting, running and stopped jobs.
- Cancel records an independent stop instruction, so a late worker checkpoint
  cannot undo it. The worker stops its pending prompt operation and asks the saved
  chat to stop generating. File transfer and posting check the stop instruction.
  An already-accepted Meta operation cannot be undone; its Posting receipt remains
  available. Delete also stops future work and hides the job; it preserves saved
  files and posting receipts rather than deleting external resources.
- Play enables the queue and resumes the saved chat, original file receipts and
  response IDs. It reloads that background tab once for the new resume token.
  If posting was already submitted, only the existing Posting job is monitored.
  A prepared job without a confirmed chat does not send another prompt blindly.
- Explicit saved-chat recovery can collect uniquely named originals even when
  ChatGPT has virtualized the original prompt out of the rendered history. It
  rejects a different visible queued-job marker and ambiguous duplicate files.
  Pinned per-file response IDs remain mandatory once recorded. Missing attachments
  cause further waiting/history loading, never fresh creative generation.
- Both queue surfaces have Add to queue with product, sport, country and type.
  They share the New Ads catalog, category detection, metadata, validation,
  prompt builder and enqueue function. Country is editable; a stored primary
  market or league-based suggestion is used where available, otherwise Australia.
  Instant Experience is the supported automatic type. The server re-resolves
  product identity and URL rather than trusting client-supplied catalog details.
- Quick-add request UUIDs are scoped to the account and deduplicate HTTP retries.
  Editing selections creates a new request; reusing a request for different
  product/market/sport is rejected. Admin and same-origin checks protect mutations.

No migration or infrastructure change is required. Upgrade the existing Edge
extension files to 1.5.1 and reload the extension and ChatGPT tabs. Keep Edge open,
signed in and the computer awake. Tests use synthetic databases, mocked provider
HTTP and offline Edge fixtures; no live ads are published during testing.
