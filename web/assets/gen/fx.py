"""2D art (HUD, icons, menus, crosshairs), effect textures/shaders, saber blades and .efx particle effects."""
import math
import os
import re
import zlib

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import common

YELLOW = (255, 232, 31)
BLUE = (74, 163, 255)


def font(size):
    return ImageFont.load_default(size)


def radial(size, color, power=2.0, core=0.0):
    y, x = np.mgrid[-1:1:size * 1j, -1:1:size * 1j]
    r = np.sqrt(x * x + y * y)
    a = np.clip(1 - r, 0, 1) ** power
    a = np.maximum(a, np.clip(1 - r / max(core, 1e-6), 0, 1) if core else 0)
    rgb = np.ones((size, size, 3)) * np.array(color)
    return Image.fromarray(np.dstack([rgb, a * 255]).astype(np.uint8), 'RGBA')


def additive_img(size, color, power=2.0):
    """Black background premultiplied version for GL_ONE GL_ONE blending."""
    y, x = np.mgrid[-1:1:size * 1j, -1:1:size * 1j]
    r = np.sqrt(x * x + y * y)
    a = np.clip(1 - r, 0, 1) ** power
    rgb = a[..., None] * np.array(color)[None, None, :]
    return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), 'RGB')


def blade_img(color, core=False, w=64, h=16):
    """Horizontal blade strip: bright along the centre line (v), fading to the edges."""
    v = np.abs(np.linspace(-1, 1, h))[:, None]
    if core:
        a = np.clip(1 - v * 1.6, 0, 1) ** 0.6
        rgb = np.array(color) * 0.4 + 255 * 0.6
    else:
        a = np.clip(1 - v, 0, 1) ** 1.6
        rgb = np.array(color)
    img = a[..., None] * rgb
    img = np.repeat(img, w, 1)
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), 'RGB')


def smoke_img(size=64):
    rng = np.random.default_rng(7)
    base = np.asarray(radial(size, (255, 255, 255), 1.4))[..., 3] / 255.0
    nz = np.asarray(Image.fromarray((rng.random((8, 8)) * 255).astype(np.uint8)).resize((size, size), Image.BICUBIC)) / 255
    a = base * (0.5 + 0.5 * nz)
    return Image.fromarray(np.dstack([np.full((size, size, 3), 200), a * 255]).astype(np.uint8), 'RGBA')


def ring_img(size=64, color=(255, 255, 255)):
    y, x = np.mgrid[-1:1:size * 1j, -1:1:size * 1j]
    r = np.sqrt(x * x + y * y)
    a = np.clip(1 - np.abs(r - 0.8) * 8, 0, 1)
    rgb = a[..., None] * np.array(color)
    return Image.fromarray(rgb.astype(np.uint8), 'RGB')


def label_icon(text, accent, size=64):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([2, 2, size - 3, size - 3], radius=10, fill=(12, 18, 32, 220), outline=accent, width=3)
    words = text.upper().split()
    txt = ''.join(w[0] for w in words[:3]) if len(text) > 7 else text.upper()
    f = font(22 if len(txt) <= 3 else 13)
    d.text((size / 2, size / 2), txt, font=f, fill=accent, anchor='mm')
    return img


def crosshair(kind, size=64):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = size // 2
    w = (255, 255, 255, 255)
    k = ord(kind) % 5
    if k == 0:
        d.ellipse([c - 3, c - 3, c + 3, c + 3], fill=w)
    elif k == 1:
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            d.line([c + dx * 6, c + dy * 6, c + dx * 18, c + dy * 18], fill=w, width=3)
    elif k == 2:
        d.ellipse([c - 14, c - 14, c + 14, c + 14], outline=w, width=3)
        d.ellipse([c - 2, c - 2, c + 2, c + 2], fill=w)
    elif k == 3:
        d.polygon([(c, c - 12), (c + 12, c + 10), (c - 12, c + 10)], outline=w)
    else:
        for dx, dy in ((1, 1), (-1, -1), (1, -1), (-1, 1)):
            d.line([c + dx * 5, c + dy * 5, c + dx * 14, c + dy * 14], fill=w, width=3)
    return img


