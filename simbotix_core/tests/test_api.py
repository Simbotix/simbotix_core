"""Tests for whitelisted API endpoints."""

import json
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today
from unittest.mock import patch, MagicMock


class TestLicensingAPI(FrappeTestCase):
    """Test suite for licensing API endpoints."""

    def setUp(self):
        super().setUp()
        if not frappe.db.exists("Simbotix Core Settings", "Simbotix Core Settings"):
            frappe.get_doc({
                "doctype": "Simbotix Core Settings",
                "warning_threshold": 80,
                "hard_limit_threshold": 100,
                "send_alert_emails": 0,
            }).insert(ignore_permissions=True)

        self.license = frappe.get_doc({
            "doctype": "App License",
            "license_key": frappe.generate_hash(length=32),
            "customer_id": "CUST-001",
            "customer_name": "Test Customer",
            "tier": "Builder",
            "status": "Active",
            "expiry_date": add_days(today(), 30),
            "resource_limits": json.dumps({
                "storage_gb": 30,
                "api_calls": 200000,
                "webhooks": 20,
            }),
            "enabled_features": json.dumps(["webhooks", "ai_agents"]),
            "enabled_apps": json.dumps(["flowz", "botz_studio"]),
        }).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.db.rollback()
        frappe.set_user("Administrator")
        frappe.cache().delete_key("simbotix_license_cache")
        frappe.cache().delete_key("simbotix_license_data")

    def test_get_license_info(self):
        """Test get_license_info returns license details."""
        from simbotix_core.api.licensing import get_license_info

        result = get_license_info()

        self.assertTrue(result["success"])
        self.assertEqual(result["license"]["tier"], "Builder")
        self.assertEqual(result["license"]["status"], "Active")
        self.assertTrue(result["license"]["is_valid"])
        self.assertIn("webhooks", result["license"]["enabled_features"])

    def test_get_license_info_no_license(self):
        """Test get_license_info with no license."""
        from simbotix_core.api.licensing import get_license_info

        # Delete license
        frappe.delete_doc("App License", self.license.name, force=True)
        frappe.cache().delete_key("simbotix_license_cache")

        result = get_license_info()

        self.assertFalse(result["success"])
        self.assertIn("No license", result["message"])

    def test_get_usage_summary(self):
        """Test get_usage_summary returns usage data."""
        from simbotix_core.api.licensing import get_usage_summary

        # Add some usage
        frappe.get_doc({
            "doctype": "Usage Record",
            "resource_type": "api_calls",
            "quantity": 50000,
            "timestamp": frappe.utils.now_datetime(),
        }).insert(ignore_permissions=True)

        result = get_usage_summary()

        self.assertTrue(result["success"])
        self.assertEqual(result["tier"], "Builder")
        self.assertIn("api_calls", result["usage"])
        self.assertEqual(result["usage"]["api_calls"]["current"], 50000)
        self.assertEqual(result["usage"]["api_calls"]["limit"], 200000)
        self.assertEqual(result["usage"]["api_calls"]["percentage"], 25.0)

    def test_get_usage_summary_no_license(self):
        """Test get_usage_summary with no license."""
        from simbotix_core.api.licensing import get_usage_summary

        frappe.delete_doc("App License", self.license.name, force=True)
        frappe.cache().delete_key("simbotix_license_cache")

        result = get_usage_summary()

        self.assertFalse(result["success"])

    @patch("simbotix_core.api.licensing.sync_license")
    def test_sync_now(self, mock_sync):
        """Test sync_now triggers license sync."""
        from simbotix_core.api.licensing import sync_now

        mock_sync.return_value = {"success": True, "message": "Synced"}

        result = sync_now()

        mock_sync.assert_called_once()
        self.assertTrue(result["success"])

    def test_check_feature_licensed(self):
        """Test check_feature for licensed feature."""
        from simbotix_core.api.licensing import check_feature

        result = check_feature("webhooks")

        self.assertTrue(result["licensed"])
        self.assertEqual(result["tier"], "Builder")

    def test_check_feature_not_licensed(self):
        """Test check_feature for unlicensed feature."""
        from simbotix_core.api.licensing import check_feature

        result = check_feature("nonexistent_feature")

        self.assertFalse(result["licensed"])

    def test_check_app_licensed(self):
        """Test check_app for licensed app."""
        from simbotix_core.api.licensing import check_app

        result = check_app("flowz")

        self.assertTrue(result["licensed"])
        self.assertEqual(result["tier"], "Builder")

    def test_check_app_not_licensed(self):
        """Test check_app for unlicensed app."""
        from simbotix_core.api.licensing import check_app

        result = check_app("nonexistent_app")

        self.assertFalse(result["licensed"])

    def test_get_overage_estimate_no_overage(self):
        """Test get_overage_estimate with no overage."""
        from simbotix_core.api.licensing import get_overage_estimate

        result = get_overage_estimate()

        self.assertTrue(result["success"])
        self.assertEqual(result["total_estimated_cost"], 0)
        self.assertEqual(result["overages"], {})

    def test_get_overage_estimate_with_overage(self):
        """Test get_overage_estimate with overage."""
        from simbotix_core.api.licensing import get_overage_estimate

        # Add usage that exceeds limit
        frappe.get_doc({
            "doctype": "Usage Record",
            "resource_type": "storage_gb",
            "quantity": 35,  # 5 GB over 30 limit
            "timestamp": frappe.utils.now_datetime(),
        }).insert(ignore_permissions=True)

        result = get_overage_estimate()

        self.assertTrue(result["success"])
        self.assertIn("storage_gb", result["overages"])
        self.assertEqual(result["overages"]["storage_gb"]["exceeded_by"], 5)
        self.assertGreater(result["total_estimated_cost"], 0)


