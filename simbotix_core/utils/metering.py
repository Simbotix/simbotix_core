"""Usage metering with batch aggregation."""

import json
import frappe
from typing import Optional, Literal, Dict
from datetime import datetime, timedelta
from frappe.utils import now_datetime, get_datetime, getdate, today, add_days

from simbotix_core.doctype.simbotix_core_settings.simbotix_core_settings import get_settings
from simbotix_core.utils.licensing import get_license, get_resource_limit


ResourceType = Literal[
    "storage_gb", "bandwidth_gb", "database_gb",
    "api_calls", "file_uploads_gb", "executions",
    "emails", "ai_queries", "webhooks"
]

LimitStatus = Literal["ok", "warning", "exceeded"]


def record_usage(
    resource: ResourceType,
    quantity: float,
    app_name: Optional[str] = None,
    doctype: Optional[str] = None,
    docname: Optional[str] = None
) -> None:
    """
    Record resource usage (queued for batch processing).

    Args:
        resource: Type of resource consumed
        quantity: Amount consumed
        app_name: Source app name
        doctype: Associated DocType
        docname: Associated document name

    Usage:
        record_usage("api_calls", 1)
        record_usage("storage_gb", 0.005, app_name="flowz")
        record_usage("emails", 10, doctype="Email Queue", docname="EQ-001")
    """
    if quantity <= 0:
        return

    try:
        # Use background job to avoid blocking the main request
        frappe.enqueue(
            _create_usage_record,
            queue="short",
            resource=resource,
            quantity=quantity,
            app_name=app_name,
            doctype=doctype,
            docname=docname,
            now=frappe.flags.in_test  # Execute immediately in tests
        )
    except Exception as e:
        # Fallback to direct insert if enqueue fails
        frappe.log_error(f"Failed to enqueue usage record: {e}", "Metering Enqueue Error")
        _create_usage_record(resource, quantity, app_name, doctype, docname)


def _create_usage_record(
    resource: str,
    quantity: float,
    app_name: Optional[str] = None,
    doctype: Optional[str] = None,
    docname: Optional[str] = None
) -> None:
    """Internal: Create the actual usage record."""
    try:
        record = frappe.new_doc("Usage Record")
        record.resource_type = resource
        record.quantity = quantity
        record.timestamp = now_datetime()
        record.app_name = app_name
        if doctype:
            record.doctype_ref = doctype
        if docname:
            record.docname_ref = docname
        record.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception as e:
        frappe.log_error(f"Failed to create usage record: {e}", "Metering Record Error")


def get_current_usage(resource: ResourceType) -> float:
    """
    Get current month's aggregated usage for resource.

    Args:
        resource: Resource type

    Returns:
        Current usage value
    """
    # Get start of current month
    today_date = getdate(today())
    month_start = today_date.replace(day=1)

    # Sum all usage records for this month
    result = frappe.db.sql("""
        SELECT COALESCE(SUM(quantity), 0) as total
        FROM `tabUsage Record`
        WHERE resource_type = %s
        AND DATE(timestamp) >= %s
    """, (resource, month_start), as_dict=True)

    return result[0].total if result else 0


def get_all_usage() -> Dict[str, float]:
    """
    Get current month's usage for all resources.

    Returns:
        {resource_type: current_usage, ...}
    """
    today_date = getdate(today())
    month_start = today_date.replace(day=1)

    result = frappe.db.sql("""
        SELECT resource_type, COALESCE(SUM(quantity), 0) as total
        FROM `tabUsage Record`
        WHERE DATE(timestamp) >= %s
        GROUP BY resource_type
    """, (month_start,), as_dict=True)

    usage = {}
    for row in result:
        usage[row.resource_type] = row.total

    # Ensure all resource types have a value
    all_resources = [
        "storage_gb", "bandwidth_gb", "database_gb", "api_calls",
        "file_uploads_gb", "executions", "emails", "ai_queries", "webhooks"
    ]
    for resource in all_resources:
        if resource not in usage:
            usage[resource] = 0

    return usage


