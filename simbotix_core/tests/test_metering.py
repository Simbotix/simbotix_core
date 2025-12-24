"""Tests for metering utilities."""

import json
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime, add_days, today, getdate
from datetime import timedelta
from unittest.mock import patch, MagicMock


class TestRecordUsage(FrappeTestCase):
    """Test suite for record_usage function."""

    def setUp(self):
        super().setUp()
        if not frappe.db.exists("Simbotix Core Settings", "Simbotix Core Settings"):
            frappe.get_doc({
                "doctype": "Simbotix Core Settings",
            }).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.db.rollback()

    @patch("simbotix_core.utils.metering.frappe.enqueue")
    def test_record_usage_enqueues(self, mock_enqueue):
        """Test record_usage enqueues background job."""
        from simbotix_core.utils.metering import record_usage

        record_usage("api_calls", 1)

        mock_enqueue.assert_called_once()
        call_args = mock_enqueue.call_args
        self.assertEqual(call_args.kwargs["queue"], "short")
        self.assertEqual(call_args.kwargs["resource"], "api_calls")
        self.assertEqual(call_args.kwargs["quantity"], 1)

    def test_record_usage_zero_quantity_ignored(self):
        """Test record_usage ignores zero quantity."""
        from simbotix_core.utils.metering import record_usage

        with patch("simbotix_core.utils.metering.frappe.enqueue") as mock_enqueue:
            record_usage("api_calls", 0)
            mock_enqueue.assert_not_called()

    def test_record_usage_negative_quantity_ignored(self):
        """Test record_usage ignores negative quantity."""
        from simbotix_core.utils.metering import record_usage

        with patch("simbotix_core.utils.metering.frappe.enqueue") as mock_enqueue:
            record_usage("api_calls", -5)
            mock_enqueue.assert_not_called()

    def test_create_usage_record_directly(self):
        """Test _create_usage_record creates record."""
        from simbotix_core.utils.metering import _create_usage_record

        _create_usage_record("api_calls", 1)

        records = frappe.get_all(
            "Usage Record",
            filters={"resource_type": "api_calls"},
            fields=["quantity"]
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].quantity, 1)

    def test_create_usage_record_with_metadata(self):
        """Test _create_usage_record with all metadata."""
        from simbotix_core.utils.metering import _create_usage_record

        _create_usage_record(
            resource="storage_gb",
            quantity=0.5,
            app_name="flowz",
            doctype="File",
            docname="FILE-001"
        )

        record = frappe.get_last_doc("Usage Record")
        self.assertEqual(record.resource_type, "storage_gb")
        self.assertEqual(record.quantity, 0.5)
        self.assertEqual(record.app_name, "flowz")
        self.assertEqual(record.doctype_ref, "File")
        self.assertEqual(record.docname_ref, "FILE-001")


class TestGetCurrentUsage(FrappeTestCase):
    """Test suite for get_current_usage function."""

    def setUp(self):
        super().setUp()
        if not frappe.db.exists("Simbotix Core Settings", "Simbotix Core Settings"):
            frappe.get_doc({
                "doctype": "Simbotix Core Settings",
            }).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.db.rollback()

    def _create_usage_record(self, resource_type, quantity, timestamp=None):
        """Helper to create usage record."""
        doc = frappe.get_doc({
            "doctype": "Usage Record",
            "resource_type": resource_type,
            "quantity": quantity,
            "timestamp": timestamp or now_datetime(),
        })
        doc.insert(ignore_permissions=True)
        return doc

    def test_get_current_usage_empty(self):
        """Test get_current_usage returns 0 for no records."""
        from simbotix_core.utils.metering import get_current_usage

        usage = get_current_usage("api_calls")
        self.assertEqual(usage, 0)

    def test_get_current_usage_single_record(self):
        """Test get_current_usage with single record."""
        from simbotix_core.utils.metering import get_current_usage

        self._create_usage_record("api_calls", 100)

        usage = get_current_usage("api_calls")
        self.assertEqual(usage, 100)

    def test_get_current_usage_multiple_records(self):
        """Test get_current_usage sums multiple records."""
        from simbotix_core.utils.metering import get_current_usage

        self._create_usage_record("api_calls", 100)
        self._create_usage_record("api_calls", 50)
        self._create_usage_record("api_calls", 25)

        usage = get_current_usage("api_calls")
        self.assertEqual(usage, 175)

    def test_get_current_usage_filters_by_resource(self):
        """Test get_current_usage filters by resource type."""
        from simbotix_core.utils.metering import get_current_usage

        self._create_usage_record("api_calls", 100)
        self._create_usage_record("storage_gb", 5)
        self._create_usage_record("emails", 50)

        api_usage = get_current_usage("api_calls")
        storage_usage = get_current_usage("storage_gb")

        self.assertEqual(api_usage, 100)
        self.assertEqual(storage_usage, 5)


