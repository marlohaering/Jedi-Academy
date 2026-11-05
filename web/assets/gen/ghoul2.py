"""Ghoul2 (GLM mesh + GLA skeleton/animation) writers and the placeholder humanoid.

Conventions (verified against tr_ghoul2.cpp):
  * Final[root] = rootMatrix * Anim[root]; Final[c] = Final[parent] * Anim[c]
  * vertices are skinned with Final[bone] directly (vertices are stored in base-pose model space),
    so Final[b] is a *deformation* matrix; bone bolts use Final[b] * BasePoseMat[b].
  * the humanoid is *authored* with +X forward, +Y left, +Z up and feet at z = -24 (the entity's mins),
    then rotated by TO_MODEL because Ghoul2 player models face -Y in model space.
"""
import math
import struct

import numpy as np

FEET = -24.0


# ----------------------------------------------------------------------------- math helpers
def rot(axis, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    x, y, z = axis
    return np.array([[c + x * x * (1 - c), x * y * (1 - c) - z * s, x * z * (1 - c) + y * s],
                     [y * x * (1 - c) + z * s, c + y * y * (1 - c), y * z * (1 - c) - x * s],
                     [z * x * (1 - c) - y * s, z * y * (1 - c) + x * s, c + z * z * (1 - c)]])


def euler(pitch=0.0, yaw=0.0, roll=0.0):
    """pitch: about +Y (positive tips +X down... i.e. forward bend for a vertical limb pointing up),
    yaw: about +Z, roll: about +X."""
    return rot((0, 0, 1), yaw) @ rot((0, 1, 0), pitch) @ rot((1, 0, 0), roll)


def mat34(R, t):
    m = np.zeros((3, 4))
    m[:, :3] = R
    m[:, 3] = t
    return m


def mul34(a, b):
    R = a[:, :3] @ b[:, :3]
    t = a[:, :3] @ b[:, 3] + a[:, 3]
    return mat34(R, t)


def inv34(a):
    R = a[:, :3].T
    return mat34(R, -R @ a[:, 3])


def mat_to_quat(R):
    """Returns (w, x, y, z) for rotation matrix R."""
    tr = R[0, 0] + R[1, 1] + R[2, 2]
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        w, x, y, z = 0.25 * s, (R[2, 1] - R[1, 2]) / s, (R[0, 2] - R[2, 0]) / s, (R[1, 0] - R[0, 1]) / s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
        w, x, y, z = (R[2, 1] - R[1, 2]) / s, 0.25 * s, (R[0, 1] + R[1, 0]) / s, (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
        w, x, y, z = (R[0, 2] - R[2, 0]) / s, (R[0, 1] + R[1, 0]) / s, 0.25 * s, (R[1, 2] + R[2, 1]) / s
    else:
        s = math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
        w, x, y, z = (R[1, 0] - R[0, 1]) / s, (R[0, 2] + R[2, 0]) / s, (R[1, 2] + R[2, 1]) / s, 0.25 * s
    return w, x, y, z


def compress_bone(m):
    w, x, y, z = mat_to_quat(m[:, :3])
    q = [max(0, min(65535, int(round((c + 2.0) * 16383.0)))) for c in (w, x, y, z)]
    t = [max(0, min(65535, int(round((c + 512.0) * 64.0)))) for c in m[:, 3]]
    return struct.pack('<7H', *q, *t)


TO_MODEL = rot((0, 0, 1), -90)   # authored +X forward -> model -Y forward


def pad4(b):
    return b + b'\0' * ((-len(b)) % 4)


# ----------------------------------------------------------------------------- GLA
def write_gla(name, bones, frames):
    """bones: list of dict(name, parent, base (3x4 base pose matrix)).
    frames: list of lists of 3x4 anim matrices (one per bone)."""
    nb = len(bones)
    children = {i: [] for i in range(nb)}
    for i, b in enumerate(bones):
        if b['parent'] >= 0:
            children[b['parent']].append(i)
    skel = []
    for i, b in enumerate(bones):
        base = b['base']
        binv = inv34(base)
        ch = children[i]
        skel.append(struct.pack('<64sIi12f12fi', b['name'].encode(), 0, b['parent'],
                                *base.flatten(), *binv.flatten(), len(ch)) +
                    struct.pack(f'<{len(ch)}i', *ch))
    header_size = 4 + 4 + 64 + 4 + 4 * 6
    offs_block = 4 * nb
    offsets, pos = [], offs_block
    for s in skel:
        offsets.append(pos)
        pos += len(s)
    skel_blob = struct.pack(f'<{nb}i', *offsets) + b''.join(skel)

    pool, pool_index, idx_bytes = [], {}, bytearray()
    for fr in frames:
        for m in fr:
            c = compress_bone(m)
            if c not in pool_index:
                pool_index[c] = len(pool)
                pool.append(c)
            i = pool_index[c]
            idx_bytes += bytes((i & 255, (i >> 8) & 255, (i >> 16) & 255))
    frames_blob = pad4(bytes(idx_bytes))
    ofs_skel = header_size
    ofs_frames = ofs_skel + len(skel_blob)
    ofs_pool = ofs_frames + len(frames_blob)
    pool_blob = b''.join(pool)
    ofs_end = ofs_pool + len(pool_blob)
    header = struct.pack('<4si64sfiiiiii', b'2LGA', 6, name.encode(), 1.0, len(frames), ofs_frames,
                         nb, ofs_pool, ofs_skel, ofs_end)
    return header + skel_blob + frames_blob + pool_blob


# ----------------------------------------------------------------------------- GLM
class Surface:
    def __init__(self, name, shader='', parent=-1, flags=0):
        self.name, self.shader, self.parent, self.flags = name, shader, parent, flags
        self.verts = []   # (pos, normal, bone, st)
        self.tris = []

    def add_vert(self, pos, normal, bone, st=(0.0, 0.0)):
        self.verts.append((np.asarray(pos, float), np.asarray(normal, float), bone, st))
        return len(self.verts) - 1

    def box(self, mins, maxs, bone, uv=(0, 0, 1, 1), xform=None):
        """Adds an axis aligned box (optionally transformed by 3x4 xform)."""
        x0, y0, z0 = mins
        x1, y1, z1 = maxs
        faces = [((1, 0, 0), [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)]),
                 ((-1, 0, 0), [(x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1)]),
                 ((0, 1, 0), [(x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1)]),
                 ((0, -1, 0), [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)]),
                 ((0, 0, 1), [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]),
                 ((0, 0, -1), [(x0, y1, z0), (x1, y1, z0), (x1, y0, z0), (x0, y0, z0)])]
        u0, v0, u1, v1 = uv
        for n, quad in faces:
            if xform is not None:
                quad = [xform[:, :3] @ np.array(p) + xform[:, 3] for p in quad]
                n = xform[:, :3] @ np.array(n)
            sts = [(u0, v1), (u1, v1), (u1, v0), (u0, v0)]
            ids = [self.add_vert(p, n, bone, st) for p, st in zip(quad, sts)]
            # engine culls with clockwise front faces (Q3 convention): emit reversed winding
            self.tris += [(ids[0], ids[2], ids[1]), (ids[0], ids[3], ids[2])]

    def tag(self, origin, xaxis, yaxis, bone, size=1.0):
        """Tag triangle such that the bolt matrix has the given X/Y axes at origin
        (see G2_ProcessSurfaceBolt2: origin = P2, X = norm(P0-P2), Y = norm(P1-P0))."""
        o = np.asarray(origin, float)
        xa, ya = np.asarray(xaxis, float), np.asarray(yaxis, float)
        p2 = o
        p0 = o + xa * size
        p1 = p0 + ya * size * 2.5
        ids = [self.add_vert(p, np.cross(xa, ya), bone) for p in (p0, p1, p2)]
        self.tris.append(tuple(ids))
        self.flags |= 1  # G2SURFACEFLAG_ISBOLT


