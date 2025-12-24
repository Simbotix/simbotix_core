"""Tests for Simbotix Core Settings DocType."""

import frappe
from frappe.tests.utils import FrappeTestCase


class TestSimbotixCoreSettings(FrappeTestCase):
    """Test suite for Simbotix Core Settings (Single DocType)."""

    def tearDown(self):
        frappe.db.rollback()

    def test_settings_exists(self):
        """Test settings document can be created/accessed."""
        settings = frappe.get_single("Simbotix Core Settings")
        self.assertIsNotNone(settings)

    def test_default_thresholds(self):
        """Test default threshold values."""
        settings = frappe.get_single("Simbotix Core Settings")

        # Defaults should be set
        self.assertEqual(settings.warning_threshold, 80)
        self.assertEqual(settings.hard_limit_threshold, 100)

    def test_get_settings_function(self):
        """Test get_settings helper function."""
        from simbotix_core.doctype.simbotix_core_settings.simbotix_core_settings import get_settings

        settings = get_settings()

        self.assertIsNotNone(settings)
        self.assertEqual(settings.doctype, "Simbotix Core Settings")

    def test_settings_license_key(self):
        """Test license key can be set."""
        settings = frappe.get_single("Simbotix Core Settings")
        settings.license_key = "test-license-key-123"
        settings.save(ignore_permissions=True)

        # Reload and verify
        settings = frappe.get_single("Simbotix Core Settings")
        self.assertEqual(settings.license_key, "test-license-key-123")

    def test_settings_api_credentials(self):
        """Test API credentials can be set."""
        settings = frappe.get_single("Simbotix Core Settings")
        settings.api_key = "test-api-key"
        settings.api_secret = "test-api-secret"
        settings.central_api_url = "https://simbotix.com/api"
        settings.save(ignore_permissions=True)

        settings = frappe.get_single("Simbotix Core Settings")
        self.assertEqual(settings.api_key, "test-api-key")
        self.assertEqual(settings.central_api_url, "https://simbotix.com/api")

    def test_settings_cache_configuration(self):
        """Test cache configuration settings."""
        settings = frappe.get_single("Simbotix Core Settings")
        settings.use_redis_cache = 1
        settings.cache_ttl_seconds = 600
        settings.save(ignore_permissions=True)

        settings = frappe.get_single("Simbotix Core Settings")
        self.assertEqual(settings.use_redis_cache, 1)
        self.assertEqual(settings.cache_ttl_seconds, 600)

    def test_settings_blocking_configuration(self):
        """Test blocking configuration."""
        settings = frappe.get_single("Simbotix Core Settings")
        settings.block_on_exceeded = 1
        settings.save(ignore_permissions=True)

        settings = frappe.get_single("Simbotix Core Settings")
        self.assertEqual(settings.block_on_exceeded, 1)

    def test_settings_alert_email(self):
        """Test alert email configuration."""
        settings = frappe.get_single("Simbotix Core Settings")
        settings.send_alert_emails = 1
        settings.alert_email = "admin@example.com"
        settings.save(ignore_permissions=True)

        settings = frappe.get_single("Simbotix Core Settings")
        self.assertEqual(settings.alert_email, "admin@example.com")
