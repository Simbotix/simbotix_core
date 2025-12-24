"""Tests for Usage Alert DocType."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime
from unittest.mock import patch, MagicMock


class TestUsageAlert(FrappeTestCase):
    """Test suite for Usage Alert document."""

    def setUp(self):
        super().setUp()
        # Ensure settings exist
        if not frappe.db.exists("Simbotix Core Settings", "Simbotix Core Settings"):
            frappe.get_doc({
                "doctype": "Simbotix Core Settings",
                "warning_threshold": 80,
                "hard_limit_threshold": 100,
                "send_alert_emails": 0,
            }).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.db.rollback()
        frappe.set_user("Administrator")

    def _create_usage_alert(self, **kwargs):
        """Helper to create test usage alert."""
        defaults = {
            "doctype": "Usage Alert",
            "resource_type": "api_calls",
            "alert_type": "Warning",
            "threshold_percent": 80,
            "current_usage": 40000,
            "limit_value": 50000,
        }
        defaults.update(kwargs)
        doc = frappe.get_doc(defaults)
        doc.insert(ignore_permissions=True)
        return doc

    def test_create_usage_alert(self):
        """Test basic usage alert creation."""
        alert = self._create_usage_alert()
        self.assertTrue(alert.name)
        self.assertEqual(alert.resource_type, "api_calls")
        self.assertEqual(alert.alert_type, "Warning")

    def test_usage_percentage_calculation(self):
        """Test usage percentage is calculated on validate."""
        alert = self._create_usage_alert(
            current_usage=40000,
            limit_value=50000
        )
        self.assertEqual(alert.usage_percent, 80.0)

    def test_usage_percentage_exceeded(self):
        """Test usage percentage over 100%."""
        alert = self._create_usage_alert(
            alert_type="Exceeded",
            current_usage=60000,
            limit_value=50000
        )
        self.assertEqual(alert.usage_percent, 120.0)

    def test_overage_calculation_api_calls(self):
        """Test overage calculation for API calls."""
        alert = self._create_usage_alert(
            alert_type="Exceeded",
            resource_type="api_calls",
            current_usage=60000,
            limit_value=50000
        )
        # 10000 over, at $0.50 per 10K = $0.50
        self.assertEqual(alert.overage_amount, 0.5)

    def test_overage_calculation_storage(self):
        """Test overage calculation for storage."""
        alert = self._create_usage_alert(
            alert_type="Exceeded",
            resource_type="storage_gb",
            current_usage=35,
            limit_value=30
        )
        # 5 GB over, at $1.50/GB = $7.50
        self.assertEqual(alert.overage_amount, 7.5)

    def test_overage_calculation_emails(self):
        """Test overage calculation for emails."""
        alert = self._create_usage_alert(
            alert_type="Exceeded",
            resource_type="emails",
            current_usage=6000,
            limit_value=5000
        )
        # 1000 over, at $1.00 per 1K = $1.00
        self.assertEqual(alert.overage_amount, 1.0)

    def test_overage_calculation_ai_queries(self):
        """Test overage calculation for AI queries."""
        alert = self._create_usage_alert(
            alert_type="Exceeded",
            resource_type="ai_queries",
            current_usage=1100,
            limit_value=1000
        )
        # 100 over, at $0.015 per query = $1.50
        self.assertEqual(alert.overage_amount, 1.5)

    def test_no_overage_for_warning(self):
        """Test no overage calculation for warning alerts."""
        alert = self._create_usage_alert(
            alert_type="Warning",
            current_usage=40000,
            limit_value=50000
        )
        self.assertFalse(alert.overage_amount)

    def test_acknowledge_alert(self):
        """Test acknowledging an alert."""
        alert = self._create_usage_alert()
        self.assertEqual(alert.acknowledged, 0)

        alert.acknowledge()

        self.assertEqual(alert.acknowledged, 1)
        self.assertEqual(alert.acknowledged_by, frappe.session.user)
        self.assertIsNotNone(alert.acknowledged_at)

    def test_acknowledge_with_specific_user(self):
        """Test acknowledging with specific user."""
        alert = self._create_usage_alert()
        alert.acknowledge(user="testuser@example.com")

        self.assertEqual(alert.acknowledged_by, "testuser@example.com")

    @patch("simbotix_core.doctype.usage_alert.usage_alert.frappe.sendmail")
    def test_send_notification(self, mock_sendmail):
        """Test sending notification email."""
        # Set up settings with email enabled
        settings = frappe.get_single("Simbotix Core Settings")
        settings.send_alert_emails = 1
        settings.alert_email = "admin@test.com"
        settings.save(ignore_permissions=True)

        alert = self._create_usage_alert()
        alert.send_notification()

        mock_sendmail.assert_called_once()
        call_args = mock_sendmail.call_args
        self.assertIn("admin@test.com", call_args.kwargs["recipients"])
        self.assertIn("api_calls", call_args.kwargs["subject"])

    @patch("simbotix_core.doctype.usage_alert.usage_alert.frappe.sendmail")
    def test_no_notification_if_disabled(self, mock_sendmail):
        """Test no notification sent if disabled in settings."""
        settings = frappe.get_single("Simbotix Core Settings")
        settings.send_alert_emails = 0
        settings.save(ignore_permissions=True)

        alert = self._create_usage_alert()
        alert.send_notification()

        mock_sendmail.assert_not_called()

    @patch("simbotix_core.doctype.usage_alert.usage_alert.frappe.sendmail")
    def test_no_duplicate_notification(self, mock_sendmail):
        """Test notification not sent twice."""
        settings = frappe.get_single("Simbotix Core Settings")
        settings.send_alert_emails = 1
        settings.alert_email = "admin@test.com"
        settings.save(ignore_permissions=True)

        alert = self._create_usage_alert()
        alert.notification_sent = 1
        alert.save(ignore_permissions=True)

        alert.send_notification()
        mock_sendmail.assert_not_called()


class TestCreateAlert(FrappeTestCase):
    """Test suite for create_alert function."""

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

    def test_create_alert_warning(self):
        """Test creating a warning alert."""
        from simbotix_core.doctype.usage_alert.usage_alert import create_alert

        alert = create_alert(
            resource_type="api_calls",
            alert_type="Warning",
            current_usage=40000,
            limit_value=50000,
            send_email=False
        )

        self.assertIsNotNone(alert)
        self.assertEqual(alert.alert_type, "Warning")
        self.assertEqual(alert.threshold_percent, 80)

    def test_create_alert_exceeded(self):
        """Test creating an exceeded alert."""
        from simbotix_core.doctype.usage_alert.usage_alert import create_alert

        alert = create_alert(
            resource_type="storage_gb",
            alert_type="Exceeded",
            current_usage=35,
            limit_value=30,
            send_email=False
        )

        self.assertIsNotNone(alert)
        self.assertEqual(alert.alert_type, "Exceeded")
        self.assertEqual(alert.threshold_percent, 100)

    def test_create_alert_updates_existing(self):
        """Test create_alert updates existing unacknowledged alert."""
        from simbotix_core.doctype.usage_alert.usage_alert import create_alert

        # Create first alert
        alert1 = create_alert(
            resource_type="api_calls",
            alert_type="Warning",
            current_usage=40000,
            limit_value=50000,
            send_email=False
        )

        # Create second alert same type/resource
        alert2 = create_alert(
            resource_type="api_calls",
            alert_type="Warning",
            current_usage=45000,  # Updated usage
            limit_value=50000,
            send_email=False
        )

        # Should be the same alert, just updated
        self.assertEqual(alert1.name, alert2.name)
        self.assertEqual(alert2.current_usage, 45000)

    def test_create_alert_new_if_acknowledged(self):
        """Test create_alert creates new if previous is acknowledged."""
        from simbotix_core.doctype.usage_alert.usage_alert import create_alert

        # Create and acknowledge first alert
        alert1 = create_alert(
            resource_type="api_calls",
            alert_type="Warning",
            current_usage=40000,
            limit_value=50000,
            send_email=False
        )
        alert1.acknowledge()

        # Create second alert - should be new
        alert2 = create_alert(
            resource_type="api_calls",
            alert_type="Warning",
            current_usage=42000,
            limit_value=50000,
            send_email=False
        )

        self.assertNotEqual(alert1.name, alert2.name)


class TestOverageRates(FrappeTestCase):
    """Test suite for overage rate constants."""

    def test_overage_rates_exist(self):
        """Test all overage rates are defined."""
        from simbotix_core.doctype.usage_alert.usage_alert import OVERAGE_RATES

        expected_resources = [
            "storage_gb", "bandwidth_gb", "database_gb", "api_calls",
            "file_uploads_gb", "executions", "emails", "ai_queries", "webhooks"
        ]

        for resource in expected_resources:
            self.assertIn(resource, OVERAGE_RATES)
            self.assertIn("rate", OVERAGE_RATES[resource])
            self.assertIn("unit", OVERAGE_RATES[resource])

    def test_overage_rates_values(self):
        """Test overage rate values match pricing guide."""
        from simbotix_core.doctype.usage_alert.usage_alert import OVERAGE_RATES

        self.assertEqual(OVERAGE_RATES["storage_gb"]["rate"], 1.50)
        self.assertEqual(OVERAGE_RATES["bandwidth_gb"]["rate"], 0.08)
        self.assertEqual(OVERAGE_RATES["database_gb"]["rate"], 3.00)
        self.assertEqual(OVERAGE_RATES["api_calls"]["rate"], 0.50)
        self.assertEqual(OVERAGE_RATES["api_calls"]["per"], 10000)
        self.assertEqual(OVERAGE_RATES["emails"]["rate"], 1.00)
        self.assertEqual(OVERAGE_RATES["emails"]["per"], 1000)
        self.assertEqual(OVERAGE_RATES["ai_queries"]["rate"], 0.015)
        self.assertEqual(OVERAGE_RATES["webhooks"]["rate"], 0)  # No overage
