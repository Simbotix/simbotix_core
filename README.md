# Simbotix Core

Shared licensing and metering foundation for all Simbotix apps.

## Overview

`simbotix_core` is the **foundation Frappe app** that provides shared infrastructure for all Simbotix applications:

1. **License Validation** - Gatekeeper pattern with decorators for feature/app access control
2. **Usage Metering** - Batch aggregation of resource consumption with hourly sync to central
3. **Alert Management** - Threshold-based notifications (80% warning, 100% hard limit)
4. **Central API Integration** - Two-way sync with simbotix.com for license and usage data

**All Simbotix apps depend on simbotix_core** for licensing checks and metering.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│        Simbotix Apps (flowz, botz_studio, etc.)         │
└──────────────────┬──────────────────────────────────────┘
                   │ depends_on
                   ▼
┌─────────────────────────────────────────────────────────┐
│             simbotix_core (this app)                    │
│  ┌──────────────────────────────────────────────────┐  │
│  │ Licensing Layer                                  │  │
│  │ - @requires_license decorator                   │  │
│  │ - License validation + Redis caching            │  │
│  │ - Feature/App access control                    │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │ Metering Layer                                   │  │
│  │ - @requires_quota decorator                     │  │
│  │ - Usage recording (batch)                       │  │
│  │ - Aggregation (hourly) → Sync (hourly)          │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │ Alert Layer                                      │  │
│  │ - Threshold-based notifications                 │  │
│  │ - Overage cost calculation                      │  │
│  │ - Email notifications                           │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────┬───────────────────────────────────────┘
                 │ HTTP API (HMAC-SHA256 signed)
                 ▼
    ┌──────────────────────────────┐
    │   simbotix.com (Central)     │
    │  - License authority         │
    │  - Usage aggregation         │
    │  - Billing & reporting       │
    └──────────────────────────────┘
```

## Installation

```bash
# Add to your site
bench get-app https://github.com/Simbotix/simbotix_core
bench --site your-site install-app simbotix_core

# Configure license
# Go to: Simbotix Core Settings
# Enter your API credentials and license key from simbotix.com
```

## DocTypes

### App License
Local cache of licenses synced from central simbotix.com.

| Field | Type | Description |
|-------|------|-------------|
| `license_key` | Data | UUID-format license key |
| `customer_id` | Data | Central customer ID |
| `tier` | Select | Trial, Pioneer, Builder, Visionary, Legend |
| `status` | Select | Active, Suspended, Expired, Cancelled, Trial |
| `expiry_date` | Date | Blank = lifetime license |
| `resource_limits` | JSON | `{storage_gb, bandwidth_gb, api_calls, ...}` |
| `enabled_features` | JSON | `["webhooks", "ai_agents", ...]` |
| `enabled_apps` | JSON | `["flowz", "botz_studio", ...]` |

### Simbotix Core Settings
Global configuration (Single document).

| Field | Type | Description |
|-------|------|-------------|
| `central_api_url` | Data | Base URL (default: https://simbotix.com/api) |
| `api_key` | Data | Site API key from simbotix.com |
| `api_secret` | Password | Site API secret |
| `license_key` | Data | Active license key |
| `warning_threshold` | Percent | Alert threshold (default: 80%) |
| `hard_limit_threshold` | Percent | Hard limit (default: 100%) |
| `block_on_exceeded` | Check | Block actions vs allow overage |

### Usage Record
Individual usage events, aggregated hourly then synced.

| Field | Type | Description |
|-------|------|-------------|
| `resource_type` | Select | Type of resource consumed |
| `quantity` | Float | Amount consumed (e.g., 0.001 GB) |
| `app_name` | Data | Source app |
| `aggregated` | Check | Whether record has been aggregated |
| `synced` | Check | Whether synced to central |

### Usage Alert
Threshold notifications when usage crosses warning/hard limits.

| Field | Type | Description |
|-------|------|-------------|
| `resource_type` | Select | Resource that triggered alert |
| `alert_type` | Select | Warning (80%), Exceeded (100%), Blocked |
| `current_usage` | Float | Current usage value |
| `limit_value` | Float | Limit value |
| `overage_amount` | Currency | Estimated overage charges |

## Usage

### Decorators

```python
from simbotix_core.utils.licensing import requires_license, requires_quota

# Require a specific feature
@requires_license(feature="webhooks")
def create_webhook(doc, method):
    pass

# Require a specific app
@requires_license(app="flowz")
def execute_workflow(workflow_id):
    pass

# Check quota and record usage (1 unit)
@requires_quota(resource="api_calls")
@frappe.whitelist()
def my_api_endpoint():
    return {"data": "..."}

