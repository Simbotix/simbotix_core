"""Tests for App License DocType."""

import json
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today, getdate


class TestAppLicense(FrappeTestCase):
    """Test suite for App License document."""

    def tearDown(self):
        frappe.db.rollback()
        frappe.set_user("Administrator")
        frappe.cache().delete_key("simbotix_license_cache")

    def _create_license(self, **kwargs):
        """Helper to create test license."""
        defaults = {
            "doctype": "App License",
            "license_key": frappe.generate_hash(length=32),
            "customer_id": "CUST-001",
            "customer_name": "Test Customer",
            "tier": "Builder",
            "status": "Active",
            "expiry_date": add_days(today(), 30),
            "resource_limits": json.dumps({
                "storage_gb": 30,
                "bandwidth_gb": 300,
                "database_gb": 5,
                "api_calls": 200000,
                "file_uploads_gb": 15,
                "executions": 50000,
                "emails": 5000,
                "ai_queries": 1000,
                "webhooks": 20
            }),
            "enabled_features": json.dumps(["webhooks", "ai_agents", "custom_fields"]),
            "enabled_apps": json.dumps(["flowz", "botz_studio"]),
        }
        defaults.update(kwargs)
        doc = frappe.get_doc(defaults)
        doc.insert(ignore_permissions=True)
        return doc

    def test_create_license(self):
        """Test basic license creation."""
        license_doc = self._create_license()
        self.assertTrue(license_doc.name)
        self.assertEqual(license_doc.tier, "Builder")
        self.assertEqual(license_doc.status, "Active")

    def test_license_is_valid_active(self):
        """Test is_valid returns True for active license with future expiry."""
        license_doc = self._create_license(
            status="Active",
            expiry_date=add_days(today(), 30)
        )
        self.assertTrue(license_doc.is_valid())

    def test_license_is_valid_trial(self):
        """Test is_valid returns True for trial license."""
        license_doc = self._create_license(
            status="Trial",
            expiry_date=add_days(today(), 14)
        )
        self.assertTrue(license_doc.is_valid())

    def test_license_is_invalid_expired(self):
        """Test is_valid returns False for expired license."""
        license_doc = self._create_license(
            status="Active",
            expiry_date=add_days(today(), -1)  # Yesterday
        )
        self.assertFalse(license_doc.is_valid())

    def test_license_is_invalid_suspended(self):
        """Test is_valid returns False for suspended license."""
        license_doc = self._create_license(status="Suspended")
        self.assertFalse(license_doc.is_valid())

    def test_license_is_invalid_expired_status(self):
        """Test is_valid returns False for license with Expired status."""
        license_doc = self._create_license(status="Expired")
        self.assertFalse(license_doc.is_valid())

    def test_get_resource_limit(self):
        """Test getting resource limits."""
        license_doc = self._create_license()

        self.assertEqual(license_doc.get_resource_limit("storage_gb"), 30)
        self.assertEqual(license_doc.get_resource_limit("api_calls"), 200000)
        self.assertEqual(license_doc.get_resource_limit("webhooks"), 20)
        self.assertEqual(license_doc.get_resource_limit("nonexistent"), 0)

    def test_get_resource_limit_empty(self):
        """Test getting resource limits when none set."""
        license_doc = self._create_license(resource_limits="")
        self.assertEqual(license_doc.get_resource_limit("storage_gb"), 0)

    def test_has_feature(self):
        """Test checking for enabled features."""
        license_doc = self._create_license()

        self.assertTrue(license_doc.has_feature("webhooks"))
        self.assertTrue(license_doc.has_feature("ai_agents"))
        self.assertFalse(license_doc.has_feature("nonexistent_feature"))

    def test_has_feature_empty(self):
        """Test has_feature when no features set."""
        license_doc = self._create_license(enabled_features="")
        self.assertFalse(license_doc.has_feature("webhooks"))

    def test_has_app(self):
        """Test checking for enabled apps."""
        license_doc = self._create_license()

        self.assertTrue(license_doc.has_app("flowz"))
        self.assertTrue(license_doc.has_app("botz_studio"))
        self.assertFalse(license_doc.has_app("nonexistent_app"))

    def test_has_app_empty(self):
        """Test has_app when no apps set."""
        license_doc = self._create_license(enabled_apps="")
        self.assertFalse(license_doc.has_app("flowz"))

    def test_validate_invalid_resource_limits_json(self):
        """Test validation fails for invalid resource_limits JSON."""
        with self.assertRaises(frappe.exceptions.ValidationError):
            self._create_license(resource_limits="invalid json")

    def test_validate_invalid_enabled_features_json(self):
        """Test validation fails for invalid enabled_features JSON."""
        with self.assertRaises(frappe.exceptions.ValidationError):
            self._create_license(enabled_features="invalid json")

    def test_validate_enabled_features_must_be_array(self):
        """Test validation fails if enabled_features is not an array."""
        with self.assertRaises(frappe.exceptions.ValidationError):
            self._create_license(enabled_features='{"not": "array"}')

    def test_validate_enabled_apps_must_be_array(self):
        """Test validation fails if enabled_apps is not an array."""
        with self.assertRaises(frappe.exceptions.ValidationError):
            self._create_license(enabled_apps='{"not": "array"}')

    def test_validate_adds_missing_resource_keys(self):
        """Test validation adds missing resource limit keys."""
        license_doc = self._create_license(
            resource_limits=json.dumps({"storage_gb": 10})
        )

        limits = json.loads(license_doc.resource_limits)
        self.assertEqual(limits["storage_gb"], 10)
        self.assertEqual(limits["api_calls"], 0)  # Added with default 0
        self.assertEqual(limits["webhooks"], 0)

    def test_cache_cleared_on_update(self):
        """Test license cache is cleared when license is updated."""
        license_doc = self._create_license()

        # Set cache
        frappe.cache().set_value("simbotix_license_cache", license_doc.name)
        self.assertEqual(frappe.cache().get_value("simbotix_license_cache"), license_doc.name)

        # Update license
        license_doc.tier = "Visionary"
        license_doc.save()

        # Cache should be cleared
        self.assertIsNone(frappe.cache().get_value("simbotix_license_cache"))


