"""Installation and migration hooks for simbotix_core."""

import frappe


def after_install():
    """Run after app installation."""
    create_default_settings()
    frappe.db.commit()


def after_migrate():
    """Run after migrations."""
    ensure_settings_exist()
    frappe.db.commit()


def create_default_settings():
    """Create default Simbotix Core Settings if not exists."""
    if not frappe.db.exists("Simbotix Core Settings"):
        settings = frappe.new_doc("Simbotix Core Settings")
        settings.central_api_url = "https://simbotix.com/api"
        settings.warning_threshold = 80
        settings.hard_limit_threshold = 100
        settings.block_on_exceeded = 0
        settings.use_redis_cache = 1
        settings.cache_ttl_seconds = 300
        settings.sync_interval_hours = 1
        settings.insert(ignore_permissions=True)
        frappe.msgprint("Simbotix Core Settings created. Please configure API credentials.")


def ensure_settings_exist():
    """Ensure settings document exists after migration."""
    if not frappe.db.exists("Simbotix Core Settings"):
        create_default_settings()
