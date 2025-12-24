# Simbotix Core

Shared licensing and metering foundation for all Simbotix apps.

## Overview

`simbotix_core` is a Frappe app that provides:

1. **License Validation** - Gatekeeper pattern with decorators for feature/app access control
2. **Usage Metering** - Batch aggregation of resource consumption with hourly sync
3. **Alert Management** - Threshold-based notifications (80% warning, 100% limit)

## Installation

```bash
# Add to your site
bench get-app https://github.com/Simbotix/simbotix_core
bench --site your-site install-app simbotix_core

# Configure license
# Go to: Simbotix Core Settings
# Enter your API credentials and license key
```

## Usage

### Decorators

```python
from simbotix_core.utils import requires_license, requires_quota

# Require a specific feature
@requires_license(feature="webhooks")
def create_webhook(doc, method):
    pass

# Require a specific app
@requires_license(app="flowz")
def execute_workflow(workflow_id):
    pass

# Check quota and record usage
@requires_quota(resource="api_calls")
@frappe.whitelist()
def my_api_endpoint():
    pass

# Record multiple units
@requires_quota(resource="emails", quantity=5)
def send_bulk_email(recipients):
    pass
```

### Functions

```python
from simbotix_core.utils import (
    is_licensed,
    get_license_tier,
    get_resource_limit,
    record_usage,
    check_limits,
    get_usage_percentage
)

# Check if licensed
if is_licensed(feature="ai_agents"):
    # Feature is available
    pass

# Get current tier
tier = get_license_tier()  # "Builder"

# Get resource limit
limit = get_resource_limit("storage_gb")  # 30.0

# Record usage manually
record_usage("executions", 1, app_name="flowz")

# Check limits
status = check_limits("api_calls")  # "ok" | "warning" | "exceeded"

# Get percentage
pct = get_usage_percentage("emails")  # 75.5
```

## Resource Types

| Resource | Description | Tracked By |
|----------|-------------|------------|
| `storage_gb` | Storage consumption | File uploads |
| `bandwidth_gb` | Bandwidth usage | Response size |
| `database_gb` | Database size | Daily check |
| `api_calls` | API call count | @requires_quota |
| `file_uploads_gb` | Monthly uploads | File doctype |
| `executions` | Workflow runs | FlowZ/n8n |
| `emails` | Emails sent | Email Queue |
| `ai_queries` | AI API calls | AI endpoints |
| `webhooks` | Active webhooks | Count |

## Tier Limits

| Resource | Pioneer | Builder | Visionary | Legend |
|----------|---------|---------|-----------|--------|
| Storage | 10 GB | 30 GB | 75 GB | 150 GB |
| Bandwidth | 100 GB | 300 GB | 750 GB | Unlimited |
| Database | 2 GB | 5 GB | 15 GB | 50 GB |
| API Calls | 50K | 200K | 1M | Unlimited |
| Executions | 10K | 50K | Unlimited | Unlimited |
| Emails | 1K | 5K | 20K | Unlimited |
| AI Queries | 0 | 1K | 5K | 20K |

## API Endpoints

```python
# Get license info
GET /api/method/simbotix_core.api.licensing.get_license_info

# Get usage summary
GET /api/method/simbotix_core.api.licensing.get_usage_summary

# Check feature
GET /api/method/simbotix_core.api.licensing.check_feature?feature=webhooks

# Check app
GET /api/method/simbotix_core.api.licensing.check_app?app_name=flowz

# Get overage estimate
GET /api/method/simbotix_core.api.licensing.get_overage_estimate

# Manual sync
POST /api/method/simbotix_core.api.licensing.sync_now

# Get pending alerts
GET /api/method/simbotix_core.api.licensing.get_pending_alerts

# Acknowledge alert
POST /api/method/simbotix_core.api.licensing.acknowledge_alert?alert_name=UA-2025-01-00001
```

## Scheduler Tasks

| Task | Frequency | Description |
|------|-----------|-------------|
| `sync_license` | Hourly | Sync license from central |
| `aggregate_usage` | Hourly | Aggregate usage records |
| `sync_usage_to_central` | Hourly | Send usage to simbotix.com |
| `check_all_limits` | Hourly | Create alerts for thresholds |
| `cleanup_old_records` | Daily | Delete old synced records |

## Adding as Dependency

In your app's `hooks.py`:

```python
required_apps = ["frappe", "simbotix_core"]
```

## Configuration

Go to **Simbotix Core Settings** to configure:

- Central API URL
- API Key and Secret
- License Key
- Alert thresholds (default: 80% warning, 100% hard limit)
- Block on exceeded (default: allow overage)
- Redis caching

## License

MIT

## Author

Rajesh Medampudi <rajesh@simbotix.com>
