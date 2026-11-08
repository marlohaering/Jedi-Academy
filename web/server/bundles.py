#!/usr/bin/env python3
"""Build private, content-addressed core/shared/map pk3s; publish the catalog atomically."""
import hashlib
import fcntl
import time
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import zipfile
from collections import defaultdict

import repack


def partition_files(core, maps):
    owners = defaultdict(list)
    for mapname, files in sorted(maps.items()):
        for name in files - core:
            owners[name].append(mapname)
    groups = {(): set(core)}
    for name, needed_by in owners.items():
        groups.setdefault(tuple(needed_by), set()).add(name)
    return groups


def input_fingerprint(source, mod=None):
    fingerprint = hashlib.sha256(Path(__file__).read_bytes() + Path(repack.__file__).read_bytes())
    for directory in [source] + ([mod] if mod and Path(mod).is_dir() else []):
        for p in sorted(Path(directory).glob('*.pk3'), key=lambda p: p.name.lower()):
            if p.name.lower().startswith(repack.CODE_PK3):
                continue
            fingerprint.update(p.name.lower().encode())
            with zipfile.ZipFile(p) as z:
                for info in z.infolist():
                    fingerprint.update(f'{info.filename}:{info.file_size}:{info.CRC}'.encode())
    return fingerprint.hexdigest()