class TestGetActiveLicense(FrappeTestCase):
    """Test suite for get_active_license function."""

    def tearDown(self):
        frappe.db.rollback()
        frappe.cache().delete_key("simbotix_license_cache")

    def test_get_active_license_returns_active(self):
        """Test get_active_license returns active license."""
        from simbotix_core.doctype.app_license.app_license import get_active_license

        # Create active license
        license_doc = frappe.get_doc({
            "doctype": "App License",
            "license_key": frappe.generate_hash(length=32),
            "tier": "Builder",
            "status": "Active",
            "expiry_date": add_days(today(), 30),
        }).insert(ignore_permissions=True)

        result = get_active_license()
        self.assertIsNotNone(result)
        self.assertEqual(result.name, license_doc.name)

    def test_get_active_license_returns_trial(self):
        """Test get_active_license returns trial license."""
        from simbotix_core.doctype.app_license.app_license import get_active_license

        license_doc = frappe.get_doc({
            "doctype": "App License",
            "license_key": frappe.generate_hash(length=32),
            "tier": "Trial",
            "status": "Trial",
        }).insert(ignore_permissions=True)

        result = get_active_license()
        self.assertIsNotNone(result)
        self.assertEqual(result.status, "Trial")

    def test_get_active_license_ignores_expired(self):
        """Test get_active_license ignores expired licenses."""
        from simbotix_core.doctype.app_license.app_license import get_active_license

        # Create only expired license
        frappe.get_doc({
            "doctype": "App License",
            "license_key": frappe.generate_hash(length=32),
            "tier": "Builder",
            "status": "Expired",
        }).insert(ignore_permissions=True)

        result = get_active_license()
        self.assertIsNone(result)

    def test_get_active_license_uses_cache(self):
        """Test get_active_license uses cache."""
        from simbotix_core.doctype.app_license.app_license import get_active_license

        license_doc = frappe.get_doc({
            "doctype": "App License",
            "license_key": frappe.generate_hash(length=32),
            "tier": "Builder",
            "status": "Active",
        }).insert(ignore_permissions=True)

        # First call populates cache
        result1 = get_active_license()

        # Verify cache is set
        cached = frappe.cache().get_value("simbotix_license_cache")
        self.assertEqual(cached, license_doc.name)

        # Second call should use cache
        result2 = get_active_license()
        self.assertEqual(result1.name, result2.name)


class TestGetTierLimits(FrappeTestCase):
    """Test suite for get_tier_limits function."""

    def test_get_tier_limits_pioneer(self):
        """Test Pioneer tier limits."""
        from simbotix_core.doctype.app_license.app_license import get_tier_limits

        limits = get_tier_limits("Pioneer")
        self.assertEqual(limits["storage_gb"], 10)
        self.assertEqual(limits["api_calls"], 50000)
        self.assertEqual(limits["emails"], 1000)

    def test_get_tier_limits_builder(self):
        """Test Builder tier limits."""
        from simbotix_core.doctype.app_license.app_license import get_tier_limits

        limits = get_tier_limits("Builder")
        self.assertEqual(limits["storage_gb"], 30)
        self.assertEqual(limits["api_calls"], 200000)
        self.assertEqual(limits["ai_queries"], 1000)

    def test_get_tier_limits_visionary(self):
        """Test Visionary tier limits (includes unlimited)."""
        from simbotix_core.doctype.app_license.app_license import get_tier_limits

        limits = get_tier_limits("Visionary")
        self.assertEqual(limits["storage_gb"], 75)
        self.assertEqual(limits["executions"], 0)  # 0 = unlimited
        self.assertEqual(limits["webhooks"], 0)  # 0 = unlimited

    def test_get_tier_limits_legend(self):
        """Test Legend tier limits (mostly unlimited)."""
        from simbotix_core.doctype.app_license.app_license import get_tier_limits

        limits = get_tier_limits("Legend")
        self.assertEqual(limits["storage_gb"], 150)
        self.assertEqual(limits["bandwidth_gb"], 0)  # unlimited
        self.assertEqual(limits["api_calls"], 0)  # unlimited
        self.assertEqual(limits["ai_queries"], 20000)  # capped

    def test_get_tier_limits_maps_starter_to_pioneer(self):
        """Test Starter tier maps to Pioneer."""
        from simbotix_core.doctype.app_license.app_license import get_tier_limits

        starter = get_tier_limits("Starter")
        pioneer = get_tier_limits("Pioneer")
        self.assertEqual(starter, pioneer)

    def test_get_tier_limits_maps_growth_to_builder(self):
        """Test Growth tier maps to Builder."""
        from simbotix_core.doctype.app_license.app_license import get_tier_limits

        growth = get_tier_limits("Growth")
        builder = get_tier_limits("Builder")
        self.assertEqual(growth, builder)

    def test_get_tier_limits_unknown_returns_trial(self):
        """Test unknown tier returns Trial limits."""
        from simbotix_core.doctype.app_license.app_license import get_tier_limits

        unknown = get_tier_limits("UnknownTier")
        trial = get_tier_limits("Trial")
        self.assertEqual(unknown, trial)