def panel(w, h, accent=BLUE, fill=(10, 16, 30, 200), radius=12):
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([1, 1, w - 2, h - 2], radius=radius, fill=fill, outline=accent + (255,), width=2)
    return img


def hud_gauge(size=128):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([6, 6, size - 6, size - 6], fill=(8, 12, 24, 170), outline=(120, 140, 170, 255), width=3)
    d.ellipse([30, 30, size - 30, size - 30], outline=(70, 90, 120, 255), width=2)
    return img


def tic(color, size=32):
    return radial(size, color, 1.2, core=0.45)


def number_glyph(ch, size=32):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((size / 2, size / 2), ch, font=font(28), fill=(255, 255, 255, 255), anchor='mm')
    return img


def background(w=512, h=384):
    rng = np.random.default_rng(3)
    y = np.linspace(0, 1, h)[:, None, None]
    img = np.array([6, 10, 24]) * (1 - y) + np.array([20, 30, 60]) * y
    img = np.repeat(img, w, 1)
    stars = rng.random((h, w)) > 0.995
    img[stars] = 220
    pil = Image.fromarray(img.astype(np.uint8), 'RGB')
    d = ImageDraw.Draw(pil)
    d.ellipse([w * 0.55, h * 0.45, w * 1.3, h * 1.4], fill=(40, 60, 110))
    d.ellipse([w * 0.57, h * 0.47, w * 1.28, h * 1.38], fill=(25, 40, 80))
    return pil


def logo(w=512, h=128):
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.text((w / 2, h * 0.42), 'JEDI ACADEMY', font=font(58), fill=YELLOW + (255,), anchor='mm', stroke_width=2,
           stroke_fill=(90, 70, 0, 255))
    d.text((w / 2, h * 0.85), 'WEB  EDITION', font=font(20), fill=(200, 210, 230, 255), anchor='mm')
    return img


def planet(name, size=128):
    h = zlib.crc32(name.encode())
    col = ((h & 0x7F) + 60, ((h >> 8) & 0x7F) + 60, ((h >> 16) & 0x7F) + 60)
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    big = radial(size, col, 0.25)
    img.alpha_composite(big)
    return img


ICON_COLORS = {'w_icon': (255, 170, 60), 'f_icon': BLUE, 'i_icon': (90, 220, 120), 'mp': (200, 200, 200)}


def gfx_image(path):
    """Pick a placeholder image for a gfx/ path."""
    name = path.rsplit('/', 1)[-1]
    if path.startswith('gfx/2d/numbers/'):
        digits = {'zero': '0', 'one': '1', 'two': '2', 'three': '3', 'four': '4', 'five': '5', 'six': '6',
                  'seven': '7', 'eight': '8', 'nine': '9', 'minus': '-'}
        key = name.split('_')[0]
        return number_glyph(digits.get(key, name[:1]))
    if path.startswith('gfx/2d/crosshair'):
        return crosshair(name[-1])
    if path.startswith('gfx/hud/'):
        for key, col in (('health', (230, 40, 40)), ('armor', (40, 210, 90)), ('ammo', (240, 200, 60)),
                         ('force', (70, 150, 255))):
            if key in name and 'tic' in name:
                return tic(col)
        if name in ('hudleft', 'hudright', 'hud_left', 'hud_right'):
            return hud_gauge()
        for prefix, col in ICON_COLORS.items():
            if name.startswith(prefix):
                label = re.sub(r'^(w|f|i)_icon_', '', name).replace('_na', '').replace('_', ' ')
                img = label_icon(label, col)
                if name.endswith('_na'):
                    img = Image.blend(img, Image.new('RGBA', img.size, (0, 0, 0, 0)), 0.5)
                return img
        if 'saber' in name:
            return label_icon(name.replace('saber_', ''), (120, 220, 255))
        return panel(64, 64)
    if path.startswith('gfx/menus/'):
        if 'main_background' in name or name in ('load_back', 'datapad', 'datapad2', 'mission_galaxy'):
            return background()
        if name == 'jediacademy' or 'logo' in name:
            return logo()
        if path.startswith('gfx/menus/planets/'):
            return planet(name)
        if 'ring' in name:
            return Image.fromarray(np.asarray(ring_img(128, BLUE)), 'RGB').convert('RGBA')
        if 'arrow' in name:
            img = Image.new('RGBA', (32, 32), (0, 0, 0, 0))
            pts = [(8, 4), (26, 16), (8, 28)] if name.endswith(('_r', '_ron')) else [(24, 4), (6, 16), (24, 28)]
            ImageDraw.Draw(img).polygon(pts, fill=YELLOW + (255,) if name.endswith('on') else (200, 200, 200, 255))
            return img
        if 'side_text' in name or name.startswith('hex_pattern') or 'blendbox' in name or 'line' in name:
            return Image.new('RGBA', (16, 16), (30, 60, 110, 90))
        if 'button' in name or 'loc_but' in name:
            return panel(128, 32, YELLOW if name.endswith('on') else BLUE, radius=8)
        return panel(128, 128)
    if path.startswith('gfx/effects/') or path.startswith('gfx/misc/'):
        return radial(64, (255, 255, 255), 2.0)
    if path.startswith('gfx/damage/'):
        return radial(64, (90, 10, 10), 1.0)
    return panel(64, 64)


