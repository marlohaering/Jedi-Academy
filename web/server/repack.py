#!/usr/bin/env python3
"""Build a slimmer client pk3 for browser players of the FFA server.

The retail assets0-3.pk3 (1.2 GB) contain a lot that a multiplayer client on one map never
touches. This merges them (later pk3s override earlier ones, as in the engine) into one
pk3 without:
  - video/                  cinematics (single player)
  - sound/chr_d|chr_e|chr_f German/French/Spanish dialogue
  - maps/* except the served maps (bsp + nav files of every other level)
  - music/* except MP music, the folder of each served map's "music" track (the engine plays the
    whole folder as dynamic music: explore, action, transitions; ext_data/dms.dat) and music=
  - textures/ and models/map_objects/ that neither the served maps, the game code nor a global
    shader reference (the walls and props of the other levels)
Other pk3s in the base dir (e.g. japlus_gla_anims.pk3) and the asset pk3s of a server mod
directory (mod=/data/japlus) are merged on top, in the engine's search order. Pk3s with game
code (jampgame*, clientplugin*, cgame*, ui*) are skipped: the browser client has its own
cgame/ui compiled in and cannot load native DLLs.
The dedicated server keeps reading the original files; the client needs sv_pure 0.

profile=mobile (phones, see web/MOBILE.md) additionally
  - scales images down to at most MOBILE_MAX px (fonts and lightmaps untouched); opaque
    TGAs become JPEGs, the others PNGs (the engine finds images under any extension)
  - converts WAVs to 22 kHz mono
  - drops single-player-only content: dialogue (sound/chars/<npc>/*, MP only uses .../misc/),
    the mission-select planets, per-level animation sets (_humanoid_<level>), and the ambience
    of other maps (sound/ambience is filtered by the map's soundSet entries in sound/sound.txt)
  - drops the menu background video
  - nomusic=1 also drops all music
Needs Pillow (python3-pil).

usage: repack.py <base dir> <output.pk3> [map=mp/ffa3,mp/duel1,...] [music=music/<dir>,...] [mod=<mod dir>]
                 [profile=desktop|mobile] [nomusic=1]
"""
import io
import os
import re
import sys
import wave
import zipfile
from array import array

MOBILE_MAX = 256
IMAGE_EXT = ('.jpg', '.tga', '.png')
# models the game code loads by name (cgame/game string literals)
CODE_MODELS = (
    'models/map_objects/mp/',
    'models/map_objects/hoth/eweb_model', 'models/map_objects/hoth/turret_',
    'models/map_objects/imp_detention/door_lock', 'models/map_objects/imp_mine/turret_',
    'models/map_objects/ships/swoop', 'models/map_objects/wedge/laser_cannon_model',
    'textures/rj/fog1', 'textures/tests/circle',
)
FILTERED = ('textures/', 'models/map_objects/')
MOBILE_DROP = ('menu/video/', 'gfx/menus/planets/', 'models/players/_humanoid_')
AMBIENCE_CODE = {'sound/ambience/spark5'}
PATH_RE = re.compile(rb'(?:textures|models|gfx|env)/[\x21\x23-\x7e]{1,60}')  # no '"': entity values are quoted
CODE_PK3 = ('jampgame', 'clientplugin', 'cgame', 'ui')


def keep(name, maps, music):
    n = name.lower()
    if n.endswith('/') or n.endswith(('.dll', '.so', '.dylib', 'thumbs.db')):
        return False
    if n.startswith('video/'):
        return False
    if n.startswith(('sound/chr_d/', 'sound/chr_e/', 'sound/chr_f/')):
        return False
    if n.startswith('maps/'):
        return os.path.splitext(n)[0] in {'maps/' + m for m in maps}
    if n.startswith('music/'):
        return music is None or n.startswith(tuple(music))
    return True


def stem(path):
    p = path.lower().replace('\\', '/')
    root, ext = os.path.splitext(p)
    return root if ext in IMAGE_EXT + ('.md3', '.glm') else p


def parse_shaders(text):
    """shader name -> set of image stems used by its stages"""
    text = re.sub(r'//[^\n]*', '', text)
    tokens = re.findall(r'[{}]|"[^"]*"|[^\s{}]+', text)
    shaders, i, depth, name, cur = {}, 0, 0, None, None
    while i < len(tokens):
        t = tokens[i]
        if t == '{':
            depth += 1
        elif t == '}':
            depth -= 1
            if depth == 0 and name:
                shaders[name] = cur
                name = None
        elif depth == 0:
            name, cur = stem(t.strip('"')), set()
        elif name is not None:
            k = t.lower()
            if k in ('map', 'clampmap') and i + 1 < len(tokens):
                cur.add(stem(tokens[i + 1].strip('"')))
            elif k == 'animmap' and i + 1 < len(tokens):
                j = i + 2  # animMap <freq> <frames...> up to the end of the line
                while j < len(tokens) and tokens[j] not in '{}' and '/' in tokens[j]:
                    cur.add(stem(tokens[j].strip('"')))
                    j += 1
            elif k == 'skyparms' and i + 1 < len(tokens) and tokens[i + 1] != '-':
                base = stem(tokens[i + 1].strip('"'))
                cur.update(base + '_' + s for s in ('rt', 'bk', 'lf', 'ft', 'up', 'dn'))
        i += 1
    return shaders


