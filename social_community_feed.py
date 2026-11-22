"""Session-scoped merged read models. No tokens, shared caches or storage writes."""
from datetime import datetime, timezone
import time

from meta_social import CommunityError, require_access

PLATFORMS = ("Facebook", "Instagram")
CACHE_SECONDS = 60


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).timestamp() if parsed.tzinfo else 0
    except (ValueError, TypeError, OverflowError):
        return 0


def next_cursor(page):
    if "after" in page:
        return page.get("after") or ""
    paging = page.get("paging") or {}
    return (paging.get("cursors") or {}).get("after", "") if paging.get("next") else ""


class CommunityFeed:
    def __init__(self, api, state, *, now=time.monotonic):
        require_access(api.user)
        self.api, self.state, self.now = api, state, now
        identity = (str(api.user.get("id")), api.page, api.instagram, getattr(api, "version", ""))
        if state.get("identity") != identity:
            state.clear()
            state["identity"] = identity

    def read(self, method, *args, **kwargs):
        require_access(self.api.user)
        key = (method, args, tuple(sorted(kwargs.items())))
        cache = self.state.setdefault("cache", {})
        entry = cache.get(key)
        if entry and self.now() - entry["at"] < CACHE_SECONDS:
            if "error" in entry:
                raise CommunityError(entry["error"])
            return entry["data"]
        try:
            data = getattr(self.api, method)(*args, **kwargs)
        except CommunityError as exc:
            cache[key] = {"at": self.now(), "error": str(exc)}
            raise
        cache[key] = {"at": self.now(), "data": data}
        self.state["synced_at"] = datetime.now(timezone.utc).isoformat()
        return data

    def invalidate(self):
        self.state.pop("cache", None)

    def _pages(self, kind):
        return self.state.setdefault(kind + "_pages", {platform: [""] for platform in PLATFORMS})

    def threads(self):
        rows, errors, more = {}, [], {}
        for platform, cursors in self._pages("thread").items():
            try:
                for after in cursors:
                    page = self.read("conversations", platform, after=after)
                    for row in page["data"]:
                        rows[(platform, row["id"])] = dict(row, platform=platform)
                more[platform] = next_cursor(page)
            except CommunityError as exc:
                errors.append(f"{platform}: {exc}")
        items = sorted(rows.values(), key=lambda row: timestamp(row.get("updated_time")), reverse=True)
        return {"items": items, "errors": errors, "more": more}

    def more_threads(self, snapshot):
        for platform, after in snapshot["more"].items():
            cursors = self._pages("thread")[platform]
            if after and after not in cursors:
                cursors.append(after)

    def comments(self):
        rows, posts, errors, more_posts, more_comments = {}, {}, [], {}, []
        extras = self.state.setdefault("comment_pages", {})
        more_ads = ""
        if hasattr(self.api, "ad_comment_feed"):
            try:
                for cursor in self.state.setdefault("ad_post_pages", [""]):
                    ad_page = self.read("ad_comment_feed", after=cursor)
                    errors.extend(ad_page.get("errors", []))
                    for post in ad_page["data"]:
                        posts[(post["platform"], post["id"])] = post
                more_ads = next_cursor(ad_page)
            except CommunityError as exc:
                errors.append("Advertising comments: " + str(exc))
        for platform, cursors in self._pages("post").items():
            try:
                platform_posts = {key[1]: post for key, post in posts.items() if key[0] == platform}
                # New posts frequently have no comments. Read through up to four
                # empty batches per visit instead of presenting a false empty inbox.
                budget = self.state.setdefault("post_scan_targets", {}).setdefault(platform, 4)
                for after in cursors:
                    page = self.read("comment_feed", platform, after=after)
                    for post in page["data"]:
                        posts[(platform, post["id"])] = dict(post, platform=platform)
                        platform_posts[post["id"]] = post
                    next_after = next_cursor(page)
                    if (after == cursors[-1] and next_after and next_after not in cursors
                            and len(cursors) < budget
                            and not any((post.get("comments") or {}).get("data") for post in platform_posts.values())):
                        cursors.append(next_after)
                more_posts[platform] = next_cursor(page)
            except CommunityError as exc:
                errors.append(f"{platform}: {exc}")
        for post_key, post in posts.items():
            platform, post_id = post_key
            page = post.get("comments") or {"data": []}
            for row in page.get("data") or []:
                rows[(platform, row["id"])] = dict(row, platform=platform, post=post)
            after = next_cursor(page)
            for cursor in extras.get(post_key, []):
                try:
                    page = self.read("comments", platform, post_id, after=cursor)
                except CommunityError as exc:
                    errors.append(f"{platform}: {exc}")
                    break
                for row in page["data"]:
                    rows[(platform, row["id"])] = dict(row, platform=platform, post=post)
                after = next_cursor(page)
            if after:
                more_comments.append((platform, post_id, after))
        items = sorted(rows.values(), key=lambda row: timestamp(row.get("created_time") or row.get("timestamp")), reverse=True)
        return {"items": items, "errors": list(dict.fromkeys(errors)), "more_posts": more_posts,
                "more_comments": more_comments, "posts_scanned": len(posts), "more_ads": more_ads}

    def more_comments(self, snapshot):
        """Advance two comment edges at most; only then fetch older post pages."""
        if snapshot["more_comments"]:
            extras = self.state.setdefault("comment_pages", {})
            for platform, post_id, after in snapshot["more_comments"][:2]:
                cursors = extras.setdefault((platform, post_id), [])
                if after not in cursors:
                    cursors.append(after)
        else:
            ad_cursor = snapshot.get("more_ads")
            if ad_cursor and ad_cursor not in self.state.setdefault("ad_post_pages", [""]):
                self.state["ad_post_pages"].append(ad_cursor)
            for platform, after in snapshot["more_posts"].items():
                cursors = self._pages("post")[platform]
                if after and after not in cursors:
                    cursors.append(after)
                    self.state.setdefault("post_scan_targets", {})[platform] = len(cursors) + 3
