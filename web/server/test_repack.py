import unittest

import repack


class ModelDependencyTests(unittest.TestCase):
    def test_filtered_ghoul2_mesh_keeps_its_animation(self):
        mesh = 'models/map_objects/hoth/eweb_model.glm'
        animation = 'models/map_objects/hoth/model.gla'
        header = b'2LGM' + (6).to_bytes(4, 'little') + bytes(64)
        header += b'models/map_objects/hoth/model'.ljust(64, b'\0')
        files = {mesh: header, animation: b'animation', 'maps/mp/test.bsp': b''}
        needed = repack.needed_stems(files.__getitem__, set(files), ['mp/test'])
        self.assertIn(repack.stem(mesh), needed)
        self.assertIn(animation, needed)

    def test_dependency_index_reuses_model_parsing_between_maps(self):
        self.assertTrue(hasattr(repack, 'dependency_index'))
        mesh = 'models/map_objects/hoth/eweb_model.glm'
        data = b'2LGM' + (6).to_bytes(4, 'little') + bytes(64) + b'models/map_objects/hoth/model'.ljust(64, b'\0')
        files = {mesh: data, 'maps/mp/a.bsp': b'', 'maps/mp/b.bsp': b''}
        reads = []
        def read(n): reads.append(n); return files[n]
        index = repack.dependency_index(read, set(files))
        a = repack.needed_stems(read, set(files), ['mp/a'], index)
        b = repack.needed_stems(read, set(files), ['mp/b'], index)
        self.assertEqual(a, b)
        self.assertEqual(reads.count(mesh), 1)
