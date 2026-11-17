# Morning designs through the existing Edge companion

Task: `20261117-9886a84e`; owner: `codex-design-morning-20261117-01a1e7c5`.
User authorised advancing this isolated task to released revision `a7f3e8a2`.
User subsequently authorised committing, pushing and deploying this task, updating
the existing Edge companion, enabling the queue and live end-to-end verification.

## Behaviour

- The existing paired Upload Companion gains a separate morning design queue.
  Its original product workflow and credential are reused. No second extension,
  desktop process, ChatGPT schedule or Render service is needed.
- Every 30 seconds it discovers Sports Updates and Legends suggestions in the
  durable morning archive. Only editions published after first activation are
  eligible. Existing suggestions from before activation are not backfilled.
  Suggestions published while Edge is offline remain discoverable on return.
- Each date/section/normalised-title identity is inserted once. Reordering,
  repeated publishing and changes to recommendation text cannot resend that job.
  A title change is a new suggestion identity. The next date has new identities.
- The exact Home `_prompt` builder and Designs project URL are used. A receipt
  field is appended for the existing final `.upload.json`; the artwork workflow
  and Review destination remain the same.
- One design slot and one product upload slot can be occupied. Paste and Submit share the existing
  product companion's serial submission queue; one design can generate concurrently with one product upload. Product Uploads retains its own existing job limit.
- Home shows a status below each suggestion. Developer → Companion Queues shows
  design history, conversation links, final PSD paths and a pause/enable toggle.
- The server verifies the job ID in an actual Dropbox sidecar, matching final
  PSD ID, revision and path, plus the existing metadata review requirements.
  Submission alone is never completion. File verification checks the metadata
  contract; it does not independently judge the artwork's visual quality.
- States: Pending, Opening ChatGPT, Generating, Uploaded (metadata still pending),
  Ready for review and Needs attention. Unconfirmed sends, interrupted openings
  and three-hour timeouts are not automatically resubmitted. They release their slot
  automatically so the next queued job can proceed. Failed jobs are never replayed
  automatically; late verified uploads can still update their status.
- Pause prevents new claims and discovery; already claimed work is still checked.
  Resume discovers suggestions published during the pause.

## Local verification

Synthetic PGlite exercises discovery, activation boundaries, repeat publication,
single-slot limits, authentication, pause, uncertainty, automatic failure advance,
timeouts, late completion, exact output correlation and revision mismatch.
Existing Home and Product Uploads tests run alongside these tests.
Node fixtures exercise the actual extension scripts, sequential submissions,
restart journals, wrong project rejection, attached/inline design prompts and
the existing product flow. There is no live ChatGPT or production preview test.

Commands (use the existing Python environment with pytest and the synthetic
`AUTO_EDITIONS_TEST_PGLITE` module configured):

```text
python -m pytest tests/test_morning_design_queue.py tests/test_home_sports_morning_brief.py tests/test_product_upload_staff_queue.py -q
node --test tests/test_morning_design_companion.cjs tests/test_upload_companion_composer.cjs tests/test_upload_companion_origin.cjs
python scripts/validate_render_topology.py
```

Focused test results and live release evidence are recorded in the Studio task. The extension ZIP was built and
its contents and manifest checked. Python syntax and Git whitespace checks passed.
Evidence and extension ZIP: `output/morning-design-queue/` (local, ignored).

## Activation after explicit release approval

1. Review/commit this scoped task, reconcile against the latest released code,
   rerun the focused checks, and deploy through the existing canonical service.
2. Apply the registered `20261117150000_morning_design_queue.sql` migration. It
   creates private, RLS-enabled tables and starts disabled. No Blueprint changes.
3. Update the existing paired Edge extension from the packaged 1.2.0 files in
   its established directory, retaining its extension ID and local storage.
   Reload it only after checking product handoffs are idle; do not install a
   second copy or clear its pairing/submission journal.
4. Enable **Automatically create morning designs** in Companion Queues before
   the next brief. Keep Edge awake and signed in to the Designs project.
5. Use **Queue a current suggestion now** to select one existing suggestion for
   an immediate run without backfilling the whole edition. Observe it end to end: correct prompt and project,
   one confirmed submission, matching final PSD/JSON in Review, and Ready for
   review on Home. Live browser compatibility remains unverified until this step.

To pause new designs, turn the toggle off. Existing product jobs are independent.
Do not clear journals or reset jobs as a recovery technique; inspect uncertain
chats and the Review folder first.
