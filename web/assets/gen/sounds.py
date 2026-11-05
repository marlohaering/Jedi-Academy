"""Synthesised placeholder sound effects (saber hum/swings/clashes, blasters, impacts, voices, UI)."""
import io
import os
import re
import wave
import zlib

import numpy as np

from . import common

RATE = 22050

# NPC types that appear in the generated level (+ the player); their voice sets get generated
VOICED_NPCS = ('stormtrooper', 'stormtrooperofficer', 'reborn', 'player', 'jedi_tf', 'kyle', 'jeditrainer')
BASIC = ['death1', 'death2', 'death3', 'jump1', 'pain25', 'pain50', 'pain75', 'pain100', 'gasp', 'land1',
         'falling1', 'drown', 'gurp1', 'gurp2']
COMBAT = ['anger1', 'anger2', 'anger3', 'victory1', 'victory2', 'victory3', 'confuse1', 'confuse2', 'confuse3',
          'pushed1', 'pushed2', 'pushed3', 'choke1', 'choke2', 'choke3', 'ffwarn', 'ffturn']
EXTRA = ['chase1', 'chase2', 'chase3', 'cover1', 'cover2', 'cover3', 'detected1', 'detected2', 'detected3',
         'lost1', 'outflank1', 'outflank2', 'escaping1', 'escaping2', 'giveup1', 'giveup2', 'look1', 'look2',
         'sight1', 'sight2', 'sight3', 'sound1', 'sound2', 'sound3', 'suspicious1', 'suspicious2']
JEDI = ['combat1', 'combat2', 'combat3', 'jdetected1', 'jdetected2', 'jdetected3', 'taunt1', 'taunt2', 'taunt3',
        'jchase1', 'jchase2', 'jchase3', 'jlost1', 'jlost2', 'jlost3', 'deflect1', 'deflect2', 'deflect3',
        'victory1', 'victory2', 'victory3', 'gloat1', 'gloat2', 'gloat3', 'pushfail']


def wav(samples):
    s = np.clip(samples, -1, 1)
    pcm = (s * 32000).astype('<i2').tobytes()
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    return buf.getvalue()


def t_(dur):
    return np.arange(int(dur * RATE)) / RATE


def env(n, attack=0.005, release=None):
    e = np.ones(n)
    a = max(1, int(attack * RATE))
    e[:a] = np.linspace(0, 1, a)
    r = n if release is None else max(1, int(release * RATE))
    e[-r:] *= np.linspace(1, 0, r) ** 2
    return e


def rng_for(name):
    return np.random.default_rng(zlib.crc32(name.encode()))


def lowpass(x, k=8):
    return np.convolve(x, np.ones(k) / k, mode='same')


def saber_hum(name):
    t = t_(1.0)
    f = 90  # integer cycles per second -> seamless loop
    x = 0.45 * np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * 2 * f * t + 0.5) \
        + 0.12 * np.sin(2 * np.pi * 3 * f * t) + 0.05 * np.sign(np.sin(2 * np.pi * f * t))
    return x * (0.85 + 0.15 * np.sin(2 * np.pi * 3 * t))


def saber_on(name, up=True):
    t = t_(0.55)
    f = np.linspace(40, 90, len(t)) if up else np.linspace(90, 30, len(t))
    ph = 2 * np.pi * np.cumsum(f) / RATE
    x = 0.5 * np.sin(ph) + 0.3 * np.sin(2 * ph) + 0.15 * rng_for(name).standard_normal(len(t)) * np.linspace(1, 0, len(t))
    return x * env(len(t), 0.01, 0.2)


def swing(name):
    r = rng_for(name)
    dur = r.uniform(0.25, 0.4)
    t = t_(dur)
    f = 90 * (1 + 0.6 * np.sin(np.pi * t / dur))
    ph = 2 * np.pi * np.cumsum(f) / RATE
    x = 0.6 * np.sin(ph) + 0.3 * np.sin(2 * ph) + 0.2 * lowpass(r.standard_normal(len(t)), 6)
    return x * np.sin(np.pi * t / dur) ** 1.5


