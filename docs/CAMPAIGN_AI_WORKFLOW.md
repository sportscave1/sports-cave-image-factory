# Manual Campaign AI workflow

Settings → Auto fill prompt → select verified product/collection and purpose → Submit → Copy prompt. Copy refreshes public product/collection and required Edition Ops facts. Attach the exact product reference in ChatGPT and manually copy back Campaign name, Subject and Preview text.

Editor → Auto fill email uses the campaign-scoped session handoff and current name, subject, preview text, market and delivery settings. It never parses generated prose. Build/Copy recheck facts; opening the editor/dialog makes no new Shopify calls. The zero-height trigger overlays the existing Header row; native section editor, preview, templates, autosave and send boundaries are retained.

Let AI decide selects the smallest effective structure. Choose components offers Hero image, Headline, Short collector story, CTA, Image gallery, Collector / edition facts, Catalogue, Offer / discount, Deadline / urgency and Video teaser. Extra direction is limited to 800 characters. View prompt starts collapsed.

The versioned body prompt requests ordered HTML SECTION blocks and native IMAGE / CATALOGUE insertion plans. It requires body-only conservative inline HTML, single-column responsive tables at 600/430/390/375/320px, images-off copy and <=60 KB generated HTML. Existing production 80/95 KB analysis and send protection remain authoritative.

Email visuals carry the Ads exact-product pixel compositing, frame/glass physics, residential realism, lighting and variation rules. Prefer 4:3 1200x900; exclude Meta's fixed square canvas, black footer, scarcity strip and image CTA. Never invent product details or image URLs. Hero requires one complete generation prompt; galleries use static slots; video uses a linked poster, never an embed.

Nathan generates images manually in ChatGPT. The existing native Image Copy prompt then handles optimization/Shopify upload with connected tools and returns actual CDN URL, ALT and responsive canonical click-through HTML. Streamlit does not generate/upload images. Verified destination, campaign name, purpose, title and market are projected into that handoff. Missing destination/reference is requested, never guessed.

Catalogue recommendations resolve fresh market facts only for the selected product or one bounded page (maximum 12) in its verified collection. Active public products require canonical URL, supported image and valid market price. No unrelated store scan or invented bestseller/edition claims. Native Catalogue remains the live-facts renderer.

Settings, Email and Image share clipboard.js: Clipboard API → execCommand fallback, including API rejection → manual View prompt only if both fail. CRM uses a nonce preflight/ack protocol to revalidate before browser copy; context is retained even if browser copy fails. Ads retains its boolean component contract. Clipboard is never read. Logs contain stage/type only, never prompt contents or payloads.

Offline validation: campaign prompt/handoff, clipboard, images, catalogue, first paint, renderer/size/send and review regressions. SQL-dependent tests require the explicit local database fixture and are skipped otherwise. Browser fixture forbids external HTTP and production DB access. Desktop 1366x768 and narrow 390x844 checked; editor header with/without helper has identical vertical position. No production operations performed.

The synthetic review baseline is frozen in tests/fixtures/crm_market_scan_baseline.py so comparison does not change when HEAD advances. It is test-only.

## Files changed in this task

- crm_campaign_page.py
- crm_campaign_prompt.py
- crm_prompt_readers.py
- crm_prompt_ui.py
- crm_prompt_copy.py (new)
- crm_email_prompt.py (new)
- crm_email_prompt_ui.py (new)
- crm_email_visual_prompt.py (new)
- crm_image_prompt.py
- crm_section_ui.py
- components/crm_sections/composer.js
- components/crm_sections/image.js
- ui_components/prompt_copy/index.html
- ui_components/prompt_copy/clipboard.js (new)
- prompts/sports_cave_email_html_prompt_v1.txt (new)
- prompts/sports_cave_email_visual_v1.txt (new)
- tests/test_crm_email_prompt.py (new)
- tests/test_crm_prompt_helper.py
- tests/test_crm_prompt_clipboard.cjs
- tests/test_crm_image_controls.cjs
- tests/test_crm_fast_review.py (frozen baseline reference only)
- tests/fixtures/crm_email_ai_preview.py (new)
- tests/fixtures/crm_market_scan_baseline.py (new, test-only historical source)
- docs/CAMPAIGN_AI_WORKFLOW.md (new)

Final Campaigns regression suite: 168 tests, 124 passed, 44 SQL-dependent skips. Seven relevant JavaScript scripts passed. py_compile and git diff --check passed (Git reports only existing line-ending conversion notices). Additional Ads integration suite: 6 passed, 1 existing assertion failure in unchanged render_prompt_copy_button: creation_instructions normalizes the supplied prompt before serialization, while the assertion expects the unnormalized original. Ads business logic/test left unchanged. New read-only collection query validated against Shopify schema (read_products); no live store calls.