def write_glm(name, anim_name, num_bones, surfaces):
    ns = len(surfaces)
    children = {i: [] for i in range(ns)}
    for i, s in enumerate(surfaces):
        if s.parent >= 0:
            children[s.parent].append(i)
    hier = []
    for i, s in enumerate(surfaces):
        ch = children[i]
        hier.append(struct.pack('<64sI64sii', s.name.encode(), s.flags, s.shader.encode(), 0, s.parent) +
                    struct.pack(f'<i{len(ch)}i', len(ch), *ch))
    offs, pos = [], 4 * ns
    for h in hier:
        offs.append(pos)
        pos += len(h)
    hier_blob = struct.pack(f'<{ns}i', *offs) + b''.join(hier)
    header_size = 4 + 4 + 64 + 64 + 4 * 7
    ofs_hier = header_size + 4 * ns   # points at the first hierarchy entry, after the offsets array
    ofs_lods = header_size + len(hier_blob)

    surf_blobs = []
    for i, s in enumerate(surfaces):
        bones = sorted({v[2] for v in s.verts})
        if len(bones) > 32:
            raise ValueError(f'surface {s.name} references too many bones')
        bref = {b: k for k, b in enumerate(bones)}
        refs = struct.pack(f'<{len(bones)}i', *bones)
        tris = b''.join(struct.pack('<3i', *t) for t in s.tris)
        verts = b''.join(struct.pack('<3f3fI4B', *v[1], *v[0], bref[v[2]], 0, 0, 0, 0) for v in s.verts)
        tcs = b''.join(struct.pack('<2f', *v[3]) for v in s.verts)
        hdr = 4 * 10
        ofs_refs = hdr
        ofs_tris = ofs_refs + len(refs)
        ofs_verts = ofs_tris + len(tris)
        ofs_end = ofs_verts + len(verts) + len(tcs)
        surf_blobs.append([i, len(s.verts), ofs_verts, len(s.tris), ofs_tris, len(bones), ofs_refs, ofs_end,
                           refs + tris + verts + tcs])
    lod_offs_size = 4 * ns
    pos = lod_offs_size
    lod_offsets = []
    for sb in surf_blobs:
        lod_offsets.append(pos)
        pos += sb[7]
    lod_body = bytearray()
    for k, sb in enumerate(surf_blobs):
        surf_abs = ofs_lods + 4 + lod_offsets[k]
        idx, nv, ov, nt, ot, nbr, obr, oe, data = sb
        lod_body += struct.pack('<10i', 0, idx, -surf_abs, nv, ov, nt, ot, nbr, obr, oe) + data
    lod = struct.pack(f'<{ns}i', *lod_offsets) + bytes(lod_body)
    lod_blob = struct.pack('<i', 4 + len(lod)) + lod
    ofs_end = ofs_lods + len(lod_blob)
    header = struct.pack('<4si64s64siiiiiii', b'2LGM', 6, name.encode(), anim_name.encode(), 0, num_bones,
                         1, ofs_lods, ns, ofs_hier, ofs_end)
    return header + hier_blob + lod_blob


