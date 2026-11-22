"""Page-token Meta community API. No requests or credential reads at import time.

Uses Facebook Login (including its linked Instagram professional account).
All public operations enforce OS permissions; mutations also require explicit
runtime enablement. Tokens never enter session state, query strings or errors.
"""
import os
import logging
import re
import time
from datetime import datetime, timedelta, timezone

import requests

import os_accounts


class CommunityError(RuntimeError):
    pass


def require_access(user):
    if not os_accounts.can_access_page(user, "Social Media"):
        raise PermissionError("Social Media access is required.")


def identifier(value):
    value = str(value or "")
    if not re.fullmatch(r"[A-Za-z0-9_:.\-]{1,200}", value):
        raise CommunityError("Invalid Meta object ID.")
    return value


def username(value):
    value = str(value or "").strip().lstrip("@").lower()
    if not re.fullmatch(r"[a-z0-9_.]{1,30}", value):
        raise CommunityError("Enter an Instagram username, without a URL.")
    return value


def reply_open(messages, owner, *, now=None):
    """Only a recent inbound message opens the standard response window."""
    now = now or datetime.now(timezone.utc)
    for message in messages:
        sender = str((message.get("from") or {}).get("id") or "")
        if not sender or sender == str(owner):
            continue
        try:
            sent = datetime.fromisoformat(message["created_time"].replace("Z", "+00:00"))
            if sent.tzinfo and timedelta(0) <= now - sent < timedelta(hours=24):
                return True
        except (KeyError, ValueError, TypeError):
            continue
    return False


