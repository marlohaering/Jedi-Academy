"""Minimal RBSP (Jedi Academy BSP version 1) writer for maps built from convex brushes.

Brushes are axis-aligned boxes, optionally with one extra cutting plane (ramps/wedges).
Every visible face becomes a subdivided triangle-soup surface with baked vertex lighting
(point lights + sun, with shadows), so no lightmaps are needed. A light grid is baked too
so that models are lit consistently with the world.
"""
import math
import struct

import numpy as np

CONTENTS_SOLID = 0x1
CONTENTS_PLAYERCLIP = 0x10
CONTENTS_OPAQUE = 0x8000
CONTENTS_OUTSIDE = 0x10000
CONTENTS_INSIDE = 0x10000000
SURF_SKY = 0x2000
SURF_NOIMPACT = 0x80000
SURF_NOMARKS = 0x100000
SURF_NODRAW = 0x200000

LS_NORMAL, LS_NONE = 0, 0xFF
LIGHTMAP_BY_VERTEX = -3
MST_TRIANGLE_SOUP = 3

AXES = [(-1, 0, 0), (1, 0, 0), (0, -1, 0), (0, 1, 0), (0, 0, -1), (0, 0, 1)]


class Shader:
    def __init__(self, name, material=0, contents=CONTENTS_SOLID | CONTENTS_OPAQUE, flags=0,
                 texscale=128.0, sky=False, nodraw=False, occluder=True):
        self.name = name
        self.flags = flags | material | (SURF_SKY | SURF_NOIMPACT | SURF_NOMARKS if sky else 0) \
            | (SURF_NODRAW if nodraw else 0)
        self.contents = contents
        self.texscale = texscale
        self.sky = sky
        self.nodraw = nodraw
        self.occluder = occluder and not sky


class Brush:
    """Axis-aligned box; `cut` = (normal, dist) adds a slanted plane that removes the part in front."""

    def __init__(self, mins, maxs, shader, cut=None, model=0, side_shaders=None):
        self.mins = np.array(mins, float)
        self.maxs = np.array(maxs, float)
        self.shader = shader
        self.cut = cut
        self.model = model
        self.side_shaders = side_shaders or {}

    def planes(self):
        out = []
        for i, n in enumerate(AXES):
            axis = i // 2
            d = -self.mins[axis] if i % 2 == 0 else self.maxs[axis]
            out.append((np.array(n, float), d, self.side_shaders.get(i, self.shader)))
        if self.cut:
            n = np.array(self.cut[0], float)
            ln = np.linalg.norm(n)
            out.append((n / ln, self.cut[1] / ln, self.side_shaders.get(6, self.shader)))
        return out

    def contains(self, pts, eps=0.5):
        """Boolean mask: points strictly inside the brush."""
        inside = np.ones(len(pts), bool)
        for n, d, _s in self.planes():
            inside &= pts @ n < d - eps
        return inside


def clip_polygon(poly, n, d):
    """Keep the part of convex polygon (list of np arrays) where dot(p,n) <= d."""
    out = []
    for i, a in enumerate(poly):
        b = poly[(i + 1) % len(poly)]
        da, db = a @ n - d, b @ n - d
        if da <= 0.01:
            out.append(a)
        if (da < -0.01 and db > 0.01) or (da > 0.01 and db < -0.01):
            t = da / (da - db)
            out.append(a + (b - a) * t)
    return out


def base_winding(n, d, size=65536.0):
    n = np.asarray(n, float)
    up = np.array([0, 0, 1.0]) if abs(n[2]) < 0.9 else np.array([1.0, 0, 0])
    right = np.cross(up, n)
    right /= np.linalg.norm(right)
    up = np.cross(n, right)
    c = n * d
    return [c + (-right + up) * size, c + (right + up) * size, c + (right - up) * size, c + (-right - up) * size]


class Light:
    def __init__(self, origin, intensity=300, color=(1, 1, 1), radius=None):
        self.origin = np.array(origin, float)
        self.intensity = intensity
        self.color = np.array(color, float)
        self.radius = radius or intensity * 2.5