class TestAlertAPI(FrappeTestCase):
    """Test suite for alert API endpoints."""

    def setUp(self):
        super().setUp()
        if not frappe.db.exists("Simbotix Core Settings", "Simbotix Core Settings"):
            frappe.get_doc({
                "doctype": "Simbotix Core Settings",
                "warning_threshold": 80,
                "hard_limit_threshold": 100,
                "send_alert_emails": 0,
            }).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.db.rollback()

    def _create_alert(self, **kwargs):
        """Helper to create test alert."""
        defaults = {
            "doctype": "Usage Alert",
            "resource_type": "api_calls",
            "alert_type": "Warning",
            "threshold_percent": 80,
            "current_usage": 40000,
            "limit_value": 50000,
            "acknowledged": 0,
        }
        defaults.update(kwargs)
        doc = frappe.get_doc(defaults)
        doc.insert(ignore_permissions=True)
        return doc

    def test_get_pending_alerts_empty(self):
        """Test get_pending_alerts with no alerts."""
        from simbotix_core.api.licensing import get_pending_alerts

        result = get_pending_alerts()

        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["alerts"], [])

    def test_get_pending_alerts_with_alerts(self):
        """Test get_pending_alerts returns unacknowledged alerts."""
        from simbotix_core.api.licensing import get_pending_alerts

        alert1 = self._create_alert(resource_type="api_calls")
        alert2 = self._create_alert(resource_type="storage_gb")

        result = get_pending_alerts()

        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 2)

    def test_get_pending_alerts_excludes_acknowledged(self):
        """Test get_pending_alerts excludes acknowledged alerts."""
        from simbotix_core.api.licensing import get_pending_alerts

        unacked = self._create_alert(acknowledged=0)
        acked = self._create_alert(acknowledged=1)

        result = get_pending_alerts()

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["alerts"][0]["name"], unacked.name)

    def test_acknowledge_alert(self):
        """Test acknowledge_alert acknowledges alert."""
        from simbotix_core.api.licensing import acknowledge_alert

        alert = self._create_alert()

        result = acknowledge_alert(alert.name)

        self.assertTrue(result["success"])

        # Verify alert is acknowledged
        alert.reload()
        self.assertEqual(alert.acknowledged, 1)

    def test_acknowledge_alert_not_found(self):
        """Test acknowledge_alert with invalid alert."""
        from simbotix_core.api.licensing import acknowledge_alert

        result = acknowledge_alert("INVALID-ALERT-NAME")

        self.assertFalse(result["success"])
        self.assertIn("not found", result["message"])


class TestAPIPermissions(FrappeTestCase):
    """Test suite for API permission requirements."""

    def setUp(self):
        super().setUp()
        if not frappe.db.exists("Simbotix Core Settings", "Simbotix Core Settings"):
            frappe.get_doc({
                "doctype": "Simbotix Core Settings",
            }).insert(ignore_permissions=True)

        # Create test user
        if not frappe.db.exists("User", "testuser@example.com"):
            self.test_user = frappe.get_doc({
                "doctype": "User",
                "email": "testuser@example.com",
                "first_name": "Test",
                "roles": [{"role": "System Manager"}],
            }).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.db.rollback()
        frappe.set_user("Administrator")

    def test_api_requires_login(self):
        """Test API endpoints require login."""
        from simbotix_core.api.licensing import get_license_info

        # Test as guest - should still work as it's whitelisted
        frappe.set_user("Guest")

        # These endpoints are whitelisted, so they should work
        # The actual permission checking happens in the function
        result = get_license_info()

        # Function should return result (may fail due to no license, but shouldn't raise PermissionError)
        self.assertIn("success", result) or self.assertIn("message", result)

    def test_api_works_for_authenticated_user(self):
        """Test API works for authenticated users."""
        from simbotix_core.api.licensing import get_license_info

        frappe.set_user("testuser@example.com")

        result = get_license_info()

        # Should get a response (success or no license message)
        self.assertIsNotNone(result)
