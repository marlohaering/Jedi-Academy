"""Placeholder asset generators. Each module exposes generate(existing) -> {path: bytes|str}."""
import importlib

MODULES = ['menus', 'core', 'fonts', 'strings', 'textures', 'models', 'fx', 'sounds', 'maps']


def generate_all(existing):
    out = {}
    for name in MODULES:
        mod = importlib.import_module(f'gen.{name}')
        out.update(mod.generate({**existing, **out}))
    return out
