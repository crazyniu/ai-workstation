#!/usr/bin/env python3
"""Build the gateway's app icons, favicons and settings icons.

Sources are the square artworks in gateway/art/icons. Each one is masked to the
macOS continuous-corner squircle, given a glass rim and a shadow, and written to
web/icons/apps. The gateway artwork also becomes the favicon set and the Apple
touch icon. The settings icons are a colored squircle with a white glyph from the
page's own sprite in web/index.html.

Needs Pillow:  python3 -m pip install Pillow
Then:          python3 gateway/scripts/build-icons.py && python3 gateway/runtime/build-info.py
"""
import base64
import io
from pathlib import Path
import re

from PIL import Image, ImageDraw, ImageFilter

GATEWAY = Path(__file__).resolve().parents[1]
ART, WEB = GATEWAY / 'art/icons', GATEWAY / 'web'
APPS = ('gateway', 'settings', 'proxy', 'transfer', 'workstation', 'panel', 'adguard')
SETTINGS = {  # file: (sprite glyph, top colour, bottom colour)
    'general': ('gear', '#a1a1a6', '#6e6e73'),
    'proxy': ('relay', '#3ea2ff', '#0a6cf0'),
    'routes': ('pin', '#ff9f43', '#f25c05'),
    'dns': ('globe', '#5ed0fa', '#1a8ff0'),
    'tailscale': ('devices', '#5a5a5f', '#2c2c30'),
    'adguard': ('shield', '#4cd964', '#21a038'),
    'desktop': ('dock', '#7d7aff', '#4b47e0'),
    'appearance': ('image', '#d77cff', '#9a3fd8'),
    'account': ('lock', '#ff6b61', '#e0263c'),
    'updates': ('download', '#4fd2e8', '#1393b3'),
    'backup': ('layers', '#ffd24a', '#f29a0c'),
    'source': ('code', '#4a4a4f', '#1c1c1e'),
    'gateway': ('gateway', '#3fa9f5', '#0e7fa8'),
}
RATIO = 0.2237  # corner radius as a share of the side, as in Apple's icon grid
SS = 4  # supersampling for smooth edges
# One continuous corner, from the incoming edge to the outgoing edge. Each point is
# (distance back along the incoming edge, distance along the outgoing edge) in radii.
CORNER = (
    ('M', ((1.52866483, 0),)),
    ('C', ((1.08849323, 0), (0.86840689, 0), (0.66993427, 0.06549600))),
    ('L', ((0.63149399, 0.07491100),)),
    ('C', ((0.37282392, 0.16905899), (0.16906013, 0.37282401), (0.07491176, 0.63149399))),
    ('C', ((0, 0.86840701), (0, 1.08849299), (0, 1.52866483))),
)


def segments(x, y, w, h, r):
    r = min(r, min(w, h) / 2 / 1.52866483)
    corners = (((x + w, y), (1, 0), (0, 1)), ((x + w, y + h), (0, 1), (-1, 0)),
               ((x, y + h), (-1, 0), (0, -1)), ((x, y), (0, -1), (1, 0)))
    for i, ((cx, cy), din, dout) in enumerate(corners):
        for op, points in CORNER:
            mapped = [(cx - a * r * din[0] + b * r * dout[0], cy - a * r * din[1] + b * r * dout[1]) for a, b in points]
            yield ('L' if op == 'M' and i else op), mapped


def squircle_path(x, y, w, h, r):
    """SVG path data of the squircle; the SVG tile icons use (10, 8, 76, 76, 76 * RATIO)."""
    fmt = lambda v: f'{round(v, 2):g}'
    return ''.join(op + ' '.join(fmt(px) + ' ' + fmt(py) for px, py in points)
                   for op, points in segments(x, y, w, h, r)) + 'Z'


def squircle_polygon(x, y, w, h, r, steps=24):
    points, last = [], None
    for op, seg in segments(x, y, w, h, r):
        if op in 'ML':
            last = seg[0]
            points.append(last)
            continue
        p0, (p1, p2, p3) = last, seg
        for i in range(1, steps + 1):
            t = i / steps
            u = 1 - t
            points.append(tuple(u ** 3 * a + 3 * u * u * t * b + 3 * u * t * t * c + t ** 3 * d
                                for a, b, c, d in zip(p0, p1, p2, p3)))
        last = p3
    return points


