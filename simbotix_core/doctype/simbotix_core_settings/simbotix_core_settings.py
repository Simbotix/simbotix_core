"""Simbotix Core Settings controller."""

import frappe
from frappe.model.document import Document


class SimbotixCoreSettings(Document):
    """Settings for Simbotix Core licensing and metering."""

    def validate(self):
        """Validate settings before save."""
        if self.warning_threshold and self.hard_limit_threshold:
            if self.warning_threshold >= self.hard_limit_threshold:
                frappe.throw("Warning threshold must be less than hard limit threshold")

        if self.sync_interval_hours:
            if self.sync_interval_hours < 1 or self.sync_interval_hours > 24:
                frappe.throw("Sync interval must be between 1 and 24 hours")

        if self.cache_ttl_seconds:
            if self.cache_ttl_seconds < 60:
                frappe.throw("Cache TTL must be at least 60 seconds")

    def on_update(self):
        """Clear cache when settings change."""
        frappe.cache().delete_key("simbotix_core_settings")
        frappe.cache().delete_key("simbotix_license_cache")


def get_settings():
    """
    Get Simbotix Core Settings with caching.

    Returns:
        frappe._dict: Settings document as dict
    """
    settings = frappe.cache().get_value("simbotix_core_settings")
    if not settings:
        if frappe.db.exists("Simbotix Core Settings"):
            doc = frappe.get_single("Simbotix Core Settings")
            settings = doc.as_dict()
            frappe.cache().set_value("simbotix_core_settings", settings, expires_in_sec=300)
        else:
            # Return defaults if settings don't exist
            settings = frappe._dict({
                "central_api_url": "https://simbotix.com/api",
                "warning_threshold": 80,
                "hard_limit_threshold": 100,
                "block_on_exceeded": 0,
                "use_redis_cache": 1,
                "cache_ttl_seconds": 300,
                "sync_interval_hours": 1,
            })
    return frappe._dict(settings)
