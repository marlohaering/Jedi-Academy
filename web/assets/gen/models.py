"""Player/NPC characters, weapons, sabers and pickup models."""
import math
import re
import struct
import zlib

import numpy as np
from PIL import Image, ImageDraw

from . import common, ghoul2
from .ghoul2 import Surface

HUMANOID_GLA = 'models/players/_humanoid/_humanoid'
BODY_SURFS = {'head': ['head'], 'torso': ['torso', 'r_arm', 'l_arm', 'r_hand', 'l_hand'], 'lower': ['hips', 'r_leg', 'l_leg']}

# character name -> palette (torso, head, legs, arms, visor, gloves) + options
PALETTES = {
    'stormtrooper': dict(c=((235, 235, 235), (240, 240, 240), (225, 225, 225), (230, 230, 230), (20, 20, 25), (30, 30, 30)), helmet=True),
    'snowtrooper': dict(c=((225, 230, 240), (235, 240, 245), (220, 225, 235), (225, 230, 240), (30, 30, 40), (60, 60, 70)), helmet=True),
    'swamptrooper': dict(c=((70, 80, 60), (80, 90, 70), (60, 70, 55), (70, 80, 60), (20, 20, 20), (30, 30, 30)), helmet=True),
    'shadowtrooper': dict(c=((30, 30, 40), (35, 35, 45), (25, 25, 35), (30, 30, 40), (180, 40, 40), (20, 20, 20)), helmet=True),
    'reborn': dict(c=((60, 20, 20), (90, 70, 60), (40, 15, 15), (50, 20, 20), (255, 200, 60), (20, 20, 20))),
    'reborn_new': dict(c=((80, 25, 25), (90, 70, 60), (40, 20, 20), (70, 25, 25), (255, 200, 60), (20, 20, 20))),
    'reborn_twin': dict(c=((40, 40, 70), (90, 70, 60), (30, 30, 50), (40, 40, 70), (255, 200, 60), (20, 20, 20))),
    'cultist': dict(c=((110, 100, 80), (90, 70, 60), (80, 70, 60), (100, 90, 70), (220, 60, 40), (40, 30, 20))),
    'tavion': dict(c=((50, 30, 40), (200, 160, 140), (40, 25, 35), (50, 30, 40), (120, 200, 255), (20, 20, 20))),
    'desann': dict(c=((70, 40, 30), (110, 160, 80), (50, 30, 20), (60, 40, 30), (255, 220, 60), (30, 20, 20))),
    'kyle': dict(c=((70, 80, 95), (200, 160, 130), (50, 55, 65), (70, 80, 95), (60, 120, 200), (40, 35, 30))),
    'luke': dict(c=((25, 25, 30), (210, 170, 140), (20, 20, 25), (25, 25, 30), (80, 140, 255), (20, 20, 20))),
    'jedi': dict(c=((150, 120, 80), (210, 170, 140), (110, 85, 60), (140, 110, 75), (90, 170, 255), (80, 60, 40))),
    'imperial': dict(c=((90, 95, 100), (210, 170, 140), (40, 40, 45), (90, 95, 100), (60, 60, 60), (20, 20, 20))),
    'rebel': dict(c=((180, 140, 90), (200, 160, 130), (100, 90, 70), (170, 130, 85), (60, 100, 160), (60, 50, 40))),
    'human_merc': dict(c=((110, 90, 60), (190, 150, 120), (70, 60, 45), (100, 85, 60), (200, 80, 40), (50, 40, 30))),
}
DEFAULT_JEDI = 'jedi'


