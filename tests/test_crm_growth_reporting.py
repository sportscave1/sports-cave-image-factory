from datetime import date
from unittest.mock import Mock

from crm_growth_reporting import device_orders
import crm_growth_reporting as growth


def test_device_cards_use_only_verified_explicit_ga4_purchases(monkeypatch):
    report = Mock()
    monkeypatch.setattr(growth, "GoogleReports", lambda: report)
    report.connection.return_value = {"ga4_property_id": "properties/123"}
    result = {
        "property_timezone": "Australia/Sydney",
        "quality": {"status": "GA4 verified"},
        "fetched_at": "2026-11-13T00:00:00Z",
        "rows": [
            {"dimensions": {"deviceCategory": "desktop"}, "metrics": {"ecommercePurchases": "0"}},
            {"dimensions": {"deviceCategory": "tablet"}, "metrics": {"ecommercePurchases": "12"}},
        ],
    }
    report.ga4.return_value = result
    day = date(2026, 1, 12)
    assert device_orders(day) == {"desktop": 0, "mobile": None, "timezone": "Australia/Sydney"}
    report.ga4.assert_called_once_with("properties/123", growth.DEVICE, day, day)
    result["rows"] += result["rows"][:1]
    assert device_orders(day) is None
    result["rows"].pop()
    result["quality"]["status"] = "Qualified"
    assert device_orders(day) is None


def test_sports_connector_reports_pending_until_requested_date_is_published(monkeypatch):
    edition = {"date": "2026-11-12", "full_brief": "Sports news", "recommendations": []}
    monkeypatch.setattr(growth, "get_app_setting", lambda *args, **kwargs: edition)
    assert growth.published_sports_edition(date(2026, 11, 13)) == {
        "date": "2026-11-13", "status": "pending",
    }
    assert growth.published_sports_edition(date(2026, 11, 12)) == edition