class TestGetAllUsage(FrappeTestCase):
    """Test suite for get_all_usage function."""

    def setUp(self):
        super().setUp()
        if not frappe.db.exists("Simbotix Core Settings", "Simbotix Core Settings"):
            frappe.get_doc({
                "doctype": "Simbotix Core Settings",
            }).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.db.rollback()

    def test_get_all_usage_empty(self):
        """Test get_all_usage returns zeros for all resources."""
        from simbotix_core.utils.metering import get_all_usage

        usage = get_all_usage()

        self.assertIn("api_calls", usage)
        self.assertIn("storage_gb", usage)
        self.assertEqual(usage["api_calls"], 0)

    def test_get_all_usage_with_data(self):
        """Test get_all_usage returns correct values."""
        from simbotix_core.utils.metering import get_all_usage

        frappe.get_doc({
            "doctype": "Usage Record",
            "resource_type": "api_calls",
            "quantity": 100,
            "timestamp": now_datetime(),
        }).insert(ignore_permissions=True)

        frappe.get_doc({
            "doctype": "Usage Record",
            "resource_type": "storage_gb",
            "quantity": 5,
            "timestamp": now_datetime(),
        }).insert(ignore_permissions=True)

        usage = get_all_usage()

        self.assertEqual(usage["api_calls"], 100)
        self.assertEqual(usage["storage_gb"], 5)
        self.assertEqual(usage["emails"], 0)


class TestCheckLimits(FrappeTestCase):
    """Test suite for check_limits function."""

    def setUp(self):
        super().setUp()
        if not frappe.db.exists("Simbotix Core Settings", "Simbotix Core Settings"):
            frappe.get_doc({
                "doctype": "Simbotix Core Settings",
                "warning_threshold": 80,
                "hard_limit_threshold": 100,
            }).insert(ignore_permissions=True)

        # Create license with known limits
        self.license = frappe.get_doc({
            "doctype": "App License",
            "license_key": frappe.generate_hash(length=32),
            "tier": "Builder",
            "status": "Active",
            "expiry_date": add_days(today(), 30),
            "resource_limits": json.dumps({
                "api_calls": 1000,
                "storage_gb": 10,
                "bandwidth_gb": 0,  # Unlimited
            }),
        }).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.db.rollback()
        frappe.cache().delete_key("simbotix_license_cache")
        frappe.cache().delete_key("simbotix_license_data")

    def test_check_limits_ok(self):
        """Test check_limits returns 'ok' under threshold."""
        from simbotix_core.utils.metering import check_limits

        # Add 50% usage
        frappe.get_doc({
            "doctype": "Usage Record",
            "resource_type": "api_calls",
            "quantity": 500,
            "timestamp": now_datetime(),
        }).insert(ignore_permissions=True)

        status = check_limits("api_calls")
        self.assertEqual(status, "ok")

    def test_check_limits_warning(self):
        """Test check_limits returns 'warning' at warning threshold."""
        from simbotix_core.utils.metering import check_limits

        # Add 85% usage
        frappe.get_doc({
            "doctype": "Usage Record",
            "resource_type": "api_calls",
            "quantity": 850,
            "timestamp": now_datetime(),
        }).insert(ignore_permissions=True)

        status = check_limits("api_calls")
        self.assertEqual(status, "warning")

    def test_check_limits_exceeded(self):
        """Test check_limits returns 'exceeded' over hard limit."""
        from simbotix_core.utils.metering import check_limits

        # Add 105% usage
        frappe.get_doc({
            "doctype": "Usage Record",
            "resource_type": "api_calls",
            "quantity": 1050,
            "timestamp": now_datetime(),
        }).insert(ignore_permissions=True)

        status = check_limits("api_calls")
        self.assertEqual(status, "exceeded")

    def test_check_limits_unlimited(self):
        """Test check_limits returns 'ok' for unlimited resources."""
        from simbotix_core.utils.metering import check_limits

        # Add huge usage for unlimited resource
        frappe.get_doc({
            "doctype": "Usage Record",
            "resource_type": "bandwidth_gb",
            "quantity": 999999,
            "timestamp": now_datetime(),
        }).insert(ignore_permissions=True)

        status = check_limits("bandwidth_gb")
        self.assertEqual(status, "ok")