def entities(bsp):
    """entity lump of an RBSP file (lump 0) as text"""
    ofs, length = int.from_bytes(bsp[8:12], 'little'), int.from_bytes(bsp[12:16], 'little')
    return bsp[ofs:ofs + length].decode('latin-1')


def needed_ambience(read, names, bsps):
    """sound/ambience stems referenced by the maps' ambient sets or by effects"""
    sets = {s for bsp in bsps for s in re.findall(r'"soundset"\s+"([^"]+)"', entities(bsp).lower())}
    out = set(AMBIENCE_CODE)
    if 'sound/sound.txt' in names:
        text = read('sound/sound.txt').decode('latin-1').lower()
        for block in re.split(r'\n(?=(?:general|local|bmodel)set\s)', text):
            head = block.split(None, 2)
            if len(head) >= 2 and head[1] in sets:
                out |= {'sound/' + m for m in re.findall(r'ambience/[\w/.-]+', block)}
    for n in names:
        if n.endswith('.efx'):
            out |= {m.decode('latin-1') for m in re.findall(rb'sound/ambience/[\w/.-]+', read(n).lower())}
    return {os.path.splitext(s)[0] for s in out}


def needed_stems(read, names, maps):
    """stems under textures/ and models/map_objects/ the client needs on these maps"""
    shaders = {}
    global_refs = set()
    for n in names:
        if n.endswith('.shader'):
            parsed = parse_shaders(read(n).decode('latin-1'))
            shaders.update(parsed)
            for s, imgs in parsed.items():
                if not s.startswith(FILTERED):  # effects, HUD, players: used by name from anywhere
                    global_refs |= imgs
        elif n.endswith(('.efx', '.skin', '.menu', '.sab', '.npc', '.veh', '.wpn')):
            global_refs |= {stem(m.decode('latin-1')) for m in PATH_RE.findall(read(n))}
    refs = {stem(m.decode('latin-1')) for mp in maps for m in PATH_RE.findall(read('maps/' + mp + '.bsp'))}
    refs |= global_refs
    refs |= {stem(n) for n in names if n.startswith(CODE_MODELS)}
    out, todo = set(), list(refs)
    while todo:
        s = todo.pop()
        if s in out:
            continue
        out.add(s)
        todo += shaders.get(s, ())
        if s.startswith('models/'):  # model: its own shader references, and its skins
            for ext in ('.md3', '.glm'):
                if s + ext in names:
                    todo += [stem(m.decode('latin-1')) for m in PATH_RE.findall(read(s + ext))]
            d = os.path.dirname(s) + '/'
            todo += [stem(n) for n in names if n.startswith(d) and n.endswith('.skin')]
            for n in names:
                if n.startswith(d) and n.endswith('.skin'):
                    todo += [stem(m.decode('latin-1')) for m in PATH_RE.findall(read(n))]
    return out