def palette_for(name):
    n = name.lower()
    for key in sorted(PALETTES, key=len, reverse=True):
        if n.startswith(key):
            return PALETTES[key]
    if n.startswith('jedi'):
        return PALETTES['jedi']
    # deterministic random-ish palette for everyone else
    h = zlib.crc32(n.encode())
    base = ((h & 0xFF) // 2 + 50, ((h >> 8) & 0xFF) // 2 + 50, ((h >> 16) & 0xFF) // 2 + 50)
    return dict(c=(base, (200, 165, 135), tuple(int(x * 0.7) for x in base), base, (240, 240, 240), (40, 40, 40)))


def character_texture(pal):
    torso, head, legs, arms, visor, gloves = pal['c']
    s = 128
    img = Image.new('RGB', (s, s))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, s // 2 - 1, s // 2 - 1], fill=torso)
    d.rectangle([s // 2, 0, s - 1, s // 2 - 1], fill=head)
    d.rectangle([0, s // 2, s // 2 - 1, s - 1], fill=legs)
    d.rectangle([s // 2, s // 2, s - 1, s - 1], fill=arms)
    d.rectangle([s // 2, s // 2, int(s * 0.6), int(s * 0.6)], fill=visor)
    d.rectangle([int(s * 0.6), s // 2, int(s * 0.7), int(s * 0.6)], fill=gloves)
    # a belt and some panel lines for readability
    d.rectangle([0, int(s * 0.5), s // 2 - 1, int(s * 0.56)], fill=tuple(int(x * 0.5) for x in legs))
    for y in range(4, s // 2, 12):
        d.line([0, y, s // 2 - 1, y], fill=tuple(int(x * 0.85) for x in torso))
    return img


def player_models(existing):
    names = set()
    for path, data in existing.items():
        if path.startswith('ext_data/npcs/'):
            names.update(m.lower() for m in re.findall(r'^\s*playerModel\s+"?([\w]+)"?', data.decode('latin-1')
                                                       if isinstance(data, bytes) else data, re.M | re.I))
    names |= {'kyle', 'luke', 'protocol', 'rebel_pilot', 'stormtrooper', 'jedi_hm', 'jedi_hf', 'jedi_tf',
              'jedi_zf', 'jedi_rm', 'jedi_kdm', 'jedi_zm', 'jedi_dm', 'reborn', '_humanoid'}
    return sorted(names)


def npc_skins(existing):
    skins = set()
    for path, data in existing.items():
        if path.startswith('ext_data/npcs/'):
            text = data.decode('latin-1') if isinstance(data, bytes) else data
            skins.update(m.lower() for m in re.findall(r'^\s*customSkin\s+"?([\w]+)"?', text, re.M | re.I))
    return skins


def build_characters(existing, anim_names):
    out = {}
    frames, cfg = ghoul2.build_animations(anim_names)
    out[HUMANOID_GLA + '.gla'] = ghoul2.write_gla(HUMANOID_GLA, ghoul2.skeleton_bones(), frames)
    out['models/players/_humanoid/animation.cfg'] = cfg
    for name in player_models(existing):
        pal = palette_for(name)
        tex = f'models/players/{name}/body'
        surfs = ghoul2.build_humanoid_mesh({'body': tex, 'helmet': pal.get('helmet', False),
                                            'width': 0.92 if name.endswith(('f', 'tf', 'hf', 'zf')) else 1.0})
        out[f'models/players/{name}/model.glm'] = ghoul2.write_glm(
            f'models/players/{name}/model.glm', HUMANOID_GLA, len(ghoul2.SKELETON), surfs)
        out[f'{tex}.png'] = common.png(character_texture(pal))
        full = ''.join(f'{s.name},{tex}\n' for s in surfs if not s.name.startswith('*'))
        for skin in {'default', 'sp', 'menu', 'red', 'blue', 'mp'} | npc_skins(existing):
            out[f'models/players/{name}/model_{skin}.skin'] = full
        for part, surf_names in BODY_SURFS.items():
            txt = ''.join(f'{s},{tex}\n' for s in surf_names)
            for variant in ('a1', 'a2', 'a3', 'b1', 'b2', 'b3', 'c1', 'c2', 'c3', 'd1', 'd2', 'd3', 'e1', 'e2',
                            'e3', 'f1', 'f2', 'f3', 'g1', 'g2', 'g3'):
                out[f'models/players/{name}/{part}_{variant}.skin'] = txt
        out[f'models/players/{name}/icon_default.png'] = common.png(character_texture(pal).resize((64, 64)))
    return out


# ----------------------------------------------------------------------------- MD3
def latlong(n):
    x, y, z = n
    if x == 0 and y == 0:
        return (0 << 8) | 0 if z > 0 else (128 << 8) | 0
    lng = int(math.atan2(y, x) * 255 / (2 * math.pi)) & 255
    lat = int(math.acos(max(-1, min(1, z))) * 255 / (2 * math.pi)) & 255
    return (lat << 8) | lng


def write_md3(name, meshes, tags=(), frames=None):
    """meshes: list of (surface name, shader, Surface-like with verts (pos, normal, _, st) & tris).
    tags: list of (name, origin, axis 3x3 rows). frames: list of 3x4 rigid transforms (default: 16 x identity,
    the first-person code indexes frames 0..15)."""
    if frames is None:
        frames = [ghoul2.mat34(np.eye(3), np.zeros(3))] * 16
    nf = len(frames)
    surf_blobs = []
    allpts = [[] for _ in frames]
    for sname, shader, s in meshes:
        nv, nt = len(s.verts), len(s.tris)
        shaders = struct.pack('<64si', shader.encode(), 0)
        tris = b''.join(struct.pack('<3i', *t) for t in s.tris)
        sts = b''.join(struct.pack('<2f', *v[3]) for v in s.verts)
        xyz = b''
        for fi, f in enumerate(frames):
            for v in s.verts:
                p = f[:, :3] @ v[0] + f[:, 3]
                n = f[:, :3] @ v[1]
                allpts[fi].append(p)
                xyz += struct.pack('<3hH', *[int(round(c * 64)) for c in p], latlong(n))
        hdr = 4 + 64 + 4 * 10
        ofs_sh = hdr
        ofs_tri = ofs_sh + len(shaders)
        ofs_st = ofs_tri + len(tris)
        ofs_xyz = ofs_st + len(sts)
        ofs_end = ofs_xyz + len(xyz)
        surf_blobs.append(struct.pack('<4s64siiiiiiiiii', b'IDP3', sname.encode(), 0, nf, 1, nv, nt,
                                      ofs_tri, ofs_sh, ofs_st, ofs_xyz, ofs_end) + shaders + tris + sts + xyz)
    frame_blob = b''
    for fi in range(nf):
        pts = np.array(allpts[fi]) if allpts[fi] else np.zeros((1, 3))
        mn, mx = pts.min(0), pts.max(0)
        radius = float(np.linalg.norm(np.maximum(abs(mn), abs(mx))))
        frame_blob += struct.pack('<3f3f3ff16s', *mn, *mx, 0, 0, 0, radius, b'frame%d' % fi)
    tag_blob = b''
    for f in frames:
        for t in tags:
            o = f[:, :3] @ np.array(t[1], float) + f[:, 3]
            ax = (f[:, :3] @ np.array(t[2], float).T).T
            tag_blob += struct.pack('<64s3f9f', t[0].encode(), *o, *ax.flatten())
    hdr = 4 + 4 + 64 + 4 * 9
    ofs_frames = hdr
    ofs_tags = ofs_frames + len(frame_blob)
    ofs_surfs = ofs_tags + len(tag_blob)
    body = b''.join(surf_blobs)
    ofs_end = ofs_surfs + len(body)
    header = struct.pack('<4si64siiiiiiiii', b'IDP3', 15, name.encode(), 0, nf, len(tags), len(meshes), 0,
                         ofs_frames, ofs_tags, ofs_surfs, ofs_end)
    return header + frame_blob + tag_blob + body


def view_hand_frames():
    """Frame 0 idle, 1-6 firing recoil, 6-10 lowering (drop), 11-15 raising."""
    out = []
    for i in range(16):
        if 1 <= i <= 5:
            k = math.exp(-(i - 1) * 0.8)
            R, t = ghoul2.euler(pitch=-8 * k), (-2.5 * k, 0, 0.6 * k)
        elif 6 <= i <= 10:
            k = (i - 6) / 4
            R, t = ghoul2.euler(pitch=40 * k), (-4 * k, 0, -10 * k)
        elif 11 <= i <= 15:
            k = 1 - (i - 11) / 4
            R, t = ghoul2.euler(pitch=40 * k), (-4 * k, 0, -10 * k)
        else:
            R, t = np.eye(3), (0, 0, 0)
        out.append(ghoul2.mat34(R, np.array(t, float)))
    return out


IDENT = ((1, 0, 0), (0, 1, 0), (0, 0, 1))


def gun_parts(kind):
    """Returns list of (mins, maxs) boxes for a gun of a given silhouette, barrel along +X, grip at origin."""
    if kind == 'pistol':
        return [((-3, -1, -1), (8, 1, 2)), ((-2, -0.8, -6), (0.5, 0.8, -1)), ((8, -0.5, 0), (11, 0.5, 1))]
    if kind == 'rifle':
        return [((-8, -1.2, -1), (14, 1.2, 2.5)), ((-2, -0.9, -6), (0.5, 0.9, -1)), ((14, -0.6, 0.2), (20, 0.6, 1.4)),
                ((-14, -1, -3), (-8, 1, 2)), ((2, -1, 2.5), (8, 1, 4))]
    if kind == 'heavy':
        return [((-8, -2, -2), (16, 2, 3)), ((-1, -1, -7), (1.5, 1, -2)), ((16, -1.5, -1), (22, 1.5, 2)),
                ((-4, -2.5, 3), (8, 2.5, 5))]
    if kind == 'grenade':
        return [((-2, -2, -2), (2, 2, 2))]
    if kind == 'baton':
        return [((-2, -0.8, -0.8), (18, 0.8, 0.8))]
    return [((-6, -1.5, -1.5), (6, 1.5, 1.5))]


def weapon_kind(path):
    p = path.lower()
    for key, kind in (('pistol', 'pistol'), ('briar', 'pistol'), ('blaster', 'rifle'), ('disruptor', 'rifle'),
                      ('bowcaster', 'rifle'), ('tusken', 'rifle'), ('repeater', 'heavy'), ('demp2', 'heavy'),
                      ('golan', 'heavy'), ('flechette', 'heavy'), ('merr_sonn', 'heavy'), ('concussion', 'heavy'),
                      ('thermal', 'grenade'), ('detpack', 'grenade'), ('laser_trap', 'grenade'),
                      ('baton', 'baton'), ('staff', 'baton'), ('stick', 'baton'), ('scepter', 'baton')):
        if key in p:
            return kind
    return 'rifle'


def mesh_from_boxes(boxes, uv=(0, 0, 1, 1)):
    s = Surface('mesh')
    for mn, mx in boxes:
        s.box(mn, mx, 0, uv)
    return s


def build_weapons(existing):
    out = {}
    out['models/placeholder/metal.png'] = common.png(metal_texture((70, 75, 85)))
    out['models/placeholder/metal_light.png'] = common.png(metal_texture((150, 155, 165)))
    out['models/placeholder/hilt.png'] = common.png(metal_texture((170, 170, 180), stripes=True))
    out['models/placeholder/item.png'] = common.png(metal_texture((60, 160, 90), stripes=True))
    paths = set()
    for path, data in existing.items():
        if path.startswith('ext_data/') and path.endswith(('.dat', '.npc', '.veh')):
            text = data.decode('latin-1') if isinstance(data, bytes) else data
            paths.update(m.lower() for m in re.findall(r'(models/[\w/\-]+\.(?:md3|glm))', text, re.I))
    weapons = {p for p in paths if p.startswith('models/weapons2/')}
    # every view weapon md3 also needs its _w.glm, _hand.md3 and possibly barrels
    extra = set()
    for p in weapons:
        if p.endswith('.md3'):
            stem = p[:-4]
            extra.add((stem if stem.endswith('_w') else stem + '_w') + '.glm')
            extra.add(stem + '_hand.md3')
            for i in range(1, 5):
                extra.add(f'{stem}_barrel{i}.md3' if i > 1 else f'{stem}_barrel.md3')
    weapons |= extra
    weapons.add('models/weapons2/briar_pistol/briar_pistol_hand.md3')
    for p in sorted(weapons):
        kind = weapon_kind(p)
        if p.endswith('_hand.md3'):
            # first person hands: a forearm + glove, weapon tag in the palm
            # view space: +X forward, +Y left, +Z up, eye at the origin -> hand sits low and to the right
            hx, hy, hz = 14, -6.5, -9
            s = mesh_from_boxes([((hx - 12, hy - 1.8, hz - 2.4), (hx + 2, hy + 1.8, hz + 1.2)),
                                 ((hx + 2, hy - 2, hz - 2.2), (hx + 5, hy + 2, hz + 1.4))], uv=(0.62, 0.52, 0.68, 0.58))
            out[p] = write_md3(p, [('hand', 'models/players/jedi_tf/body', s)],
                               [('tag_weapon', (hx + 3.5, hy, hz + 1.5), IDENT)], view_hand_frames())
        elif '_barrel' in p:
            continue
        elif p.endswith('.md3'):
            s = mesh_from_boxes(gun_parts(kind))
            muzzle = max(b[1][0] for b in gun_parts(kind))
            out[p] = write_md3(p, [('gun', 'models/placeholder/metal', s)],
                               [('tag_flash', (muzzle, 0, 0.8), IDENT), ('tag_barrel', (0, 0, 0), IDENT)])
        elif p.endswith('.glm') and '/saber' not in p:
            s = Surface('gun', 'models/placeholder/metal')
            for mn, mx in gun_parts(kind):
                s.box(mn, mx, 0)
            muzzle = max(b[1][0] for b in gun_parts(kind))
            surfs = [s]
            for tag in ('*flash', '*flash01', '*flash02', '*flash03', '*muzzle1', '*muzzle2'):
                t = Surface(tag, '', 0)
                t.tag((muzzle, 0, 0.8), (1, 0, 0), (0, 1, 0), 0)
                surfs.append(t)
            out[p] = ghoul2.write_rigid_glm(p, surfs)
    return out


def metal_texture(color, stripes=False):
    rng = np.random.default_rng(sum(color))
    a = np.ones((64, 64, 3)) * np.array(color) * (0.85 + 0.25 * rng.random((64, 64, 1)))
    if stripes:
        for y in range(0, 64, 8):
            a[y:y + 2] *= 0.5
    a[:2] *= 1.3
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


# ----------------------------------------------------------------------------- sabers
def saber_hilt(path, blades):
    """Hilt along +X (the hand tag's forward axis, i.e. through the fist). The blade direction is -X of the
    '*bladeN' tag (cg_players.cpp), so blade 1 points along +X and blade 2 (staffs) along -X."""
    s = Surface('hilt', 'models/placeholder/hilt')
    half = 9 if blades == 2 else 5
    s.box((-half if blades == 2 else -3, -0.8, -0.8), (half, 0.8, 0.8), 0)
    s.box((half - 1.5, -1.1, -1.1), (half, 1.1, 1.1), 0)
    if blades == 2:
        s.box((-half, -1.1, -1.1), (-half + 1.5, 1.1, 1.1), 0)
    surfs = [s]
    for i, (origin, xaxis) in enumerate((((half, 0, 0), (-1, 0, 0)), ((-half, 0, 0), (1, 0, 0)))[:blades]):
        t = Surface(f'*blade{i + 1}', '', 0)
        t.tag(origin, xaxis, (0, 1, 0), 0)
        surfs.append(t)
    fl = Surface('*flash', '', 0)
    fl.tag((half, 0, 0), (-1, 0, 0), (0, 1, 0), 0)
    surfs.append(fl)
    return ghoul2.write_rigid_glm(path, surfs)


def build_sabers(existing):
    out = {}
    for path, data in existing.items():
        if not path.startswith('ext_data/sabers/') or not path.endswith('.sab'):
            continue
        text = data.decode('latin-1') if isinstance(data, bytes) else data
        for block in re.split(r'\n(?=\w)', text):
            model = re.search(r'saberModel\s+"?([\w/\-.]+)"?', block, re.I)
            if not model:
                continue
            nb = re.search(r'numBlades\s+(\d+)', block, re.I)
            blades = int(nb.group(1)) if nb else 1
            p = model.group(1).lower()
            out[p] = saber_hilt(p, 2 if blades >= 2 else 1)
    for p in ('models/weapons2/saber/saber_w.glm', 'models/weapons2/saber_reborn/saber_w.glm'):
        out.setdefault(p, saber_hilt(p, 1))
    out['models/weapons2/saber/saber_w.md3'] = write_md3('models/weapons2/saber/saber_w.md3', [
        ('hilt', 'models/placeholder/hilt', mesh_from_boxes([((-0.8, -0.8, -3), (0.8, 0.8, 5))]))],
        [('tag_flash', (0, 0, 5), IDENT)])
    return out


# ----------------------------------------------------------------------------- items
def build_items(existing):
    out = {}
    paths = set()
    for path, data in existing.items():
        if path.startswith('ext_data/') and path.endswith('.dat'):
            text = data.decode('latin-1') if isinstance(data, bytes) else data
            paths.update(m.lower() for m in re.findall(r'(models/(?:items|map_objects)/[\w/\-]+\.md3)', text, re.I))
    for p in sorted(paths):
        s = mesh_from_boxes([((-5, -5, 0), (5, 5, 7)), ((-3, -3, 7), (3, 3, 9))])
        out[p] = write_md3(p, [('item', 'models/placeholder/item', s)])
    return out


def generate(existing):
    anim_names = common.anim_names()
    out = {}
    out.update(build_characters(existing, anim_names))
    out.update(build_weapons(existing))
    out.update(build_sabers(existing))
    out.update(build_items(existing))
    return out