SABER_COLORS = {'blue': (60, 120, 255), 'green': (60, 255, 80), 'red': (255, 40, 30), 'orange': (255, 140, 30),
                'purple': (190, 60, 255), 'yellow': (255, 240, 60)}


def shaders():
    out = []
    for col in SABER_COLORS:
        out.append(f'''gfx/effects/sabers/{col}_glow
{{
	cull twosided
	{{
		map gfx/effects/sabers/{col}_glow
		blendFunc GL_ONE GL_ONE
		glow
	}}
}}

gfx/effects/sabers/{col}_line
{{
	cull twosided
	{{
		map gfx/effects/sabers/{col}_line
		blendFunc GL_ONE GL_ONE
	}}
}}
''')
    for name in ('saberBlur', 'swordTrail'):
        out.append(f'''gfx/effects/sabers/{name}
{{
	cull twosided
	{{
		map gfx/effects/sabers/trail
		blendFunc GL_ONE GL_ONE
		rgbGen vertex
	}}
}}
''')
    for name in ('flare', 'spark', 'bolt', 'ring', 'glow_add'):
        out.append(f'''gfx/effects/placeholder/{name}
{{
	cull twosided
	{{
		map gfx/effects/placeholder/{name}
		blendFunc GL_ONE GL_ONE
		rgbGen vertex
	}}
}}
''')
    out.append('''gfx/effects/placeholder/smoke
{
	cull twosided
	{
		map gfx/effects/placeholder/smoke
		blendFunc GL_SRC_ALPHA GL_ONE_MINUS_SRC_ALPHA
		rgbGen vertex
		alphaGen vertex
	}
}
''')
    return '\n'.join(out)


MARK_SHADERS = """
markShadow
{
	polygonOffset
	{
		map gfx/placeholder/shadow
		blendFunc GL_ZERO GL_ONE_MINUS_SRC_ALPHA
		rgbGen exactVertex
		alphaGen vertex
	}
}
""" + "".join(f"""
{n}
{{
	polygonOffset
	{{
		map gfx/placeholder/footstep
		blendFunc GL_ZERO GL_ONE_MINUS_SRC_ALPHA
		alphaGen vertex
	}}
}}
""" for n in ("footstep_l", "footstep_r", "footstep_heavy_l", "footstep_heavy_r"))


# ----------------------------------------------------------------------------- .efx
BOLT_COLORS = {'blaster': (1, .25, .15), 'bryar': (1, .45, .1), 'bowcaster': (.3, 1, .3), 'repeater': (1, .9, .3),
               'demp2': (.4, .6, 1), 'flechette': (1, .8, .3), 'concussion': (1, .5, .2), 'disruptor': (1, .2, .2),
               'emplaced': (1, .3, .2), 'eweb': (1, .3, .2), 'atst': (1, .3, .2), 'noghri': (.5, 1, .3),
               'tusken': (1, .8, .4), 'force': (.4, .6, 1), 'saber': (1, .9, .5), 'rocket': (1, .6, .3)}


