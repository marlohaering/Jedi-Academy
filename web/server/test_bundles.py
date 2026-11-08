import unittest

import bundles


class BundleTests(unittest.TestCase):
    def test_shared_map_assets_have_one_owner_and_complete_coverage(self):
        core = {'weapons', 'characters'}
        maps = {'mp/a': {'weapons', 'a.bsp', 'stone'},
                'mp/b': {'characters', 'b.bsp', 'stone'}}
        self.assertTrue(hasattr(bundles, 'partition_files'))
        groups = bundles.partition_files(core, maps)
        self.assertEqual(set().union(*groups.values()), core | set().union(*maps.values()))
        self.assertEqual(sum(map(len, groups.values())), 5)
        for name, required in maps.items():
            available = set().union(*(files for owners, files in groups.items() if not owners or name in owners))
            self.assertTrue(required <= available)
        self.assertEqual(groups[('mp/a', 'mp/b')], {'stone'})

    def test_rebuild_is_content_stable_and_selects_only_requested_map(self):
        import json
        from pathlib import Path
        import tempfile
        import zipfile
        with tempfile.TemporaryDirectory() as d:
            source, out = Path(d, 'source'), Path(d, 'out')
            source.mkdir()
            def bsp(texture):
                text = ('{"classname" "worldspawn" "shader" "' + texture + '"}').encode()
                return b'RBSP' + (1).to_bytes(4, 'little') + (16).to_bytes(4, 'little') + len(text).to_bytes(4, 'little') + text
            with zipfile.ZipFile(source / 'assets0.pk3', 'w') as z:
                z.writestr('default.cfg', b'set test 1')
                z.writestr('maps/mp/a.bsp', bsp('textures/a/stone'))
                z.writestr('maps/mp/b.bsp', bsp('textures/b/stone'))
                z.writestr('textures/a/stone.jpg', b'image a')
                z.writestr('textures/b/stone.jpg', b'image b')
            first = bundles.build(source, out)
            (out / 'bundles.json').unlink()
            second = bundles.build(source, out)
            self.assertEqual(first['packages'], second['packages'])
            manifest = bundles.select_manifest(second, 'mp/a')
            for key in ('paks', 'mobile'):
                files = []
                for package in manifest[key]:
                    with zipfile.ZipFile(out / package['name']) as z:
                        files += [n for n in z.namelist() if not n.endswith('/')]
                self.assertIn('maps/mp/a.bsp', files)
                self.assertIn('textures/a/stone.jpg', files)
                self.assertNotIn('maps/mp/b.bsp', files)
                self.assertNotIn('textures/b/stone.jpg', files)
                self.assertEqual(len(files), len(set(files)))
