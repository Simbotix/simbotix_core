"""Tests for licensing utilities."""

import json
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today
from unittest.mock import patch, MagicMock


class TestLicensingDecorators(FrappeTestCase):
    """Test suite for licensing decorators."""

    def setUp(self):
        super().setUp()
        # Ensure settings exist
        if not frappe.db.exists("Simbotix Core Settings", "Simbotix Core Settings"):
            frappe.get_doc({
                "doctype": "Simbotix Core Settings",
                "warning_threshold": 80,
                "hard_limit_threshold": 100,
                "block_on_exceeded": 1,
            }).insert(ignore_permissions=True)

        # Create test license
        self.license = frappe.get_doc({
            "doctype": "App License",
            "license_key": frappe.generate_hash(length=32),
            "tier": "Builder",
            "status": "Active",
            "expiry_date": add_days(today(), 30),
            "resource_limits": json.dumps({
                "storage_gb": 30,
                "api_calls": 200000,
            }),
            "enabled_features": json.dumps(["webhooks", "ai_agents"]),
            "enabled_apps": json.dumps(["flowz", "botz_studio"]),
        }).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.db.rollback()
        frappe.cache().delete_key("simbotix_license_cache")
        frappe.cache().delete_key("simbotix_license_data")

    def test_requires_license_passes(self):
        """Test requires_license passes with valid license."""
        from simbotix_core.utils.licensing import requires_license

        @requires_license()
        def test_function():
            return "success"

        result = test_function()
        self.assertEqual(result, "success")

    def test_requires_license_with_feature_passes(self):
        """Test requires_license with enabled feature."""
        from simbotix_core.utils.licensing import requires_license

        @requires_license(feature="webhooks")
        def test_function():
            return "success"

        result = test_function()
        self.assertEqual(result, "success")

    def test_requires_license_with_feature_fails(self):
        """Test requires_license fails for disabled feature."""
        from simbotix_core.utils.licensing import requires_license

        @requires_license(feature="nonexistent_feature")
        def test_function():
            return "success"

        with self.assertRaises(frappe.PermissionError) as ctx:
            test_function()

        self.assertIn("nonexistent_feature", str(ctx.exception))
        self.assertIn("not included", str(ctx.exception))

    def test_requires_license_with_app_passes(self):
        """Test requires_license with enabled app."""
        from simbotix_core.utils.licensing import requires_license

        @requires_license(app="flowz")
        def test_function():
            return "success"

        result = test_function()
        self.assertEqual(result, "success")

    def test_requires_license_with_app_fails(self):
        """Test requires_license fails for disabled app."""
        from simbotix_core.utils.licensing import requires_license

        @requires_license(app="nonexistent_app")
        def test_function():
            return "success"

        with self.assertRaises(frappe.PermissionError) as ctx:
            test_function()

        self.assertIn("nonexistent_app", str(ctx.exception))

    def test_requires_license_no_license(self):
        """Test requires_license fails with no license."""
        from simbotix_core.utils.licensing import requires_license

        # Delete the license
        frappe.delete_doc("App License", self.license.name, force=True)
        frappe.cache().delete_key("simbotix_license_cache")

        @requires_license()
        def test_function():
            return "success"

        with self.assertRaises(frappe.PermissionError) as ctx:
            test_function()

        self.assertIn("No valid license", str(ctx.exception))

    def test_requires_license_expired(self):
        """Test requires_license fails with expired license."""
        from simbotix_core.utils.licensing import requires_license

        # Expire the license
        self.license.expiry_date = add_days(today(), -1)
        self.license.save(ignore_permissions=True)
        frappe.cache().delete_key("simbotix_license_cache")

        @requires_license()
        def test_function():
            return "success"

        with self.assertRaises(frappe.PermissionError) as ctx:
            test_function()

        self.assertIn("not active", str(ctx.exception))


