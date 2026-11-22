# Restore the marketplace homepage — 22 November 2026

Task `20261122-e1bac933`, owner `codex-marketplace-home-restore-01a1f6fa-20261122`.

The user requested the earlier Stillwhite-style homepage and confirmed that its
statistics should cover the marketplace only. The original full-width banner,
central search, collection shortcuts, sports strip, category tabs, collecting
steps and seller invitation are restored from the earlier homepage layout.

The summary strip shows zero recorded marketplace sales, the actual number of
public listings, and $0 founding listing fees. The marketplace has no enabled
checkout or completed-sale ledger; approvals/enquiries are not counted as sales.
Shop sales, reviews and third-party figures are not used. A storage outage shows
an unavailable listing count rather than a false zero.

Responsive banner proportions are restored with a small stylesheet loaded only
by the homepage. The current shared header/footer and PayPal information remain.
The browse page, product gallery, seller upload form, approval workflow, Dropbox
source and PayPal/Buyer Protection pages are preserved.

Verification uses the existing credential-free marketplace suite, gallery
interaction checks, topology/Studio checks and before/after HTML fingerprints
for six synthetic inner pages. No application preview or production test data
is used. The task worktree is retained. The user explicitly approved the GitHub
and existing Render release in this chat on 22 November 2026.