def mask(size, inset=0.0):
    big = size * SS
    side = big - 2 * inset * SS
    image = Image.new('L', (big, big), 0)
    ImageDraw.Draw(image).polygon(squircle_polygon(inset * SS, inset * SS, side, side, side * RATIO), fill=255)
    return image.resize((size, size), Image.LANCZOS)


def tile(art, size):
    """The artwork inside the squircle, with a light rim brightest at the top left."""
    image = art.resize((size, size), Image.LANCZOS).convert('RGBA')
    ring = Image.composite(Image.new('L', (size, size), 0), mask(size), mask(size, max(1.0, size / 160)))
    fade = Image.linear_gradient('L').rotate(45, expand=True).resize((size, size))
    fade = fade.point(lambda v: int(150 * max(0.0, 1 - v / 110) + 60 * max(0.0, (v - 150) / 105)))
    rim = Image.composite(fade, Image.new('L', (size, size), 0), ring)
    white = Image.new('L', (size, size), 255)
    image = Image.alpha_composite(image, Image.merge('RGBA', (white, white, white, rim)))
    image.putalpha(mask(size))
    return image


def app_icon(art, canvas=256):
    # Same geometry as the SVG family: a 76-unit tile at (10, 8) on a 96-unit canvas.
    unit = canvas / 96
    size, x, y = round(76 * unit), round(10 * unit), round(8 * unit)
    body = tile(art, size)
    shadow = Image.new('L', (canvas, canvas), 0)
    shadow.paste(body.getchannel('A'), (x, y + round(3 * unit)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(2.5 * unit)).point(lambda v: v * 56 // 255)
    out = Image.new('RGBA', (canvas, canvas), (22, 62, 82, 0))
    out.putalpha(shadow)
    out.alpha_composite(body, (x, y))
    return out


def settings_icon(glyph, top, bottom):
    shape = squircle_path(0, 0, 32, 32, 32 * RATIO)
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" fill="none"><defs>'
            f'<linearGradient id="bg" x1="16" y1="0" x2="16" y2="32" gradientUnits="userSpaceOnUse"><stop stop-color="{top}"/><stop offset="1" stop-color="{bottom}"/></linearGradient>'
            '<linearGradient id="gloss" x1="16" y1="0" x2="16" y2="18" gradientUnits="userSpaceOnUse"><stop stop-color="#fff" stop-opacity=".28"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
            f'</defs><path d="{shape}" fill="url(#bg)"/><path d="{shape}" fill="url(#gloss)"/>'
            f'<g transform="translate(6.4 6.4) scale(.8)" stroke="#fff" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round">{glyph}</g></svg>\n')


def main():
    (WEB / 'icons/apps').mkdir(exist_ok=True)
    for name in APPS:
        app_icon(Image.open(ART / f'{name}.webp').convert('RGB')).save(WEB / f'icons/apps/{name}.webp', 'WEBP', quality=90, method=6)
    art = Image.open(ART / 'gateway.webp').convert('RGB')
    favicon = tile(art, 256)
    favicon.save(WEB / 'favicon.ico', sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64)])
    favicon.resize((32, 32), Image.LANCZOS).save(WEB / 'favicon-32.png', optimize=True)
    png = io.BytesIO()
    favicon.resize((64, 64), Image.LANCZOS).save(png, 'PNG', optimize=True)
    (WEB / 'favicon.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><image width="64" height="64" href="data:image/png;base64,'
                                     + base64.b64encode(png.getvalue()).decode() + '"/></svg>\n')
    # iOS rounds the touch icon itself and expects an opaque square.
    art.resize((180, 180), Image.LANCZOS).save(WEB / 'apple-touch-icon.png', optimize=True)
    sprite = dict(re.findall(r'<symbol id="i-([\w-]+)" viewBox="0 0 24 24">(.*?)</symbol>', (WEB / 'index.html').read_text()))
    (WEB / 'icons/settings').mkdir(exist_ok=True)
    for name, (glyph, top, bottom) in SETTINGS.items():
        (WEB / f'icons/settings/{name}.svg').write_text(settings_icon(sprite[glyph], top, bottom))


if __name__ == '__main__':
    main()
