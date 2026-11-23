"""Synthetic community fixtures: no server startup, env discovery or provider calls."""
from datetime import datetime, timezone

ADMIN = {"id": "fixture-admin", "role": "admin", "is_active": True}
EVENTS = []
READS = []


class FakeCommunity:
    def __init__(self, user):
        self.user = user
        self.page = "page"
        self.instagram = "ig"
        self.writes = True

    def owner(self, platform):
        return self.page if platform == "Facebook" else self.instagram

    def conversations(self, platform, **kwargs):
        READS.append(("conversations", platform))
        return {"data": [{"id": "thread", "unread_count": 1, "updated_time": "2026-11-22T00:00:00Z" if platform == "Facebook" else "2026-11-21T23:00:00Z", "participants": {"data": [
            {"id": self.owner(platform), "name": "Sports Cave"}, {"id": "person", "name": "Fixture customer"}]}}], "after": ""}

    def messages(self, platform, thread, **kwargs):
        READS.append(("messages", platform))
        return {"data": [{"id": "message", "from": {"id": "person", "name": "Fixture customer"},
                          "created_time": datetime.now(timezone.utc).isoformat(), "message": "Do you deliver to Sydney?"}], "after": ""}

    def send(self, platform, thread, text):
        EVENTS.append(("send", platform, thread, text))
        return {"message_id": "sent"}

    def posts(self, platform, **kwargs):
        return {"data": [{"id": "post", "message": "Fixture Sports Cave Edition", "caption": "Fixture Sports Cave Edition",
                          "permalink": "https://www.instagram.com/p/fixture/"}], "after": ""}

    def comments(self, platform, post, **kwargs):
        return {"data": [{"id": "comment", "text": "Love this edition", "message": "Love this edition",
                          "timestamp": "2026-11-21T23:00:00Z", "created_time": "2026-11-22T00:00:00Z", "like_count": 3, "username": "fixture", "from": {"id": "person", "name": "Fixture fan"}}], "after": ""}

    def comment_feed(self, platform, **kwargs):
        READS.append(("comment_feed", platform))
        posts = self.posts(platform)
        return {"data": [dict(post, comments=self.comments(platform, post["id"])) for post in posts["data"]], "after": ""}

    def moderate(self, platform, post, comment, action, text=""):
        EVENTS.append((action, platform, comment, text))
        return {"success": True}

    def discover_engaged(self):
        return ["fixture"]

    def discover(self, handle):
        return {"username": handle, "followers_count": 5000, "biography": "Basketball and NBA collector",
                "media": {"data": [{"like_count": 200, "comments_count": 20}]}}

    def connection(self):
        return {"name": "Fixture Page", "instagram": "fixture", "writes": True}


class FakeStore:
    rows = []
    enabled = False

    @classmethod
    def list_creators(cls, user):
        return cls.rows

    @classmethod
    def save_creator(cls, user, row):
        if not any(p["username"] == row["username"] for p in cls.rows):
            cls.rows.append(dict(row, state="discovered", sent_at=None))

    @classmethod
    def update_creator(cls, user, handle, state, draft):
        row = next(p for p in cls.rows if p["username"] == handle)
        row.update(state=state, draft=draft)

    @classmethod
    def automation(cls, user, enabled=None):
        if enabled is not None:
            cls.enabled = enabled
        return {"automation_enabled": cls.enabled}
