import tempfile
import unittest
from pathlib import Path

import metrics as gateway


class ProcessMetricsTests(unittest.TestCase):
    def test_cpu_delta_restart_and_missing_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            process = root / '42'
            process.mkdir()

            def write(ticks, start=99):
                fields = ['S'] + ['0'] * 21
                fields[11] = str(ticks)  # utime, stat field 14
                fields[19] = str(start)  # starttime, stat field 22
                fields[21] = '256'      # rss pages, stat field 24
                (process / 'stat').write_text('42 (game (server)) ' + ' '.join(fields))

            self.assertTrue(hasattr(gateway, 'ProcessMetrics'), 'process sampler is missing')
            sampler = gateway.ProcessMetrics('42', root, ticks_per_second=100, page_size=4096)
            write(100)
            self.assertEqual(sampler.sample(10), {'cpuPercent': None, 'ramMb': 1.0})
            write(250)
            self.assertEqual(sampler.sample(12), {'cpuPercent': 75.0, 'ramMb': 1.0})
            write(5, start=100)
            self.assertIsNone(sampler.sample(14)['cpuPercent'])
            (process / 'stat').unlink()
            self.assertEqual(sampler.sample(16), {'cpuPercent': None, 'ramMb': None})
