"""License validation utilities with gatekeeper pattern."""

import json
import frappe
from functools import wraps
from typing import Optional, Callable, Any, List

from simbotix_core.doctype.simbotix_core_settings.simbotix_core_settings import get_settings
from simbotix_core.doctype.app_license.app_license import get_active_license


# ============== DECORATORS ==============

def requires_license(feature: Optional[str] = None, app: Optional[str] = None):
    """
    Decorator to enforce license requirements.

    Usage:
        @requires_license(feature="webhooks")
        def create_webhook(doc, method):
            ...

        @requires_license(app="flowz")
        def run_workflow(workflow_id):
            ...

    Args:
        feature: Required feature code (e.g., "webhooks", "ai_agents")
        app: Required app name (e.g., "flowz", "botz_studio")

    Raises:
        frappe.PermissionError: If license invalid or feature not enabled
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            _validate_license_requirement(feature=feature, app=app)
            return func(*args, **kwargs)
        return wrapper
    return decorator


def requires_quota(resource: str, quantity: float = 1):
    """
    Decorator to check quota before action and record usage after.

    Usage:
        @requires_quota(resource="api_calls")
        def api_endpoint():
            ...

        @requires_quota(resource="emails", quantity=5)
        def send_bulk_email(recipients):
            ...

    Args:
        resource: Resource type (storage_gb, api_calls, etc.)
        quantity: Amount to consume

    Raises:
        frappe.ValidationError: If quota exceeded and blocking enabled
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            from simbotix_core.utils.metering import check_limits, record_usage

            status = check_limits(resource)
            if status == "exceeded":
                settings = get_settings()
                if settings.block_on_exceeded:
                    raise frappe.ValidationError(
                        f"Quota exceeded for {resource}. Please upgrade your plan or contact support."
                    )

            result = func(*args, **kwargs)

            # Record usage after successful execution
            record_usage(resource, quantity)

            return result
        return wrapper
    return decorator


# ============== FUNCTIONS ==============

def is_licensed(feature: Optional[str] = None, app: Optional[str] = None) -> bool:
    """
    Check if feature or app is licensed.

    Args:
        feature: Feature code to check
        app: App name to check

    Returns:
        True if licensed, False otherwise
    """
    license_doc = get_license()
    if not license_doc:
        return False

    if not license_doc.get("is_valid"):
        return False

    if feature:
        enabled_features = license_doc.get("enabled_features", [])
        if isinstance(enabled_features, str):
            try:
                enabled_features = json.loads(enabled_features)
            except (json.JSONDecodeError, TypeError):
                enabled_features = []
        if feature not in enabled_features:
            return False

    if app:
        enabled_apps = license_doc.get("enabled_apps", [])
        if isinstance(enabled_apps, str):
            try:
                enabled_apps = json.loads(enabled_apps)
            except (json.JSONDecodeError, TypeError):
                enabled_apps = []
        if app not in enabled_apps:
            return False

    return True


def get_license() -> Optional[frappe._dict]:
    """
    Get current active license with caching.

    Returns:
        License dict with tier, status, limits, features
        None if no valid license
    """
    # Check Redis cache first
    cached = _get_cached_license()
    if cached:
        return cached

    # Get from database
    license_doc = get_active_license()
    if not license_doc:
        return None

    # Build license dict
    license_data = frappe._dict({
        "license_key": license_doc.license_key,
        "customer_id": license_doc.customer_id,
        "customer_name": license_doc.customer_name,
        "tier": license_doc.tier,
        "status": license_doc.status,
        "expiry_date": license_doc.expiry_date,
        "is_valid": license_doc.is_valid(),
        "resource_limits": _parse_json(license_doc.resource_limits, {}),
        "enabled_features": _parse_json(license_doc.enabled_features, []),
        "enabled_apps": _parse_json(license_doc.enabled_apps, []),
    })

    # Cache the license
    _set_cached_license(license_data)

    return license_data


def get_license_tier() -> Optional[str]:
    """
    Get current license tier name.

    Returns:
        Tier name (Pioneer, Builder, etc.) or None
    """
    license_doc = get_license()
    if not license_doc:
        return None
    return license_doc.get("tier")


def get_resource_limit(resource: str) -> float:
    """
    Get limit for specific resource.

    Args:
        resource: Resource type

    Returns:
        Limit value (0 = unlimited)
    """
    license_doc = get_license()
    if not license_doc:
        return 0

    limits = license_doc.get("resource_limits", {})
    return limits.get(resource, 0)


def get_enabled_features() -> List[str]:
    """
    Get list of enabled feature codes.

    Returns:
        List of feature codes
    """
    license_doc = get_license()
    if not license_doc:
        return []

    features = license_doc.get("enabled_features", [])
    if isinstance(features, str):
        features = _parse_json(features, [])
    return features


