"""Tests for Usage Record DocType."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime, add_days, today


class TestUsageRecord(FrappeTestCase):
    """Test suite for Usage Record document."""

    def tearDown(self):
        frappe.db.rollback()

    def _create_usage_record(self, **kwargs):
        """Helper to create test usage record."""
        defaults = {
            "doctype": "Usage Record",
            "resource_type": "api_calls",
            "quantity": 1,
            "timestamp": now_datetime(),
        }
        defaults.update(kwargs)
        doc = frappe.get_doc(defaults)
        doc.insert(ignore_permissions=True)
        return doc

    def test_create_usage_record(self):
        """Test basic usage record creation."""
        record = self._create_usage_record()
        self.assertTrue(record.name)
        self.assertEqual(record.resource_type, "api_calls")
        self.assertEqual(record.quantity, 1)

    def test_create_with_all_fields(self):
        """Test usage record with all optional fields."""
        record = self._create_usage_record(
            resource_type="storage_gb",
            quantity=0.5,
            app_name="flowz",
            doctype_ref="File",
            docname_ref="FILE-001"
        )
        self.assertEqual(record.app_name, "flowz")
        self.assertEqual(record.doctype_ref, "File")
        self.assertEqual(record.docname_ref, "FILE-001")

    def test_create_multiple_resource_types(self):
        """Test creating records for different resource types."""
        resources = [
            "storage_gb", "bandwidth_gb", "database_gb", "api_calls",
            "file_uploads_gb", "executions", "emails", "ai_queries", "webhooks"
        ]

        for resource in resources:
            record = self._create_usage_record(
                resource_type=resource,
                quantity=1
            )
            self.assertEqual(record.resource_type, resource)

    def test_aggregated_flag_default(self):
        """Test aggregated flag defaults to 0."""
        record = self._create_usage_record()
        self.assertEqual(record.aggregated, 0)

    def test_synced_flag_default(self):
        """Test synced flag defaults to 0."""
        record = self._create_usage_record()
        self.assertEqual(record.synced, 0)

    def test_quantity_decimal(self):
        """Test quantity can be decimal for storage/bandwidth."""
        record = self._create_usage_record(
            resource_type="storage_gb",
            quantity=0.005  # 5 MB
        )
        self.assertEqual(record.quantity, 0.005)

    def test_timestamp_auto_set(self):
        """Test timestamp is set correctly."""
        before = now_datetime()
        record = self._create_usage_record()
        after = now_datetime()

        self.assertIsNotNone(record.timestamp)
        self.assertGreaterEqual(record.timestamp, before)
        self.assertLessEqual(record.timestamp, after)