class TestCalculateOverage(FrappeTestCase):
    """Test suite for calculate_overage function."""

    def setUp(self):
        super().setUp()
        if not frappe.db.exists("Simbotix Core Settings", "Simbotix Core Settings"):
            frappe.get_doc({
                "doctype": "Simbotix Core Settings",
            }).insert(ignore_permissions=True)

        self.license = frappe.get_doc({
            "doctype": "App License",
            "license_key": frappe.generate_hash(length=32),
            "tier": "Builder",
            "status": "Active",
            "expiry_date": add_days(today(), 30),
            "resource_limits": json.dumps({
                "api_calls": 1000,
                "storage_gb": 10,
                "emails": 500,
            }),
        }).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.db.rollback()
        frappe.cache().delete_key("simbotix_license_cache")
        frappe.cache().delete_key("simbotix_license_data")

    def test_calculate_overage_no_overage(self):
        """Test calculate_overage with no overage."""
        from simbotix_core.utils.metering import calculate_overage

        frappe.get_doc({
            "doctype": "Usage Record",
            "resource_type": "api_calls",
            "quantity": 500,
            "timestamp": now_datetime(),
        }).insert(ignore_permissions=True)

        result = calculate_overage("api_calls")

        self.assertEqual(result["exceeded_by"], 0)
        self.assertEqual(result["overage_cost"], 0)

    def test_calculate_overage_with_overage(self):
        """Test calculate_overage with overage."""
        from simbotix_core.utils.metering import calculate_overage

        # Add 15000 API calls (1000 limit, 14000 over)
        frappe.get_doc({
            "doctype": "Usage Record",
            "resource_type": "api_calls",
            "quantity": 15000,
            "timestamp": now_datetime(),
        }).insert(ignore_permissions=True)

        result = calculate_overage("api_calls")

        self.assertEqual(result["exceeded_by"], 14000)
        # 14000 over at $0.50 per 10K = $0.70
        self.assertEqual(result["overage_cost"], 0.7)

    def test_calculate_overage_storage(self):
        """Test calculate_overage for storage."""
        from simbotix_core.utils.metering import calculate_overage

        frappe.get_doc({
            "doctype": "Usage Record",
            "resource_type": "storage_gb",
            "quantity": 15,  # 5 GB over
            "timestamp": now_datetime(),
        }).insert(ignore_permissions=True)

        result = calculate_overage("storage_gb")

        self.assertEqual(result["exceeded_by"], 5)
        # 5 GB at $1.50/GB = $7.50
        self.assertEqual(result["overage_cost"], 7.5)