def color_for(path):
    for k, c in BOLT_COLORS.items():
        if k in path:
            return c
    return (1, .8, .5)


def efx_particle(shader, count, life, size, rgb, vel=0, alpha=(1, 0), grav=0, size_end=None, name='p'):
    vmin, vmax = (-vel, -vel, -vel), (vel, vel, vel)
    se = size if size_end is None else size_end
    return f'''
	Particle
	{{
		name	{name}
		count	{count[0]} {count[1]}
		life	{life[0]} {life[1]}
		velocity	{vmin[0]} {vmin[1]} {vmin[2]} {vmax[0]} {vmax[1]} {vmax[2]}
		gravity	{grav} {grav}
		rotation	0 360
		size
		{{
			start	{size[0]} {size[1]}
			end	{se[0]} {se[1]}
			flags	linear
		}}
		rgb
		{{
			start	{rgb[0]:.2f} {rgb[1]:.2f} {rgb[2]:.2f}
		}}
		alpha
		{{
			start	{alpha[0]}
			end	{alpha[1]}
			flags	linear
		}}
		shaders
		[
			{shader}
		]
	}}'''


def efx_light(size, rgb, life=(80, 120)):
    return f'''
	Light
	{{
		life	{life[0]} {life[1]}
		size
		{{
			start	{size}
			end	0
			flags	linear
		}}
		rgb
		{{
			start	{rgb[0]:.2f} {rgb[1]:.2f} {rgb[2]:.2f}
		}}
	}}'''


def efx_tail(rgb, length=28, width=2.5, life=(30, 30)):
    return f'''
	Tail
	{{
		life	{life[0]} {life[1]}
		velocity	1 0 0
		size
		{{
			start	{width}
		}}
		length
		{{
			start	{length}
		}}
		rgb
		{{
			start	{rgb[0]:.2f} {rgb[1]:.2f} {rgb[2]:.2f}
		}}
		shaders
		[
			gfx/effects/placeholder/bolt
		]
	}}'''


def efx_for(path):
    p = path.lower()
    rgb = color_for(p)
    F, S, SM = 'gfx/effects/placeholder/flare', 'gfx/effects/placeholder/spark', 'gfx/effects/placeholder/smoke'
    parts = []
    if any(k in p for k in ('shot', 'projectile', 'crackle')) and 'muzzle' not in p:
        parts += [efx_tail(rgb, 32 if 'repeater' not in p else 18), efx_particle(F, (1, 1), (30, 30), (5, 6), rgb)]
    elif 'muzzle' in p:
        parts += [efx_particle(F, (1, 2), (60, 100), (8, 14), rgb, size_end=(2, 3)), efx_light(120, rgb)]
    elif any(k in p for k in ('explosion', 'explode', 'blow', 'detonate', 'destroyed', 'alt_hit', 'big')):
        parts += [efx_particle(F, (3, 5), (300, 500), (40, 70), (1, .7, .3), vel=60, size_end=(80, 120)),
                  efx_particle(S, (15, 25), (400, 800), (2, 4), (1, .8, .4), vel=350, grav=-400),
                  efx_particle(SM, (5, 8), (900, 1500), (30, 40), (.35, .33, .3), vel=40, size_end=(90, 120)),
                  efx_light(400, (1, .7, .3), (300, 400)),
                  '\n\tCameraShake\n\t{\n\t\tlife\t400 500\n\t\tintensity\t3 4\n\t\tradius\t500\n\t}']
    elif any(k in p for k in ('impact', 'bounce', 'ricochet', 'deflect', 'hit', 'spark', 'clash', 'block')):
        parts += [efx_particle(S, (6, 10), (200, 400), (1, 2), rgb, vel=160, grav=-300),
                  efx_particle(F, (1, 1), (80, 120), (8, 12), rgb, size_end=(1, 2)),
                  efx_light(90, rgb, (60, 90))]
    elif any(k in p for k in ('smoke', 'dust', 'materials', 'gas', 'breath', 'steam', 'splash', 'env/', 'burning')):
        parts += [efx_particle(SM, (3, 6), (600, 1200), (6, 10), (.6, .58, .55), vel=25, alpha=(.6, 0),
                               size_end=(20, 30))]
    elif p.startswith('force') or '/force' in p:
        parts += [efx_particle(F, (6, 10), (300, 600), (4, 8), (.4, .6, 1), vel=60, size_end=(1, 2)),
                  efx_light(150, (.4, .6, 1))]
    else:
        parts += [efx_particle(F, (2, 4), (150, 300), (4, 8), rgb, vel=40, size_end=(1, 2))]
    return 'repeatDelay\t300\n' + ''.join(parts) + '\n'


