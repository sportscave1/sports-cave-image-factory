# Upload edition flag prevention — 4 November 2026

Task `20261104-36ee35ef`, owner `codex-edition-flag-20261104-02`.
Baseline: deployed `7a2ffebbf860b33ba4113a22345248bc36bc34f4`.

## Attribution and evidence

The strongest supported explanation is that the external upload assistant used
`sports_cave.edition_enabled=false` to keep purchasing disabled while awaiting
edition/PSD setup. The exposed Shopify event history does not identify the exact
metafield writer; attribution to a particular API call is not proven.

- Product `15466713841971` was created at 02:46:39 UTC, 13:46:39 Sydney.
- Worker logs show DRAFT classification, without registration, through 02:51:35.
- The lone edition metafield was `edition_enabled=false`, last changed at
  02:51:39 UTC, 13:51:39 Sydney (recorded in the preceding incident).
- By 02:52:28 the worker saw ACTIVE and eligible, then failed with
  `PendingRegistration`; database receipts explain this as
  `explicitly_disabled_mirror_requires_review`.
- Chat `Shopify draft publish തീരുമാനം` (`6aea9b95-bea4-83ec-a9d6-bc0ac412ffe8`)
  contains a publish-live turn spanning this interval. Its response reports
  purchasing disabled while setup is pending and directs the user to attach a PSD.
- Chat `Verify product upload` (`6aeaa1aa-1b60-83ec-bfac-99fb40ba84c4`) later repeats
  that purchasing remains disabled pending setup. Its attached generated brief
  says to preserve the archived/unavailable message and disabled purchasing until
  normal setup completes. It also correctly says that a PSD is not required for
  automatic sync, illustrating the conflicting workflow guidance.
- This ambiguous clause is generated in `product_upload_compact.py`; git history
  associates it with `d6a3e1bd8489bfb50819a50c4d61659643daa9f3` (21 October).
- Saved new/existing upload templates contain no literal `edition_enabled`
  instruction. The ambiguous clause is supplied by the generated completion text.
- The product event query for 02:45–03:00 UTC returned no events. The chat reader
  exposes message summaries, not the underlying Shopify mutation call.

There is no evidence that theme code wrote this metafield. The OS deliberately
refuses to overwrite explicit disable/archival signals; that protection stays.

## Prevention

- Put edition ownership rules before media transfer and product writes for all
  three upload modes. Upload agents must not initialize, disable, re-enable or
  delete edition-control metafields, including inside product create/update input.
- Explain that pending UI state is an observation, not a request to manufacture a
  purchase block. Missing PSDs and pending setup must not cause flag writes.
- Omit OS-owned edition metafields from saved metadata exported as upload inputs;
  retain unrelated custom/category fields, even in the same namespace.
- Remove known conflicting saved-template purchase-block/flag instructions while
  retaining unrelated custom clauses. The explicit ownership rule takes precedence.
- Bump the prompt revision used in clipboard cache identity. Prompts already
  copied into external chats cannot be revoked; copy a fresh prompt after rollout.
- Do not change actual edition counters, archived products, theme code, inventory
  policy, Shopify subscriptions or the already-repaired Max product.

## Validation

72 passed and 14 subtests passed across live-edition prompt, compact prompt,
deferred handoff, naming convention, activation and webhook restoration suites.
New contracts cover DRAFT/LIVE/UPDATE, old saved instructions, conflicting saved
edition values, unrelated field preservation and deliberate-disable protection.

The broader `test_product_upload_prompts.py` suite has four pre-existing failures
(two legacy UI contracts and two LIVE pricing-appendix subtests). All four were
reproduced with the unchanged baseline compact module, using `git show HEAD:...`
in an isolated Python process; they are not introduced by this fix. Its other
31 tests and 30 subtests pass. No live store was used for tests.
