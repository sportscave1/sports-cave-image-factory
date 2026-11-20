# No Fear USA Instant Experience — observed live run

Studio task 20261120-0462bb78, owner codex-no-fear-usa-20261120-06.
User authorized this live ad workflow, observation, error diagnosis and release.
Observed 20 November 2026, approximately 00:32–00:40 UTC (11:32–11:40 Sydney).

## Outcome

Queued exactly one new No Fear — Kobe Bryant vs Allen Iverson Wall Art package through New Ads with NBA, USA and Instant Experience selected. Job: `dddf3ca0-bf8a-5af1-87a4-5cdc4300595c`.
The original black-frame Shopify reference was visibly checked before submission.
The Companion submitted the prompt once, opened the saved conversation, tracked generation and reached a terminal Needs attention state. No Meta posting receipt was created for this incomplete package. Queue remained playing with no running or waiting ads afterward.

Saved conversation: https://chatgpt.com/g/g-p-6a6bd98cd6f081918788b544dcdecfc2-sports-cave-meta-ads/c/6aff956a-1250-83ec-a57e-2e250903b595

| Route | Result | Assigned footer headline | Assigned supporting sentence |
|---|---|---|---|
| Collector Hallway | JPEG exported and downloaded | 100 Edition Collector Run | Once this edition sells out, there is no second run. |
| Architectural Wall | Provider rejected; no image file | Limited to 100 Editions | Once they’re claimed, this edition retires forever. |
| Man Cave | JPEG exported and downloaded | Only 100 Editions Available | Once it sells out, it’s done. |

## Recorded error

Architectural Wall (`premium_scarcity_front`, `architectural-wall.jpg`) returned **moderation_blocked** during provider output review. Provider request ID: `e331e00d-4ea0-41c4-8f58-7fafdd48cc71`. No specific triggering content or phrase was supplied. The same reason and request ID appeared in the chat's SC_AD_BLOCKED marker and the Companion queue history. The checkpoint was 00:39:02.898962 UTC.

This is a provider rejection, not an observed upload, prompt-submission, CSV or Companion crash. The run continued its independent Man Cave slot and all three copy rows, preserving successful files. It did not substitute a reserve room or reword and retry the rejected slot. No claim can be made that a particular prompt phrase caused the rejection.

## Actual output review

Read the exact submitted 86,467-character attachment in the browser. It contains the shared 160 px footer profile and the three assignments above, with no old 18–20% footer range.

Downloaded final Library originals through their native Download controls, rather than judging only initial generated-image previews. Both are valid 1024 × 1024 JPEGs. Visual and pixel-row inspection locate their gold seam at y=864, consistent with a 160 px footer. The initial generated previews used taller panels; the final exports conform to the requested geometry. This demonstrates why the existing final-export review matters.

Both final footers contain exactly the assigned headline, supporting sentence and CLAIM YOUR EDITION, with no fourth text baseline. The gold number stays inline, with its underline below it. Titles are visually dominant, editorial serif, openly spaced and ivory; supporting text is subordinate; CTA is tracked gold. The separator shows a localized bright metallic sheen. All three lines remain readable at preview size, without a large unused black tail. Pixel inspection cannot certify the exact named font or font-size metadata in a raster image.

The two rooms differ visibly: a light classical hallway seen from the right and a darker courtyard-facing collector room seen from the left. Each retains the complete black frame, No Fear title, Iverson in black facing Bryant in gold, edition seal, believable wall mounting, visible glass reflections and a dominant artwork. No obvious missing artwork element or footer text defect was found in the completed exports. The blocked route has no image to review.

| Downloaded original | Bytes | SHA256 |
|---|---:|---|
| collector-hallway(20261120-003825).jpg | 443093 | 98a944a79ec8097476816235863482d6f1a5685a1397d6d6efe2b29774457650 |
| man-cave(20261120-003826).jpg | 481347 | 86c9bc82fb66d81827c6707e9d4167e0888059d8c4a4b4fc187911568483c6c3 |

The downloaded ad_copy(20261120-003825).csv contains exactly three route rows with the existing 11-column schema. It passed the existing offline Instant Experience CSV parser. Its headlines are “Iverson Sizes Up Kobe”, “Kobe Holds His Ground” and “Philly Black, Lakers Gold”; all CTAs are Claim Your Edition. These are ad-copy headlines, separate from image-footer headlines. Offline parsing used a synthetic result record; it does not establish a live Meta import receipt.

## Recommendations for recurrence

1. For moderation_blocked or an unexplained rejection, preserve the successful files and original chat, record the rejected route and provider request ID, and seek provider review/support when available. Do not guess a forbidden word, promise that another room will pass, or treat this as a technical-retry condition.
2. For an explicitly retryable technical failure that produces no image, use the existing one-attempt reserve-room rule only for the missing slot. Keep its copy, camera role and filename. Completed images do not need generation again.
3. For a broken attachment, recover the original bytes using the associated Library link and existing bounded repair. A download failure does not justify regenerating an image. The native Library originals downloaded successfully in this run.
4. Inspect exported JPEGs at full and mobile size, count actual text baselines and verify the seam position. Initial generation previews are not the final delivery artifact. Retain the current geometry/type contract and final creative review; no additional prompt override is supported by this run.
5. Optional future engineering improvement: a distinct partial-output archival action could collect already-created assets from a blocked job without generation or posting. Current terminal rejection handling preserves the chat and its Library files; this observation does not prove automatic Dropbox import of partial outputs. Such an action would need separate provenance, idempotency and no-post tests before release.

No reproducible Companion or footer-code defect was found, so this release records the incident and recommendations only. It does not change runtime code, prompts, project sources, extension permissions or posting behavior. The package remains incomplete and unposted because Architectural Wall is absent.
