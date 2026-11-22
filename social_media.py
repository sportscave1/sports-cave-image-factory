"""Shared social routes and profile links; legacy reel names redirect to Social Media."""
from zoneinfo import ZoneInfo

SOCIAL_MEDIA_PAGE_KEY = "social_media"
WALL_PREVIEW_PAGE_KEY = "social_media_wall_previews"
WALL_PREVIEW_ROUTE = "Wall Preview Inbox"
AI_REELS_PAGE_KEY = "social_media_ai_reels"
LEGACY_REELS_PAGE_KEY = "social_media_reels_studio"
SOCIAL_MEDIA_ROUTE = "Social Media"
AI_REELS_ROUTE = "AI Reels"
LEGACY_REELS_ROUTE = "Social Media Reels Studio"
SOCIAL_TIMEZONE = "Australia/Sydney"
SYDNEY_TZ = ZoneInfo(SOCIAL_TIMEZONE)
SOCIAL_PROFILES = (
    ("Instagram", "https://www.instagram.com/sportscaveshop/"),
    ("Facebook", "https://www.facebook.com/profile.php?id=100090408036260"),
    ("Pinterest", "https://au.pinterest.com/SportsCaveShop/"),
    ("TikTok", "https://www.tiktok.com/@sportscaveshop"),
    ("YouTube", "https://www.youtube.com/channel/UCDZjmaJrIXMvh7z6r123lig"),
)
SOCIAL_PROFILE_URLS = dict(SOCIAL_PROFILES)