def shrink_image(name, data, taken):
    """-> (name, data); may change the extension (tga -> jpg/png)"""
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception:
        return name, data
    w, h = im.size
    scale = 1
    while max(w, h) // scale > MOBILE_MAX:
        scale *= 2
    root, ext = os.path.splitext(name)
    if scale == 1 and ext.lower() != '.tga':
        return name, data
    if scale > 1:
        im = im.resize((max(1, w // scale), max(1, h // scale)), Image.LANCZOS)
    has_alpha = im.mode in ('RGBA', 'LA', 'PA') or (im.mode == 'P' and 'transparency' in im.info)
    if has_alpha and im.mode != 'RGBA':
        im = im.convert('RGBA')
    if has_alpha and im.getchannel('A').getextrema()[0] == 255:
        has_alpha = False
    if ext.lower() == '.jpg' or not has_alpha:
        fmt, new_ext = 'JPEG', '.jpg'
    else:
        fmt, new_ext = 'PNG', '.png'
    if new_ext != ext.lower() and (root.lower() + new_ext) in taken:
        fmt, new_ext = ('PNG', '.png') if ext.lower() == '.png' else ('TGA', ext)
    if fmt == 'JPEG' and im.mode != 'RGB':
        im = im.convert('RGB')
    buf = io.BytesIO()
    im.save(buf, fmt, **({'quality': 82} if fmt == 'JPEG' else {'optimize': True} if fmt == 'PNG' else {}))
    out = buf.getvalue()
    if new_ext == ext.lower() and len(out) >= len(data):
        return name, data
    return root + new_ext, out


def shrink_wav(data):
    try:
        r = wave.open(io.BytesIO(data))
        ch, sw, rate, n = r.getnchannels(), r.getsampwidth(), r.getframerate(), r.getnframes()
        frames = r.readframes(n)
    except Exception:
        return data
    if sw != 2 or (ch == 1 and rate <= 22050):
        return data
    s = array('h', frames)
    if sys.byteorder == 'big':
        s.byteswap()
    if ch == 2:
        s = array('h', ((a + b) >> 1 for a, b in zip(s[0::2], s[1::2])))
    elif ch != 1:
        return data
    if rate > 22050:
        step = round(rate / 22050)
        if step >= 2:
            s = array('h', ((a + b) >> 1 for a, b in zip(s[0::step], s[1::step])))
            rate //= step
    if sys.byteorder == 'big':
        s.byteswap()
    buf = io.BytesIO()
    w = wave.open(buf, 'wb')
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(rate)
    w.writeframes(s.tobytes())
    w.close()
    return buf.getvalue()


def main():
    src, out = sys.argv[1], sys.argv[2]
    opts = dict(a.split('=', 1) for a in sys.argv[3:])
    maps = [m.strip().lower() for m in opts.get('map', 'mp/ffa3').split(',') if m.strip()]
    mobile = opts.get('profile', 'desktop') == 'mobile'

    def pk3s(d):
        # the engine loads a directory's pk3s in name order, later ones override earlier ones
        return [os.path.join(d, f) for f in sorted(os.listdir(d), key=str.lower)
                if f.lower().endswith('.pk3') and not f.lower().startswith(CODE_PK3)]
    paks = pk3s(src) + (pk3s(opts['mod']) if opts.get('mod') and os.path.isdir(opts['mod']) else [])
    zips = {pak: zipfile.ZipFile(pak) for pak in paks}

    def read(n):
        pak, orig = chosen[n]
        return zips[pak].read(orig)

    chosen = {}  # lowercase name -> (pak, original name); later paks win
    for pak in paks:
        for info in zips[pak].infolist():
            if keep(info.filename, maps, None):  # music is filtered below, once the bsps are known
                chosen[info.filename.lower()] = (pak, info.filename)
    missing = [m for m in maps if 'maps/' + m + '.bsp' not in chosen]
    if missing:
        sys.exit('maps not found: ' + ', '.join(missing))
    bsps = [read('maps/' + m + '.bsp') for m in maps]

    # music folders: MP menu music, the folder of every map's worldspawn "music" track, music=
    music = {'music/mp/'} | {d.strip().lower().rstrip('/') + '/' for d in opts.get('music', '').split(',') if d.strip()}
    for bsp in bsps:
        m = re.search(r'"music"\s+"([^"]+)"', entities(bsp).split('}', 1)[0], re.I)
        if m:
            for track in m.group(1).lower().replace('\\', '/').split():  # "<intro> <loop>"
                music.add(os.path.dirname(track) + '/')
    if mobile and opts.get('nomusic') == '1':
        music = set()
    for n in list(chosen):
        if not keep(n, maps, music):
            del chosen[n]

    need = needed_stems(read, set(chosen), maps)
    ambience = needed_ambience(read, set(chosen), bsps) if mobile else None
    for n in list(chosen):
        parts = n.split('/')
        if n.startswith(FILTERED) and stem(n) not in need:
            del chosen[n]
        elif mobile and (n.startswith(MOBILE_DROP)
                         or (n.startswith('sound/ambience/') and os.path.splitext(n)[0] not in ambience)
                         or (parts[:2] == ['sound', 'chars'] and len(parts) == 4)):
            del chosen[n]

    tmp = out + '.tmp'
    total = 0
    taken = set(chosen)
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as dst:
        for pak in paks:
            for info in zips[pak].infolist():
                if chosen.get(info.filename.lower()) != (pak, info.filename):
                    continue
                name, data = info.filename, zips[pak].read(info)
                low = name.lower()
                if mobile and low.endswith(IMAGE_EXT) and not low.startswith(('fonts/', 'maps/')):
                    name, data = shrink_image(name, data, taken)
                elif mobile and low.endswith('.wav'):
                    data = shrink_wav(data)
                # already-compressed formats are stored as-is
                method = zipfile.ZIP_STORED if name.lower().endswith(('.jpg', '.mp3', '.png', '.roq')) else zipfile.ZIP_DEFLATED
                zi = zipfile.ZipInfo(name, date_time=info.date_time)
                zi.compress_type = method
                dst.writestr(zi, data)
                total += 1
        # The engine lists subdirectories of a pk3 only from explicit directory entries
        # (FS_GetFileList(path, "/"), e.g. models/players/ for the UI's character lists).
        # keep() skips the originals, so write one for every directory that still holds files.
        dirs = {}
        for _, orig in chosen.values():
            for i, c in enumerate(orig):
                if c == '/':
                    dirs.setdefault(orig[:i + 1].lower(), orig[:i + 1])
        for d in sorted(dirs.values()):
            dst.writestr(zipfile.ZipInfo(d), b'')
    os.replace(tmp, out)
    print(f'{out}: {total} files, {os.path.getsize(out) / 1e6:.0f} MB')


if __name__ == '__main__':
    main()
