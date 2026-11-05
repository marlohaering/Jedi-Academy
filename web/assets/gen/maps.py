"""maps/academy.bsp - a small original training level built from boxes.

Layout (top view, +y = north):

        +-----------------------------+
        |   balcony (z=192) + stairs  |
        |  P     P      P      P      |      main hall: 2048 x 1536, 448 high
        |        [ raised dais ]      |      P = pillars, glowing trim strips
        |  P     P      P      P      |
        +-----------+ door +----------+
                    |      |
        +-----------+      +----------+
        |  open-air courtyard (sky)   |      crates for cover, enemies
        +-----------------------------+
"""
from . import bsp
from .bsp import Light, Shader

MAT = {'marble': 12, 'tiles': 26, 'metal': 3, 'rock': 23, 'grass': 5, 'wood': 1}


def sh(name, material, scale=128.0, **kw):
    return Shader(f'textures/placeholder/{name}', material=MAT.get(material, 0), texscale=scale, **kw)


FLOOR = sh('floor', 'marble')
FLOOR_DARK = sh('floor_dark', 'tiles')
WALL = sh('wall', 'metal')
STONE = sh('stone', 'rock')
TRIM = sh('trim', 'metal', 64)
GRASS = sh('grass', 'grass', 256)
CRATE = sh('crate', 'wood', 64)
GLOW_B = sh('glow_blue', 'metal', 64)
GLOW_R = sh('glow_red', 'metal', 64)
GLOW_G = sh('glow_gold', 'metal', 64)
SKY = Shader('textures/placeholder/sky', sky=True)