class TestRequiresQuotaDecorator(FrappeTestCase):
    """Test suite for requires_quota decorator."""

    def setUp(self):
        super().setUp()
        if not frappe.db.exists("Simbotix Core Settings", "Simbotix Core Settings"):
            frappe.get_doc({
                "doctype": "Simbotix Core Settings",
                "warning_threshold": 80,
                "hard_limit_threshold": 100,
                "block_on_exceeded": 1,
            }).insert(ignore_permissions=True)

        self.license = frappe.get_doc({
            "doctype": "App License",
            "license_key": frappe.generate_hash(length=32),
            "tier": "Builder",
            "status": "Active",
            "expiry_date": add_days(today(), 30),
            "resource_limits": json.dumps({
                "api_calls": 100,  # Low limit for testing
            }),
            "enabled_features": json.dumps([]),
            "enabled_apps": json.dumps([]),
        }).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.db.rollback()
        frappe.cache().delete_key("simbotix_license_cache")
        frappe.cache().delete_key("simbotix_license_data")

    @patch("simbotix_core.utils.metering.record_usage")
    def test_requires_quota_passes_under_limit(self, mock_record):
        """Test requires_quota passes when under limit."""
        from simbotix_core.utils.licensing import requires_quota

        @requires_quota(resource="api_calls")
        def test_function():
            return "success"

        result = test_function()
        self.assertEqual(result, "success")
        mock_record.assert_called_once_with("api_calls", 1)

    @patch("simbotix_core.utils.metering.record_usage")
    def test_requires_quota_custom_quantity(self, mock_record):
        """Test requires_quota with custom quantity."""
        from simbotix_core.utils.licensing import requires_quota

        @requires_quota(resource="emails", quantity=5)
        def test_function():
            return "success"

        result = test_function()
        self.assertEqual(result, "success")
        mock_record.assert_called_once_with("emails", 5)

    @patch("simbotix_core.utils.metering.check_limits")
    @patch("simbotix_core.utils.metering.record_usage")
    def test_requires_quota_blocks_when_exceeded(self, mock_record, mock_check):
        """Test requires_quota blocks when limit exceeded and blocking enabled."""
        from simbotix_core.utils.licensing import requires_quota

        mock_check.return_value = "exceeded"

        @requires_quota(resource="api_calls")
        def test_function():
            return "success"

        with self.assertRaises(frappe.ValidationError) as ctx:
            test_function()

        self.assertIn("Quota exceeded", str(ctx.exception))
        mock_record.assert_not_called()

    @patch("simbotix_core.utils.metering.check_limits")
    @patch("simbotix_core.utils.metering.record_usage")
    def test_requires_quota_allows_when_blocking_disabled(self, mock_record, mock_check):
        """Test requires_quota allows when blocking disabled."""
        from simbotix_core.utils.licensing import requires_quota

        # Disable blocking
        settings = frappe.get_single("Simbotix Core Settings")
        settings.block_on_exceeded = 0
        settings.save(ignore_permissions=True)

        mock_check.return_value = "exceeded"

        @requires_quota(resource="api_calls")
        def test_function():
            return "success"

        result = test_function()
        self.assertEqual(result, "success")
        mock_record.assert_called_once()


