# Sports Cave Social Media

## Navigation And Access

`Social Media` is the main sidebar destination. Its nested `AI Reels` child is
the existing reels studio with the same prompts, uploads, output naming and
prompt permissions. The old `Social Media Reels Studio` route and
`social_media_reels_studio` permission key are accepted as compatibility
aliases, so previously approved workers keep access without receiving unrelated
pages.

Accounts & Access shows one `Social Media` permission. Workers can read and edit
only their own social plans, posts and weekly check-ins. Administrators can use
the staff selector to view authorised social staff and make corrections. Every
route and data helper repeats the server-side permission check.

## Daily Workflow

1. Open `Social Media` and leave the view on `Today`.
2. Add the Top priority and a short content plan. Focus, two secondary
   priorities, planned platforms, post count and improvement test are optional.
3. Use `Save today's plan` or `Update plan` to save a draft.
4. Track content in `Post Tracker`. One content item can contain several
   platform statuses and optional platform-specific results.
5. Complete the four short end-of-day review prompts, then select `Complete day`.

The daily score is out of 10. Completed priorities provide up to 8 points; the
Top priority is weighted twice as strongly as either secondary priority. The
available priority points are scaled fairly when fewer than three priorities
were entered. Each completed review answer adds 0.5 points. Platform count,
post count and performance metrics do not add score points.

## Post Tracker

Each post stores one content item and only the selected platform rows. Platform
status can be Planned, Created, Scheduled or Live. A public URL is recommended
but optional for Live posts and must be a valid HTTPS link for that platform.
Reach/views, engagements, clicks, saves/shares and the result note can be added
later. Blank metrics remain blank rather than being stored as zero.

Save requests use deterministic request keys backed by a unique database row,
so a rerun or double-click does not create a duplicate post or duplicate
Activity Log event.

## Weekly Check-In

The week is Monday through Sunday in `Australia/Sydney`. Enter only metrics the
platform provides, plus the three short learning prompts. Draft saves update the
same staff/week report. Submission calculates platform-specific absolute
changes against the previous submitted week, total published posts, audience
growth, average daily score, completed MIPs and completed social workdays.
Missing or prior-zero values are not converted into misleading percentages.

## History And Monitoring

History defaults to a recent bounded date range and applies staff, platform,
format and status filters in server-side queries. Page size is capped at 50.
The Today team table uses aggregate queries rather than loading every plan or
post. Workers cannot select another staff member; administrators see only active
accounts that are authorised for Social Media.

Meaningful saves, completions, live posts, submissions, reopenings and admin
corrections use the existing Activity Log. Keystrokes, page views, filters and
automatic score calculations are not logged.

When the existing Reporting feature is installed, daily reports include a
compact Social Media subsection per relevant staff member and a team summary on
the Reporting page. Nathan's Daily Execution report remains a separate
subsection and source of truth.

## Database Setup

Apply the additive migration through the repository's normal migration command:

```bash
python run_migrations.py
```

The required migration is:

```text
migrations/20260728_social_media_hub.sql
```

It creates dedicated daily plan, priority, post, post-platform, weekly report,
weekly platform-metric and idempotency tables. Row-level security is enabled and
the app continues to use the existing server-side Supabase connection. No
social passwords, cookies, OAuth tokens or API credentials are stored.

A normal application deployment is required after review. Apply the migration
before staff use the new Social Media page. No desktop helper update is needed.
