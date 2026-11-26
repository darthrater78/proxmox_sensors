"""Per-entry SMART polling cache."""


class SmartCache:
    def __init__(self, interval_minutes):
        self.interval_seconds = interval_minutes * 60
        self.last_refresh = None
        self.data = None

    def due(self, now):
        return self.last_refresh is None or now - self.last_refresh >= self.interval_seconds

    def should_refresh(self, enabled, now):
        return enabled and self.due(now)

    def accept(self, data, now):
        if not isinstance(data, dict) or "error" in data:
            return False
        previous = self.data or {}
        # The sidecar reports a spun-down disk instead of waking it; keep its
        # last reading rather than showing it as a disk without SMART.
        self.data = {
            disk: previous[disk]
            if isinstance(info, dict) and info.get("standby") and disk in previous
            else info
            for disk, info in data.items()
        }
        self.last_refresh = now
        return True

    def snapshot(self, node):
        return {node: self.data if self.data is not None else {}}
