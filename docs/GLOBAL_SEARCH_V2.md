# Global Search V2 — local implementation report

1. **Menu cause:** the old scorer returned a finite score for every page when the
   query was empty. Opening search fetched an index and immediately rendered it.
2. **Dismissal causes:** outside-click detection exempted the entire header,
   rather than just the search input/results. Email iframe pointer events never
   reach the parent document. Streamlit also preserves header DOM while replacing
   its controller, potentially leaving a visible panel without live open state.
3. **Architecture:** `app_search.py` extends the existing account page registry
   with metadata-only feature entries. It caches permission-scoped registries
   (maximum 64 scopes). The header receives the index in its configuration and
   prepares it in memory. The compatibility endpoint uses this same registry and
   no longer loads persisted entities. Legacy entity helpers are inactive.
4. **Size:** 46 entries for an admin with activity access; restricted users see
   only entries whose existing destination route they can access.
5. **Ranking:** exact title, exact alias, title prefix, alias prefix, title
   contains, alias/keyword contains, then fuzzy match. Priority and registry order
   break ties deterministically. Maximum eight results; 48px rows and a bounded
   scrolling panel directly under the existing search field.
6. **Aliases:** explicit Sports Cave terminology, including fulfilment/fulfillment,
   Prodigi/shipping, collector number, product upload, GA4, GSC, inbox and staff.
   Visible page titles and existing routing are unchanged.
7. **Typos:** bounded Damerau-Levenshtein matching supports adjacent transpositions
   such as `analtyics`. Fuzzy matches always follow direct matches; disabled below
   four characters and above 64 characters. Queries normalize case, spacing and
   hyphens. A single meaningful character is enough for direct matching.
8. **Outside click:** input/results are the only search-specific safe area.
   Clicking header, sidebar or content closes search without returning focus.
   Parent-window blur closes it when focus enters an embedded component. New
   controllers explicitly hide stale search DOM after Streamlit reruns.
9. **Escape:** closes results reliably, preserving the query without reopening.
10. **Keyboard navigation:** Down/Up move and wrap the selection; Enter uses the
    existing route navigator. Navigation closes results and clears the query.
11. **Ctrl/Cmd+K:** focuses a cleared input. Empty input displays no panel, loading
    spinner, suggestions or page list. Clicking the input focuses it and only
    renders results if meaningful text exists.
12. **Editable protection:** previous focus fix is preserved: ordinary typing
    cannot activate search. Inputs, textareas, selects, buttons, contenteditable
    descendants, textbox/combobox roles, composer wrappers, shadow paths and
    focused iframes retain their keyboard input. No unrelated autofocus added.
13. **Performance:** production ranking code, 46 entries, 1,000 mixed local queries:
    mean **0.468ms**, p95 **0.940ms**, maximum **1.551ms**. This measures ranking,
    not network latency or browser paint. No search network request is needed.
14. **External services:** search makes no database, Shopify, Meta, IMAP, GA4, GSC
    or other external API calls. Existing independent notification polling is
    unchanged. No application pages are preloaded for search.
15. **Files changed:** `app_search.py`, `top_bar.py`, `top_bar_api.py`,
    `components/sports_cave_top_bar/index.html`, `tests/test_app_search.py`,
    `tests/test_app_search_component.cjs`, `tests/test_top_bar.py`,
    `tests/fixtures/email_notifications_preview.py`, and this report.
16. **Tests:** 265 distinct selected Python tests: **262 passed**, three known
    existing failures (obsolete sidebar source assertion, order-status suite cache
    contamination, obsolete literal 30-second timer assertion). Focused rerun:
    24 tests, 23 passed and the same sidebar failure. New executable JS ranking,
    rendering, dismissal and keyboard/navigation tests pass. Existing composer
    isolation (2,404 checks), Email helpers (20) and notification badge (22) pass.
    Python compilation, extracted top-bar JS syntax and `git diff --check` pass.
17. **Browser:** production OS shell and Email component with fabricated data,
    at **1920×1080** and **1440×900**. Empty click/shortcut hides the panel; Email
    ranks first; Creative Refresh routes correctly; `analtyics` finds Analytics;
    header and iframe clicks dismiss; Escape closes; click and Enter navigation
    clear the query. Compact screenshots are in `output/GLOBAL_SEARCH_V2_1920.png`
    and `output/GLOBAL_SEARCH_V2_1440.png`. Feature-only entries such as Signatures
    deliberately open their parent page because no supported section deep link
    exists. Destination business logic was not exercised against real services.
18. **Email:** To/CC/BCC/Subject/body typing verified at 1440×900 and To/Subject/body
    at 1920×1080; search stayed closed. No Email code changed in this task.
19. **Unrelated behavior:** sidebar logic, notifications, Orders, Ads, Analytics,
    SEO, Email transport/signatures/caching and other page implementations untouched.
20. **Readiness:** ready for Nathan's approval and a controlled deployment smoke
    test. No commit, push, deployment or Render modification performed. No real
    messages sent or mailbox changes made. Work stops here.