def check_limits(resource: ResourceType) -> LimitStatus:
    """
    Check if resource usage is within limits.

    Args:
        resource: Resource type

    Returns:
        "ok" - under warning threshold
        "warning" - between warning and hard limit
        "exceeded" - over hard limit
    """
    settings = get_settings()
    limit = get_resource_limit(resource)

    # 0 = unlimited
    if limit == 0:
        return "ok"

    current = get_current_usage(resource)
    percentage = (current / limit) * 100

    if percentage >= settings.hard_limit_threshold:
        return "exceeded"
    elif percentage >= settings.warning_threshold:
        return "warning"
    else:
        return "ok"


def get_usage_percentage(resource: ResourceType) -> float:
    """
    Get usage as percentage of limit.

    Args:
        resource: Resource type

    Returns:
        Percentage (0-100+), 0 if unlimited
    """
    limit = get_resource_limit(resource)
    if limit == 0:
        return 0

    current = get_current_usage(resource)
    return (current / limit) * 100


def calculate_overage(resource: ResourceType) -> dict:
    """
    Calculate overage amount and cost.

    Args:
        resource: Resource type

    Returns:
        {exceeded_by: float, overage_cost: float, rate: float}
    """
    from simbotix_core.doctype.usage_alert.usage_alert import OVERAGE_RATES

    limit = get_resource_limit(resource)
    if limit == 0:
        return {"exceeded_by": 0, "overage_cost": 0, "rate": 0}

    current = get_current_usage(resource)
    exceeded_by = max(0, current - limit)

    if exceeded_by == 0:
        return {"exceeded_by": 0, "overage_cost": 0, "rate": 0}

    rate_info = OVERAGE_RATES.get(resource, {"rate": 0})
    rate = rate_info.get("rate", 0)
    per = rate_info.get("per", 1)

    if per > 1:
        overage_cost = (exceeded_by / per) * rate
    else:
        overage_cost = exceeded_by * rate

    return {
        "exceeded_by": exceeded_by,
        "overage_cost": round(overage_cost, 2),
        "rate": rate
    }


# ============== SCHEDULER TASKS ==============

def aggregate_usage() -> dict:
    """
    Hourly task: Aggregate individual usage records.
    Groups by resource type and hour.

    Returns:
        {aggregated_count: int, resources: [...]}
    """
    # Get records that haven't been aggregated
    records = frappe.get_all(
        "Usage Record",
        filters={"aggregated": 0},
        fields=["name", "resource_type", "quantity", "timestamp", "app_name"],
        order_by="timestamp asc"
    )

    if not records:
        return {"aggregated_count": 0, "resources": []}

    # Group by resource and hour
    aggregated = {}
    for record in records:
        resource = record.resource_type
        hour = get_datetime(record.timestamp).replace(minute=0, second=0, microsecond=0)
        key = f"{resource}_{hour}"

        if key not in aggregated:
            aggregated[key] = {
                "resource_type": resource,
                "quantity": 0,
                "hour": hour,
                "records": []
            }

        aggregated[key]["quantity"] += record.quantity
        aggregated[key]["records"].append(record.name)

    # Mark records as aggregated
    aggregated_count = 0
    resources = []

    for key, data in aggregated.items():
        try:
            # Update all records in this group
            for record_name in data["records"]:
                frappe.db.set_value(
                    "Usage Record",
                    record_name,
                    {
                        "aggregated": 1,
                        "aggregated_at": now_datetime(),
                        "period_start": data["hour"],
                        "period_end": data["hour"] + timedelta(hours=1)
                    },
                    update_modified=False
                )
                aggregated_count += 1

            resources.append(data["resource_type"])
        except Exception as e:
            frappe.log_error(f"Failed to aggregate usage: {e}", "Metering Aggregation Error")

    frappe.db.commit()

    return {
        "aggregated_count": aggregated_count,
        "resources": list(set(resources))
    }


