app_name = "simbotix_core"
app_title = "Simbotix Core"
app_publisher = "Rajesh Medampudi"
app_description = "Shared licensing and metering foundation for all Simbotix apps"
app_email = "rajesh@simbotix.com"
app_license = "MIT"

# Required apps - frappe must be installed first
required_apps = ["frappe"]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/simbotix_core/css/simbotix_core.css"
# app_include_js = "/assets/simbotix_core/js/simbotix_core.js"

# include js, css files in header of web template
# web_include_css = "/assets/simbotix_core/css/simbotix_core.css"
# web_include_js = "/assets/simbotix_core/js/simbotix_core.js"

# Installation
# ------------

after_install = "simbotix_core.setup.after_install"
after_migrate = "simbotix_core.setup.after_migrate"

# Scheduled Tasks
# ---------------

scheduler_events = {
    "hourly": [
        "simbotix_core.utils.licensing.sync_license",
        "simbotix_core.utils.metering.aggregate_usage",
        "simbotix_core.utils.metering.sync_usage_to_central",
        "simbotix_core.utils.metering.check_all_limits",
    ],
    "daily": [
        "simbotix_core.utils.metering.cleanup_old_records",
    ],
}

# Document Events
# ---------------
# Auto-track usage on key doctypes

doc_events = {
    "File": {
        "after_insert": "simbotix_core.doc_events.track_file_upload",
    },
    "Email Queue": {
        "after_insert": "simbotix_core.doc_events.track_email_queued",
    },
}

# Fixtures
# --------

fixtures = [
    {
        "dt": "Simbotix Core Settings",
    },
    {
        "dt": "Email Template",
        "filters": [
            ["name", "in", [
                "Welcome to Simbotix",
                "Quick Start Guide",
                "Pro Tips Email",
                "Customer Case Study",
                "Feedback Request",
                "Trial Expiry 3 Days",
                "Trial Expiry 1 Day",
                "Trial Ended",
                "Invoice Email",
                "Payment Received",
                "Password Reset",
                "Product Launch Announcement",
                "Monthly Newsletter",
                "Subscription Confirmation",
                "Subscription Cancelled"
            ]]
        ]
    },
    {
        "dt": "Email Campaign",
        "filters": [
            ["name", "in", [
                "Welcome Sequence",
                "Trial Expiry Sequence"
            ]]
        ]
    }
]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
#     "methods": "simbotix_core.utils.jinja_methods",
#     "filters": "simbotix_core.utils.jinja_filters"
# }

# User Data Protection
# --------------------

# user_data_fields = [
#     {
#         "doctype": "{doctype_1}",
#         "filter_by": "{filter_by}",
#         "redact_fields": ["{field_1}", "{field_2}"],
#         "partial": 1,
#     },
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
#     "simbotix_core.auth.validate"
# ]

# Automatically update python controller files with type annotations
# export_python_type_annotations = True