def effect_names(existing):
    names = set()
    src = os.path.join(common.ENGINE_SRC, 'code')
    for root, _d, files in os.walk(src):
        for f in files:
            if f.endswith(('.cpp', '.h')):
                with open(os.path.join(root, f), encoding='latin-1') as fh:
                    text = fh.read()
                names.update(re.findall(r'RegisterEffect\(\s*"([^"]+)"', text))
                names.update(re.findall(r'PlayEffect\(\s*"([^"]+)"', text))
    for path, data in existing.items():
        if path.startswith('ext_data/') or path.endswith('.menu'):
            text = data.decode('latin-1') if isinstance(data, bytes) else data
            names.update(re.findall(r'(?:Effect|FX|fx)\s+"?([a-zA-Z0-9_]+/[a-zA-Z0-9_/]+)', text))
    out = set()
    for n in names:
        n = n.lower().replace('\\', '/')
        if n.endswith('.efx'):
            n = n[:-4]
        if n.startswith('effects/'):
            n = n[len('effects/'):]
        out.add(n)
    return out


def gfx_paths(existing):
    paths = set()
    for path, data in existing.items():
        if path.endswith(('.menu', '.txt', '.dat', '.npc', '.sab', '.veh', '.vwp')):
            text = data.decode('latin-1') if isinstance(data, bytes) else data
            paths.update(p.lower() for p in re.findall(r'(gfx/[A-Za-z0-9_/\-]+)', text))
    src = os.path.join(common.ENGINE_SRC, 'code')
    for root, _d, files in os.walk(src):
        for f in files:
            if f.endswith(('.cpp', '.h')):
                with open(os.path.join(root, f), encoding='latin-1') as fh:
                    paths.update(p.lower() for p in re.findall(r'"(gfx/[A-Za-z0-9_/\-]+)"', fh.read()))
    return {p for p in paths if not p.endswith('/')}


def generate(existing):
    out = {}
    for p in sorted(gfx_paths(existing)):
        if p.startswith('gfx/effects/sabers/'):
            continue
        out[p + '.png'] = common.png(gfx_image(p))
    for col, rgb in SABER_COLORS.items():
        out[f'gfx/effects/sabers/{col}_glow.png'] = common.png(blade_img(rgb))
        out[f'gfx/effects/sabers/{col}_line.png'] = common.png(blade_img(rgb, core=True))
    out['gfx/effects/sabers/trail.png'] = common.png(blade_img((160, 160, 160)))
    out['gfx/effects/placeholder/flare.png'] = common.png(additive_img(64, (255, 255, 255), 2.2))
    out['gfx/effects/placeholder/glow_add.png'] = common.png(additive_img(64, (255, 255, 255), 1.2))
    out['gfx/effects/placeholder/spark.png'] = common.png(additive_img(16, (255, 255, 255), 0.8))
    out['gfx/effects/placeholder/bolt.png'] = common.png(blade_img((255, 255, 255), core=True, w=32, h=16))
    out['gfx/effects/placeholder/ring.png'] = common.png(ring_img())
    out['gfx/effects/placeholder/smoke.png'] = common.png(smoke_img())
    for c in 'abcdefghij':
        out[f'gfx/2d/crosshair{c}.png'] = common.png(crosshair(c))
    shadow = radial(64, (0, 0, 0), 1.0)
    out['gfx/placeholder/shadow.png'] = common.png(shadow)
    out['gfx/placeholder/footstep.png'] = common.png(radial(32, (0, 0, 0), 0.7))
    out['shaders/zz_placeholder_fx.shader'] = shaders() + MARK_SHADERS
    for name in sorted(effect_names(existing)):
        out[f'effects/{name}.efx'] = efx_for(name)
    return out