class MetaCommunity:
    def __init__(self, user, *, env=None, session=None):
        require_access(user)
        self.user = user
        env = os.environ if env is None else env
        self.page = str(env.get("META_FACEBOOK_PAGE_ID") or env.get("META_PAGE_ID") or env.get("FACEBOOK_PAGE_ID") or "")
        self.instagram = str(env.get("META_INSTAGRAM_ACTOR_ID") or env.get("META_INSTAGRAM_ACCOUNT_ID") or env.get("INSTAGRAM_ACCOUNT_ID") or env.get("INSTAGRAM_ACTOR_ID") or "")
        self._token = env.get("META_PAGE_ACCESS_TOKEN", "")
        self._discovery_token = env.get("META_SOCIAL_DISCOVERY_TOKEN") or env.get("META_ACCESS_TOKEN", "")
        # A Facebook User token can be added for community ad comments without
        # replacing the System User token used by posting, reporting and CRM.
        self._ads_token = env.get("META_SOCIAL_ACCESS_TOKEN") or env.get("META_ACCESS_TOKEN", "")
        account = str(env.get("META_AD_ACCOUNT_ID", "")).strip()
        self.ad_account = (account if account.startswith("act_") else "act_" + account) if account else ""
        self.writes = env.get("META_SOCIAL_WRITES_ENABLED") == "1"
        self.version = env.get("META_API_VERSION", "v26.0")
        if not re.fullmatch(r"v\d+\.0", self.version):
            raise CommunityError("Invalid Meta API version setting.")
        self._session = session or requests.Session()
        self._last_conversation_read = 0.0
        self._instagram_user_posts = set()

    def owner(self, platform):
        require_access(self.user)
        if platform not in ("Facebook", "Instagram"):
            raise CommunityError("Choose Facebook or Instagram.")
        owner = self.page if platform == "Facebook" else self.instagram
        if not owner or not self._token:
            raise CommunityError(f"{platform} connection is not configured. See Connection.")
        return identifier(owner)

    def _request(self, method, path, *, params=None, data=None, discovery=False, advertising=False):
        require_access(self.user)
        if method != "GET" and not self.writes:
            raise CommunityError("Sending and moderation are disabled for this environment.")
        token = self._ads_token if advertising else self._discovery_token if discovery else self._token
        if not token:
            raise CommunityError("The required Meta connection is not configured.")
        if method == "GET" and path.endswith("/conversations"):
            # Meta permits two conversation reads/second/account. Keep a single
            # workspace client below that limit during pagination/ownership checks.
            delay = .55 - (time.monotonic() - self._last_conversation_read)
            if delay > 0:
                time.sleep(delay)
            self._last_conversation_read = time.monotonic()
        try:
            response = self._session.request(
                method, f"https://graph.facebook.com/{self.version}/{path}",
                headers={"Authorization": f"Bearer {token}"},
                params=params, json=data, timeout=(5, 25), allow_redirects=False,
            )
            result = response.json()
        except (requests.RequestException, ValueError):
            raise CommunityError("Meta could not confirm the result. Refresh before retrying; a write may have succeeded.") from None
        if response.status_code >= 300 or (isinstance(result, dict) and result.get("error")):
            code = (result.get("error") or {}).get("code") if isinstance(result, dict) else None
            hint = {190: "Reconnect the Page token.", 10: "Check Meta App Review and permissions.",
                    200: "Check the Page token permissions and Page tasks.",
                    4: "Meta is rate limiting requests. Try again later.",
                    100: "This operation or object is unavailable to this Meta connection."}.get(code, "Check the connection and refresh before retrying.")
            error = result.get("error") or {} if isinstance(result, dict) else {}
            # Report useful diagnostics without echoing provider text, URLs or tokens.
            scopes = re.findall(r"\b(?:instagram|pages)_[a-z_]+\b", str(error.get("message", "")))
            allowed = {"instagram_basic", "instagram_manage_messages", "instagram_manage_comments",
                       "pages_manage_metadata", "pages_messaging", "pages_read_engagement",
                       "pages_read_user_content", "pages_manage_engagement"}
            missing = sorted(set(scopes) & allowed)
            detail = " Required permissions: " + ", ".join(missing) + "." if missing else ""
            reference = f" (Meta {code}" if isinstance(code, int) else ""
            subcode = error.get("error_subcode")
            if code == 100:
                provider_message = str(error.get("message", "")).lower()
                if "unsupported get request" in provider_message:
                    hint = "The requested media is unavailable to this token or has been removed."
                elif "nonexisting field" in provider_message or "non-existing field" in provider_message:
                    fields = {"caption", "permalink", "timestamp", "owner", "comments", "like_count", "username", "text"}
                    match = re.search(r"field \(([^)]+)\)", provider_message)
                    hint = "Meta does not support the requested " + (match[1] if match and match[1] in fields else "media") + " field."
            if code == 200 and subcode == 2534041:
                hint = ("Instagram message access is disabled for connected tools. In Instagram, open Settings and activity → "
                        "Messages and story replies → Message requests → Connected tools, and enable Allow access to messages. "
                        "Then refresh this inbox.")
            if reference:
                reference += f"/{subcode})" if isinstance(subcode, int) else ")"
            raise CommunityError("Meta rejected the request" + reference + ". " + hint + detail)
        if result is False or (isinstance(result, dict) and result.get("success") is False):
            raise CommunityError("Meta did not confirm this operation. Refresh before retrying.")
        return result

    def _edge(self, path, fields, *, after="", extra=None, advertising=False):
        params = {"fields": fields, "limit": 30, **(extra or {})}
        if after:
            # Meta cursors are opaque. Truncation corrupts long cursors and makes
            # older posts/comments fail with error 100. Never follow paging URLs.
            params["after"] = str(after)
        result = self._request("GET", path, params=params, advertising=advertising)
        paging = result.get("paging") or {}
        return {"data": result.get("data") or [],
                "after": (paging.get("cursors") or {}).get("after", "") if paging.get("next") else ""}

    def connection(self):
        self.owner("Facebook")
        result = self._request("GET", "me", params={"fields": "id,name,instagram_business_account{id,username}"})
        if str(result.get("id")) != self.page:
            raise CommunityError("The Page token belongs to a different Page.")
        linked = result.get("instagram_business_account") or {}
        if self.instagram and str(linked.get("id")) != self.instagram:
            raise CommunityError("The configured Instagram account is not linked to this Page.")
        return {"name": result.get("name"), "instagram": linked.get("username"), "writes": self.writes}

    def conversations(self, platform, *, after=""):
        owner = self.owner(platform)
        # Facebook Login Instagram conversations use the Page conversations edge.
        return self._edge(f"{self.owner('Facebook')}/conversations", "id,updated_time,participants,unread_count,is_owner",
                          after=after, extra={"platform": "instagram" if platform == "Instagram" else "messenger"})

    def connection_checks(self):
        """Read-only capability probes; a valid Page token alone proves little."""
        checks = []
        for platform in ("Facebook", "Instagram"):
            for capability, method in (("Messages", self.conversations), ("Comments", self.comment_feed)):
                try:
                    method(platform)
                    checks.append({"Channel": platform, "Feature": capability, "Status": "Available", "Details": "Read access verified"})
                except CommunityError as exc:
                    checks.append({"Channel": platform, "Feature": capability, "Status": "Needs attention", "Details": str(exc)})
        return checks

    def _thread(self, platform, thread_id):
        owner = self.owner(platform)
        thread_id = identifier(thread_id)
        # Never trust an arbitrary thread ID supplied by a browser/client.
        after = ""
        for _ in range(20):
            page = self.conversations(platform, after=after)
            for row in page["data"]:
                if str(row.get("id")) == thread_id:
                    return row
            after = page["after"]
            if not after:
                break
        raise CommunityError("This conversation is not in the connected account's recent inbox.")

    def messages(self, platform, thread_id, *, after=""):
        self._thread(platform, thread_id)
        return self._edge(f"{identifier(thread_id)}/messages", "id,created_time,from,to,message,attachments", after=after)

    def send(self, platform, thread_id, text):
        thread = self._thread(platform, thread_id)
        if thread.get("is_owner") is False:
            raise CommunityError("Another app owns this conversation. Check conversation routing in Business Suite.")
        owner = self.owner(platform)
        messages = self.messages(platform, thread_id)["data"]
        if not reply_open(messages, owner):
            raise CommunityError("No inbound message within 24 hours. Open this conversation in Business Suite.")
        peers = [row for row in (thread.get("participants") or {}).get("data", [])
                 if str(row.get("id")) not in {owner, self.page, self.instagram}]
        if len(peers) != 1:
            raise CommunityError("A unique conversation recipient could not be verified.")
        text = str(text or "").strip()
        if not text or len(text) > 1000:
            raise CommunityError("Write a reply between 1 and 1,000 characters.")
        body = {"recipient": {"id": identifier(peers[0]["id"])}, "message": {"text": text}}
        if platform == "Facebook":
            body["messaging_type"] = "RESPONSE"
        result = self._request("POST", f"{owner}/messages", data=body)
        if not isinstance(result, dict) or not result.get("message_id"):
            raise CommunityError("Meta did not confirm a message ID. Refresh Inbox before retrying.")
        return result

    def posts(self, platform, *, after=""):
        owner = self.owner(platform)
        edge = "posts" if platform == "Facebook" else "media"
        fields = "id,message,created_time,permalink_url" if platform == "Facebook" else "id,caption,timestamp,permalink"
        return self._edge(f"{owner}/{edge}", fields, after=after)

    def comment_feed(self, platform, *, after=""):
        """Read owned posts and their first comment page in one Graph request."""
        owner = self.owner(platform)
        if platform == "Facebook":
            edge = "posts"
            fields = ("id,message,created_time,permalink_url,"
                      "comments.filter(stream).limit(20){id,message,from,created_time,like_count}")
        else:
            edge = "media"
            fields = ("id,caption,timestamp,permalink,"
                      "comments.limit(20){id,text,username,timestamp,like_count}")
        return self._edge(f"{owner}/{edge}", fields, after=after, extra={"limit": 8})

    def ad_comment_feed(self, *, after=""):
        """Resolve actual ad post IDs: unpublished ad posts are absent from /posts.

        Ads are read with the existing advertising token; owned post/comment reads
        use the Page token. No advertising writes or new permissions are granted.
        """
        require_access(self.user)
        if not self.ad_account or not self._ads_token:
            return {"data": [], "after": "", "errors": []}
        self.owner("Facebook")
        params = {"fields": "id,creative{effective_object_story_id,effective_instagram_media_id,source_instagram_media_id,instagram_user_id}", "limit": 5}
        if after:
            params["after"] = str(after)
        ads = self._request("GET", identifier(self.ad_account) + "/ads", params=params, advertising=True)
        ids = {"Facebook": set(), "Instagram": set()}
        ad_proofs = {}
        for ad in ads.get("data") or []:
            creative = ad.get("creative") or {}
            story = str(creative.get("effective_object_story_id") or "")
            # Only resolve creatives tied to this Page. Check the returned owner
            # again before exposing comments or allowing a moderation action.
            if story.startswith(self.page + "_"):
                ids["Facebook"].add(identifier(story))
                ig_actor = str(creative.get("instagram_user_id") or "")
                if (creative.get("effective_instagram_media_id") and self.instagram
                        and (not ig_actor or ig_actor == self.instagram)):
                    ids["Instagram"].add(identifier(creative["effective_instagram_media_id"]))
                    if ig_actor == self.instagram and ad.get("id"):
                        ad_proofs[str(creative["effective_instagram_media_id"])] = {
                            "ad_id": identifier(ad["id"]),
                            "source_id": str(creative.get("source_instagram_media_id") or "")}
        posts, errors = [], []
        for platform, post_ids in ids.items():
            if not post_ids:
                continue
            fields = ("id,from,message,created_time,permalink_url,comments.filter(stream).limit(20){id,message,from,created_time,like_count}"
                      if platform == "Facebook" else
                      "id,owner,comments.limit(20){id,text,username,timestamp,like_count}")
            unreadable = 0
            reason = ""
            for post_id in sorted(post_ids):
                # These unpublished objects reject the root multi-ID expansion
                # with error 100. Read each bounded ad post directly instead.
                try:
                    if platform == "Instagram" and post_id in ad_proofs:
                        # Ad media can expose its comments edge while rejecting
                        # the ordinary media metadata expansion (100/33). The
                        # creative came from our ad account and names our exact
                        # Instagram actor, so metadata is not an access gate.
                        post = self._instagram_ad_post(post_id, **ad_proofs[post_id])
                    else:
                        post = self._request("GET", post_id, params={"fields": fields}, advertising=platform == "Instagram")
                except CommunityError as exc:
                    unreadable += 1
                    reason = str(exc)
                    if platform == "Instagram":
                        logging.getLogger(__name__).warning(
                            "social_ad_comments_unavailable media=%s ad=%s reason=%s",
                            post_id, (ad_proofs.get(post_id) or {}).get("ad_id", "unverified"), reason)
                    continue
                owner = post.get("from" if platform == "Facebook" else "owner") or {}
                if post.get("error"):
                    unreadable += 1
                elif str(owner.get("id")) == self.owner(platform) and post.get("id"):
                    posts.append(dict(post, platform=platform, advertising=True))
            if unreadable:
                if platform == "Instagram":
                    reason += " " + self.advertising_access_hint()
                errors.append(f"{platform}: {unreadable} advertising posts could not be read. " + reason)
        paging = ads.get("paging") or {}
        cursor = (paging.get("cursors") or {}).get("after", "") if paging.get("next") else ""
        return {"data": posts, "after": cursor, "errors": errors}

    def _instagram_ad_post(self, post_id, ad_id, source_id=""):
        # Boosted posts can have a distinct original media ID. Meta documents
        # /comments on either object as including the original and boosted ad.
        candidates = list(dict.fromkeys([post_id, *([identifier(source_id)] if source_id else [])]))
        for candidate in candidates:
            try:
                comments = self._instagram_ad_comments(candidate)
                return {"id": candidate, "owner": {"id": self.instagram},
                        "ad_id": ad_id, "comments": comments}
            except CommunityError as exc:
                failure = exc
                logging.getLogger(__name__).warning(
                    "social_ad_media_read_failed ad=%s media=%s source=%s reason=%s",
                    ad_id, candidate, source_id or "none", str(exc))
        raise failure

    def _instagram_ad_comments(self, post_id, *, after=""):
        """Read all ad placements, falling back for Story/carousel child media.

        ordered_comments is documented for Facebook Login and includes the
        other media used by placement customization. No writes are retried.
        """
        fields = "id,text,from{id,username},timestamp,like_count"
        try:
            page = self._edge(f"{post_id}/ordered_comments", fields, after=after, advertising=True)
            self._instagram_user_posts.add(post_id)
            return page
        except CommunityError:
            # ordered_comments excludes Story and carousel child media. Its
            # cursor must never be passed to the different /comments edge.
            if after:
                raise
            try:
                page = self._edge(f"{post_id}/comments", fields, advertising=True)
                self._instagram_user_posts.add(post_id)
                page["comment_edge"] = "comments"
                return page
            except CommunityError:
                # The linked Page token may have access to individual media
                # that the advertising User token cannot access. Its successful
                # read also determines the token for the subsequent write.
                page = self._edge(f"{post_id}/comments", fields)
                self._instagram_user_posts.discard(post_id)
                page["comment_edge"] = "page_comments"
                return page

    def _verify_instagram_ad(self, post_id, ad_id):
        """Recheck untrusted UI context against Meta before every action."""
        if not self.ad_account or not self._ads_token:
            raise CommunityError("The advertising connection is not configured.")
        ad = self._request("GET", identifier(ad_id), params={
            "fields": "id,account_id,creative{effective_object_story_id,effective_instagram_media_id,source_instagram_media_id,instagram_user_id}"
        }, advertising=True)
        creative = ad.get("creative") or {}
        if (str(ad.get("id")) != str(ad_id)
                or "act_" + str(ad.get("account_id")) != self.ad_account
                or str(creative.get("instagram_user_id")) != self.owner("Instagram")
                or str(post_id) not in {str(creative.get("effective_instagram_media_id")),
                                        str(creative.get("source_instagram_media_id"))}
                or not str(creative.get("effective_object_story_id", "")).startswith(self.page + "_")):
            raise CommunityError("This advertising post does not belong to the connected account.")
        self._instagram_user_posts.add(str(post_id))

    def advertising_access_hint(self):
        """Distinguish missing advertising-token grants from unavailable media."""
        require_access(self.user)
        if not self._ads_token:
            return "The advertising connection is not configured."
        try:
            payload = self._request("GET", "me/permissions", params={"fields": "permission,status"}, advertising=True)
            granted = {row.get("permission") for row in payload.get("data", []) if row.get("status") == "granted"}
            missing = {"instagram_basic", "instagram_manage_comments", "pages_read_engagement"} - granted
            if not ({"ads_read", "ads_management"} & granted):
                missing.add("ads_read")
            if missing:
                return "The advertising token needs these Meta permissions: " + ", ".join(sorted(missing)) + ". Reconnect that token with Instagram access."
            identity = self._request("GET", self.owner("Instagram"), params={"fields": "id"}, advertising=True)
            if str(identity.get("id")) != self.instagram:
                return "The advertising token could not verify the linked Instagram account."
        except CommunityError:
            return "Check the advertising token's access to the linked Instagram account in Meta Business Settings."
        return "The advertising token can read the linked Instagram account; these individual advertising media are unavailable."

    def _own_post(self, platform, post_id):
        post_id = identifier(post_id)
        owner = self.owner(platform)
        fields = "id,from" if platform == "Facebook" else "id,owner"
        try:
            result = self._request("GET", post_id, params={"fields": fields})
        except CommunityError:
            if platform != "Instagram" or not self._ads_token:
                raise
            # Instagram ad media requires the Facebook User/Business token with
            # advertising access, unlike the Page conversations edge.
            result = self._request("GET", post_id, params={"fields": fields}, advertising=True)
            self._instagram_user_posts.add(post_id)
        author = result.get("from" if platform == "Facebook" else "owner") or {}
        if str(author.get("id")) != owner:
            raise CommunityError("This post does not belong to the connected account.")
        return post_id

    def comments(self, platform, post_id, *, after="", ad_id="", comment_edge=""):
        if platform == "Instagram" and ad_id:
            post_id = identifier(post_id)
            self._verify_instagram_ad(post_id, ad_id)
            if comment_edge in ("comments", "page_comments"):
                advertising = comment_edge != "page_comments"
                if not advertising:
                    self._instagram_user_posts.discard(post_id)
                page = self._edge(f"{post_id}/comments", "id,text,from{id,username},timestamp,like_count",
                                  after=after, advertising=advertising)
                page["comment_edge"] = comment_edge
                return page
            return self._instagram_ad_comments(post_id, after=after)
        post_id = self._own_post(platform, post_id)
        fields = "id,message,from,created_time,like_count" if platform == "Facebook" else "id,text,username,timestamp,like_count"
        try:
            return self._edge(f"{post_id}/comments", fields, after=after,
                              extra={"filter": "stream"} if platform == "Facebook" else None,
                              advertising=post_id in self._instagram_user_posts)
        except CommunityError:
            if platform != "Instagram" or not self._ads_token or post_id in self._instagram_user_posts:
                raise
            result = self._edge(f"{post_id}/comments", fields, after=after, advertising=True)
            self._instagram_user_posts.add(post_id)
            return result

    def moderate(self, platform, post_id, comment_id, action, text="", *, ad_id="", comment_edge=""):
        if action not in ("reply", "delete", "like", "unlike", "hide", "unhide"):
            raise CommunityError("Unknown comment action.")
        if platform == "Instagram" and action in ("like", "unlike"):
            raise CommunityError("Instagram comment likes are not enabled by this API integration. Open Instagram to like it.")
        comment_id = identifier(comment_id)
        after = ""
        found = False
        for _ in range(20):
            context = {"ad_id": ad_id, "comment_edge": comment_edge} if ad_id else {}
            page = self.comments(platform, post_id, after=after, **context)
            comment_edge = page.get("comment_edge", comment_edge)
            if any(str(row.get("id")) == comment_id for row in page["data"]):
                found = True
                break
            after = page["after"]
            if not after:
                break
        if not found:
            raise CommunityError("This comment could not be verified on the selected account's post.")
        auth = {"advertising": platform == "Instagram" and str(post_id) in self._instagram_user_posts}
        if action == "reply":
            text = str(text or "").strip()
            if not text or len(text) > 1000:
                raise CommunityError("Write a reply between 1 and 1,000 characters.")
            edge = "comments" if platform == "Facebook" else "replies"
            return self._request("POST", f"{comment_id}/{edge}", data={"message": text}, **auth)
        if action in ("like", "unlike"):
            return self._request("POST" if action == "like" else "DELETE", f"{comment_id}/likes")
        if action in ("hide", "unhide"):
            key = "is_hidden" if platform == "Facebook" else "hide"
            return self._request("POST", comment_id, data={key: action == "hide"}, **auth)
        return self._request("DELETE", comment_id, **auth)

    def discover(self, handle):
        handle = username(handle)
        fields = f"business_discovery.username({handle}){{id,username,name,biography,followers_count,media_count,media.limit(12){{like_count,comments_count,caption}}}}"
        return self._request("GET", self.owner("Instagram"), params={"fields": fields}, discovery=True).get("business_discovery") or {}

    def discover_engaged(self):
        """Discover prospects from actual comment authors on our own recent posts."""
        handles = set()
        for post in self.posts("Instagram")["data"][:10]:
            for comment in self.comments("Instagram", post["id"])["data"]:
                if comment.get("username"):
                    handles.add(username(comment["username"]))
        return sorted(handles)[:30]


