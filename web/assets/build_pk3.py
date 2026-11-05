#!/usr/bin/env python3
"""Builds zz_placeholder.pk3: everything the engine needs to boot and play,
made from (a) the text data shipped in this repo's base/ folder and
(b) procedurally generated placeholder art (textures, fonts, models, map, sounds).

Usage: build_pk3.py <output dir>
"""
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE)

import gen  # noqa: E402  (generators live in assets/gen/)


def repo_base_files():
    """Text assets that Raven shipped with the source release."""
    base = os.path.join(REPO, 'base')
    out = {}
    for root, _dirs, files in os.walk(base):
        for f in files:
            if f.endswith('.scc'):
                continue
            full = os.path.join(root, f)
            rel = os.path.relpath(full, base).replace(os.sep, '/')
            if rel.startswith('ui/jamp') or rel.startswith('ext_data/MP') or rel.startswith('ext_data/siege'):
                continue  # multiplayer-only data
            with open(full, 'rb') as fh:
                out[rel] = fh.read()
    return out


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, 'web', 'dist', 'base')
    os.makedirs(outdir, exist_ok=True)
    files = repo_base_files()
    files.update(gen.generate_all(files))
    path = os.path.join(outdir, 'zz_placeholder.pk3')
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for name in sorted(files):
            data = files[name]
            if isinstance(data, str):
                data = data.encode('latin-1')
            z.writestr(name, data)
    print(f'wrote {path}: {len(files)} files, {os.path.getsize(path) // 1024} KiB')


if __name__ == '__main__':
    main()
