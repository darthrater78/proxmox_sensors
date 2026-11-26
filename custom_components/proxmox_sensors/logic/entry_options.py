"""Read user-tunable settings with one precedence rule: options, then data, then default.

Older entries stored settings in ``entry.data`` (the setup flow still does);
the options flow writes ``entry.options``. Every reader goes through here so a
setting means the same thing, with the same default, in every platform.
"""

from __future__ import annotations

# Sensor groups the PVE options page can switch on or off; all default to on.
PVE_SENSOR_GROUPS = (
    "enable_physical_disks",
    "enable_lm_sensors",
    "enable_smart_monitoring",
    "enable_memory_monitoring",
    "enable_backup_progress",
    "enable_storage_list",
    "enable_nodes_list",
)

# Optional CLUSTER sensor groups; all default to on.
CLUSTER_SENSOR_GROUPS = (
    "enable_cluster_backups",
    "enable_cluster_failed_tasks",
    "enable_cluster_firewall",
    "enable_cluster_ha",
)

EXCLUDED_DATASTORES = "excluded_datastores"


def entry_option(entry, key, default=None):
    """Return a setting from options, falling back to data, then ``default``."""
    if key in (entry.options or {}):
        return entry.options[key]
    return (entry.data or {}).get(key, default)


def excluded_pbs_datastores(entry) -> frozenset[str]:
    """Datastores the user switched off; new datastores are monitored by default."""
    value = entry_option(entry, EXCLUDED_DATASTORES, ())
    if not isinstance(value, (list, tuple, set, frozenset)):
        return frozenset()
    return frozenset(str(store) for store in value)


def monitored_pbs_datastores(entry, datastores):
    """Filter a datastore mapping/iterable down to the ones being monitored."""
    excluded = excluded_pbs_datastores(entry)
    if isinstance(datastores, dict):
        return {store: value for store, value in datastores.items() if store not in excluded}
    return [store for store in datastores if store not in excluded]