def get_enabled_apps() -> List[str]:
    """
    Get list of enabled app names.

    Returns:
        List of app names
    """
    license_doc = get_license()
    if not license_doc:
        return []

    apps = license_doc.get("enabled_apps", [])
    if isinstance(apps, str):
        apps = _parse_json(apps, [])
    return apps


def sync_license() -> dict:
    """
    Sync license from central simbotix.com API.
    Called by scheduler and manually.

    Returns:
        {success: bool, message: str, license: dict}
    """
    from simbotix_core.utils.central_api import get_api_client
    from frappe.utils import now_datetime

    settings = get_settings()

    if not settings.license_key:
        return {
            "success": False,
            "message": "No license key configured",
            "license": None
        }

    try:
        client = get_api_client()
        result = client.get_license_details(settings.license_key)

        if not result:
            _update_settings_sync_status("Failed", "No response from central API")
            return {
                "success": False,
                "message": "No response from central API",
                "license": None
            }

        # Update or create local license cache
        if frappe.db.exists("App License", settings.license_key):
            license_doc = frappe.get_doc("App License", settings.license_key)
        else:
            license_doc = frappe.new_doc("App License")
            license_doc.license_key = settings.license_key

        # Update fields from central
        license_doc.customer_id = result.get("customer_id", "")
        license_doc.customer_name = result.get("customer_name", "")
        license_doc.tier = result.get("tier", "Trial")
        license_doc.status = result.get("status", "Trial")
        license_doc.expiry_date = result.get("expiry_date")
        license_doc.resource_limits = json.dumps(result.get("resource_limits", {}))
        license_doc.enabled_features = json.dumps(result.get("enabled_features", []))
        license_doc.enabled_apps = json.dumps(result.get("enabled_apps", []))
        license_doc.last_synced = now_datetime()
        license_doc.sync_status = "Synced"
        license_doc.sync_error = ""

        license_doc.save(ignore_permissions=True)
        frappe.db.commit()

        # Clear cache
        frappe.cache().delete_key("simbotix_license_cache")

        # Update settings sync status
        _update_settings_sync_status("Synced", "")

        return {
            "success": True,
            "message": "License synced successfully",
            "license": license_doc.as_dict()
        }

    except Exception as e:
        error_msg = str(e)
        frappe.log_error(f"License sync failed: {error_msg}", "Simbotix License Sync Error")
        _update_settings_sync_status("Failed", error_msg)

        return {
            "success": False,
            "message": error_msg,
            "license": None
        }


# ============== INTERNAL FUNCTIONS ==============

def _validate_license_requirement(
    feature: Optional[str] = None,
    app: Optional[str] = None
) -> None:
    """
    Internal: Validate license and raise if invalid.

    Raises:
        frappe.PermissionError: If validation fails
    """
    license_doc = get_license()

    if not license_doc:
        raise frappe.PermissionError(
            "No valid license found. Please configure a license in Simbotix Core Settings."
        )

    if not license_doc.get("is_valid"):
        status = license_doc.get("status", "Unknown")
        raise frappe.PermissionError(
            f"License is not active. Current status: {status}"
        )

    if feature:
        enabled_features = license_doc.get("enabled_features", [])
        if isinstance(enabled_features, str):
            enabled_features = _parse_json(enabled_features, [])
        if feature not in enabled_features:
            tier = license_doc.get("tier", "Unknown")
            raise frappe.PermissionError(
                f"Feature '{feature}' is not included in your {tier} plan. Please upgrade to access this feature."
            )

    if app:
        enabled_apps = license_doc.get("enabled_apps", [])
        if isinstance(enabled_apps, str):
            enabled_apps = _parse_json(enabled_apps, [])
        if app not in enabled_apps:
            tier = license_doc.get("tier", "Unknown")
            raise frappe.PermissionError(
                f"App '{app}' is not included in your {tier} plan. Please upgrade to access this app."
            )


def _get_cached_license() -> Optional[dict]:
    """Internal: Get license from Redis cache."""
    settings = get_settings()
    if not settings.use_redis_cache:
        return None

    cached = frappe.cache().get_value("simbotix_license_data")
    if cached:
        return frappe._dict(cached)
    return None


def _set_cached_license(license_data: dict) -> None:
    """Internal: Cache license in Redis."""
    settings = get_settings()
    if not settings.use_redis_cache:
        return

    ttl = settings.cache_ttl_seconds or 300
    frappe.cache().set_value(
        "simbotix_license_data",
        dict(license_data),
        expires_in_sec=ttl
    )


def _parse_json(value: Any, default: Any) -> Any:
    """Internal: Parse JSON string or return default."""
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def _update_settings_sync_status(status: str, error: str) -> None:
    """Internal: Update settings sync status."""
    from frappe.utils import now_datetime

    try:
        settings = frappe.get_single("Simbotix Core Settings")
        settings.sync_status = status
        settings.last_license_sync = now_datetime()
        settings.last_sync_error = error
        settings.save(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        pass  # Don't fail if settings update fails
