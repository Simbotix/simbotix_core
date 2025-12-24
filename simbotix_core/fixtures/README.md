# Simbotix Core Fixtures

This directory contains Frappe fixtures for the Simbotix ecosystem.

## Email Templates

### Importing Templates

After installing `simbotix_core`, the email templates and campaigns are automatically imported via fixtures.

**Manual import (if needed):**
```bash
# From the frappe-bench directory
bench --site your-site.com import-fixtures simbotix_core
```

### Available Templates

| Template | Purpose | When to Use |
|----------|---------|-------------|
| Welcome to Simbotix | Onboarding Day 0 | After signup |
| Quick Start Guide | Onboarding Day 1 | Getting started |
| Pro Tips Email | Onboarding Day 3 | Feature discovery |
| Customer Case Study | Onboarding Day 5 | Social proof |
| Feedback Request | Onboarding Day 7 | NPS collection |
| Trial Expiry 3 Days | Conversion | 3 days before trial ends |
| Trial Expiry 1 Day | Conversion | 1 day before trial ends |
| Trial Ended | Conversion | Trial expired |
| Invoice Email | Billing | Invoice generated |
| Payment Received | Billing | Payment confirmed |
| Password Reset | Auth | Password reset request |
| Product Launch Announcement | Marketing | New product launch |
| Monthly Newsletter | Marketing | Monthly updates |
| Subscription Confirmation | Billing | New subscription |
| Subscription Cancelled | Billing | Subscription cancelled |

### Email Campaigns

Two automated sequences are included:

**Welcome Sequence** (for new Leads):
- Day 0: Welcome to Simbotix
- Day 1: Quick Start Guide
- Day 3: Pro Tips Email
- Day 5: Customer Case Study
- Day 7: Feedback Request

**Trial Expiry Sequence** (for trial users):
- Day 0: Trial Expiry 3 Days
- Day 2: Trial Expiry 1 Day
- Day 3: Trial Ended

---

## AWS SES Setup

### Prerequisites
- AWS SES verified domain or email
- SMTP credentials from AWS SES console

### Configure in Frappe

1. **Go to Email Domain Settings:**
   ```
   Setup → Email → Email Domain
   ```

2. **Create Email Domain:**
   - Domain: `simbotix.com`
   - Email Server: `email-smtp.us-east-1.amazonaws.com` (your SES region)
   - Use IMAP: No
   - Use SSL for Outgoing: Yes
   - SMTP Server: `email-smtp.us-east-1.amazonaws.com`
   - SMTP Port: `587`
   - Append Outgoing: No

3. **Create Email Account:**
   ```
   Setup → Email → Email Account
   ```
   - Email Address: `rajesh@simbotix.com`
   - Domain: `simbotix.com`
   - Password: Your SES SMTP password
   - Enable Outgoing: Yes
   - Default Outgoing: Yes
   - SMTP Server: `email-smtp.us-east-1.amazonaws.com`
   - SMTP Port: `587`
   - Use TLS: Yes

4. **Test Email:**
   ```bash
   bench --site your-site.com send-test-email rajesh@simbotix.com
   ```

---

## Using Email Templates

### Programmatic Usage

```python
import frappe

# Send using template
frappe.sendmail(
    recipients=["user@example.com"],
    template="Welcome to Simbotix",
    args={"doc": lead_doc},
    delayed=False
)

# Or with Email Queue
from frappe.core.doctype.communication.email import make
make(
    doctype="Lead",
    name="LEAD-00001",
    recipients="user@example.com",
    subject="Welcome!",
    content=None,
    email_template="Welcome to Simbotix"
)
```

### Using Email Campaigns

1. **Go to:** CRM → Email Campaign
2. **Create New Email Campaign:**
   - Select "Welcome Sequence" or "Trial Expiry Sequence"
   - Target: Lead or any DocType with email field
   - Status: Scheduled
3. **Link to automation or trigger manually**

### Automated Triggers

Add to your app's `hooks.py`:

```python
# Trigger welcome sequence on Lead creation
doc_events = {
    "Lead": {
        "after_insert": "your_app.triggers.start_welcome_sequence"
    }
}
```

```python
# your_app/triggers.py
import frappe

def start_welcome_sequence(doc, method):
    """Start welcome email sequence for new leads"""
    # Create Email Campaign Member
    if not frappe.db.exists("Email Campaign Member", {"lead": doc.name}):
        campaign = frappe.get_doc({
            "doctype": "Email Campaign Member",
            "email_campaign": "Welcome Sequence",
            "lead": doc.name,
            "status": "Active"
        })
        campaign.insert(ignore_permissions=True)
```

---

## Template Variables

All templates use Jinja2 syntax. Common variables:

| Variable | Description |
|----------|-------------|
| `{{ doc.customer_name }}` | Customer name |
| `{{ doc.lead_name }}` | Lead name |
| `{{ doc.email }}` | Email address |
| `{{ doc.expiry_date }}` | Trial/subscription expiry |
| `{{ doc.plan_name }}` | Subscription plan name |
| `{{ doc.portal_url }}` | Customer portal URL |
| `{{ doc.upgrade_link }}` | Upgrade/payment link |

**Default fallbacks** are included (e.g., `{{ doc.customer_name or 'there' }}`).

---

## Customizing Templates

1. **Edit in Frappe:**
   ```
   Setup → Email → Email Template → [Template Name]
   ```

2. **Re-export fixtures:**
   ```bash
   bench --site your-site.com export-fixtures --app simbotix_core
   ```

3. **Commit changes to fixtures/email_template.json**

---

## Troubleshooting

### Emails not sending
```bash
# Check email queue
bench --site your-site.com show-pending-emails

# Process queue manually
bench --site your-site.com send-pending-emails
```

### SES Sandbox Mode
If in SES sandbox, you can only send to verified emails. Request production access in AWS Console.

### Check logs
```bash
# Email sending logs
tail -f ~/frappe-bench/logs/worker.log | grep -i email

# Frappe scheduler
bench --site your-site.com scheduler status
```

---

*Part of Simbotix Core - Shared licensing and metering foundation for all Simbotix apps*