def assess_creator(profile, *, minimum=1000, maximum=50000):
    followers = int(profile.get("followers_count") or 0)
    media = (profile.get("media") or {}).get("data") or []
    engagement = round(100 * sum(int(p.get("like_count") or 0) + int(p.get("comments_count") or 0)
                             for p in media) / (len(media) * followers), 2) if media and followers else None
    text = " ".join([profile.get("biography") or "", *(p.get("caption") or "" for p in media)]).lower()
    keywords = ("sport", "basketball", "football", "cricket", "rugby", "nba", "afl", "nrl", "soccer", "memorabilia", "man cave", "mancave", "f1", "formula 1")
    matches = [word for word in keywords if word in text]
    eligible = minimum <= followers <= maximum and bool(matches)
    return {"username": username(profile.get("username")), "followers": followers,
            "engagement": engagement, "fit": eligible,
            "score": min(100, len(matches) * 10 + (30 if eligible else 0) + min(30, int(engagement or 0) * 5)),
            "reason": f"Sports interests: {', '.join(matches) or 'not established'}; {len(media)} recent posts assessed.",
            "draft": "Hi! We’re Sports Cave. We loved seeing your passion for sport. Would you be interested in a collaboration featuring a Sports Cave Edition in your space? If you’re keen, we’d love to discuss the idea and the collaboration terms with you."}
