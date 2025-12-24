"""Whitelisted API endpoints for licensing and metering."""

import frappe
from frappe import _


@frappe.whitelist()
def get_license_info():
    """
    Get current license information.

    Returns:
        dict: License details including tier, status, limits
    """
    from simbotix_core.utils.licensing import get_license

    license_doc = get_license()
    if not license_doc:
        return {
            "success": False,
            "message": "No license configured"
        }

    return {
        "success": True,
        "license": {
            "tier": license_doc.get("tier"),
            "status": license_doc.get("status"),
            "is_valid": license_doc.get("is_valid"),
            "expiry_date": license_doc.get("expiry_date"),
            "enabled_features": license_doc.get("enabled_features"),
            "enabled_apps": license_doc.get("enabled_apps"),
            "resource_limits": license_doc.get("resource_limits")
        }
    }


@frappe.whitelist()
def get_usage_summary():
    """
    Get current usage summary for all resources.

    Returns:
        dict: Usage data with limits and percentages
    """
    from simbotix_core.utils.licensing import get_license
    from simbotix_core.utils.metering import get_all_usage, get_usage_percentage, check_limits

    license_doc = get_license()
    if not license_doc:
        return {
            "success": False,
            "message": "No license configured"
        }

    limits = license_doc.get("resource_limits", {})
    usage = get_all_usage()

    summary = {}
    for resource in usage.keys():
        limit = limits.get(resource, 0)
        current = usage.get(resource, 0)
        percentage = (current / limit * 100) if limit > 0 else 0

        summary[resource] = {
            "current": current,
            "limit": limit,
            "percentage": round(percentage, 1),
            "status": check_limits(resource),
            "unlimited": limit == 0
        }

    return {
        "success": True,
        "tier": license_doc.get("tier"),
        "usage": summary
    }


@frappe.whitelist()
def sync_now():
    """
    Manually trigger license sync from central.

    Returns:
        dict: Sync result
    """
    from simbotix_core.utils.licensing import sync_license

    result = sync_license()
    return result


@frappe.whitelist()
def check_feature(feature):
    """
    Check if a feature is licensed.

    Args:
        feature: Feature code to check

    Returns:
        dict: {licensed: bool, tier: str}
    """
    from simbotix_core.utils.licensing import is_licensed, get_license_tier

    return {
        "licensed": is_licensed(feature=feature),
        "tier": get_license_tier()
    }


@frappe.whitelist()
def check_app(app_name):
    """
    Check if an app is licensed.

    Args:
        app_name: App name to check

    Returns:
        dict: {licensed: bool, tier: str}
    """
    from simbotix_core.utils.licensing import is_licensed, get_license_tier

    return {
        "licensed": is_licensed(app=app_name),
        "tier": get_license_tier()
    }


@frappe.whitelist()
def get_overage_estimate():
    """
    Get estimated overage costs for all resources.

    Returns:
        dict: Overage estimates per resource
    """
    from simbotix_core.utils.metering import calculate_overage, get_all_usage
    from simbotix_core.utils.licensing import get_license

    license_doc = get_license()
    if not license_doc:
        return {
            "success": False,
            "message": "No license configured"
        }

    usage = get_all_usage()
    estimates = {}
    total_overage = 0

    for resource in usage.keys():
        overage = calculate_overage(resource)
        if overage["exceeded_by"] > 0:
            estimates[resource] = overage
            total_overage += overage["overage_cost"]

    return {
        "success": True,
        "tier": license_doc.get("tier"),
        "overages": estimates,
        "total_estimated_cost": round(total_overage, 2)
    }


@frappe.whitelist()
def acknowledge_alert(alert_name):
    """
    Acknowledge a usage alert.

    Args:
        alert_name: Name of the Usage Alert document

    Returns:
        dict: Result
    """
    if not frappe.db.exists("Usage Alert", alert_name):
        return {
            "success": False,
            "message": "Alert not found"
        }

    alert = frappe.get_doc("Usage Alert", alert_name)
    alert.acknowledge()

    return {
        "success": True,
        "message": "Alert acknowledged"
    }


@frappe.whitelist()
def get_pending_alerts():
    """
    Get all unacknowledged alerts.

    Returns:
        list: Pending alerts
    """
    alerts = frappe.get_all(
        "Usage Alert",
        filters={"acknowledged": 0},
        fields=["name", "resource_type", "alert_type", "current_usage", "limit_value", "usage_percent", "creation"],
        order_by="creation desc"
    )

    return {
        "success": True,
        "alerts": alerts,
        "count": len(alerts)
    }
