"""Usage Record controller - Batched usage events."""

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class UsageRecord(Document):
    """Individual usage event, aggregated hourly."""

    def validate(self):
        """Validate usage record."""
        if not self.timestamp:
            self.timestamp = now_datetime()

        if self.quantity is None or self.quantity < 0:
            frappe.throw("Quantity must be a non-negative number")

    def before_insert(self):
        """Set defaults before insert."""
        if not self.timestamp:
            self.timestamp = now_datetime()
