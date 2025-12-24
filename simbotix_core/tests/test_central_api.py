"""Tests for Central API client."""

import json
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch, MagicMock
import responses


class TestCentralAPIClient(FrappeTestCase):
    """Test suite for CentralAPIClient."""

    def setUp(self):
        super().setUp()
        if not frappe.db.exists("Simbotix Core Settings", "Simbotix Core Settings"):
            frappe.get_doc({
                "doctype": "Simbotix Core Settings",
                "central_api_url": "https://simbotix.com/api",
                "api_key": "test-api-key",
                "api_secret": "test-api-secret",
            }).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.db.rollback()

    def test_client_initialization(self):
        """Test client initializes with settings."""
        from simbotix_core.utils.central_api import CentralAPIClient

        client = CentralAPIClient()

        self.assertEqual(client.base_url, "https://simbotix.com/api")
        self.assertEqual(client.api_key, "test-api-key")
        self.assertEqual(client.api_secret, "test-api-secret")
        self.assertEqual(client.timeout, 30)

    def test_client_custom_base_url(self):
        """Test client accepts custom base URL."""
        from simbotix_core.utils.central_api import CentralAPIClient

        client = CentralAPIClient(base_url="https://custom.example.com")

        self.assertEqual(client.base_url, "https://custom.example.com")

    @responses.activate
    def test_validate_license_success(self):
        """Test validate_license on success."""
        from simbotix_core.utils.central_api import CentralAPIClient

        responses.add(
            responses.POST,
            "https://simbotix.com/api/method/simbotix.api.licensing.validate_license",
            json={
                "message": {
                    "success": True,
                    "license": {"tier": "Builder", "status": "Active"},
                    "message": "License valid"
                }
            },
            status=200
        )

        client = CentralAPIClient()
        result = client.validate_license("test-key")

        self.assertTrue(result["valid"])
        self.assertEqual(result["license"]["tier"], "Builder")

    @responses.activate
    def test_validate_license_failure(self):
        """Test validate_license on failure."""
        from simbotix_core.utils.central_api import CentralAPIClient

        responses.add(
            responses.POST,
            "https://simbotix.com/api/method/simbotix.api.licensing.validate_license",
            json={
                "message": {
                    "success": False,
                    "message": "License not found"
                }
            },
            status=200
        )

        client = CentralAPIClient()
        result = client.validate_license("invalid-key")

        self.assertFalse(result["valid"])
        self.assertIn("not found", result["message"])

    @responses.activate
    def test_get_license_details_success(self):
        """Test get_license_details returns license info."""
        from simbotix_core.utils.central_api import CentralAPIClient

        responses.add(
            responses.POST,
            "https://simbotix.com/api/method/simbotix.api.licensing.get_license_details",
            json={
                "message": {
                    "success": True,
                    "license": {
                        "tier": "Builder",
                        "status": "Active",
                        "resource_limits": {"api_calls": 200000},
                        "enabled_features": ["webhooks"],
                        "enabled_apps": ["flowz"]
                    }
                }
            },
            status=200
        )

        client = CentralAPIClient()
        result = client.get_license_details("test-key")

        self.assertEqual(result["tier"], "Builder")
        self.assertEqual(result["resource_limits"]["api_calls"], 200000)

    @responses.activate
    def test_report_usage_success(self):
        """Test report_usage on success."""
        from simbotix_core.utils.central_api import CentralAPIClient

        responses.add(
            responses.POST,
            "https://simbotix.com/api/method/simbotix.api.metering.report_usage",
            json={
                "message": {
                    "success": True,
                    "accepted": 5,
                    "message": "Usage recorded"
                }
            },
            status=200
        )

        client = CentralAPIClient()
        usage_data = [
            {"resource": "api_calls", "quantity": 100}
        ]
        result = client.report_usage("test-key", usage_data)

        self.assertTrue(result["success"])
        self.assertEqual(result["accepted"], 5)

    @responses.activate
    def test_heartbeat_success(self):
        """Test heartbeat on success."""
        from simbotix_core.utils.central_api import CentralAPIClient

        responses.add(
            responses.POST,
            "https://simbotix.com/api/method/simbotix.api.heartbeat.ping",
            json={
                "message": {
                    "acknowledged": True,
                    "commands": []
                }
            },
            status=200
        )

        client = CentralAPIClient()
        site_info = {"version": "14.0.0"}
        result = client.heartbeat("test-key", site_info)

        self.assertTrue(result["acknowledged"])
        self.assertEqual(result["commands"], [])

    @responses.activate
    def test_request_handles_401(self):
        """Test request handles 401 unauthorized."""
        from simbotix_core.utils.central_api import CentralAPIClient

        responses.add(
            responses.POST,
            "https://simbotix.com/api/method/simbotix.api.licensing.validate_license",
            json={"error": "Unauthorized"},
            status=401
        )

        client = CentralAPIClient()
        result = client.validate_license("test-key")

        self.assertFalse(result["valid"])
        self.assertIn("Authentication failed", result["message"])

    @responses.activate
    def test_request_handles_403(self):
        """Test request handles 403 forbidden."""
        from simbotix_core.utils.central_api import CentralAPIClient

        responses.add(
            responses.POST,
            "https://simbotix.com/api/method/simbotix.api.licensing.validate_license",
            json={"error": "Forbidden"},
            status=403
        )

        client = CentralAPIClient()
        result = client.validate_license("test-key")

        self.assertFalse(result["valid"])
        self.assertIn("Access denied", result["message"])

    @responses.activate
    def test_request_handles_404(self):
        """Test request handles 404 not found."""
        from simbotix_core.utils.central_api import CentralAPIClient

        responses.add(
            responses.POST,
            "https://simbotix.com/api/method/simbotix.api.licensing.validate_license",
            json={"error": "Not found"},
            status=404
        )

        client = CentralAPIClient()
        result = client.validate_license("test-key")

        self.assertFalse(result["valid"])
        self.assertIn("Endpoint not found", result["message"])

    @responses.activate
    def test_request_retries_on_failure(self):
        """Test request retries on server error."""
        from simbotix_core.utils.central_api import CentralAPIClient

        # First two requests fail, third succeeds
        responses.add(
            responses.POST,
            "https://simbotix.com/api/method/simbotix.api.licensing.validate_license",
            json={"error": "Server error"},
            status=500
        )
        responses.add(
            responses.POST,
            "https://simbotix.com/api/method/simbotix.api.licensing.validate_license",
            json={"error": "Server error"},
            status=500
        )
        responses.add(
            responses.POST,
            "https://simbotix.com/api/method/simbotix.api.licensing.validate_license",
            json={
                "message": {
                    "success": True,
                    "license": {"tier": "Builder"},
                }
            },
            status=200
        )

        client = CentralAPIClient()
        result = client.validate_license("test-key")

        self.assertTrue(result["valid"])
        self.assertEqual(len(responses.calls), 3)

    def test_generate_signature(self):
        """Test HMAC signature generation."""
        from simbotix_core.utils.central_api import CentralAPIClient

        client = CentralAPIClient()
        payload = '{"license_key": "test"}'
        signature = client._generate_signature(payload)

        self.assertIsInstance(signature, str)
        self.assertEqual(len(signature), 64)  # SHA256 hex is 64 chars

    def test_generate_signature_empty_secret(self):
        """Test signature generation with no secret."""
        from simbotix_core.utils.central_api import CentralAPIClient

        # Clear the secret
        settings = frappe.get_single("Simbotix Core Settings")
        settings.api_secret = ""
        settings.save(ignore_permissions=True)

        client = CentralAPIClient()
        signature = client._generate_signature("test")

        self.assertEqual(signature, "")


class TestGetAPIClient(FrappeTestCase):
    """Test suite for get_api_client function."""

    def setUp(self):
        super().setUp()
        if not frappe.db.exists("Simbotix Core Settings", "Simbotix Core Settings"):
            frappe.get_doc({
                "doctype": "Simbotix Core Settings",
                "central_api_url": "https://simbotix.com/api",
            }).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.db.rollback()

    def test_get_api_client_returns_instance(self):
        """Test get_api_client returns CentralAPIClient instance."""
        from simbotix_core.utils.central_api import get_api_client, CentralAPIClient

        client = get_api_client()

        self.assertIsInstance(client, CentralAPIClient)
