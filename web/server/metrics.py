"""Dedicated-server CPU (100% = one core) and resident memory via Linux procfs."""
import os
from pathlib import Path


class ProcessMetrics:
    def __init__(self, pid, proc_root='/proc', ticks_per_second=None, page_size=None):
        self.path = Path(proc_root) / str(pid) / 'stat'
        self.hz = ticks_per_second or os.sysconf('SC_CLK_TCK')
        self.page_size = page_size or os.sysconf('SC_PAGE_SIZE')
        self.previous = None

    def sample(self, now):
        result = {'cpuPercent': None, 'ramMb': None}
        try:
            # comm may contain spaces and parentheses; fields after its final ')' are stable.
            fields = self.path.read_text().rsplit(')', 1)[1].split()
            ticks = int(fields[11]) + int(fields[12])
            identity = int(fields[19])
            result['ramMb'] = max(0, int(fields[21])) * self.page_size / (1024 * 1024)
            if self.previous:
                old_time, old_ticks, old_identity = self.previous
                if identity == old_identity and now > old_time and ticks >= old_ticks:
                    result['cpuPercent'] = 100 * (ticks - old_ticks) / self.hz / (now - old_time)
            self.previous = (now, ticks, identity)
        except (OSError, ValueError, IndexError):
            self.previous = None
        return result
