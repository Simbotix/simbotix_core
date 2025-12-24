"""Usage Alert controller - Threshold notifications."""

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


# Overage rates from COMPLETE-PRICING-GUIDE.md
OVERAGE_RATES = {
    "storage_gb": {"rate": 1.50, "unit": "GB/mo"},
    "bandwidth_gb": {"rate": 0.08, "unit": "GB"},
    "database_gb": {"rate": 3.00, "unit": "GB/mo"},
    "api_calls": {"rate": 0.50, "per": 10000, "unit": "10K calls"},
    "file_uploads_gb": {"rate": 1.50, "unit": "GB/mo"},
    "executions": {"rate": 2.00, "per": 10000, "unit": "10K executions"},
    "emails": {"rate": 1.00, "per": 1000, "unit": "1K emails"},
    "ai_queries": {"rate": 0.015, "unit": "query"},
    "webhooks": {"rate": 0, "unit": "N/A"},  # No overage for webhooks
}


class UsageAlert(Document):
    """Alert triggered when usage thresholds are reached."""

    def validate(self):
        """Calculate usage percentage and overage."""
        if self.current_usage and self.limit_value and self.limit_value > 0:
            self.usage_percent = (self.current_usage / self.limit_value) * 100

        # Calculate overage if exceeded
        if self.alert_type in ["Exceeded", "Blocked"] and self.current_usage and self.limit_value:
            overage = self.current_usage - self.limit_value
            if overage > 0:
                self.overage_amount = self.calculate_overage_cost(self.resource_type, overage)
                rate_info = OVERAGE_RATES.get(self.resource_type, {})
                self.overage_rate = f"${rate_info.get('rate', 0)}/{rate_info.get('unit', 'unit')}"

    def calculate_overage_cost(self, resource_type, overage_quantity):
        """
        Calculate overage cost for a resource.

        Args:
            resource_type: Type of resource
            overage_quantity: Amount over the limit

        Returns:
            float: Overage cost in USD
        """
        rate_info = OVERAGE_RATES.get(resource_type, {"rate": 0})
        rate = rate_info.get("rate", 0)
        per = rate_info.get("per", 1)

        if per > 1:
            # Rate is per X units (e.g., $0.50 per 10K API calls)
            return (overage_quantity / per) * rate
        else:
            # Rate is per unit
            return overage_quantity * rate

    def acknowledge(self, user=None):
        """
        Mark alert as acknowledged.

        Args:
            user: User acknowledging (defaults to session user)
        """
        self.acknowledged = 1
        self.acknowledged_by = user or frappe.session.user
        self.acknowledged_at = now_datetime()
        self.save(ignore_permissions=True)

    def send_notification(self):
        """Send email notification for this alert."""
        from simbotix_core.doctype.simbotix_core_settings.simbotix_core_settings import get_settings

        settings = get_settings()

        if not settings.send_alert_emails:
            return

        if not settings.alert_email:
            return

        if self.notification_sent:
            return

        subject = f"[Simbotix] Usage {self.alert_type}: {self.resource_type}"
        message = f"""
        <h3>Usage Alert: {self.alert_type}</h3>
        <p><strong>Resource:</strong> {self.resource_type}</p>
        <p><strong>Current Usage:</strong> {self.current_usage}</p>
        <p><strong>Limit:</strong> {self.limit_value}</p>
        <p><strong>Usage:</strong> {self.usage_percent:.1f}%</p>
        """

        if self.overage_amount:
            message += f"<p><strong>Estimated Overage:</strong> ${self.overage_amount:.2f}</p>"

        try:
            frappe.sendmail(
                recipients=[settings.alert_email],
                subject=subject,
                message=message,
                now=True
            )
            self.notification_sent = 1
            self.email_sent_to = settings.alert_email
            self.save(ignore_permissions=True)
        except Exception as e:
            frappe.log_error(f"Failed to send usage alert email: {e}", "Usage Alert Email Error")


def create_alert(resource_type, alert_type, current_usage, limit_value, send_email=True):
    """
    Create a usage alert.

    Args:
        resource_type: Type of resource
        alert_type: Warning, Exceeded, or Blocked
        current_usage: Current usage value
        limit_value: Limit value
        send_email: Whether to send notification email

    Returns:
        UsageAlert: Created alert document
    """
    from simbotix_core.doctype.simbotix_core_settings.simbotix_core_settings import get_settings

    settings = get_settings()

    # Determine threshold based on alert type
    if alert_type == "Warning":
        threshold = settings.warning_threshold
    else:
        threshold = settings.hard_limit_threshold

    # Check if similar unacknowledged alert exists today
    existing = frappe.get_all(
        "Usage Alert",
        filters={
            "resource_type": resource_type,
            "alert_type": alert_type,
            "acknowledged": 0,
            "creation": [">=", frappe.utils.today()]
        },
        limit=1
    )

    if existing:
        # Update existing alert instead of creating new
        alert = frappe.get_doc("Usage Alert", existing[0].name)
        alert.current_usage = current_usage
        alert.save(ignore_permissions=True)
        return alert

    # Create new alert
    alert = frappe.new_doc("Usage Alert")
    alert.resource_type = resource_type
    alert.alert_type = alert_type
    alert.threshold_percent = threshold
    alert.current_usage = current_usage
    alert.limit_value = limit_value
    alert.insert(ignore_permissions=True)

    if send_email:
        alert.send_notification()

    return alert
