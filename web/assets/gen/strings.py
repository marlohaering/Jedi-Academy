"""strings/english/*.str: StringEd tables.

The original string tables are part of the copyrighted asset paks, so we scan the
menus, ext_data and engine source for every string reference and generate a
readable English placeholder from the reference name (MENUS_NEW_GAME -> "New Game").
"""
import os
import re

from . import common

PREFIXES = ('MENUS', 'SP', 'CON', 'OBJECTIVES', 'BRIEFINGS', 'TIERVICTORY', 'MISC', 'CREDITS',
            'TIER1', 'TIER2', 'TIER3', 'T1', 'T2', 'T3', 'KEYNAMES', 'SABERS', 'DATAPAD', 'LOADSCREENS',
            'INGAME', 'HUD', 'MENU', 'MENUS0', 'MENUS1', 'MENUS2', 'MENUS3', 'MP')

# A few strings that read badly when derived mechanically.
OVERRIDES = {
    'MENUS_JEDI_ACADEMY': 'Jedi Academy',
    'MENUS_YES': 'Yes',
    'MENUS_NO': 'No',
    'MENUS_KEYBIND_OR': 'or',
    'MENUS_WAITINGFORKEY': 'Press a key...',
    'CON_TEXT_SKIPPING': 'Skipping',
    'SP_INGAME_LOADING': 'Loading',
    'MENUS_NEW': 'New Game',
}

REF_RE = re.compile(r'@([A-Z][A-Z0-9]*_[A-Za-z0-9_]+)')
QUOTED_RE = re.compile(r'"([A-Z][A-Z0-9]*_[A-Z0-9_]+)"')


def prettify(ref):
    words = ref.split('_')[1:]
    # drop the sub-file prefix for SP_INGAME_xxx style keys
    if words and words[0] in ('INGAME',) and len(words) > 1:
        words = words[1:]
    text = ' '.join(w.capitalize() if not w.isdigit() else w for w in words)
    return text or ref


def collect_refs(existing):
    refs = set()
    for name, data in existing.items():
        if name.endswith(('.menu', '.txt', '.npc', '.sab', '.cfg')):
            text = data.decode('latin-1') if isinstance(data, bytes) else data
            refs.update(REF_RE.findall(text))
    src = os.path.join(common.ENGINE_SRC, 'code')
    for root, _d, files in os.walk(src):
        for f in files:
            if not f.endswith(('.cpp', '.c', '.h')):
                continue
            with open(os.path.join(root, f), encoding='latin-1') as fh:
                text = fh.read()
            refs.update(REF_RE.findall(text))
            refs.update(QUOTED_RE.findall(text))
    return {r.upper() for r in refs if r.split('_')[0].upper() in PREFIXES}


def generate(existing):
    files = {}
    for ref in sorted(collect_refs(existing)):
        fileref, local = ref.split('_', 1)
        files.setdefault(fileref, []).append((local, OVERRIDES.get(ref, prettify(ref))))
    out = {}
    for fileref, entries in files.items():
        lines = ['VERSION "1"', 'CONFIG "W:\\bin\\stringed.cfg"', f'FILENOTES "placeholder {fileref}"', '']
        for local, text in entries:
            text = text.replace('"', "'")
            lines += [f'REFERENCE {local}', f'LANG_ENGLISH "{text}"', '']
        lines.append('ENDMARKER')
        out[f'strings/english/{fileref.lower()}.str'] = '\r\n'.join(lines) + '\r\n'
    return out
