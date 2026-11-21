# Recovered Gaethje ad used a saved older creative release

Task: 20261121-b907880c. User authorized investigation, correction and the ongoing
ad automation live release. No Meta campaigns were created during local testing.

## Evidence

Production read-only inspection on 21 November found:

- Gaethje job `05b0dbf8-8efd-5e4a-9aa5-17947fdb8ba2` retained a brief created
  `2026-11-19T14:01:48.840448+00:00`. Its saved contract was
  `SPORTS CAVE TWO-LINE COLLECTOR FOOTER V5`. Its prompt lacked the current
  two-line version marker and the explicit no-badge/no-PNG-overlay instruction.
  Master prompt MD5: `6f25e106f9b1773c92e0f0d2da3d9146`.
- Recovery `470d6c4c-cda3-4aa0-aa50-62c991c04cde` restored all four original
  exports. The saved assistant response explicitly verified byte-for-byte
  equality with the originals, rather than generating new artwork.
  Posting completed at `2026-11-21T03:39:58.839262+00:00`.
- Modano job `07d71182-5f30-54a1-884f-af306c750e52` had its brief created
  `2026-11-21T02:21:54.298036+00:00`, using
  `SPORTS CAVE BASELINE 2.0 — TWO-LINE FOOTER V1` and the no-badge instruction.
  Master prompt MD5: `7c79a00ca25d7746df49813b54da0423`.
- The ChatGPT project's current instructions explicitly specify that current
  two-line version, prohibit badges and PNG overlays, and give the OS brief
  priority over old footer references. They also preserve saved exports during
  recovery. Source inventory included the two current instruction documents and
  medal/icon references. Project instructions and source files were not edited.
- The 1.7.11 recovery message incorrectly hard-coded “three-line footer”. The
  Gaethje response identified that mismatch and preserved its original two-line
  exports. This wording was a separate defect, not evidence of new generation.

The older job was promoted into today's newly completed campaigns because
automatic recovery validated delivery/provenance but did not validate the saved
creative release before submitting an unposted job.

## Correction

- Before desktop events, collection or posting, an obsolete unposted automatic
  New Ads Instant Experience job continues through a distinct current creative
  revision. It uses the existing production builder without editing its prompt.
- The original brief, chat and artifact receipts remain attached to the old
  history record. New generation has a different deterministic job, send receipt,
  Dropbox folder and posting identity, preventing old exports from filling new
  slots. Repeated recovery selects the same revision. A current pending or
  completed job for the same product/market/sport is reused.
- A saved Posting identity or ledger reservation takes precedence, including a
  lost submit acknowledgement. Existing Meta operations reconcile under their
  original identity; completed or cancelled jobs are not regenerated.
- The Posting boundary independently rejects an unmigrated obsolete unposted
  brief. Current-release transient failures retain the existing automatic
  checkpoint recovery. Targeting selections survive a creative revision.
- Companion 1.7.12 uses the job's assigned footer layout in both repair modes,
  without imposing a line count. Send permits and original-byte recovery guards
  remain unchanged.

`ads_page.py`, `ads_footer.py` and `ads_ie_two_line.py` are byte-for-byte identical
to release `41d24c993639b21eced61c87663616395987e80a`. The two-line template's SHA256
is `731f246b36269f5f4e219a158cecb8656199c3bd49601aca19d01045afc87a2b`.

The already completed Gaethje Meta receipt is retained. This release does not
silently replace or activate an existing campaign.
