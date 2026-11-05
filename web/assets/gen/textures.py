"""Procedural world textures + their shader definitions."""
import numpy as np
from PIL import Image, ImageFilter

from . import common

RNG = np.random.default_rng(1138)


def noise(size, scale, octaves=4):
    """Tileable value noise in 0..1."""
    acc = np.zeros((size, size))
    amp, total = 1.0, 0.0
    for o in range(octaves):
        cells = max(1, int(scale * 2 ** o))
        g = RNG.random((cells, cells))
        img = Image.fromarray((g * 255).astype(np.uint8)).resize((size, size), Image.BICUBIC)
        # make tileable by blending with a rolled copy
        a = np.asarray(img, float) / 255
        a = (a + np.roll(a, size // 2, 0) + np.roll(a, size // 2, 1) + np.roll(np.roll(a, size // 2, 0), size // 2, 1)) / 4
        acc += a * amp
        total += amp
        amp *= 0.5
    acc /= total
    return (acc - acc.min()) / (np.ptp(acc) + 1e-9)


def to_img(rgb):
    return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), 'RGB')


def tiles(size=256, n=4, base=(150, 142, 128), grout=(70, 66, 60), var=18):
    nz = noise(size, 4)
    img = np.ones((size, size, 3)) * np.array(base) * (0.85 + 0.3 * nz[..., None])
    step = size // n
    for i in range(n):
        for j in range(n):
            img[j * step:(j + 1) * step, i * step:(i + 1) * step] += RNG.integers(-var, var)
    for k in range(n):
        img[k * step:k * step + 3, :] = grout
        img[:, k * step:k * step + 3] = grout
    return to_img(img)


def panels(size=256, base=(88, 96, 108), line=(40, 44, 52), light=(130, 140, 155)):
    nz = noise(size, 8)
    img = np.ones((size, size, 3)) * np.array(base) * (0.9 + 0.15 * nz[..., None])
    for y0, y1 in ((0, 96), (96, 160), (160, 256)):
        img[y0:y0 + 2, :] = light
        img[y1 - 2:y1, :] = line
    for x in (0, 128):
        img[:, x:x + 2] = line
    # rivets
    for x in (12, 116, 140, 244):
        for y in (8, 88, 104, 152, 168, 248):
            img[y - 2:y + 2, x - 2:x + 2] = light
    return to_img(img)


def stone(size=256, base=(120, 108, 92)):
    nz = noise(size, 3, 5)
    img = np.ones((size, size, 3)) * np.array(base) * (0.65 + 0.55 * nz[..., None])
    rows = 4
    h = size // rows
    for r in range(rows):
        img[r * h:r * h + 3, :] *= 0.45
        off = (r % 2) * size // 4
        for c in range(2):
            x = (off + c * size // 2) % size
            img[r * h:(r + 1) * h, x:x + 3] *= 0.45
    return to_img(img)


def trim(size=128, base=(170, 150, 60)):
    img = np.ones((size, size, 3)) * np.array(base)
    nz = noise(size, 8)
    img *= (0.8 + 0.3 * nz[..., None])
    for y in range(0, size, 32):
        img[y:y + 4] *= 0.5
    return to_img(img)


def glow(size=64, color=(80, 200, 255)):
    y = np.linspace(-1, 1, size)
    prof = np.clip(1.2 - np.abs(y) * 1.1, 0, 1) ** 1.5
    img = np.ones((size, size, 3)) * np.array(color)[None, None, :] * prof[:, None, None]
    img += 255 * np.clip(1 - np.abs(y) * 3, 0, 1)[:, None, None] * 0.6
    return to_img(img)


def grass(size=256):
    nz = noise(size, 16, 3)
    nz2 = noise(size, 4, 3)
    img = np.stack([50 + 40 * nz2, 95 + 70 * nz, 35 + 20 * nz2], -1)
    return to_img(img)


def crate(size=128):
    img = np.ones((size, size, 3)) * np.array([140, 100, 55])
    nz = noise(size, 16, 2)
    img *= (0.75 + 0.35 * nz[..., None])
    img[:10] *= 0.55
    img[-10:] *= 0.55
    img[:, :10] *= 0.55
    img[:, -10:] *= 0.55
    for i in range(size):
        img[i, max(0, i - 6):i + 6] *= 0.7
    return to_img(img)


def sky_face(face, size=256):
    """Dusky sky with stars; 'up' gets more stars, 'dn' is dark ground."""
    y = np.linspace(0, 1, size)[:, None]
    if face == 'up':
        img = np.ones((size, size, 3)) * np.array([8, 10, 30])
    elif face == 'dn':
        img = np.ones((size, size, 3)) * np.array([20, 18, 22])
    else:
        top = np.array([10, 14, 40])
        hor = np.array([150, 90, 80])
        t = (y ** 2.2)[..., None]
        img = top * (1 - t) + hor * t
        img = np.repeat(img, size, 1)
        # distant mountains silhouette
        xs = np.arange(size)
        ridge = (0.78 + 0.08 * np.sin(xs / size * 6.28 * 2 + hash(face) % 7) + 0.04 * np.sin(xs / 9.0)) * size
        mask = np.arange(size)[:, None] > ridge[None, :]
        img[mask] = np.array([25, 22, 30])
    if face != 'dn':
        stars = RNG.random((size, size)) > (0.996 if face != 'up' else 0.99)
        if face != 'up':
            stars &= (np.arange(size)[:, None] < size * 0.6)
        img[stars] = 230
    return to_img(img)


# name -> (image fn, material, texscale, extra shader stages)
WORLD = {
    'floor': (lambda: tiles(), 'marble', 128),
    'floor_dark': (lambda: tiles(base=(70, 75, 90), grout=(30, 30, 40)), 'tiles', 128),
    'wall': (lambda: panels(), 'metal', 128),
    'stone': (lambda: stone(), 'rock', 128),
    'trim': (lambda: trim(), 'metal', 64),
    'grass': (lambda: grass(), 'grass', 256),
    'crate': (lambda: crate(), 'wood', 64),
}

GLOWS = {
    'glow_blue': (80, 190, 255),
    'glow_red': (255, 70, 60),
    'glow_gold': (255, 200, 90),
}

SKY = 'textures/placeholder/sky'


def shader_text():
    out = []
    for name, color in GLOWS.items():
        out.append(f'''textures/placeholder/{name}
{{
	q3map_surfacelight 400
	surfaceparm nomarks
	{{
		map textures/placeholder/{name}
		rgbGen identity
		glow
	}}
}}
''')
    out.append(f'''{SKY}
{{
	surfaceparm sky
	surfaceparm noimpact
	surfaceparm nomarks
	notc
	skyParms textures/placeholder/env/sky 512 -
}}
''')
    return '\n'.join(out)


def generate(existing):
    out = {}
    for name, (fn, _mat, _scale) in WORLD.items():
        out[f'textures/placeholder/{name}.png'] = common.png(fn())
    for name, color in GLOWS.items():
        out[f'textures/placeholder/{name}.png'] = common.png(glow(color=color))
    for face in ('rt', 'lf', 'bk', 'ft', 'up', 'dn'):
        out[f'textures/placeholder/env/sky_{face}.png'] = common.png(sky_face(face))
    out['shaders/zz_placeholder_world.shader'] = shader_text()
    return out