class TestAggregateUsage(FrappeTestCase):
    """Test suite for aggregate_usage scheduler task."""

    def setUp(self):
        super().setUp()
        if not frappe.db.exists("Simbotix Core Settings", "Simbotix Core Settings"):
            frappe.get_doc({
                "doctype": "Simbotix Core Settings",
            }).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.db.rollback()

    def test_aggregate_usage_empty(self):
        """Test aggregate_usage with no records."""
        from simbotix_core.utils.metering import aggregate_usage

        result = aggregate_usage()

        self.assertEqual(result["aggregated_count"], 0)
        self.assertEqual(result["resources"], [])

    def test_aggregate_usage_marks_records(self):
        """Test aggregate_usage marks records as aggregated."""
        from simbotix_core.utils.metering import aggregate_usage

        record = frappe.get_doc({
            "doctype": "Usage Record",
            "resource_type": "api_calls",
            "quantity": 1,
            "timestamp": now_datetime(),
            "aggregated": 0,
        }).insert(ignore_permissions=True)

        result = aggregate_usage()

        self.assertEqual(result["aggregated_count"], 1)

        # Check record is marked
        record.reload()
        self.assertEqual(record.aggregated, 1)
        self.assertIsNotNone(record.aggregated_at)


class TestSyncUsageToCentral(FrappeTestCase):
    """Test suite for sync_usage_to_central scheduler task."""

    def setUp(self):
        super().setUp()
        if not frappe.db.exists("Simbotix Core Settings", "Simbotix Core Settings"):
            frappe.get_doc({
                "doctype": "Simbotix Core Settings",
                "license_key": "test-key",
                "central_api_url": "https://simbotix.com/api",
            }).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.db.rollback()

    def test_sync_usage_no_license_key(self):
        """Test sync fails without license key."""
        from simbotix_core.utils.metering import sync_usage_to_central

        settings = frappe.get_single("Simbotix Core Settings")
        settings.license_key = ""
        settings.save(ignore_permissions=True)

        result = sync_usage_to_central()

        self.assertFalse(result["success"])
        self.assertIn("No license key", result["message"])

    def test_sync_usage_no_records(self):
        """Test sync with no records to sync."""
        from simbotix_core.utils.metering import sync_usage_to_central

        result = sync_usage_to_central()

        self.assertTrue(result["success"])
        self.assertEqual(result["synced_count"], 0)

    @patch("simbotix_core.utils.metering.get_api_client")
    def test_sync_usage_success(self, mock_get_client):
        """Test successful usage sync."""
        from simbotix_core.utils.metering import sync_usage_to_central

        # Create aggregated but not synced record
        frappe.get_doc({
            "doctype": "Usage Record",
            "resource_type": "api_calls",
            "quantity": 100,
            "timestamp": now_datetime(),
            "aggregated": 1,
            "synced": 0,
        }).insert(ignore_permissions=True)

        mock_client = MagicMock()
        mock_client.report_usage.return_value = {"success": True}
        mock_get_client.return_value = mock_client

        result = sync_usage_to_central()

        self.assertTrue(result["success"])
        self.assertEqual(result["synced_count"], 1)

    @patch("simbotix_core.utils.metering.get_api_client")
    def test_sync_usage_marks_synced(self, mock_get_client):
        """Test sync marks records as synced."""
        from simbotix_core.utils.metering import sync_usage_to_central

        record = frappe.get_doc({
            "doctype": "Usage Record",
            "resource_type": "api_calls",
            "quantity": 100,
            "timestamp": now_datetime(),
            "aggregated": 1,
            "synced": 0,
        }).insert(ignore_permissions=True)

        mock_client = MagicMock()
        mock_client.report_usage.return_value = {"success": True}
        mock_get_client.return_value = mock_client

        sync_usage_to_central()

        record.reload()
        self.assertEqual(record.synced, 1)
        self.assertIsNotNone(record.synced_at)


