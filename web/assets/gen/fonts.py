"""fonts/*.fontdat + glyph atlases, rendered from Pillow's built-in (CC0) font."""
import struct

from PIL import Image, ImageDraw, ImageFont

from . import common

# name -> (point size, style)
FONTS = {
    'anewhope': (28, 'upper'),     # big titles
    'ergoec': (20, 'normal'),
    'arialnb': (16, 'normal'),
    'ocr_a': (16, 'normal'),
    'aurabesh': (16, 'alien'),
    'reallybigfont': (40, 'normal'),
}
ATLAS = 512


def build_font(point, style):
    font = ImageFont.load_default(point)
    ascent, descent = font.getmetrics()
    atlas = Image.new('RGBA', (ATLAS, ATLAS), (255, 255, 255, 0))
    draw = ImageDraw.Draw(atlas)
    glyphs = [(0, 0, 0, 0, 0, 0.0, 0.0, 0.0, 0.0)] * 256
    x, y, row_h = 1, 1, 0
    for code in range(32, 127):
        ch = chr(code)
        if style == 'upper':
            ch = ch.upper()
        left, top, right, bottom = font.getbbox(ch)
        adv = max(1, round(font.getlength(ch)))
        w, h = max(1, right - left), max(1, bottom - top)
        if code == 32:
            glyphs[code] = (0, 0, adv, 0, 0, 0.0, 0.0, 0.0, 0.0)
            continue
        if x + w + 2 > ATLAS:
            x, y, row_h = 1, y + row_h + 2, 0
        if style == 'alien':
            # "Aurebesh-like": blocky strokes derived from the character code
            for i in range(4):
                if (code >> i) & 1:
                    draw.rectangle([x + (i % 2) * w // 2, y + (i // 2) * h // 2,
                                    x + (i % 2 + 1) * w // 2 - 1, y + (i // 2 + 1) * h // 2 - 1],
                                   fill=(255, 255, 255, 255))
        else:
            draw.text((x - left, y - top), ch, font=font, fill=(255, 255, 255, 255))
        glyphs[code] = (w, h, adv, left, ascent - top,
                        x / ATLAS, y / ATLAS, (x + w) / ATLAS, (y + h) / ATLAS)
        x += w + 2
        row_h = max(row_h, h)
    data = b''.join(struct.pack('<4hi4f', *g) for g in glyphs)
    height = ascent + descent
    data += struct.pack('<5h2x', point, height, ascent, descent, 0)  # sizeof(dfontdat_t) == 7180
    return data, atlas


def generate(existing):
    out = {}
    for name, (point, style) in FONTS.items():
        dat, atlas = build_font(point, style)
        out[f'fonts/{name}.fontdat'] = dat
        out[f'fonts/{name}.tga'] = common.tga(atlas)
    return out