def sync_usage_to_central() -> dict:
    """
    Hourly task: Sync aggregated usage to simbotix.com.

    Returns:
        {success: bool, synced_count: int, message: str}
    """
    from simbotix_core.utils.central_api import get_api_client

    settings = get_settings()

    if not settings.license_key:
        return {"success": False, "synced_count": 0, "message": "No license key configured"}

    # Get aggregated but not synced records
    records = frappe.get_all(
        "Usage Record",
        filters={"aggregated": 1, "synced": 0},
        fields=["name", "resource_type", "quantity", "period_start", "period_end"],
        order_by="period_start asc",
        limit=1000  # Batch limit
    )

    if not records:
        return {"success": True, "synced_count": 0, "message": "No records to sync"}

    # Prepare usage data for API
    usage_data = []
    for record in records:
        usage_data.append({
            "resource": record.resource_type,
            "quantity": record.quantity,
            "period_start": str(record.period_start) if record.period_start else None,
            "period_end": str(record.period_end) if record.period_end else None
        })

    try:
        client = get_api_client()
        result = client.report_usage(settings.license_key, usage_data)

        if result.get("success"):
            # Mark records as synced
            for record in records:
                frappe.db.set_value(
                    "Usage Record",
                    record.name,
                    {
                        "synced": 1,
                        "synced_at": now_datetime()
                    },
                    update_modified=False
                )

            # Update settings
            try:
                settings_doc = frappe.get_single("Simbotix Core Settings")
                settings_doc.last_usage_sync = now_datetime()
                settings_doc.save(ignore_permissions=True)
            except Exception:
                pass

            frappe.db.commit()

            return {
                "success": True,
                "synced_count": len(records),
                "message": f"Synced {len(records)} usage records"
            }
        else:
            return {
                "success": False,
                "synced_count": 0,
                "message": result.get("message", "Sync failed")
            }

    except Exception as e:
        error_msg = str(e)
        frappe.log_error(f"Usage sync failed: {error_msg}", "Metering Sync Error")
        return {
            "success": False,
            "synced_count": 0,
            "message": error_msg
        }


def check_all_limits() -> dict:
    """
    Hourly task: Check all resource limits and create alerts.

    Returns:
        {alerts_created: int, resources_checked: int}
    """
    from simbotix_core.doctype.usage_alert.usage_alert import create_alert

    settings = get_settings()
    license_doc = get_license()

    if not license_doc:
        return {"alerts_created": 0, "resources_checked": 0}

    limits = license_doc.get("resource_limits", {})
    if isinstance(limits, str):
        try:
            limits = json.loads(limits)
        except (json.JSONDecodeError, TypeError):
            limits = {}

    alerts_created = 0
    resources_checked = 0

    for resource, limit in limits.items():
        resources_checked += 1

        # Skip unlimited resources
        if limit == 0:
            continue

        current = get_current_usage(resource)
        percentage = (current / limit) * 100

        if percentage >= settings.hard_limit_threshold:
            create_alert(resource, "Exceeded", current, limit)
            alerts_created += 1
        elif percentage >= settings.warning_threshold:
            create_alert(resource, "Warning", current, limit)
            alerts_created += 1

    return {
        "alerts_created": alerts_created,
        "resources_checked": resources_checked
    }


def cleanup_old_records() -> dict:
    """
    Daily task: Clean up synced usage records older than 30 days.

    Returns:
        {deleted_count: int}
    """
    cutoff_date = add_days(today(), -30)

    # Delete old synced records
    deleted = frappe.db.delete(
        "Usage Record",
        filters={
            "synced": 1,
            "creation": ["<", cutoff_date]
        }
    )

    frappe.db.commit()

    return {"deleted_count": deleted or 0}
