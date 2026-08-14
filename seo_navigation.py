import os


SEO_PAGE_KEY = "seo"
SEO_OVERVIEW_ROUTE = "SEO Overview"
SEO_KEYWORDS_ROUTE = "Keyword Research & Mapping"
SEO_REPORTS_ROUTE = "Reports & Strategy"
SEO_TASKS_ROUTE = "Tasks & Results"
SEO_CITATIONS_ROUTE = "Citations"
SEO_BLOG_ROUTE = "Blog Content"
SEO_INTERNAL_LINKING_ROUTE = "Internal Linking"
SEO_BACKLINKS_ROUTE = "Backlinks & Outreach"

SEO_ANALYTICS_ROUTES = (
    SEO_OVERVIEW_ROUTE,
    SEO_KEYWORDS_ROUTE,
)

SEO_WORKSPACE_ROUTES = (
    SEO_REPORTS_ROUTE,
    SEO_TASKS_ROUTE,
    SEO_BLOG_ROUTE,
    SEO_INTERNAL_LINKING_ROUTE,
    SEO_BACKLINKS_ROUTE,
    SEO_CITATIONS_ROUTE,
)

SEO_FULL_WORKSPACE_ENABLED = os.getenv("SEO_FULL_WORKSPACE_ENABLED", "").strip().casefold() in {
    "1", "true", "yes", "on",
}

# The underlying workspace routes and data remain intact and can be restored by
# enabling the admin feature flag.
SEO_ROUTES = (
    (*SEO_ANALYTICS_ROUTES, *SEO_WORKSPACE_ROUTES)
    if SEO_FULL_WORKSPACE_ENABLED
    else SEO_ANALYTICS_ROUTES
)

SEO_NAV_LABELS = {
    SEO_OVERVIEW_ROUTE: "Overview",
    SEO_KEYWORDS_ROUTE: "Keyword Research & Mapping",
    SEO_REPORTS_ROUTE: "Reports & Strategy",
    SEO_TASKS_ROUTE: "Tasks & Results",
    SEO_CITATIONS_ROUTE: "Citations",
    SEO_BLOG_ROUTE: "Blog Content",
    SEO_INTERNAL_LINKING_ROUTE: "Internal Linking",
    SEO_BACKLINKS_ROUTE: "Backlinks & Outreach",
}
