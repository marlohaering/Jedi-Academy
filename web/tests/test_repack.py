"""Tiny archives exercise the same build interface used by server startup."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('repack', Path(__file__).resolve().parents[1] / 'server/repack.py')
repack = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(repack)


class ClientArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / 'base'
        self.base.mkdir()
        self.out = self.root / 'client.pk3'
        self.opts = {'map': 'mp/test'}
        # Only entity lump 0 is needed by the repacker.
        entities = b'{ "model" "models/map_objects/test/chair.md3" }'
        self.bsp = b'RBSP' + (1).to_bytes(4, 'little') + (16).to_bytes(4, 'little') + len(entities).to_bytes(4, 'little') + entities
        self.write_pak(self.base / 'assets.pk3', {'maps/mp/test.bsp': self.bsp,
                       'models/map_objects/test/chair.md3': b'chair',
                       'models/players/kyle/model.glm': b'player'})

    def write_pak(self, path, files):
        with zipfile.ZipFile(path, 'w') as archive:
            for name, data in files.items():
                archive.writestr(name, data)

    def build(self):
        return repack.ensure_current(str(self.base), str(self.out), self.opts)

    def test_unchanged_inputs_skip_and_preserve_quoted_model_and_directories(self):
        self.assertTrue(self.build())
        before = self.out.stat().st_mtime_ns
        self.assertFalse(self.build())
        self.assertEqual(before, self.out.stat().st_mtime_ns)
        with zipfile.ZipFile(self.out) as archive:
            self.assertEqual(archive.read('models/map_objects/test/chair.md3'), b'chair')
            self.assertIn('models/players/', archive.namelist())
            self.assertIn('models/players/kyle/', archive.namelist())

    def test_changed_options_and_deleted_input_invalidate(self):
        extra = self.base / 'z-extra.pk3'
        self.write_pak(extra, {'test.txt': b'override'})
        self.build()
        self.opts['music'] = 'music/new'
        self.assertTrue(self.build())
        self.opts['nomusic'] = '1'
        self.assertTrue(self.build())
        extra.unlink()
        self.assertTrue(self.build())
        with zipfile.ZipFile(self.out) as archive:
            self.assertNotIn('test.txt', archive.namelist())

    def test_input_replacement_with_older_timestamp_invalidates(self):
        self.build()
        pak = self.base / 'assets.pk3'
        self.write_pak(pak, {'maps/mp/test.bsp': self.bsp, 'new.txt': b'new'})
        os.utime(pak, (1, 1))
        self.assertTrue(self.build())
        with zipfile.ZipFile(self.out) as archive:
            self.assertEqual(archive.read('new.txt'), b'new')

    def test_script_content_change_with_unchanged_mtime_invalidates(self):
        script = self.root / 'repack.py'
        script.write_text('old')
        with patch.object(repack, '__file__', str(script)):
            self.build()
            stamp = script.stat()
            script.write_text('new')
            os.utime(script, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
            self.assertTrue(self.build())

    def test_failed_desktop_rebuild_keeps_previous_complete_archive(self):
        self.build()
        old = self.out.read_bytes()
        self.opts['map'] = 'mp/missing'
        with self.assertRaises(SystemExit):
            self.build()
        self.assertEqual(old, self.out.read_bytes())
        self.opts['map'] = 'mp/test'
        self.assertFalse(self.build())

    def test_stale_mobile_archive_is_not_served_after_failed_rebuild(self):
        self.opts['profile'] = 'mobile'
        self.build()
        self.opts['map'] = 'mp/missing'
        with self.assertRaises(SystemExit):
            self.build()
        self.assertFalse(self.out.exists())
        self.opts['map'] = 'mp/test'
        self.assertTrue(self.build())

    def test_mod_overrides_and_replaced_output_invalidate(self):
        mod = self.root / 'mod'
        mod.mkdir()
        self.write_pak(mod / 'extra.pk3', {'models/players/kyle/model.glm': b'mod'})
        self.opts['mod'] = str(mod)
        self.build()
        with zipfile.ZipFile(self.out) as archive:
            self.assertEqual(archive.read('models/players/kyle/model.glm'), b'mod')
        self.out.write_bytes(b'broken')
        self.assertTrue(self.build())


if __name__ == '__main__':
    unittest.main()
