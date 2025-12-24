"""API client for simbotix.com central services."""

import hashlib
import hmac
import json
import time
import frappe
import requests
from typing import Optional, Dict, Any, List


class CentralAPIClient:
    """
    Client for simbotix.com central API.

    Handles:
    - License validation and sync
    - Usage data upload
    - Retry logic with exponential backoff
    """

    def __init__(self, base_url: Optional[str] = None):
        """
        Initialize API client.

        Args:
            base_url: Override base URL (uses settings if None)
        """
        from simbotix_core.doctype.simbotix_core_settings.simbotix_core_settings import get_settings

        settings = get_settings()
        self.base_url = base_url or settings.central_api_url
        self.api_key = settings.api_key
        self.api_secret = settings.api_secret
        self.timeout = 30  # seconds

    def validate_license(self, license_key: str) -> Dict[str, Any]:
        """
        Validate license key against central system.

        Args:
            license_key: License key to validate

        Returns:
            {valid: bool, license: {...}, message: str}
        """
        endpoint = "/method/simbotix.api.licensing.validate_license"
        data = {"license_key": license_key}

        result = self._make_request("POST", endpoint, data)

        if result.get("success"):
            return {
                "valid": True,
                "license": result.get("license", {}),
                "message": result.get("message", "License is valid")
            }
        else:
            return {
                "valid": False,
                "license": None,
                "message": result.get("message", "License validation failed")
            }

    def get_license_details(self, license_key: str) -> Dict[str, Any]:
        """
        Get full license details including limits and features.

        Args:
            license_key: License key

        Returns:
            {tier, status, expiry, resource_limits, enabled_features, enabled_apps}
        """
        endpoint = "/method/simbotix.api.licensing.get_license_details"
        data = {"license_key": license_key}

        result = self._make_request("POST", endpoint, data)

        if result.get("success"):
            return result.get("license", {})
        else:
            return {}

    def report_usage(self, license_key: str, usage_data: List[Dict]) -> Dict[str, Any]:
        """
        Report aggregated usage data to central.

        Args:
            license_key: Associated license
            usage_data: List of {resource, quantity, period_start, period_end}

        Returns:
            {success: bool, accepted: int, message: str}
        """
        endpoint = "/method/simbotix.api.metering.report_usage"
        data = {
            "license_key": license_key,
            "usage_data": json.dumps(usage_data)
        }

        result = self._make_request("POST", endpoint, data)

        return {
            "success": result.get("success", False),
            "accepted": result.get("accepted", 0),
            "message": result.get("message", "")
        }

    def heartbeat(self, license_key: str, site_info: Dict) -> Dict[str, Any]:
        """
        Send heartbeat to central (hourly).
        Includes site status, version info, active apps.

        Args:
            license_key: License key
            site_info: Site information dict

        Returns:
            {acknowledged: bool, commands: [...]}
        """
        endpoint = "/method/simbotix.api.heartbeat.ping"
        data = {
            "license_key": license_key,
            "site_info": json.dumps(site_info)
        }

        result = self._make_request("POST", endpoint, data)

        return {
            "acknowledged": result.get("acknowledged", False),
            "commands": result.get("commands", [])
        }

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        retry_count: int = 3
    ) -> Dict[str, Any]:
        """
        Internal: Make HTTP request with retry logic.
        Uses HMAC signature for authentication.

        Args:
            method: HTTP method
            endpoint: API endpoint
            data: Request data
            retry_count: Number of retries

        Returns:
            Response data dict
        """
        url = f"{self.base_url.rstrip('/')}{endpoint}"

        headers = {
            "Content-Type": "application/json",
            "X-Api-Key": self.api_key or "",
        }

        # Add HMAC signature if we have a secret
        if self.api_secret and data:
            payload = json.dumps(data, sort_keys=True)
            signature = self._generate_signature(payload)
            headers["X-Api-Signature"] = signature
            headers["X-Api-Timestamp"] = str(int(time.time()))

        last_error = None

        for attempt in range(retry_count):
            try:
                if method.upper() == "GET":
                    response = requests.get(
                        url,
                        params=data,
                        headers=headers,
                        timeout=self.timeout
                    )
                else:
                    response = requests.post(
                        url,
                        json=data,
                        headers=headers,
                        timeout=self.timeout
                    )

                if response.status_code == 200:
                    result = response.json()
                    # Handle Frappe API response format
                    if "message" in result:
                        return result["message"]
                    return result
                elif response.status_code == 401:
                    return {"success": False, "message": "Authentication failed"}
                elif response.status_code == 403:
                    return {"success": False, "message": "Access denied"}
                elif response.status_code == 404:
                    return {"success": False, "message": "Endpoint not found"}
                else:
                    last_error = f"HTTP {response.status_code}: {response.text}"

            except requests.exceptions.Timeout:
                last_error = "Request timed out"
            except requests.exceptions.ConnectionError:
                last_error = "Connection failed"
            except requests.exceptions.RequestException as e:
                last_error = str(e)
            except json.JSONDecodeError:
                last_error = "Invalid JSON response"

            # Exponential backoff
            if attempt < retry_count - 1:
                time.sleep(2 ** attempt)

        # Log final error
        frappe.log_error(
            f"Central API request failed after {retry_count} attempts: {last_error}",
            "Simbotix Central API Error"
        )

        return {"success": False, "message": last_error}

    def _generate_signature(self, payload: str) -> str:
        """
        Internal: Generate HMAC-SHA256 signature.

        Args:
            payload: Request payload as string

        Returns:
            Hex-encoded signature
        """
        if not self.api_secret:
            return ""

        secret = self.api_secret.encode("utf-8")
        message = payload.encode("utf-8")

        signature = hmac.new(secret, message, hashlib.sha256)
        return signature.hexdigest()


def get_api_client() -> CentralAPIClient:
    """
    Get a configured API client instance.

    Returns:
        CentralAPIClient instance
    """
    return CentralAPIClient()