class TestCheckAllLimits(FrappeTestCase):
    """Test suite for check_all_limits scheduler task."""

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
            "tier": "Builder",
            "status": "Active",
            "expiry_date": add_days(today(), 30),
            "resource_limits": json.dumps({
                "api_calls": 1000,
                "storage_gb": 10,
            }),
        }).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.db.rollback()
        frappe.cache().delete_key("simbotix_license_cache")
        frappe.cache().delete_key("simbotix_license_data")

    def test_check_all_limits_no_alerts(self):
        """Test check_all_limits with usage under threshold."""
        from simbotix_core.utils.metering import check_all_limits

        # Add 50% usage
        frappe.get_doc({
            "doctype": "Usage Record",
            "resource_type": "api_calls",
            "quantity": 500,
            "timestamp": now_datetime(),
        }).insert(ignore_permissions=True)

        result = check_all_limits()

        self.assertEqual(result["alerts_created"], 0)
        self.assertGreater(result["resources_checked"], 0)

    def test_check_all_limits_creates_warning(self):
        """Test check_all_limits creates warning alert."""
        from simbotix_core.utils.metering import check_all_limits

        # Add 85% usage
        frappe.get_doc({
            "doctype": "Usage Record",
            "resource_type": "api_calls",
            "quantity": 850,
            "timestamp": now_datetime(),
        }).insert(ignore_permissions=True)

        result = check_all_limits()

        self.assertGreater(result["alerts_created"], 0)

        # Check alert was created
        alerts = frappe.get_all(
            "Usage Alert",
            filters={"resource_type": "api_calls", "alert_type": "Warning"}
        )
        self.assertEqual(len(alerts), 1)

    def test_check_all_limits_creates_exceeded(self):
        """Test check_all_limits creates exceeded alert."""
        from simbotix_core.utils.metering import check_all_limits

        # Add 105% usage
        frappe.get_doc({
            "doctype": "Usage Record",
            "resource_type": "api_calls",
            "quantity": 1050,
            "timestamp": now_datetime(),
        }).insert(ignore_permissions=True)

        result = check_all_limits()

        # Check exceeded alert was created
        alerts = frappe.get_all(
            "Usage Alert",
            filters={"resource_type": "api_calls", "alert_type": "Exceeded"}
        )
        self.assertEqual(len(alerts), 1)


class TestCleanupOldRecords(FrappeTestCase):
    """Test suite for cleanup_old_records scheduler task."""

    def setUp(self):
        super().setUp()
        if not frappe.db.exists("Simbotix Core Settings", "Simbotix Core Settings"):
            frappe.get_doc({
                "doctype": "Simbotix Core Settings",
            }).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.db.rollback()

    def test_cleanup_deletes_old_synced(self):
        """Test cleanup deletes old synced records."""
        from simbotix_core.utils.metering import cleanup_old_records

        # Create old synced record (manually set creation)
        old_record = frappe.get_doc({
            "doctype": "Usage Record",
            "resource_type": "api_calls",
            "quantity": 100,
            "timestamp": now_datetime(),
            "synced": 1,
        }).insert(ignore_permissions=True)

        # Update creation date to 35 days ago
        frappe.db.set_value(
            "Usage Record", old_record.name,
            "creation", add_days(today(), -35)
        )

        result = cleanup_old_records()

        # Record should be deleted
        self.assertFalse(frappe.db.exists("Usage Record", old_record.name))

    def test_cleanup_keeps_recent(self):
        """Test cleanup keeps recent records."""
        from simbotix_core.utils.metering import cleanup_old_records

        # Create recent synced record
        recent_record = frappe.get_doc({
            "doctype": "Usage Record",
            "resource_type": "api_calls",
            "quantity": 100,
            "timestamp": now_datetime(),
            "synced": 1,
        }).insert(ignore_permissions=True)

        result = cleanup_old_records()

        # Record should still exist
        self.assertTrue(frappe.db.exists("Usage Record", recent_record.name))

    def test_cleanup_keeps_unsynced(self):
        """Test cleanup keeps unsynced records."""
        from simbotix_core.utils.metering import cleanup_old_records

        # Create old but unsynced record
        old_record = frappe.get_doc({
            "doctype": "Usage Record",
            "resource_type": "api_calls",
            "quantity": 100,
            "timestamp": now_datetime(),
            "synced": 0,
        }).insert(ignore_permissions=True)

        # Update creation date to 35 days ago
        frappe.db.set_value(
            "Usage Record", old_record.name,
            "creation", add_days(today(), -35)
        )

        result = cleanup_old_records()

        # Record should still exist (unsynced)
        self.assertTrue(frappe.db.exists("Usage Record", old_record.name))