# Record multiple units
@requires_quota(resource="emails", quantity=5)
def send_bulk_email(recipients):
    pass
```

### Functions

```python
from simbotix_core.utils.licensing import (
    is_licensed,
    get_license,
    get_license_tier,
    get_resource_limit,
    get_enabled_features,
    get_enabled_apps,
    sync_license
)

from simbotix_core.utils.metering import (
    record_usage,
    get_current_usage,
    get_all_usage,
    get_usage_percentage,
    check_limits,
    calculate_overage
)

# Check if licensed
if is_licensed(feature="ai_agents"):
    # Feature is available
    pass

if is_licensed(app="flowz"):
    # App is licensed
    pass

# Get full license info
license = get_license()
# Returns: {license_key, customer_id, tier, status, is_valid,
#           resource_limits, enabled_features, enabled_apps}

# Get current tier
tier = get_license_tier()  # "Builder"

# Get resource limit
limit = get_resource_limit("storage_gb")  # 30.0 (0 = unlimited)

# Get enabled features/apps
features = get_enabled_features()  # ["webhooks", "funnel_analytics"]
apps = get_enabled_apps()  # ["flowz", "botz_studio"]

# Record usage manually
record_usage("executions", 1, app_name="flowz")
record_usage("storage_gb", 0.005, app_name="my_app", doctype="File", docname="file123")

# Check current usage
current = get_current_usage("api_calls")  # 45000
all_usage = get_all_usage()  # {storage_gb: 15.5, api_calls: 45000, ...}

# Get percentage of limit used
pct = get_usage_percentage("emails")  # 75.5

# Check limit status
status = check_limits("api_calls")  # "ok" | "warning" | "exceeded"

# Calculate overage
overage = calculate_overage("storage_gb")
# Returns: {exceeded_by: 5.5, overage_cost: 8.25, rate: 1.50}
```

### Central API Client

```python
from simbotix_core.utils.central_api import get_api_client

client = get_api_client()

# Validate license
result = client.validate_license("license-key-uuid")
# Returns: {valid: True, license: {...}, message: "..."}

# Get license details
details = client.get_license_details("license-key-uuid")

# Report usage
client.report_usage("license-key-uuid", [
    {"resource": "api_calls", "quantity": 1000, "period_start": "...", "period_end": "..."}
])

# Heartbeat
result = client.heartbeat("license-key-uuid", {"site": "mysite.com", "version": "1.0"})
# Returns: {acknowledged: True, commands: [...]}
```

## Resource Types

| Resource | Description | Tracked By |
|----------|-------------|------------|
| `storage_gb` | Storage consumption | File uploads (auto) |
| `bandwidth_gb` | Bandwidth usage | Response size |
| `database_gb` | Database size | Daily check |
| `api_calls` | API call count | @requires_quota |
| `file_uploads_gb` | Monthly uploads | File doctype (auto) |
| `executions` | Workflow runs | FlowZ/BotZ |
| `emails` | Emails sent | Email Queue (auto) |
| `ai_queries` | AI API calls | AI endpoints |
| `webhooks` | Active webhooks | Count |

## Tier Limits

| Resource | Trial | Pioneer | Builder | Visionary | Legend |
|----------|-------|---------|---------|-----------|--------|
| Storage (GB) | 1 | 10 | 30 | 75 | 150 |
| Bandwidth (GB) | 10 | 100 | 300 | 750 | Unlimited |
| Database (GB) | 0.5 | 2 | 5 | 15 | 50 |
| API Calls | 5K | 50K | 200K | 1M | Unlimited |
| File Uploads (GB) | 1 | 5 | 15 | 50 | Unlimited |
| Executions | 1K | 10K | 50K | Unlimited | Unlimited |
| Emails | 100 | 1K | 5K | 20K | Unlimited |
| AI Queries | 0 | 0 | 1K | 5K | 20K |
| Webhooks | 2 | 5 | 20 | Unlimited | Unlimited |

*Note: Starter, Growth, Scale, Enterprise map to Pioneer, Builder, Visionary, Legend respectively*

## Overage Pricing

| Resource | Rate | Unit |
|----------|------|------|
| storage_gb | $1.50 | per GB/month |
| bandwidth_gb | $0.08 | per GB |
| database_gb | $3.00 | per GB/month |
| api_calls | $0.50 | per 10K calls |
| file_uploads_gb | $1.50 | per GB/month |
| executions | $2.00 | per 10K executions |
| emails | $1.00 | per 1K emails |
| ai_queries | $0.015 | per query |
| webhooks | $0 | (no overage) |

## API Endpoints

### License Queries

```bash
# Get license info
GET /api/method/simbotix_core.api.licensing.get_license_info
# Returns: {success, license: {tier, status, is_valid, expiry_date, ...}}