def build():
    m = bsp.Map('academy')
    T = 32  # wall thickness

    # ---------------- main hall: x -1024..1024, y -768..768, z 0..448
    hx, hy, hz = 1024, 768, 448
    m.box((-hx - T, -hy - T, -T), (hx + T, hy + T, 0), FLOOR)                  # floor
    m.box((-hx - T, -hy - T, hz), (hx + T, hy + T, hz + T), STONE)             # ceiling
    m.box((-hx - T, -hy, 0), (-hx, hy, hz), WALL)                              # west
    m.box((hx, -hy, 0), (hx + T, hy, hz), WALL)                                # east
    m.box((-hx - T, hy, 0), (hx + T, hy + T, hz), WALL)                        # north
    # south wall with a 256-wide, 224-high doorway at x -128..128
    m.box((-hx - T, -hy - T, 0), (-128, -hy, hz), WALL)
    m.box((128, -hy - T, 0), (hx + T, -hy, hz), WALL)
    m.box((-128, -hy - T, 224), (128, -hy, hz), WALL)
    m.box((-144, -hy - T - 8, 0), (-128, -hy + 8, 224), TRIM)                  # door frame
    m.box((128, -hy - T - 8, 0), (144, -hy + 8, 224), TRIM)
    m.box((-144, -hy - T - 8, 224), (144, -hy + 8, 240), TRIM)

    # dark inlay walkway + raised dais with two steps
    m.box((-160, -hy, 0), (160, hy, 2), FLOOR_DARK)
    m.box((-320, -192, 0), (320, 192, 16), FLOOR_DARK)
    m.box((-256, -128, 16), (256, 128, 32), FLOOR)
    for x0 in (-260, 252):
        m.box((x0, -132, 32), (x0 + 8, 132, 36), GLOW_B)
    m.lights.append(Light((0, 0, 300), 520, (0.75, 0.88, 1.0)))

    # pillars with glowing strips
    for x in (-704, -352, 352, 704):
        for y in (-448, 448):
            m.box((x - 40, y - 40, 0), (x + 40, y + 40, hz), STONE)
            m.box((x - 48, y - 48, 0), (x + 48, y + 48, 24), TRIM)
            m.box((x - 48, y - 48, hz - 24), (x + 48, y + 48, hz), TRIM)
            m.box((x - 44, y - 6, 96), (x - 40, y + 6, 352), GLOW_B)
            m.box((x + 40, y - 6, 96), (x + 44, y + 6, 352), GLOW_B)
            m.lights.append(Light((x, y + (90 if y < 0 else -90), 300), 300, (0.6, 0.8, 1.0)))

    # wall glow strips + lights along the side walls
    for y in range(-576, 577, 384):
        m.box((-hx, y - 64, 280), (-hx + 4, y + 64, 288), GLOW_G)
        m.box((hx - 4, y - 64, 280), (hx, y + 64, 288), GLOW_G)
        m.lights.append(Light((-hx + 96, y, 300), 320, (1.0, 0.85, 0.6)))
        m.lights.append(Light((hx - 96, y, 300), 320, (1.0, 0.85, 0.6)))

    # north balcony at z=192 reached by stairs on both sides
    by = hy - 192
    m.box((-640, by, 176), (640, hy, 192), STONE)
    m.box((-640, by - 8, 192), (640, by, 232), TRIM)                            # railing
    for side in (-1, 1):
        for i in range(12):                                                   # 12 steps of 16 units
            x0 = side * (640 + i * 24)
            x1 = x0 + side * 24
            lo, hi = min(x0, x1), max(x0, x1)
            m.box((lo, by, 0), (hi, hy, 192 - i * 16), STONE)
    m.box((-96, hy - 4, 220), (96, hy, 380), GLOW_R)                            # emblem
    m.lights.append(Light((0, hy - 160, 360), 420, (1.0, 0.55, 0.5)))

    # ---------------- corridor + courtyard to the south
    cy0, cy1 = -hy - T, -hy - T - 256                                           # corridor y range
    m.box((-160, cy1, -T), (160, cy0, 0), FLOOR_DARK)
    m.box((-160 - T, cy1, 0), (-128, cy0, 224), WALL)
    m.box((128, cy1, 0), (160 + T, cy0, 224), WALL)
    m.box((-160 - T, cy1, 224), (160 + T, cy0, 224 + T), STONE)
    m.lights.append(Light((0, (cy0 + cy1) / 2, 180), 260, (0.8, 0.9, 1.0)))

    qx, qy0, qy1, qz = 1152, cy1, cy1 - 1536, 768
    m.box((-qx - T, qy1 - T, -T), (qx + T, qy0, 0), GRASS)
    m.box((-qx - T, qy1 - T, qz), (qx + T, qy0 + T, qz + T), SKY)
    m.box((-qx - T, qy1, 0), (-qx, qy0, qz), STONE)
    m.box((qx, qy1, 0), (qx + T, qy0, qz), STONE)
    m.box((-qx - T, qy1 - T, 0), (qx + T, qy1, qz), STONE)
    m.box((-qx - T, qy0, 0), (-128, qy0 + T, qz), STONE)                        # north wall w/ opening
    m.box((128, qy0, 0), (qx + T, qy0 + T, qz), STONE)
    m.box((-128, qy0, 224 + T), (128, qy0 + T, qz), STONE)
    # paved path + crates
    m.box((-128, qy1, 0), (128, qy0, 2), FLOOR)
    for (x, y, s) in ((-520, -1500, 64), (-456, -1500, 64), (-488, -1500, 64), (480, -1700, 96),
                      (-300, -2150, 64), (620, -2250, 64), (650, -2190, 48), (0, -1900, 96)):
        m.box((x - s / 2, y - s / 2, 0), (x + s / 2, y + s / 2, s), CRATE)
    m.box((-488 - 32, -1500 - 32, 64), (-488 + 32, -1500 + 32, 128), CRATE)
    # a low wall with ramps for jumping around
    m.box((-900, -2350, 0), (-600, -2300, 96), STONE)
    m.box((600, -2050, 0), (900, -1950, 128), STONE)
    # ramp rising northwards: keep z <= 1.28 * (y + 2150)
    m.box((600, -2150, 0), (900, -2050, 128), STONE, cut=((0, -1.28, 1), 1.28 * 2150))
    m.sun = ((0.45, 0.3, 0.84), (1.0, 0.8, 0.65), 200)

    # ---------------- entities
    m.entities.append({'classname': 'worldspawn', 'message': 'Jedi Academy Web - Training Grounds',
                       'music': '', 'ambient': '20', 'gridsize': '64 64 128'})
    m.entities.append({'classname': 'info_player_start', 'origin': '0 -600 24', 'angle': '90'})
    for cls, pos in (('weapon_blaster', (-200, -400, 16)), ('ammo_blaster', (-260, -400, 16)),
                     ('item_medpak_instant', (200, -400, 16)), ('item_shield_sm_instant', (260, -400, 16)),
                     ('weapon_thermal', (0, 650, 208)), ('weapon_repeater', (500, -1600, 16))):
        m.entities.append({'classname': cls, 'origin': '%d %d %d' % pos})
    # enemies: troopers guard the courtyard, a saber-wielding Reborn waits on the balcony and another outside
    for cls, pos, yaw in (('NPC_Stormtrooper', (-450, -1600, 24), 90), ('NPC_Stormtrooper', (450, -1850, 24), 90),
                          ('NPC_Stormtrooper', (-200, -2250, 24), 90), ('NPC_StormtrooperOfficer', (700, -2350, 24), 120),
                          ('NPC_Reborn', (0, 640, 216), 270), ('NPC_Reborn', (0, -2400, 24), 90)):
        m.entities.append({'classname': cls, 'origin': '%d %d %d' % pos, 'angle': str(yaw)})
    return m


def generate(existing):
    m = build()
    data, stats = m.compile()
    print('  academy.bsp:', stats)
    return {'maps/academy.bsp': data}
