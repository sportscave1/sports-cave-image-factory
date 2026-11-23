# Companion 1.7.41: sleeping-tab recovery

23 November 2026, Australia/Sydney. Follow-up to ac25beb3 / 1.7.40.

## Live findings

The paired desktop reported 1.7.40. Both guarded recoveries requeued the previously verified artworks without uploading again. Allocation 965 (#SC3533 Tiger Woods) passed individual QA and correctly waits for its two sibling PSD repairs. Allocation 968 (#SC3534) passed full QA and submitted; supplier readback reports on hold. Its verified shipping selection is Standard $9.34, tied for cheapest with Budget. Tax checkbox evidence is absent for this Australian order; this run does not establish a US tax-declaration canary. No payment was triggered and countdown preferences were not changed.

Edge's UI explicitly marked both old worker-owned order tabs Sleeping. The native worker's ready-message promise remained pending for minutes, so the attempt count did not enforce a real deadline. Bringing each exact tab forward allowed QA to proceed. These runs therefore validate guarded QA/submission, with manual wake assistance; they do not prove autonomous sleeping-tab recovery.

## Focused correction

Read-only readiness probes now time out after 1.5 seconds and clear their timers. On the first timeout, re-read the owned-tab mapping and current URL; activate only that exact worker-owned order tab and set its autoDiscardable flag false. Do not change global Edge sleep/privacy settings, user-owned tabs, supplier state or countdowns. An immediate missing receiver continues normal bounded loading retries without stealing focus. A navigated/closed tab aborts before wake or reload. Fresh QA still records the previous page instance and requires a new one after reload.

This can briefly select the companion's Prodigi tab when Edge has frozen it. The wake is attempted once per page handoff. Permanently unavailable pages still report a meaningful failure rather than passing blindly.

## Validation and rollout

35 browser regression checks passed, including a never-resolving sleeping probe, exact-tab wake, different-page fencing, protection against user navigation during ordinary and fresh QA, and timer cleanup. The focused combined companion gate passed 63 checks; the offline package check passed. Re-run the full Node set after final edits. Install and verify only changed files; preserve pairing and all permissions. Activation of 1.7.41 and a genuine future sleeping-tab canary remain separate acceptance checks; never Reset an already submitted order to manufacture one.
