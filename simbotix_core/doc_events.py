"""Document event handlers for automatic usage tracking."""

import frappe
from simbotix_core.utils.metering import record_usage


def track_file_upload(doc, method):
    """
    Track file uploads for storage metering.
    Called on File after_insert.
    """
    if doc.file_size:
        # Convert bytes to GB
        size_gb = doc.file_size / (1024 * 1024 * 1024)
        record_usage(
            resource="storage_gb",
            quantity=size_gb,
            app_name="frappe",
            doctype="File",
            docname=doc.name
        )


def track_email_queued(doc, method):
    """
    Track emails queued for sending.
    Called on Email Queue after_insert.
    """
    record_usage(
        resource="emails",
        quantity=1,
        app_name="frappe",
        doctype="Email Queue",
        docname=doc.name
    )