# ----------------------------------------------------------------------------- humanoid skeleton
# local axes for bones the game rotates with (POSITIVE_X, NEGATIVE_Y, NEGATIVE_Z):
# X = up, Y = left, Z = back
SPINE_AXES = np.array([[0, 0, -1], [0, 1, 0], [1, 0, 0]], float)   # columns = local X, Y, Z in model space
MOTION_AXES = np.array([[0, -1, 0], [-1, 0, 0], [0, 0, -1]], float)

# name, parent, pivot (feet at z=0), axes
SKELETON = [
    ('model_root', None, (0, 0, 0), None),
    ('Motion', 'model_root', (0, 0, 38), MOTION_AXES),
    ('pelvis', 'model_root', (0, 0, 38), SPINE_AXES),
    ('lower_lumbar', 'pelvis', (0, 0, 41), SPINE_AXES),
    ('upper_lumbar', 'lower_lumbar', (0, 0, 45), SPINE_AXES),
    ('thoracic', 'upper_lumbar', (0, 0, 50), SPINE_AXES),
    ('cervical', 'thoracic', (0, 0, 59), SPINE_AXES),
    ('cranium', 'cervical', (0, 0, 62), SPINE_AXES),
    ('rclavical', 'thoracic', (0, -3, 57), None),
    ('rhumerus', 'rclavical', (0, -9, 57), None),
    ('rradius', 'rhumerus', (0, -10, 46), None),
    ('rhand', 'rradius', (0, -10, 36), None),
    ('lclavical', 'thoracic', (0, 3, 57), None),
    ('lhumerus', 'lclavical', (0, 9, 57), None),
    ('lradius', 'lhumerus', (0, 10, 46), None),
    ('lhand', 'lradius', (0, 10, 36), None),
    ('rfemurYZ', 'pelvis', (0, -4.5, 37), None),
    ('rtibia', 'rfemurYZ', (0, -4.5, 20), None),
    ('rtalus', 'rtibia', (0, -4.5, 4), None),
    ('lfemurYZ', 'pelvis', (0, 4.5, 37), None),
    ('ltibia', 'lfemurYZ', (0, 4.5, 20), None),
    ('ltalus', 'ltibia', (0, 4.5, 4), None),
    ('face', 'cranium', (3, 0, 66), SPINE_AXES),
]
BONE = {b[0]: i for i, b in enumerate(SKELETON)}


def skeleton_bones():
    out = []
    for name, parent, pivot, axes in SKELETON:
        p = np.array(pivot, float) + np.array([0, 0, FEET])
        R = axes if axes is not None else np.eye(3)
        out.append(dict(name=name, parent=BONE[parent] if parent else -1, base=mat34(TO_MODEL @ R, TO_MODEL @ p)))
    return out


def pivot(b):
    return np.array(SKELETON[b][2], float) + np.array([0, 0, FEET])


def pose_to_anim(pose):
    """pose: dict bone_name -> (R 3x3 in model axes, translation). Returns list of anim 3x4 matrices."""
    anims = []
    for i, (name, parent, _p, _a) in enumerate(SKELETON):
        R, t = pose.get(name, (np.eye(3), np.zeros(3)))
        p = pivot(i)
        # rotate about pivot, then translate (authored space), then conjugate into model space
        t_auth = p - R @ p + np.asarray(t, float)
        anims.append(mat34(TO_MODEL @ R @ TO_MODEL.T, TO_MODEL @ t_auth))
    return anims


