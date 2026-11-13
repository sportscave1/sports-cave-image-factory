# Meta CRM Morning Brief

ChatGPT reviews Meta and Shopify daily at 06:00 Australia/Sydney. The desktop publisher checks Home at 06:45 with an 08:45 fallback. It uses the existing signed-in owner session and subscription.

## Daily prompt

> Prepare the Meta CRM Morning Brief for Sports Cave OS Home. Use the last completed Sydney reporting day. Use authorised read-only reporting to verify Meta ROAS and the Shopify order count for that same day. Set either metric to null if its source is missing or incomplete. Keep a confirmed zero as zero. A ratio from partially populated rows is not verified ROAS. Review delivery, creatives, product availability and the current Sports Brief to prioritise up to three actions. Return a single JSON object with date (today in Sydney), report_date (the completed Sydney reporting day), roas (number or null), orders (whole number or null) and actions (an array of distinct codes). Both dates use YYYY-MM-DD. Supported codes are check_reporting, review_delivery, check_orders, review_creative, review_catalogue and review_sports. Output only the JSON. Keep money amounts, payouts, spend and other figures out of the brief. Make no ad, store or access changes.

Submit the JSON at `/ops/meta-morning-brief/publish` using the OS reporting owner session and verify Home. The publisher accepts typed numbers, dates and fixed action codes only. Home never displays old free text or money metrics.
