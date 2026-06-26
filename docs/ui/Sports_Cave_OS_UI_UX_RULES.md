# Sports Cave OS UI/UX Rules

1. Purpose first:
   Every page must make the next action obvious. Avoid decorative dashboards that do not drive action.

2. Shopify-style layout:
   Use compact admin-style layouts: top header, controls/filters, metric strip, table, detail/action panel. Prefer table-first workflow for operational data.

3. Reduce vertical scroll:
   Keep the first screen useful. Avoid oversized cards and excessive blank space. Use compact metric cards, tabs, columns, expanders, and tables.

4. Readability rule:
   Dark backgrounds must use light text.
   Light cards/buttons must use dark text.
   Never use white text on white/cream buttons.
   Never use black text on black/dark buttons.
   All text must remain readable on hover, focus, active, and clicked states.

5. Button rule:
   Buttons must keep consistent colour on hover/click/focus. No disappearing text, no colour inversion that makes text unreadable.
   Primary dark button = dark background + white text.
   Secondary light button = light background + black text.
   Danger button = controlled red background + white text.
   Gold/accent button = gold background + black text unless contrast fails.

6. Tables rule:
   Operational data should be shown in compact tables like Orders. Use dataframe/table style where possible. Tables should include sortable/filterable columns and avoid giant custom card lists.

7. Status labels:
   Use clear labels such as Connected, Missing, Needs review, Ready, Error, Scale candidate, Watch, Kill candidate, Refresh creative. Labels should be compact and readable.

8. Source-of-truth label:
   Pages that use external/synced data should show source and last sync clearly.

9. No hidden secrets:
   Never show API keys, tokens, app secrets, headers, passwords, raw secret errors, or env values. Show only configured yes/no.

10. Speed:
    No external API calls on startup. Heavy sections must lazy-load. Default tables should be capped/filtered.

11. Mobile/desktop:
    Desktop should be compact and table-first. Mobile should stack logically but still avoid huge vertical empty cards.

12. Consistency:
    New pages should reuse shared UI helpers/styles where possible instead of creating one-off CSS.