def clash(name):
    r = rng_for(name)
    t = t_(0.35)
    x = sum(np.sin(2 * np.pi * f * t) * a for f, a in ((1200 * r.uniform(.9, 1.1), .3), (2300, .2), (3700, .1)))
    x = x + 0.8 * r.standard_normal(len(t)) * np.exp(-t * 40)
    return x * np.exp(-t * 9)


def blaster(name):
    r = rng_for(name)
    dur = 0.28
    t = t_(dur)
    f0 = r.uniform(1400, 2200)
    f = f0 * np.exp(-t * 9) + 180
    ph = 2 * np.pi * np.cumsum(f) / RATE
    x = 0.6 * np.sin(ph) + 0.25 * np.sign(np.sin(ph)) + 0.15 * r.standard_normal(len(t)) * np.exp(-t * 30)
    return x * env(len(t), 0.002, 0.15)


def impact(name, dur=0.25, low=False):
    r = rng_for(name)
    t = t_(dur)
    n = r.standard_normal(len(t))
    if low:
        n = lowpass(n, 30) * 3
    return np.clip(n * np.exp(-t * (8 if low else 22)), -1, 1) * 0.8


def explosion(name):
    t = t_(1.2)
    r = rng_for(name)
    n = lowpass(r.standard_normal(len(t)), 40) * 4
    rumble = 0.5 * np.sin(2 * np.pi * 45 * t) * np.exp(-t * 3)
    return np.clip((n * np.exp(-t * 3.5) + rumble), -1, 1)


def footstep(name):
    r = rng_for(name)
    t = t_(0.09)
    x = lowpass(r.standard_normal(len(t)), 12) * 2 + 0.4 * np.sin(2 * np.pi * 70 * t)
    return x * np.exp(-t * 45) * 0.5


def click(name):
    t = t_(0.06)
    f = 1800 if 'off' not in name else 900
    return 0.4 * np.sin(2 * np.pi * f * t) * np.exp(-t * 60)


def voice(name, dur=None):
    """Vocal-ish grunt: buzzy glottal pulse train through two formant resonances."""
    r = rng_for(name)
    is_death = 'death' in name
    dur = dur or (0.6 if is_death else r.uniform(0.25, 0.45))
    t = t_(dur)
    f0 = r.uniform(95, 140) if not name.endswith('_f') else r.uniform(190, 240)
    f = f0 * (np.linspace(1.1, 0.6, len(t)) if is_death else 1 + 0.15 * np.sin(np.pi * t / dur))
    ph = 2 * np.pi * np.cumsum(f) / RATE
    src = np.sign(np.sin(ph)) * 0.5 + 0.5 * np.sin(ph)
    x = np.zeros_like(src)
    for formant, amp in ((r.uniform(500, 800), 1.0), (r.uniform(1100, 1600), 0.5)):
        x += amp * np.sin(2 * np.pi * formant * t) * (0.5 + 0.5 * src)
    x = 0.6 * src + 0.2 * x
    return lowpass(x, 3) * env(len(t), 0.02, dur * 0.6) * 0.6


def ambient(name):
    r = rng_for(name)
    t = t_(1.0)
    return lowpass(r.standard_normal(len(t)), 60) * 0.3 * env(len(t), 0.2, 0.3)


