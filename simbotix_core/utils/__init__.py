"""Utility modules for simbotix_core."""

from simbotix_core.utils.licensing import (
    requires_license,
    requires_quota,
    is_licensed,
    get_license,
    get_license_tier,
    get_resource_limit,
    get_enabled_features,
    get_enabled_apps,
    sync_license,
)

from simbotix_core.utils.metering import (
    record_usage,
    get_current_usage,
    get_all_usage,
    check_limits,
    get_usage_percentage,
    calculate_overage,
)

__all__ = [
    # Licensing
    "requires_license",
    "requires_quota",
    "is_licensed",
    "get_license",
    "get_license_tier",
    "get_resource_limit",
    "get_enabled_features",
    "get_enabled_apps",
    "sync_license",
    # Metering
    "record_usage",
    "get_current_usage",
    "get_all_usage",
    "check_limits",
    "get_usage_percentage",
    "calculate_overage",
]