# Get usage summary
GET /api/method/simbotix_core.api.licensing.get_usage_summary
# Returns: {success, tier, usage: {resource: {current, limit, percentage, status}}}

# Check feature
GET /api/method/simbotix_core.api.licensing.check_feature?feature=webhooks
# Returns: {licensed: bool, tier: str}

# Check app
GET /api/method/simbotix_core.api.licensing.check_app?app_name=flowz
# Returns: {licensed: bool, tier: str}
```

### Overage & Alerts

```bash
# Get overage estimate
GET /api/method/simbotix_core.api.licensing.get_overage_estimate
# Returns: {success, overages: {...}, total_estimated_cost}

# Get pending alerts
GET /api/method/simbotix_core.api.licensing.get_pending_alerts
# Returns: {success, alerts: [...], count}

# Acknowledge alert
POST /api/method/simbotix_core.api.licensing.acknowledge_alert?alert_name=UA-2025-01-00001
# Returns: {success, message}
```

### Sync

```bash
# Manual sync
POST /api/method/simbotix_core.api.licensing.sync_now
# Returns: {success, message, license: {...}}
```

## Scheduler Tasks

| Task | Frequency | Description |
|------|-----------|-------------|
| `sync_license` | Hourly | Sync license from central |
| `aggregate_usage` | Hourly | Group individual records by resource+hour |
| `sync_usage_to_central` | Hourly | Send aggregated usage to simbotix.com |
| `check_all_limits` | Hourly | Create alerts for thresholds |
| `cleanup_old_records` | Daily | Delete synced records older than 30 days |

## Document Events (Auto-tracking)

The following are automatically tracked:

- **File.after_insert** → Records `storage_gb` usage
- **Email Queue.after_insert** → Records `emails` usage

## Adding as Dependency

In your app's `hooks.py`:

```python
required_apps = ["frappe", "simbotix_core"]
```

## Caching

Redis cache keys (5-minute TTL by default):
- `simbotix_license_cache` - Active license key
- `simbotix_license_data` - Full license document
- `simbotix_core_settings` - Settings document

Cache is automatically invalidated on:
- App License save
- Simbotix Core Settings save
- Manual sync via API

## Flow Examples

### License Check Flow
```
App calls @requires_license(feature="x")
  ↓
Check Redis cache → (miss) → Fetch App License document
  ↓
Validate status & expiry
  ↓
Check feature in enabled_features
  ↓ (success)
Execute function
  ↓ (failure)
Raise PermissionError
```

### Usage Metering Flow
```
App calls record_usage("api_calls", 1)
  ↓
Enqueue background job → Create Usage Record
  ↓
Hourly: aggregate_usage() → Groups by resource+hour
  ↓
Hourly: sync_usage_to_central() → POST to simbotix.com
  ↓
Daily: cleanup_old_records() → Delete synced records >30 days
```

### Alert Flow
```
Hourly: check_all_limits()
  ↓
Compare current usage vs limit vs thresholds
  ↓
At 80%: Create Warning alert → Send email
  ↓
At 100%: Create Exceeded alert → Send email (optionally block)
  ↓
User acknowledges via API or desk
```

## Testing

Run tests with:

```bash
bench --site your-site run-tests --app simbotix_core
```

Test files:
- `test_app_license.py` - License document tests
- `test_simbotix_core_settings.py` - Settings tests
- `test_usage_alert.py` - Alert tests
- `test_usage_record.py` - Usage record tests
- `test_api.py` - API endpoint tests
- `test_licensing.py` - Licensing utility tests
- `test_metering.py` - Metering utility tests
- `test_central_api.py` - Central API client tests

## Configuration

Go to **Simbotix Core Settings** to configure:

| Setting | Default | Description |
|---------|---------|-------------|
| Central API URL | https://simbotix.com/api | Central server URL |
| API Key | - | Site API key from simbotix.com |
| API Secret | - | Site API secret |
| License Key | - | Active license key |
| Sync Interval (hours) | 1 | 1-24 hours |
| Warning Threshold | 80% | Alert when usage reaches this % |
| Hard Limit Threshold | 100% | Block/overage when usage reaches this % |
| Block on Exceeded | No | Block actions (Yes) or allow overage (No) |
| Use Redis Cache | Yes | Cache license in Redis |
| Cache TTL (seconds) | 300 | Cache expiry time |
| Alert Email | - | Email for notifications |

## License

MIT

## Author

Rajesh Medampudi <rajesh@simbotix.com>