# ----------------------------------------------------------------------------- humanoid mesh
def build_humanoid_mesh(style):
    """style: dict with shader names per part + proportions. Returns list of Surfaces."""
    S = {}
    order = ['hips', 'torso', 'head', 'r_arm', 'l_arm', 'r_hand', 'l_hand', 'r_leg', 'l_leg']
    surfs = []
    for name in order:
        parent = -1 if name == 'hips' else 0
        if name in ('head', 'r_arm', 'l_arm'):
            parent = 1
        if name == 'r_hand':
            parent = 3
        if name == 'l_hand':
            parent = 4
        s = Surface(name, style.get(name, style['body']), parent)
        S[name] = s
        surfs.append(s)
    F = FEET
    b = BONE
    w = style.get('width', 1.0)

    def bx(surf, mins, maxs, bone, uv=(0, 0, 1, 1)):
        S[surf].box((mins[0], mins[1] * w, mins[2] + F), (maxs[0], maxs[1] * w, maxs[2] + F), bone, uv)

    # body (uv regions: atlas split into quadrants per part type)
    bx('hips', (-4, -7.5, 33), (4, 7.5, 41), b['pelvis'], (0, 0.5, 0.5, 1))
    bx('torso', (-4.5, -7, 41), (4, 7, 49), b['upper_lumbar'], (0, 0, 0.5, 0.5))
    bx('torso', (-5, -8.5, 49), (4.5, 8.5, 59), b['thoracic'], (0, 0, 0.5, 0.5))
    bx('torso', (-1.5, -2, 58), (1.5, 2, 62), b['cervical'], (0, 0, 0.5, 0.5))
    # head + visor (front = +X so facing is obvious)
    bx('head', (-4.2, -4, 61.5), (4.2, 4, 71), b['cranium'], (0.5, 0, 1, 0.5))
    bx('head', (3.6, -3.2, 64.5), (4.8, 3.2, 67.5), b['face'], (0.5, 0.5, 0.6, 0.6))
    if style.get('helmet'):
        bx('head', (-4.8, -4.6, 67), (4.8, 4.6, 72), b['cranium'], (0.5, 0, 1, 0.5))
    for side, sg in (('r', -1), ('l', 1)):
        arm = f'{side}_arm'
        y0, y1 = sorted((sg * 7.5, sg * 12))
        bx(arm, (-2.2, y0, 56), (2.2, y1, 60), b[f'{side}clavical'], (0.5, 0.5, 1, 1))
        y0, y1 = sorted((sg * 8, sg * 12))
        bx(arm, (-2, y0, 46), (2, y1, 58), b[f'{side}humerus'], (0.5, 0.5, 1, 1))
        y0, y1 = sorted((sg * 8.3, sg * 11.7))
        bx(arm, (-1.8, y0, 36.5), (1.8, y1, 46.5), b[f'{side}radius'], (0.5, 0.5, 1, 1))
        y0, y1 = sorted((sg * 8.5, sg * 11.5))
        bx(f'{side}_hand', (-1.6, y0, 32), (2.2, y1, 36.5), b[f'{side}hand'], (0.6, 0.5, 0.7, 0.6))
        leg = f'{side}_leg'
        y0, y1 = sorted((sg * 1.2, sg * 7.5))
        bx(leg, (-3, y0, 20), (3, y1, 37), b[f'{side}femurYZ'], (0, 0.5, 0.5, 1))
        y0, y1 = sorted((sg * 1.6, sg * 7))
        bx(leg, (-2.6, y0, 3.5), (2.6, y1, 20.5), b[f'{side}tibia'], (0, 0.5, 0.5, 1))
        bx(leg, (-3, y0, 0), (6, y1, 4), b[f'{side}talus'], (0.5, 0.5, 1, 1))

    # bolt tags. Hand tags: X = forward, Y = left, Z = up (in the neutral pose, arms hanging)
    tags = [
        ('*r_hand', 'r_hand', (0.5, -10, 33.5), (1, 0, 0), (0, 1, 0), 'rhand'),
        ('*l_hand', 'l_hand', (0.5, 10, 33.5), (1, 0, 0), (0, 1, 0), 'lhand'),
        ('*head_eyes', 'head', (4.2, 0, 66), (1, 0, 0), (0, 1, 0), 'cranium'),
        ('*head_front', 'head', (4.2, 0, 66), (1, 0, 0), (0, 1, 0), 'cranium'),
        ('*head_top', 'head', (0, 0, 71), (1, 0, 0), (0, 1, 0), 'cranium'),
        ('*chestg', 'torso', (4.5, 0, 54), (1, 0, 0), (0, 1, 0), 'thoracic'),
        ('*back', 'torso', (-5, 0, 54), (1, 0, 0), (0, 1, 0), 'thoracic'),
        ('*hip_r', 'hips', (0, -8, 36), (1, 0, 0), (0, 1, 0), 'pelvis'),
        ('*hip_l', 'hips', (0, 8, 36), (1, 0, 0), (0, 1, 0), 'pelvis'),
        ('*hip_fr', 'hips', (4, -6, 36), (1, 0, 0), (0, 1, 0), 'pelvis'),
        ('*hip_fl', 'hips', (4, 6, 36), (1, 0, 0), (0, 1, 0), 'pelvis'),
        ('*hip_bl', 'hips', (-4, 6, 36), (1, 0, 0), (0, 1, 0), 'pelvis'),
        ('*hip_br', 'hips', (-4, -6, 36), (1, 0, 0), (0, 1, 0), 'pelvis'),
        ('*r_leg_foot', 'r_leg', (2, -4.5, 0.5), (1, 0, 0), (0, 1, 0), 'rtalus'),
        ('*l_leg_foot', 'l_leg', (2, 4.5, 0.5), (1, 0, 0), (0, 1, 0), 'ltalus'),
        ('*r_arm_elbow', 'r_arm', (0, -10, 46), (1, 0, 0), (0, 1, 0), 'rradius'),
        ('*l_arm_elbow', 'l_arm', (0, 10, 46), (1, 0, 0), (0, 1, 0), 'lradius'),
        ('*hips_r_knee', 'r_leg', (2.6, -4.5, 20), (1, 0, 0), (0, 1, 0), 'rtibia'),
        ('*hips_l_knee', 'l_leg', (2.6, 4.5, 20), (1, 0, 0), (0, 1, 0), 'ltibia'),
    ]
    for tname, parent, origin, xa, ya, bone in tags:
        t = Surface(tname, '', order.index(parent))
        o = np.array(origin, float) + np.array([0, 0, F])
        o[1] *= w if abs(o[1]) > 2 else 1
        t.tag(o, xa, ya, b[bone])
        surfs.append(t)
    for sf in surfs:
        sf.verts = [(TO_MODEL @ v[0], TO_MODEL @ v[1], v[2], v[3]) for v in sf.verts]
    return surfs