def _build(source, output, mod=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    source_key = input_fingerprint(source, mod)
    try:
        previous = json.loads((output / 'bundles.json').read_text())
        if previous.get('sourceKey') == source_key and all((output / n).is_file() for n in previous['packages']):
            print('Map packages are up to date', flush=True)
            return previous
    except (OSError, ValueError, KeyError):
        pass
    archives = []
    chosen = {}
    for directory in [source] + ([mod] if mod and Path(mod).is_dir() else []):
        for path in sorted(Path(directory).glob('*.pk3'), key=lambda p: p.name.lower()):
            if path.name.lower().startswith(repack.CODE_PK3):
                continue
            z = zipfile.ZipFile(path)
            archives.append(z)
            for info in z.infolist():
                if repack.keep(info.filename, [], None) or info.filename.lower().startswith('maps/'):
                    if not info.is_dir():
                        chosen[info.filename.lower()] = (z, info)
    def read(name):
        z, info = chosen[name]
        return z.read(info)
    names = set(chosen)
    maps = sorted(n[5:-4] for n in names if n.startswith('maps/') and n.endswith('.bsp'))
    if not maps:
        raise ValueError('No installed BSP maps')
    print(f'Computing dependencies for {len(maps)} maps', flush=True)
    index = repack.dependency_index(read, names)
    global_need = repack.needed_stems(read, names, [], index)
    needs, music, ambience = {}, {}, {}
    base_ambience = repack.needed_ambience(read, names, [])
    for mapname in maps:
        bsp = read('maps/' + mapname + '.bsp')
        needs[mapname] = repack.needed_stems(read, names, [mapname], index)
        music[mapname] = set()
        track = re.search(r'"music"\s+"([^"]+)"', repack.entities(bsp).split('}', 1)[0], re.I)
        if track:
            music[mapname] = {os.path.dirname(t) + '/' for t in track[1].lower().replace('\\', '/').split()}
        ambience[mapname] = repack.needed_ambience(read, names, [bsp])
    catalog = {'sourceKey': source_key, 'format': 1, 'packages': {}, 'profiles': {}}
    for profile in ('desktop', 'mobile'):
        mobile = profile == 'mobile'
        def permitted(n):
            if not repack.keep(n, maps, None):
                return False
            if mobile:
                parts = n.split('/')
                if n.startswith(repack.MOBILE_DROP) or (parts[:2] == ['sound', 'chars'] and len(parts) == 4):
                    return False
            return True
        allowed = {n for n in names if permitted(n)}
        core = set()
        requirements = {m: set() for m in maps}
        for n in allowed:
            if n.startswith('maps/'):
                for m in maps:
                    if os.path.splitext(n)[0] == 'maps/' + m:
                        requirements[m].add(n)
            elif n.startswith('music/'):
                if n.startswith('music/mp/'):
                    core.add(n)
                else:
                    for m in maps:
                        if music[m] and n.startswith(tuple(music[m])):
                            requirements[m].add(n)
            elif n.startswith(repack.FILTERED):
                if repack.stem(n) in global_need:
                    core.add(n)
                else:
                    for m in maps:
                        if repack.stem(n) in needs[m]:
                            requirements[m].add(n)
            elif mobile and n.startswith('sound/ambience/'):
                if os.path.splitext(n)[0] in base_ambience:
                    core.add(n)
                else:
                    for m in maps:
                        if os.path.splitext(n)[0] in ambience[m]:
                            requirements[m].add(n)
            else:
                core.add(n)
        groups = partition_files(core, requirements)
        entries = {'core': [], 'maps': {m: [] for m in maps}}
        # Every selected source file belongs to exactly one package per profile.
        assert sum(map(len, groups.values())) == len(set().union(*groups.values()))
        for owners, files in sorted(groups.items()):
            if not files:
                continue
            fd, temporary = tempfile.mkstemp(prefix='.bundle-', dir=output)
            os.close(fd)
            try:
                directories = set()
                with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as dst:
                    for n in sorted(files):
                        _, info = chosen[n]
                        name, data = info.filename, read(n)
                        if mobile and n.endswith(repack.IMAGE_EXT) and not n.startswith(('fonts/', 'maps/')):
                            name, data = repack.shrink_image(name, data, allowed)
                        elif mobile and n.endswith('.wav'):
                            data = repack.shrink_wav(data)
                        zi = zipfile.ZipInfo(name, date_time=info.date_time)
                        zi.compress_type = zipfile.ZIP_STORED if name.lower().endswith(('.jpg', '.mp3', '.png', '.roq')) else zipfile.ZIP_DEFLATED
                        dst.writestr(zi, data)
                        for i, c in enumerate(name):
                            if c == '/': directories.add(name[:i + 1])
                    for d in sorted(directories): dst.writestr(zipfile.ZipInfo(d), b'')
                digest = None
                if digest is None:
                    h = hashlib.sha256()
                    with open(temporary, 'rb') as f:
                        for chunk in iter(lambda: f.read(1024 * 1024), b''): h.update(chunk)
                    digest = h.hexdigest()
                filename = f'jka-bundle-{profile}-{digest[:20]}.pk3'
                size = os.path.getsize(temporary)
                os.replace(temporary, output / filename)
                catalog['packages'][filename] = {'name': filename, 'size': size, 'version': digest}
                if not owners:
                    entries['core'].append(filename)
                else:
                    for m in owners: entries['maps'][m].append(filename)
            finally:
                if os.path.exists(temporary): os.unlink(temporary)
        catalog['profiles'][profile] = entries
        print(f'{profile}: {len(groups)} packages, {sum(catalog["packages"][n]["size"] for n in catalog["packages"] if n.startswith("jka-bundle-" + profile)) / 1e6:.1f} MB', flush=True)
    temp_index = output / '.bundles.json.tmp'
    temp_index.write_text(json.dumps(catalog, sort_keys=True))
    os.replace(temp_index, output / 'bundles.json')
    for z in archives: z.close()
    return catalog


def build(source, output, mod=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with open(output / '.build.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            old = json.loads((output / 'bundles.json').read_text())
            referenced = set(old['packages'])
        except (OSError, ValueError, KeyError):
            referenced = set()
        # Preserve the active catalog and allow 24 hours for in-flight old manifests.
        for p in output.glob('jka-bundle-*.pk3'):
            if p.name not in referenced and time.time() - p.stat().st_mtime > 86400:
                p.unlink()
        return _build(source, output, mod)


if __name__ == '__main__':
    build(*sys.argv[1:])


def select_manifest(catalog, mapname):
    """Resolve only the packages needed for this map in each device profile."""
    result = {'map': mapname, 'bundles': True}
    for profile, key in [('desktop', 'paks'), ('mobile', 'mobile')]:
        entries = catalog['profiles'][profile]
        names = entries['core'] + entries['maps'][mapname]
        result[key] = [catalog['packages'][n] for n in dict.fromkeys(names)]
    return result
