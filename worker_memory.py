"""Small process-tree/cgroup samples; no customer data or job control."""
import logging
import os
from pathlib import Path
import time

MIB = 1024 * 1024


def _number(path):
    try:
        value = int(Path(path).read_text().strip())
        return value if 0 <= value < 2**60 else None
    except (OSError, ValueError):
        return None


def cgroup_memory():
    # Render uses a container-scoped cgroup mount. Also support cgroup v1.
    for root, names in (
        ('/sys/fs/cgroup', ('memory.current', 'memory.max', 'memory.peak')),
        ('/sys/fs/cgroup/memory', ('memory.usage_in_bytes', 'memory.limit_in_bytes', 'memory.max_usage_in_bytes')),
    ):
        values = [_number(Path(root) / name) for name in names]
        if any(value is not None for value in values):
            return dict(zip(('current', 'limit', 'peak'), values))
    return {'current': None, 'limit': None, 'peak': None}


def thumbnail_workers(requested):
    limit = cgroup_memory()['limit']
    # Two Python + Playwright + Chromium trees can exhaust the shared 512 MiB
    # container. Preserve the existing queue, with one renderer on small plans.
    return min(requested, 1) if limit is not None and limit <= 768 * MIB else requested


class MemoryMonitor:
    def __init__(self):
        self.next_sample = 0
        self.next_log = 0
        self.peak = 0
        self.last_logged = 0

    def sample(self, children):
        at = time.monotonic()
        if at < self.next_sample:
            return
        self.next_sample = at + 5
        try:
            import psutil
            group = cgroup_memory()
            totals = {}
            count = 1
            rss = psutil.Process(os.getpid()).memory_info().rss
            for name, child in children.items():
                total = 0
                try:
                    parent = psutil.Process(child.pid)
                    processes = [parent, *parent.children(recursive=True)]
                except psutil.Error:
                    processes = []
                for process in processes:
                    try:
                        total += process.memory_info().rss
                        count += 1
                    except psutil.Error:
                        pass  # Short-lived browser processes may already be gone.
                totals[name] = total
                rss += total
            self.peak = max(self.peak, rss)
            current = group['current'] if group['current'] is not None else rss
            pressure = group['limit'] is not None and current >= group['limit'] * .8
            if at >= self.next_log or current - self.last_logged >= 32 * MIB or pressure:
                logger = logging.getLogger(__name__)
                log = logger.warning if pressure else logger.info
                log('worker_memory rss_bytes=%s sampled_peak_rss_bytes=%s seo_tree_bytes=%s '
                    'crm_tree_bytes=%s processes=%s cgroup_bytes=%s cgroup_limit_bytes=%s cgroup_peak_bytes=%s',
                    rss, self.peak, totals.get('seo', 0), totals.get('crm', 0), count,
                    group['current'], group['limit'], group['peak'])
                self.next_log = at + 60
                self.last_logged = current
        except Exception as exc:
            # Diagnostics must never terminate workers or expose exception text.
            if at >= self.next_log:
                logging.getLogger(__name__).warning('worker_memory_unavailable error_type=%s', type(exc).__name__)
                self.next_log = at + 60