class TestLicensingFunctions(FrappeTestCase):
    """Test suite for licensing functions."""

    def setUp(self):
        super().setUp()
        if not frappe.db.exists("Simbotix Core Settings", "Simbotix Core Settings"):
            frappe.get_doc({
                "doctype": "Simbotix Core Settings",
                "use_redis_cache": 1,
                "cache_ttl_seconds": 300,
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
        frappe.cache().delete_key("simbotix_license_cache")
        frappe.cache().delete_key("simbotix_license_data")

    def test_is_licensed_valid(self):
        """Test is_licensed returns True for valid license."""
        from simbotix_core.utils.licensing import is_licensed

        self.assertTrue(is_licensed())

    def test_is_licensed_with_feature(self):
        """Test is_licensed checks feature."""
        from simbotix_core.utils.licensing import is_licensed

        self.assertTrue(is_licensed(feature="webhooks"))
        self.assertFalse(is_licensed(feature="nonexistent"))

    def test_is_licensed_with_app(self):
        """Test is_licensed checks app."""
        from simbotix_core.utils.licensing import is_licensed

        self.assertTrue(is_licensed(app="flowz"))
        self.assertFalse(is_licensed(app="nonexistent"))

    def test_get_license(self):
        """Test get_license returns license dict."""
        from simbotix_core.utils.licensing import get_license

        license_doc = get_license()

        self.assertIsNotNone(license_doc)
        self.assertEqual(license_doc["tier"], "Builder")
        self.assertEqual(license_doc["status"], "Active")
        self.assertTrue(license_doc["is_valid"])

    def test_get_license_caches_result(self):
        """Test get_license caches result."""
        from simbotix_core.utils.licensing import get_license

        # First call
        license1 = get_license()

        # Check cache is set
        cached = frappe.cache().get_value("simbotix_license_data")
        self.assertIsNotNone(cached)

        # Second call should use cache
        license2 = get_license()
        self.assertEqual(license1["license_key"], license2["license_key"])

    def test_get_license_tier(self):
        """Test get_license_tier returns tier name."""
        from simbotix_core.utils.licensing import get_license_tier

        tier = get_license_tier()
        self.assertEqual(tier, "Builder")

    def test_get_resource_limit(self):
        """Test get_resource_limit returns limit value."""
        from simbotix_core.utils.licensing import get_resource_limit

        self.assertEqual(get_resource_limit("storage_gb"), 30)
        self.assertEqual(get_resource_limit("api_calls"), 200000)
        self.assertEqual(get_resource_limit("nonexistent"), 0)

    def test_get_enabled_features(self):
        """Test get_enabled_features returns feature list."""
        from simbotix_core.utils.licensing import get_enabled_features

        features = get_enabled_features()
        self.assertIn("webhooks", features)
        self.assertIn("ai_agents", features)

    def test_get_enabled_apps(self):
        """Test get_enabled_apps returns app list."""
        from simbotix_core.utils.licensing import get_enabled_apps

        apps = get_enabled_apps()
        self.assertIn("flowz", apps)
        self.assertIn("botz_studio", apps)


class TestSyncLicense(FrappeTestCase):
    """Test suite for sync_license function."""

    def setUp(self):
        super().setUp()
        if not frappe.db.exists("Simbotix Core Settings", "Simbotix Core Settings"):
            frappe.get_doc({
                "doctype": "Simbotix Core Settings",
                "license_key": "test-license-key",
                "central_api_url": "https://simbotix.com/api",
            }).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.db.rollback()
        frappe.cache().delete_key("simbotix_license_cache")

    def test_sync_license_no_key(self):
        """Test sync_license fails without license key."""
        from simbotix_core.utils.licensing import sync_license

        settings = frappe.get_single("Simbotix Core Settings")
        settings.license_key = ""
        settings.save(ignore_permissions=True)

        result = sync_license()

        self.assertFalse(result["success"])
        self.assertIn("No license key", result["message"])

    @patch("simbotix_core.utils.licensing.get_api_client")
    def test_sync_license_success(self, mock_get_client):
        """Test sync_license creates/updates license on success."""
        from simbotix_core.utils.licensing import sync_license

        mock_client = MagicMock()
        mock_client.get_license_details.return_value = {
            "customer_id": "CUST-001",
            "customer_name": "Test Customer",
            "tier": "Builder",
            "status": "Active",
            "expiry_date": str(add_days(today(), 30)),
            "resource_limits": {"api_calls": 200000},
            "enabled_features": ["webhooks"],
            "enabled_apps": ["flowz"],
        }
        mock_get_client.return_value = mock_client

        result = sync_license()

        self.assertTrue(result["success"])
        self.assertIn("synced successfully", result["message"])
        self.assertIsNotNone(result["license"])

    @patch("simbotix_core.utils.licensing.get_api_client")
    def test_sync_license_no_response(self, mock_get_client):
        """Test sync_license handles no API response."""
        from simbotix_core.utils.licensing import sync_license

        mock_client = MagicMock()
        mock_client.get_license_details.return_value = None
        mock_get_client.return_value = mock_client

        result = sync_license()

        self.assertFalse(result["success"])
        self.assertIn("No response", result["message"])

    @patch("simbotix_core.utils.licensing.get_api_client")
    def test_sync_license_handles_exception(self, mock_get_client):
        """Test sync_license handles API exceptions."""
        from simbotix_core.utils.licensing import sync_license

        mock_client = MagicMock()
        mock_client.get_license_details.side_effect = Exception("Connection failed")
        mock_get_client.return_value = mock_client

        result = sync_license()

        self.assertFalse(result["success"])
        self.assertIn("Connection failed", result["message"])
