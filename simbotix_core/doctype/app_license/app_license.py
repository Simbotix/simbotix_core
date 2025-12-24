"""App License controller - Local cache of license from central simbotix.com."""

import json
import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime, getdate, today


class AppLicense(Document):
    """License document cached from central simbotix.com."""

    def validate(self):
        """Validate license data."""
        # Parse and validate resource_limits JSON
        if self.resource_limits:
            try:
                limits = json.loads(self.resource_limits) if isinstance(self.resource_limits, str) else self.resource_limits
                # Ensure all expected keys exist
                expected_keys = [
                    "storage_gb", "bandwidth_gb", "database_gb", "api_calls",
                    "file_uploads_gb", "executions", "emails", "ai_queries", "webhooks"
                ]
                for key in expected_keys:
                    if key not in limits:
                        limits[key] = 0
                self.resource_limits = json.dumps(limits)
            except (json.JSONDecodeError, TypeError) as e:
                frappe.throw(f"Invalid resource_limits JSON: {e}")

        # Parse and validate enabled_features JSON
        if self.enabled_features:
            try:
                features = json.loads(self.enabled_features) if isinstance(self.enabled_features, str) else self.enabled_features
                if not isinstance(features, list):
                    frappe.throw("enabled_features must be a JSON array")
            except (json.JSONDecodeError, TypeError) as e:
                frappe.throw(f"Invalid enabled_features JSON: {e}")

        # Parse and validate enabled_apps JSON
        if self.enabled_apps:
            try:
                apps = json.loads(self.enabled_apps) if isinstance(self.enabled_apps, str) else self.enabled_apps
                if not isinstance(apps, list):
                    frappe.throw("enabled_apps must be a JSON array")
            except (json.JSONDecodeError, TypeError) as e:
                frappe.throw(f"Invalid enabled_apps JSON: {e}")

    def on_update(self):
        """Clear license cache when updated."""
        frappe.cache().delete_key("simbotix_license_cache")

    def is_valid(self):
        """Check if license is currently valid."""
        if self.status not in ["Active", "Trial"]:
            return False

        if self.expiry_date and getdate(self.expiry_date) < getdate(today()):
            return False

        return True

    def get_resource_limit(self, resource):
        """
        Get limit for a specific resource.

        Args:
            resource: Resource type (storage_gb, api_calls, etc.)

        Returns:
            float: Limit value (0 = unlimited for this tier)
        """
        if not self.resource_limits:
            return 0

        try:
            limits = json.loads(self.resource_limits) if isinstance(self.resource_limits, str) else self.resource_limits
            return limits.get(resource, 0)
        except (json.JSONDecodeError, TypeError):
            return 0

    def has_feature(self, feature):
        """
        Check if a feature is enabled.

        Args:
            feature: Feature code

        Returns:
            bool: True if feature is enabled
        """
        if not self.enabled_features:
            return False

        try:
            features = json.loads(self.enabled_features) if isinstance(self.enabled_features, str) else self.enabled_features
            return feature in features
        except (json.JSONDecodeError, TypeError):
            return False

    def has_app(self, app_name):
        """
        Check if an app is enabled.

        Args:
            app_name: App name

        Returns:
            bool: True if app is enabled
        """
        if not self.enabled_apps:
            return False

        try:
            apps = json.loads(self.enabled_apps) if isinstance(self.enabled_apps, str) else self.enabled_apps
            return app_name in apps
        except (json.JSONDecodeError, TypeError):
            return False


def get_active_license():
    """
    Get the currently active license.

    Returns:
        AppLicense: Active license document or None
    """
    # Check cache first
    cached = frappe.cache().get_value("simbotix_license_cache")
    if cached:
        return frappe.get_doc("App License", cached)

    # Find active license
    licenses = frappe.get_all(
        "App License",
        filters={"status": ["in", ["Active", "Trial"]]},
        order_by="modified desc",
        limit=1
    )

    if licenses:
        license_key = licenses[0].name
        frappe.cache().set_value("simbotix_license_cache", license_key, expires_in_sec=300)
        return frappe.get_doc("App License", license_key)

    return None


def get_tier_limits(tier):
    """
    Get default resource limits for a tier.

    Args:
        tier: Tier name (Pioneer, Builder, etc.)

    Returns:
        dict: Resource limits for the tier
    """
    tier_limits = {
        "Trial": {
            "storage_gb": 1,
            "bandwidth_gb": 10,
            "database_gb": 0.5,
            "api_calls": 5000,
            "file_uploads_gb": 1,
            "executions": 1000,
            "emails": 100,
            "ai_queries": 0,
            "webhooks": 2
        },
        "Pioneer": {
            "storage_gb": 10,
            "bandwidth_gb": 100,
            "database_gb": 2,
            "api_calls": 50000,
            "file_uploads_gb": 5,
            "executions": 10000,
            "emails": 1000,
            "ai_queries": 0,
            "webhooks": 5
        },
        "Builder": {
            "storage_gb": 30,
            "bandwidth_gb": 300,
            "database_gb": 5,
            "api_calls": 200000,
            "file_uploads_gb": 15,
            "executions": 50000,
            "emails": 5000,
            "ai_queries": 1000,
            "webhooks": 20
        },
        "Visionary": {
            "storage_gb": 75,
            "bandwidth_gb": 750,
            "database_gb": 15,
            "api_calls": 1000000,
            "file_uploads_gb": 50,
            "executions": 0,  # 0 = unlimited
            "emails": 20000,
            "ai_queries": 5000,
            "webhooks": 0  # 0 = unlimited
        },
        "Legend": {
            "storage_gb": 150,
            "bandwidth_gb": 0,  # 0 = unlimited
            "database_gb": 50,
            "api_calls": 0,  # 0 = unlimited
            "file_uploads_gb": 0,  # 0 = unlimited
            "executions": 0,  # 0 = unlimited
            "emails": 0,  # 0 = unlimited
            "ai_queries": 20000,
            "webhooks": 0  # 0 = unlimited
        },
        # Regular tiers match Founding tiers
        "Starter": None,  # Same as Pioneer
        "Growth": None,   # Same as Builder
        "Scale": None,    # Same as Visionary
        "Enterprise": None  # Same as Legend
    }

    # Map regular tiers to founding equivalents
    tier_mapping = {
        "Starter": "Pioneer",
        "Growth": "Builder",
        "Scale": "Visionary",
        "Enterprise": "Legend"
    }

    if tier in tier_mapping:
        tier = tier_mapping[tier]

    return tier_limits.get(tier, tier_limits["Trial"])