class Map:
    def __init__(self, name):
        self.name = name
        self.brushes = []
        self.lights = []
        self.entities = []
        self.sun = None          # (direction towards sun, color, intensity)
        self.ambient = np.array([28, 28, 34], float)
        self.models = 1

    def box(self, mins, maxs, shader, **kw):
        b = Brush(mins, maxs, shader, **kw)
        self.brushes.append(b)
        return b

    def add_model(self):
        self.models += 1
        return self.models - 1

    # ------------------------------------------------------------------ geometry
    def _faces(self):
        """Yield (brush, polygon, normal, shader) for all candidate visible faces."""
        for b in self.brushes:
            planes = b.planes()
            for i, (n, d, sh) in enumerate(planes):
                if sh.nodraw:
                    continue
                poly = base_winding(n, d)
                for j, (n2, d2, _s) in enumerate(planes):
                    if j != i:
                        poly = clip_polygon(poly, n2, d2)
                    if len(poly) < 3:
                        break
                if len(poly) >= 3:
                    yield b, poly, n, sh

    def _build_surfaces(self, cell=48.0):
        surfaces = []   # dicts: shader, verts(np Nx3), normals, st, indexes, model
        world_brushes = [b for b in self.brushes if b.model == 0]
        for b, poly, n, sh in self._faces():
            # parametrise the convex polygon on a 2D grid in its plane
            u = np.array([1.0, 0, 0]) if abs(n[0]) < 0.9 else np.array([0, 1.0, 0])
            u = u - n * (u @ n)
            u /= np.linalg.norm(u)
            v = np.cross(n, u)
            p2 = np.array([[p @ u, p @ v] for p in poly])
            lo, hi = p2.min(0), p2.max(0)
            nu = max(1, min(24, math.ceil((hi[0] - lo[0]) / cell)))
            nv = max(1, min(24, math.ceil((hi[1] - lo[1]) / cell)))
            origin_d = poly[0] @ n
            gu = np.linspace(lo[0], hi[0], nu + 1)
            gv = np.linspace(lo[1], hi[1], nv + 1)
            grid = np.array([[n * origin_d + u * a + v * c for a in gu] for c in gv])  # (nv+1, nu+1, 3)
            # clip grid vertices onto the polygon (needed for slanted/triangular faces)
            pts = grid.reshape(-1, 3)
            inside_poly = np.ones(len(pts), bool)
            edges = []
            centroid = np.mean(poly, 0)
            for k in range(len(poly)):
                a, c = poly[k], poly[(k + 1) % len(poly)]
                if np.linalg.norm(c - a) < 0.01:
                    continue
                en = np.cross(c - a, n)
                en /= np.linalg.norm(en)
                if en @ centroid > en @ a:
                    en = -en
                edges.append((en, en @ a))
                inside_poly &= pts @ en <= en @ a + 0.01
            # a cell is drawn if its centre lies in the polygon and is not buried in another solid
            tris = []
            centres = []
            for j in range(nv):
                for i in range(nu):
                    centres.append((grid[j, i] + grid[j + 1, i + 1]) / 2)
            centres = np.array(centres) + n * 1.0
            buried = np.zeros(len(centres), bool)
            for other in (world_brushes if b.model == 0 else [x for x in self.brushes if x.model == b.model]):
                if other is b or other.shader.sky and not b.shader.sky:
                    continue
                if not other.shader.occluder and not other.shader.sky:
                    continue
                buried |= other.contains(centres, eps=0.0)
            cen_in = np.ones(len(centres), bool)
            for en, ed in edges:
                cen_in &= (centres - n) @ en <= ed + 0.01
            k = 0
            for j in range(nv):
                for i in range(nu):
                    if cen_in[k] and not buried[k]:
                        a, bb = j * (nu + 1) + i, j * (nu + 1) + i + 1
                        c, d = (j + 1) * (nu + 1) + i, (j + 1) * (nu + 1) + i + 1
                        tris += [a, c, bb, bb, c, d]
                    k += 1
            if not tris:
                continue
            # project out-of-polygon vertices back onto the polygon edges
            for en, ed in edges:
                over = pts @ en - ed
                m = over > 0
                pts[m] -= np.outer(over[m], en)
            used = sorted(set(tris))
            remap = {old: new for new, old in enumerate(used)}
            verts = pts[used]
            # split into chunks the renderer can handle (SHADER_MAX_VERTEXES = 1000)
            idx = [remap[t] for t in tris]
            ts = sh.texscale
            st = np.stack([verts @ u / ts, -(verts @ v) / ts], 1) if abs(n[2]) > 0.7 else \
                np.stack([verts @ u / ts, -verts[:, 2] / ts], 1)
            surfaces.append(dict(shader=sh, verts=verts, normal=n, st=st, indexes=idx, model=b.model))
        return surfaces

    # ------------------------------------------------------------------ lighting
    def _occluders(self):
        bs = [b for b in self.brushes if b.model == 0 and b.shader.occluder and not b.shader.nodraw]
        return bs

    def _shadow(self, start, end, occ):
        """Mask of segments start->end that are NOT blocked by any box (cut planes ignored)."""
        d = end - start
        clear = np.ones(len(start), bool)
        with np.errstate(divide='ignore', invalid='ignore'):
            inv = 1.0 / np.where(np.abs(d) < 1e-9, 1e-9, d)
            for b in occ:
                t1 = (b.mins - start) * inv
                t2 = (b.maxs - start) * inv
                tmin = np.minimum(t1, t2).max(1)
                tmax = np.maximum(t1, t2).min(1)
                hit = (tmax >= np.maximum(tmin, 0.0)) & (tmin < 1.0) & (tmax > 0.0)
                if b.cut is not None:   # treat wedges as their bounding box but be lenient
                    hit &= tmin > 0.02
                clear &= ~hit
        return clear

    def light_points(self, pts, normals=None):
        """Returns (colour Nx3 in 0..255, dominant direction Nx3, direct Nx3) for points."""
        occ = self._occluders()
        total = np.tile(self.ambient, (len(pts), 1))
        direct = np.zeros((len(pts), 3))
        dirsum = np.zeros((len(pts), 3))
        start = pts + (normals * 2.0 if normals is not None else 0)
        for L in self.lights:
            delta = L.origin - pts
            dist = np.linalg.norm(delta, axis=1) + 1e-6
            ldir = delta / dist[:, None]
            lam = np.clip((normals * ldir).sum(1), 0, 1) if normals is not None else np.ones(len(pts))
            att = np.clip(1.0 - dist / L.radius, 0, 1) ** 1.6
            amount = L.intensity * att * (0.25 + 0.75 * lam if normals is None else lam)
            m = amount > 0.5
            if not m.any():
                continue
            vis = np.zeros(len(pts), bool)
            vis[m] = self._shadow(start[m], np.tile(L.origin, (m.sum(), 1)), occ)
            amount = amount * vis
            contrib = amount[:, None] * L.color[None, :]
            total += contrib
            direct += contrib
            dirsum += ldir * amount[:, None]
        if self.sun is not None:
            sdir, scol, sint = self.sun
            sdir = np.array(sdir, float)
            sdir /= np.linalg.norm(sdir)
            lam = np.clip(normals @ sdir, 0, 1) if normals is not None else np.ones(len(pts))
            m = lam > 0
            vis = np.zeros(len(pts), bool)
            if m.any():
                vis[m] = self._shadow(start[m], start[m] + sdir * 8192, occ)
            amount = sint * lam * vis
            contrib = amount[:, None] * np.array(scol, float)[None, :]
            total += contrib
            direct += contrib
            dirsum += sdir[None, :] * amount[:, None]
        n = np.linalg.norm(dirsum, axis=1, keepdims=True)
        ldir = np.where(n > 1e-6, dirsum / np.maximum(n, 1e-6), np.array([0.3, 0.3, 0.9]))
        return np.clip(total, 0, 255), ldir, np.clip(direct, 0, 255)

    # ------------------------------------------------------------------ BSP tree
    def _build_tree(self, items, bounds, depth=0):
        """items: list of (kind, index, mins, maxs). Returns nested node structure."""
        mins, maxs = bounds
        if len(items) <= 12 or depth > 14:
            return ('leaf', items, bounds)
        size = maxs - mins
        axis = int(np.argmax(size))
        centres = sorted(((it[2][axis] + it[3][axis]) / 2 for it in items))
        split = round(centres[len(centres) // 2] / 8) * 8
        if split <= mins[axis] + 16 or split >= maxs[axis] - 16:
            split = round((mins[axis] + maxs[axis]) / 2 / 8) * 8
        front = [it for it in items if it[3][axis] > split]
        back = [it for it in items if it[2][axis] < split]
        if len(front) == len(items) and len(back) == len(items):
            return ('leaf', items, bounds)
        fmins = mins.copy()
        fmins[axis] = split
        bmaxs = maxs.copy()
        bmaxs[axis] = split
        return ('node', axis, split,
                self._build_tree(front, (fmins, maxs), depth + 1),
                self._build_tree(back, (mins, bmaxs), depth + 1), bounds)

    # ------------------------------------------------------------------ write
    def compile(self):
        shaders, shader_index = [], {}

        def shnum(sh):
            if sh.name not in shader_index:
                shader_index[sh.name] = len(shaders)
                shaders.append(sh)
            return shader_index[sh.name]

        planes, plane_index = [], {}

        def plnum(n, d):
            key = (round(n[0], 5), round(n[1], 5), round(n[2], 5), round(d, 3))
            if key not in plane_index:
                plane_index[key] = len(planes)
                planes.append((n, d))
                neg = (-n[0] + 0.0, -n[1] + 0.0, -n[2] + 0.0)
                plane_index[(round(neg[0], 5), round(neg[1], 5), round(neg[2], 5), round(-d, 3))] = len(planes)
                planes.append((np.array(neg), -d))
            return plane_index[key]

        # brushes, ordered by model
        order = sorted(range(len(self.brushes)), key=lambda i: self.brushes[i].model)
        brushes = [self.brushes[i] for i in order]
        dbrushes, dsides = [], []
        for b in brushes:
            first = len(dsides)
            for n, d, sh in b.planes():
                dsides.append((plnum(n, d), shnum(sh), -1))
            dbrushes.append((first, len(dsides) - first, shnum(b.shader)))

        # surfaces (lit), ordered by model
        surfs = self._build_surfaces()
        surfs.sort(key=lambda s: s['model'])
        verts, indexes, dsurfs = [], [], []
        for s in surfs:
            nrm = np.tile(s['normal'], (len(s['verts']), 1))
            if s['shader'].sky:
                col = np.full((len(s['verts']), 3), 255.0)
            else:
                col, _d, _x = self.light_points(s['verts'], nrm)
            s['color'] = col
            fv, fi = len(verts), len(indexes)
            for p, t, c in zip(s['verts'], s['st'], col):
                verts.append((p, t, s['normal'], c))
            indexes += s['indexes']
            dsurfs.append(dict(shader=shnum(s['shader']), firstVert=fv, numVerts=len(s['verts']),
                               firstIndex=fi, numIndexes=len(s['indexes']), model=s['model'],
                               mins=s['verts'].min(0), maxs=s['verts'].max(0)))

        # tree over world brushes + surfaces
        world_b = [i for i, b in enumerate(brushes) if b.model == 0]
        world_s = [i for i, s in enumerate(dsurfs) if s['model'] == 0]
        wmins = np.min([brushes[i].mins for i in world_b], 0)
        wmaxs = np.max([brushes[i].maxs for i in world_b], 0)
        items = [('b', i, brushes[i].mins, brushes[i].maxs) for i in world_b] + \
                [('s', i, dsurfs[i]['mins'], dsurfs[i]['maxs']) for i in world_s]
        tree = self._build_tree(items, (wmins - 8, wmaxs + 8))

        nodes, leafs, leafsurfs, leafbrushes = [], [], [], []

        def emit(t):
            if t[0] == 'leaf':
                _k, its, (mn, mx) = t
                bs = [it[1] for it in its if it[0] == 'b']
                ss = [it[1] for it in its if it[0] == 's']
                leafs.append((0, 0, mn, mx, len(leafsurfs), len(ss), len(leafbrushes), len(bs)))
                leafsurfs.extend(ss)
                leafbrushes.extend(bs)
                return -len(leafs)   # -(leaf+1)
            _k, axis, split, front, back, (mn, mx) = t
            idx = len(nodes)
            nodes.append(None)
            n = np.zeros(3)
            n[axis] = 1
            pn = plnum(n, split)
            f = emit(front)
            b = emit(back)
            nodes[idx] = (pn, f, b, mn, mx)
            return idx

        emit(tree)

        # models
        dmodels = []
        for m in range(self.models):
            ms = [i for i, s in enumerate(dsurfs) if s['model'] == m]
            mb = [i for i, b in enumerate(brushes) if b.model == m]
            if mb:
                mn = np.min([brushes[i].mins for i in mb], 0)
                mx = np.max([brushes[i].maxs for i in mb], 0)
            else:
                mn = mx = np.zeros(3)
            dmodels.append((mn, mx, ms[0] if ms else 0, len(ms), mb[0] if mb else 0, len(mb)))

        # light grid
        grid_size = np.array([64.0, 64.0, 128.0])
        gmin = grid_size * np.ceil(dmodels[0][0] / grid_size)
        gmax = grid_size * np.floor(dmodels[0][1] / grid_size)
        gb = ((gmax - gmin) / grid_size + 1).astype(int)
        xs, ys, zs = (gmin[i] + np.arange(gb[i]) * grid_size[i] for i in range(3))
        gpts = np.array([[x, y, z] for z in zs for y in ys for x in xs])
        col, ldir, direct = self.light_points(gpts + np.array([0, 0, 8.0]))
        grid_entries, grid_lookup, grid_array = [], {}, []
        for c, dvec, dl in zip(col, ldir, direct):
            amb = np.clip(c - dl * 0.6, 0, 255) * 0.5
            dl = dl * 0.6
            lng = math.acos(max(-1.0, min(1.0, dvec[2])))
            lat = math.atan2(dvec[1], dvec[0]) % (2 * math.pi)
            entry = struct.pack('<12B12B4B2B',
                                *[int(x) for x in amb], *([0] * 9),
                                *[int(x) for x in dl], *([0] * 9),
                                LS_NORMAL, LS_NONE, LS_NONE, LS_NONE,
                                int(lng * 255 / (2 * math.pi)) & 255, int(lat * 255 / (2 * math.pi)) & 255)
            if entry not in grid_lookup:
                grid_lookup[entry] = len(grid_entries)
                grid_entries.append(entry)
            grid_array.append(grid_lookup[entry])

        # ---- pack lumps
        L = [b''] * 18
        L[0] = self.entity_string().encode('latin-1') + b'\0'
        L[1] = b''.join(struct.pack('<64sii', s.name.encode(), s.flags, s.contents) for s in shaders)
        L[2] = b''.join(struct.pack('<4f', n[0], n[1], n[2], d) for n, d in planes)
        L[3] = b''.join(struct.pack('<3i3i3i', pn, f, b, *[int(math.floor(x)) for x in mn],
                                    *[int(math.ceil(x)) for x in mx]) for pn, f, b, mn, mx in nodes)
        L[4] = b''.join(struct.pack('<2i3i3i4i', cl, ar, *[int(math.floor(x)) for x in mn],
                                    *[int(math.ceil(x)) for x in mx], fs, ns, fb, nb)
                        for cl, ar, mn, mx, fs, ns, fb, nb in leafs)
        L[5] = struct.pack(f'<{len(leafsurfs)}i', *leafsurfs)
        L[6] = struct.pack(f'<{len(leafbrushes)}i', *leafbrushes)
        L[7] = b''.join(struct.pack('<6f4i', *mn, *mx, fs, ns, fb, nb) for mn, mx, fs, ns, fb, nb in dmodels)
        L[8] = b''.join(struct.pack('<3i', *b) for b in dbrushes)
        L[9] = b''.join(struct.pack('<3i', pn, sn, ds) for pn, sn, ds in dsides)
        vbuf = []
        for p, t, n, c in verts:
            rgb = [int(round(x)) for x in c]
            vbuf.append(struct.pack('<3f2f8f3f16B', *p, *t, *([0.0] * 8), *n,
                                    rgb[0], rgb[1], rgb[2], 255, *([0] * 12)))
        L[10] = b''.join(vbuf)
        L[11] = struct.pack(f'<{len(indexes)}i', *indexes)
        sbuf = []
        for s in dsurfs:
            sbuf.append(struct.pack('<7i4B4B4i4i4i2i3f9f2i',
                                    s['shader'], -1, MST_TRIANGLE_SOUP, s['firstVert'], s['numVerts'],
                                    s['firstIndex'], s['numIndexes'],
                                    LS_NORMAL, LS_NONE, LS_NONE, LS_NONE,
                                    LS_NORMAL, LS_NONE, LS_NONE, LS_NONE,
                                    *([LIGHTMAP_BY_VERTEX] * 4), *([0] * 4), *([0] * 4), 0, 0,
                                    *([0.0] * 3), *([0.0] * 9), 0, 0))
        L[13] = b''.join(sbuf)
        L[15] = b''.join(grid_entries)
        L[17] = struct.pack(f'<{len(grid_array)}H', *grid_array)

        header_size = 8 + 18 * 8
        out = bytearray()
        offs = []
        pos = header_size
        for lump in L:
            offs.append((pos, len(lump)))
            out += lump
            pad = (-len(lump)) % 4
            out += b'\0' * pad
            pos += len(lump) + pad
        header = struct.pack('<4si', b'RBSP', 1) + b''.join(struct.pack('<2i', o, l) for o, l in offs)
        stats = dict(brushes=len(dbrushes), surfaces=len(dsurfs), verts=len(verts), tris=len(indexes) // 3,
                     leafs=len(leafs), nodes=len(nodes), grid=len(grid_entries))
        return header + bytes(out), stats

    def entity_string(self):
        parts = []
        for ent in self.entities:
            parts.append('{\n' + ''.join(f'"{k}" "{v}"\n' for k, v in ent.items()) + '}\n')
        return ''.join(parts)
