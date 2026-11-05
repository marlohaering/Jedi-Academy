"""Core 2D art + the main placeholder shader file."""
from PIL import Image, ImageDraw, ImageFont

from . import common

SHADERS = r'''
// ---- generated placeholder shaders ----
white
{
	{
		map *white
		blendfunc GL_SRC_ALPHA GL_ONE_MINUS_SRC_ALPHA
		rgbgen vertex
	}
}

console
{
	nopicmip
	nomipmaps
	{
		map gfx/menus/console_bg
		rgbgen identity
	}
}
'''


def charset():
    """gfx/2d/charsgrid_med: 16x16 grid of the 256 console characters."""
    size, cell = 512, 32
    img = Image.new('RGBA', (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(26)
    for code in range(33, 127):
        cx, cy = (code % 16) * cell, (code // 16) * cell
        draw.text((cx + cell / 2, cy + cell / 2), chr(code), font=font, fill=(255, 255, 255, 255), anchor='mm')
    return img


def console_bg():
    img = Image.new('RGBA', (256, 256))
    px = img.load()
    for y in range(256):
        for x in range(256):
            v = 10 + (y * 30) // 256
            px[x, y] = (v // 2, v, v + 25, 230)
    return img


def generate(existing):
    return {
        'shaders/zz_placeholder.shader': SHADERS,
        'sound/sound.txt': 'type ambientSet\n\n',
        'gfx/2d/charsgrid_med.tga': common.tga(charset()),
        'gfx/menus/console_bg.tga': common.tga(console_bg()),
    }
