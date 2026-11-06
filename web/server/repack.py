#!/usr/bin/env python3
"""Build a slimmer client pk3 for browser players of the ffa3 FFA server.

The retail assets0-3.pk3 (1.2 GB) contain a lot that a multiplayer client on one map never
touches. This merges them (later pk3s override earlier ones, as in the engine) into one
pk3 without:
  - video/                  cinematics (single player)
  - sound/chr_d|chr_e|chr_f German/French/Spanish dialogue
  - maps/* except the served map (bsp + nav files of every other level)
  - music/* except MP music and the served map's music
Other pk3s in the base dir (e.g. japlus_gla_anims.pk3) and the asset pk3s of a server mod
directory (mod=/data/japlus) are merged on top, in the engine's search order. Pk3s with game
code (jampgame*, clientplugin*, cgame*, ui*) are skipped: the browser client has its own
cgame/ui compiled in and cannot load native DLLs.
The dedicated server keeps reading the original files; the client needs sv_pure 0.

usage: repack.py <base dir> <output.pk3> [map=mp/ffa3] [music=music/t1_sour] [mod=<mod dir>]
"""
import os
import sys
import zipfile


CODE_PK3 = ('jampgame', 'clientplugin', 'cgame', 'ui')


def keep(name, map_name, music_dirs):
    n = name.lower()
    if n.endswith('/') or n.endswith(('.dll', '.so', '.dylib', 'thumbs.db')):
        return False
    if n.startswith('video/'):
        return False
    if n.startswith(('sound/chr_d/', 'sound/chr_e/', 'sound/chr_f/')):
        return False
    if n.startswith('maps/'):
        return os.path.splitext(n)[0] == 'maps/' + map_name
    if n.startswith('music/'):
        return n.startswith(tuple(d + '/' for d in music_dirs))
    return True


def main():
    src, out = sys.argv[1], sys.argv[2]
    opts = dict(a.split('=', 1) for a in sys.argv[3:])
    map_name = opts.get('map', 'mp/ffa3').lower()
    music_dirs = ['music/mp'] + [d.lower() for d in opts.get('music', 'music/t1_sour').split(',')]

    def pk3s(d):
        # the engine loads a directory's pk3s in name order, later ones override earlier ones
        return [os.path.join(d, f) for f in sorted(os.listdir(d), key=str.lower)
                if f.lower().endswith('.pk3') and not f.lower().startswith(CODE_PK3)]
    paks = pk3s(src) + (pk3s(opts['mod']) if opts.get('mod') and os.path.isdir(opts['mod']) else [])
    chosen = {}  # lowercase name -> (pak, original name); later paks win
    for pak in paks:
        with zipfile.ZipFile(pak) as z:
            for info in z.infolist():
                if keep(info.filename, map_name, music_dirs):
                    chosen[info.filename.lower()] = (pak, info.filename)

    tmp = out + '.tmp'
    total = 0
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as dst:
        for pak in paks:
            with zipfile.ZipFile(pak) as z:
                for info in z.infolist():
                    hit = chosen.get(info.filename.lower())
                    if hit != (pak, info.filename):
                        continue
                    data = z.read(info)
                    # already-compressed formats are stored as-is
                    method = zipfile.ZIP_STORED if info.filename.lower().endswith(('.jpg', '.mp3', '.png', '.roq')) else zipfile.ZIP_DEFLATED
                    zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                    zi.compress_type = method
                    dst.writestr(zi, data)
                    total += 1
    os.replace(tmp, out)
    print(f'{out}: {total} files, {os.path.getsize(out) / 1e6:.0f} MB')


if __name__ == '__main__':
    main()