def synth(path):
    p = path.lower()
    name = os.path.basename(p)
    if 'saber' in p or 'lightsaber' in p:
        if 'hum' in name or 'loop' in name:
            return saber_hum(name)
        if name.startswith(('saberon', 'enemy_saber_on')) or 'ignite' in name or name.endswith('on'):
            return saber_on(name, True)
        if name.startswith('saberoff') or name.endswith('off'):
            return saber_on(name, False)
        if any(k in name for k in ('hup', 'swing', 'spin', 'swish', 'whoosh', 'woosh')):
            return swing(name)
        if any(k in name for k in ('block', 'hit', 'clash', 'bounce', 'saberhit', 'lock')):
            return clash(name)
        return swing(name)
    if 'footstep' in p or '/foot' in p or 'step' in name:
        return footstep(name)
    if 'interface' in p or 'menu' in p or 'button' in name:
        return click(name)
    if any(k in p for k in ('explo', 'detpack', 'thermal/explode', 'rocket/explode', 'boom')):
        return explosion(name)
    if '/chars/' in p or 'voice' in name:
        return voice(name)
    if '/weapons/' in p:
        if any(k in name for k in ('fire', 'shot', 'shoot', 'alt_fire', 'charge')):
            return blaster(name)
        if any(k in name for k in ('hit', 'impact', 'ric', 'bounce', 'deflect', 'wall')):
            return impact(name)
        if 'select' in name or 'change' in name or 'pkup' in name or 'pickup' in name:
            return click(name)
        return impact(name, 0.15)
    if 'ambience' in p or 'ambient' in p or 'loop' in name:
        return ambient(name)
    if 'player' in p or 'movers' in p:
        return impact(name, 0.2, low=True)
    return impact(name, 0.15)


def expand(pattern):
    if '%s' in pattern:
        return []
    out = [pattern]
    for _ in range(pattern.count('%')):
        nxt = []
        for p in out:
            m = re.search(r'%0?(\d)?[di]', p)
            if not m:
                nxt.append(p)
                continue
            for i in range(1, 5):
                nxt.append(p[:m.start()] + (f'{i:02d}' if '%02' in m.group(0) else str(i)) + p[m.end():])
        out = nxt
    return out


def sound_paths(existing):
    paths = set()
    src = os.path.join(common.ENGINE_SRC, 'code')
    for root, _d, files in os.walk(src):
        for f in files:
            if f.endswith(('.cpp', '.h')):
                with open(os.path.join(root, f), encoding='latin-1') as fh:
                    for m in re.findall(r'"(sound/[^"]+)"', fh.read()):
                        paths.update(expand(m))
    for path, data in existing.items():
        if path.endswith(('.menu', '.dat', '.npc', '.sab', '.veh', '.vwp', '.txt', '.cfg')):
            text = data.decode('latin-1') if isinstance(data, bytes) else data
            paths.update(re.findall(r'(sound/[A-Za-z0-9_/\.\-]+)', text))
    out = set()
    for p in paths:
        p = p.lower().strip('.').replace('\\', '/')
        if p.endswith('/') or '%' in p:
            continue
        stem = re.sub(r'\.(wav|mp3)$', '', p)
        # skip story/cinematic dialogue and other big unused sets
        if stem.startswith(('sound/chars/storyinfo', 'sound/chars/tiervictory', 'sound/cinematics', 'sound/music')):
            continue
        out.add(stem + '.wav')
    return out


def voice_paths(existing):
    dirs = set()
    for path, data in existing.items():
        if not path.startswith('ext_data/npcs/'):
            continue
        text = data.decode('latin-1') if isinstance(data, bytes) else data
        for block in re.finditer(r'^\s*(\w+)\s*\{(.*?)^\s*\}', text, re.M | re.S):
            if block.group(1).lower() not in VOICED_NPCS:
                continue
            for key, d in re.findall(r'^\s*(snd|sndcombat|sndextra|sndjedi)\s+"?([\w]+)"?', block.group(2), re.M | re.I):
                dirs.add((key.lower(), d.lower()))
    out = set()
    sets = {'snd': BASIC, 'sndcombat': COMBAT, 'sndextra': EXTRA, 'sndjedi': JEDI}
    for key, d in dirs:
        for n in sets[key]:
            out.add(f'sound/chars/{d}/misc/{n}.wav')
    return out


def generate(existing):
    out = {}
    for p in sorted(sound_paths(existing) | voice_paths(existing)):
        out[p] = wav(synth(p))
    return out
