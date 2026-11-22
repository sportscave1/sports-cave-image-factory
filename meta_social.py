"""Page-token Meta community API. No requests or credential reads at import time.

Uses Facebook Login (including its linked Instagram professional account).
All public operations enforce OS permissions; mutations also require explicit
runtime enablement. Tokens never enter session state, query strings or errors.
"""
import os
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
        self._discovery_token = env.get("META_SOCIAL_DISCOVERY_TOKEN", "")
        self.writes = env.get("META_SOCIAL_WRITES_ENABLED") == "1"
        self.version = env.get("META_API_VERSION", "v26.0")
        if not re.fullmatch(r"v\d+\.0", self.version):
            raise CommunityError("Invalid Meta API version setting.")
        self._session = session or requests.Session()
        self._last_conversation_read = 0.0

    def owner(self, platform):
        require_access(self.user)
        if platform not in ("Facebook", "Instagram"):
            raise CommunityError("Choose Facebook or Instagram.")
        owner = self.page if platform == "Facebook" else self.instagram
        if not owner or not self._token:
            raise CommunityError(f"{platform} connection is not configured. See Connection.")
        return identifier(owner)

    def _request(self, method, path, *, params=None, data=None, discovery=False):
        require_access(self.user)
        if method != "GET" and not self.writes:
            raise CommunityError("Sending and moderation are disabled for this environment.")
        token = self._discovery_token if discovery else self._token
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
            raise CommunityError("Meta rejected the request. " + hint)
        if result is False or (isinstance(result, dict) and result.get("success") is False):
            raise CommunityError("Meta did not confirm this operation. Refresh before retrying.")
        return result

    def _edge(self, path, fields, *, after="", extra=None):
        params = {"fields": fields, "limit": 30, **(extra or {})}
        if after:
            params["after"] = str(after)[:500]
        result = self._request("GET", path, params=params)
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

    def _own_post(self, platform, post_id):
        post_id = identifier(post_id)
        owner = self.owner(platform)
        fields = "id,from" if platform == "Facebook" else "id,owner"
        result = self._request("GET", post_id, params={"fields": fields})
        author = result.get("from" if platform == "Facebook" else "owner") or {}
        if str(author.get("id")) != owner:
            raise CommunityError("This post does not belong to the connected account.")
        return post_id

    def comments(self, platform, post_id, *, after=""):
        post_id = self._own_post(platform, post_id)
        fields = "id,message,from,created_time,like_count" if platform == "Facebook" else "id,text,username,timestamp,like_count"
        return self._edge(f"{post_id}/comments", fields, after=after,
                          extra={"filter": "stream"} if platform == "Facebook" else None)

    def moderate(self, platform, post_id, comment_id, action, text=""):
        if action not in ("reply", "delete", "like", "unlike", "hide", "unhide"):
            raise CommunityError("Unknown comment action.")
        if platform == "Instagram" and action in ("like", "unlike"):
            raise CommunityError("Instagram comment likes are not enabled by this API integration. Open Instagram to like it.")
        comment_id = identifier(comment_id)
        after = ""
        found = False
        for _ in range(20):
            page = self.comments(platform, post_id, after=after)
            if any(str(row.get("id")) == comment_id for row in page["data"]):
                found = True
                break
            after = page["after"]
            if not after:
                break
        if not found:
            raise CommunityError("This comment could not be verified on the selected account's post.")
        if action == "reply":
            text = str(text or "").strip()
            if not text or len(text) > 1000:
                raise CommunityError("Write a reply between 1 and 1,000 characters.")
            edge = "comments" if platform == "Facebook" else "replies"
            return self._request("POST", f"{comment_id}/{edge}", data={"message": text})
        if action in ("like", "unlike"):
            return self._request("POST" if action == "like" else "DELETE", f"{comment_id}/likes")
        if action in ("hide", "unhide"):
            key = "is_hidden" if platform == "Facebook" else "hide"
            return self._request("POST", comment_id, data={key: action == "hide"})
        return self._request("DELETE", comment_id)

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