# ----------------------------------------------------------------------------- animation clips
def P(name, pitch=0.0, yaw=0.0, roll=0.0, t=(0, 0, 0)):
    return name, (euler(pitch, yaw, roll), np.array(t, float))


def blend(a, b, k):
    """Linear blend of two pose dicts (rotations via quaternion nlerp)."""
    out = {}
    for name in set(a) | set(b):
        Ra, ta = a.get(name, (np.eye(3), np.zeros(3)))
        Rb, tb = b.get(name, (np.eye(3), np.zeros(3)))
        qa, qb = np.array(mat_to_quat(Ra)), np.array(mat_to_quat(Rb))
        if qa @ qb < 0:
            qb = -qb
        q = qa * (1 - k) + qb * k
        q /= np.linalg.norm(q)
        w, x, y, z = q
        R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                      [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                      [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
        out[name] = (R, ta * (1 - k) + tb * k)
    return out


def pose(*parts):
    return dict(parts)


# Rotation sign notes (right hand rule, model axes):
#   pitch about +Y: positive rotates +X (forward) towards -Z, i.e. a limb hanging down (-Z) swings
#   towards -X (backwards). So to swing a hanging arm/leg FORWARD use a NEGATIVE pitch.
#   roll about +X: positive rotates +Y towards +Z (raises a left arm sideways, lowers a right arm).
#   yaw about +Z: positive turns left.

ARMS_RELAX = [P('rhumerus', roll=8), P('lhumerus', roll=-8), P('rradius', pitch=-15), P('lradius', pitch=-15)]


def stand(t):
    br = math.sin(t * 2 * math.pi) * 1.5
    return pose(*ARMS_RELAX, P('thoracic', pitch=-br), P('cranium', pitch=br))


def saber_ready(t):
    br = math.sin(t * 2 * math.pi) * 1.5
    return pose(P('rhumerus', pitch=-35, roll=10), P('rradius', pitch=-55), P('rhand', pitch=-30),
                P('lhumerus', pitch=-20, roll=-10), P('lradius', pitch=-40),
                P('upper_lumbar', yaw=-10, pitch=-br), P('rfemurYZ', pitch=-12), P('rtibia', pitch=14),
                P('lfemurYZ', pitch=8), P('ltibia', pitch=6), P('pelvis', t=(0, 0, -1.5)))


def gun_ready(t):
    return pose(P('rhumerus', pitch=-75, yaw=8), P('rradius', pitch=-15), P('lhumerus', pitch=-70, yaw=-25),
                P('lradius', pitch=-30, yaw=-30), P('cranium', pitch=0))


def locomotion(t, stride=30, knee=35, arm=25, bounce=1.5, side=False, back=False):
    s = math.sin(t * 2 * math.pi)
    c = math.cos(t * 2 * math.pi)
    sign = -1 if back else 1
    if side:
        legs = [P('rfemurYZ', roll=stride * 0.5 * s), P('lfemurYZ', roll=stride * 0.5 * s),
                P('rtibia', pitch=knee * 0.4 * max(0, c)), P('ltibia', pitch=knee * 0.4 * max(0, -c))]
    else:
        legs = [P('rfemurYZ', pitch=-stride * s * sign), P('lfemurYZ', pitch=stride * s * sign),
                P('rtibia', pitch=knee * max(0, c)), P('ltibia', pitch=knee * max(0, -c))]
    arms = [P('rhumerus', pitch=arm * s * sign, roll=8), P('lhumerus', pitch=-arm * s * sign, roll=-8),
            P('rradius', pitch=-20 - 10 * max(0, s)), P('lradius', pitch=-20 - 10 * max(0, -s))]
    return pose(*legs, *arms, P('pelvis', t=(0, 0, -bounce * abs(c))), P('thoracic', pitch=-4 if not back else 2))


def run(t):
    return locomotion(t, stride=40, knee=60, arm=35, bounce=2.5)


def crouch(t, walk=False):
    s = math.sin(t * 2 * math.pi) if walk else 0
    return pose(P('pelvis', t=(0, 0, -14)), P('rfemurYZ', pitch=-70 - 15 * s), P('lfemurYZ', pitch=-70 + 15 * s),
                P('rtibia', pitch=100), P('ltibia', pitch=100), P('rtalus', pitch=-30), P('ltalus', pitch=-30),
                P('lower_lumbar', pitch=-20), *ARMS_RELAX)


def jump(t):
    k = math.sin(min(1.0, t) * math.pi)
    return pose(P('rfemurYZ', pitch=-50 * k), P('lfemurYZ', pitch=-20 * k), P('rtibia', pitch=80 * k),
                P('ltibia', pitch=50 * k), P('rhumerus', roll=30 * k + 8, pitch=-20 * k),
                P('lhumerus', roll=-30 * k - 8, pitch=-20 * k))


def inair(t):
    return jump(0.5)


def land(t):
    k = math.sin(t * math.pi)
    return pose(P('pelvis', t=(0, 0, -8 * k)), P('rfemurYZ', pitch=-40 * k), P('lfemurYZ', pitch=-40 * k),
                P('rtibia', pitch=60 * k), P('ltibia', pitch=60 * k), *ARMS_RELAX)


def swing(t, kind=0):
    """Saber swing: ease from wind-up to follow-through."""
    k = 0.5 - 0.5 * math.cos(min(1.0, t * 1.25) * math.pi)
    kinds = [  # (start pose, end pose): right arm pitch/yaw/roll + torso yaw
        ((-150, 30, 40, 25), (-30, -40, -10, -30)),    # high right to low left
        ((-150, -20, -20, -25), (-40, 40, 20, 30)),   # high left to low right
        ((-90, 70, 0, 35), (-90, -60, 0, -35)),       # horizontal right to left
        ((-170, 0, 0, 0), (-20, 0, 0, 0)),            # overhead chop
        ((-20, 0, 0, 20), (-140, 10, 20, -10)),       # upward slash
    ]
    (p0, y0, r0, ty0), (p1, y1, r1, ty1) = kinds[kind % len(kinds)]
    pp, yy, rr, ty = (p0 + (p1 - p0) * k, y0 + (y1 - y0) * k, r0 + (r1 - r0) * k, ty0 + (ty1 - ty0) * k)
    return pose(P('rhumerus', pitch=pp, yaw=yy, roll=rr), P('rradius', pitch=-25), P('rhand', pitch=-20),
                P('lhumerus', pitch=-20, roll=-15), P('lradius', pitch=-40),
                P('upper_lumbar', yaw=ty * 0.6), P('thoracic', yaw=ty * 0.4),
                P('rfemurYZ', pitch=-20), P('rtibia', pitch=20), P('lfemurYZ', pitch=10))


def block(t, high=True):
    return pose(P('rhumerus', pitch=-120 if high else -60, yaw=-30), P('rradius', pitch=-60),
                P('rhand', pitch=-40), P('lhumerus', pitch=-30, roll=-10), P('lradius', pitch=-50),
                P('rfemurYZ', pitch=-15), P('rtibia', pitch=20))


def force(t):
    k = math.sin(min(1.0, t * 1.5) * math.pi / 2)
    return pose(P('lhumerus', pitch=-85 * k, yaw=-10 * k), P('lradius', pitch=-5), P('lhand', pitch=60 * k),
                P('rhumerus', pitch=-30, roll=10), P('rradius', pitch=-50), P('upper_lumbar', yaw=15 * k))


def pain(t):
    k = math.sin(t * math.pi)
    return pose(P('thoracic', pitch=15 * k), P('cranium', pitch=15 * k), P('rhumerus', roll=20 * k),
                P('lhumerus', roll=-20 * k), P('pelvis', t=(-2 * k, 0, 0)))


def death(t):
    k = min(1.0, t * 1.4)
    k = k * k * (3 - 2 * k)
    # topple backwards around the heels
    return pose(P('model_root', pitch=-88 * k, t=(-2 * k, 0, 0)), P('rfemurYZ', pitch=-15 * k),
                P('rtibia', pitch=30 * k), P('rhumerus', roll=60 * k), P('lhumerus', roll=-60 * k),
                P('cranium', pitch=-20 * k))


def knockdown(t):
    return death(min(1.0, t * 2))


def getup(t):
    return blend(death(1.0), stand(0), min(1.0, t * 1.2))


def gun_fire(t):
    k = math.exp(-t * 6)
    return blend(gun_ready(0), pose(P('rhumerus', pitch=-85, yaw=8), P('rradius', pitch=-25),
                                    P('lhumerus', pitch=-75, yaw=-25), P('lradius', pitch=-35, yaw=-30),
                                    P('thoracic', pitch=5)), k)


def throw(t):
    k = math.sin(min(1.0, t) * math.pi)
    return pose(P('rhumerus', pitch=-160 + 140 * t, roll=10), P('rradius', pitch=-30 * k),
                P('upper_lumbar', yaw=-20 + 40 * t))


def turn(t):
    s = math.sin(t * 2 * math.pi)
    return pose(P('rfemurYZ', pitch=-15 * s), P('lfemurYZ', pitch=15 * s), *ARMS_RELAX)


def roll_(t):
    return pose(P('model_root', pitch=-360 * t, t=(0, 0, 18 * math.sin(t * math.pi))),
                P('rfemurYZ', pitch=-100), P('lfemurYZ', pitch=-100), P('rtibia', pitch=120),
                P('ltibia', pitch=120))


def flip(t):
    return pose(P('model_root', pitch=360 * t, t=(0, 0, 12 * math.sin(t * math.pi))),
                P('rfemurYZ', pitch=-90), P('lfemurYZ', pitch=-90), P('rtibia', pitch=110),
                P('ltibia', pitch=110))


# clip name -> (fn, frames, fps, loops)
CLIPS = {
    'stand': (stand, 20, 10, True),
    'saber_ready': (saber_ready, 20, 10, True),
    'gun_ready': (gun_ready, 2, 10, True),
    'walk': (lambda t: locomotion(t), 20, 20, True),
    'walkback': (lambda t: locomotion(t, back=True), 20, 20, True),
    'run': (run, 16, 22, True),
    'runback': (lambda t: locomotion(t, stride=35, knee=50, back=True), 16, 22, True),
    'strafe': (lambda t: locomotion(t, side=True), 16, 20, True),
    'crouch': (crouch, 2, 10, True),
    'crouchwalk': (lambda t: crouch(t, True), 20, 15, True),
    'jump': (jump, 10, 20, False),
    'inair': (inair, 2, 10, True),
    'land': (land, 8, 20, False),
    'swing0': (lambda t: swing(t, 0), 12, 24, False),
    'swing1': (lambda t: swing(t, 1), 12, 24, False),
    'swing2': (lambda t: swing(t, 2), 12, 24, False),
    'swing3': (lambda t: swing(t, 3), 12, 24, False),
    'swing4': (lambda t: swing(t, 4), 12, 24, False),
    'block_high': (lambda t: block(t, True), 6, 20, False),
    'block_low': (lambda t: block(t, False), 6, 20, False),
    'force': (force, 14, 20, False),
    'pain': (pain, 8, 20, False),
    'death': (death, 20, 20, False),
    'knockdown': (knockdown, 16, 20, False),
    'getup': (getup, 16, 20, False),
    'gun_fire': (gun_fire, 6, 20, False),
    'throw': (throw, 10, 20, False),
    'turn': (turn, 10, 15, True),
    'roll': (roll_, 14, 20, False),
    'flip': (flip, 16, 20, False),
}


def classify(anim):
    """Maps one of the 1645 JA animation names onto a placeholder clip."""
    a = anim.upper()
    body = a.split('_', 1)[1] if '_' in a else a
    import re
    if a.startswith('FACE_'):
        return 'stand'
    if 'DEATH' in body or body.startswith(('DEAD', 'LYING')) or 'DISMEMBER' in body or body.startswith('FALLDEATH'):
        return 'death'
    if body.startswith(('KNOCKDOWN', 'PLAYER_PAIN')) or 'KNOCKDOWN' in body or body.startswith(('SLAPDOWN', 'BF1', 'BF2')):
        return 'knockdown'
    if body.startswith(('GETUP', 'FORCE_GETUP')) or 'GETUP' in body:
        return 'getup'
    if body.startswith('PAIN') or body.startswith(('CHOKE', 'SONICPAIN', 'STUMBLE', 'HIT')):
        return 'pain'
    if body.startswith(('ROLL', 'FLIP_ROLL', 'GETUP_ROLL', 'DODGE')):
        return 'roll'
    if body.startswith(('FLIP', 'ARIAL', 'CARTWHEEL', 'BUTTERFLY', 'WALL_FLIP', 'JUMPFLIP')):
        return 'flip'
    if body.startswith(('FORCE', 'MINDTRICK', 'RESISTPUSH', 'GESTURE')) or 'GRIP' in body or 'LIGHTNING' in body \
            or 'DRAIN' in body:
        return 'force'
    if body.startswith(('THERMAL_THROW', 'THROW', 'TOSS')):
        return 'throw'
    m = re.match(r'([ATSRBD])(\d)_', body)
    if m or body.startswith(('LK_', 'SPINATTACK', 'ATTACK_BACK', 'STABDOWN', 'JUMPATTACK', 'LUNGE', 'FORCELEAP2',
                             'A7_', 'BACK_STAB', 'ALORA_SPIN', 'KYLE_', 'TUSKEN', 'SABERTHROW', 'SABERPULL',
                             'SPECIAL', 'PULL_IMPALE', 'HANG_ATTACK', 'STAFF_')):
        if m and m.group(1) in 'BD' or body.startswith(('B', 'D')) and m:
            return 'block_high' if int(m.group(2)) % 2 else 'block_low'
        n = sum(map(ord, body)) % 5
        return f'swing{n}'
    if body.startswith(('P1_', 'P2_', 'P3_', 'P4_', 'P5_', 'P6_', 'P7_', 'K1_', 'K2_', 'K3_', 'K4_', 'K5_', 'K6_',
                        'K7_', 'V1_', 'V2_', 'V3_', 'V4_', 'V5_', 'V6_', 'V7_', 'H1_', 'H2_', 'H3_', 'H4_',
                        'H5_', 'H6_', 'H7_', 'BLOCK', 'PARRY', 'SABERBLOCK', 'CC', 'VS', 'VT', 'LK_')):
        return 'block_high'
    if body.startswith(('ATTACK', 'MELEE', 'SNIPER', 'SHOOT', 'FIRE', 'GUN')) or 'ATTACK' in body:
        return 'gun_fire' if not body.startswith('MELEE') else 'swing2'
    if body.startswith(('JUMP', 'FORCEJUMP', 'FORCEINAIR', 'FORCELONGLEAP', 'WALL_RUN', 'WALL', 'LEAP')):
        if 'LAND' in body:
            return 'land'
        if 'INAIR' in body or body.startswith('FORCEINAIR'):
            return 'inair'
        return 'jump'
    if body.startswith(('INAIR', 'FALL', 'SWIM')):
        return 'inair'
    if body.startswith('LAND') or 'LAND' in body:
        return 'land'
    if body.startswith(('CROUCH', 'DUCK', 'KNEEL', 'SIT', 'HIDE', 'COWER')):
        return 'crouchwalk' if 'WALK' in body else 'crouch'
    if body.startswith(('RUNBACK', 'RUN_BACK')):
        return 'runback'
    if body.startswith(('WALKBACK', 'WALK_BACK')):
        return 'walkback'
    if body.startswith(('RUN', 'SPRINT')):
        return 'run'
    if body.startswith('WALK'):
        return 'walk'
    if body.startswith(('STRAFE', 'SIDESTEP')):
        return 'strafe'
    if body.startswith(('TURN',)):
        return 'turn'
    if body.startswith(('WEAPONREADY', 'RAISEWEAP', 'DROPWEAP', 'GUARD', 'WEAPONIDLE')):
        if re.search(r'(\d+)$', body) and int(re.search(r'(\d+)$', body).group(1)) in (1, 2):
            return 'saber_ready'
        return 'gun_ready'
    if body.startswith(('SABERFAST_STANCE', 'SABERSLOW_STANCE', 'SABERDUAL_STANCE', 'SABERSTAFF_STANCE',
                        'SABERTHROW', 'STAND2', 'SABER', 'IGNITE', 'TURNON', 'TURNOFF')):
        return 'saber_ready'
    return 'stand'


def build_animations(anim_names):
    """Returns (frames list, animation.cfg text)."""
    frames, starts = [], {}
    for name, (fn, n, fps, loops) in CLIPS.items():
        starts[name] = len(frames)
        for i in range(n):
            t = i / n if loops else i / max(1, n - 1)
            frames.append(pose_to_anim(fn(t)))
    lines = ['// placeholder animation set, generated by web/assets/gen/ghoul2.py',
             '// AnimName  Start  Length  Loop  FPS']
    for a in anim_names:
        clip = classify(a)
        fn, n, fps, loops = CLIPS[clip]
        lines.append(f'{a}\t{starts[clip]}\t{n}\t{0 if loops else -1}\t{fps}')
    return frames, '\n'.join(lines) + '\n'


# ----------------------------------------------------------------------------- simple rigid models
def write_rigid_glm(name, surfaces):
    """GLM using the engine's built-in single bone '*default' skeleton."""
    return write_glm(name, '*default', 1, surfaces)
