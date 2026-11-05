"""Shared helpers for the placeholder generators."""
import io
import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.abspath(os.path.join(HERE, '..', '..'))
ENGINE_SRC = os.path.join(WEB, 'engine', 'src')


def png(img):
    buf = io.BytesIO()
    img.save(buf, 'PNG', optimize=True)
    return buf.getvalue()


def tga(img):
    """Uncompressed 32-bit TGA (the engine reads TGAs for every image type)."""
    buf = io.BytesIO()
    img.convert('RGBA').save(buf, 'TGA', compression=None)
    return buf.getvalue()


def solid(color, size=(8, 8)):
    return Image.new('RGBA', size, color)


def checker(c1, c2, size=64, cells=4):
    img = Image.new('RGBA', (size, size), c1)
    step = size // cells
    for y in range(cells):
        for x in range(cells):
            if (x + y) % 2:
                img.paste(c2, (x * step, y * step, (x + 1) * step, (y + 1) * step))
    return img


def anim_names():
    """All animation enum names the game knows (from the engine's animtable)."""
    import re
    with open(os.path.join(ENGINE_SRC, 'code', 'cgame', 'animtable.cpp'), encoding='latin-1') as fh:
        return re.findall(r'ENUM2STRING\(((?:BOTH|TORSO|LEGS|FACE)_\w+)\)', fh.read())
