#!/usr/bin/env python3
"""Build the gateway's app icons, favicons and settings icons.

Sources are the square artworks in gateway/art/icons: each app is drawn as a
full-bleed 1024 px SVG there, and its .webp beside it is that SVG rendered at
1024 px (any SVG renderer, for example a browser). Each artwork is masked to the
macOS continuous-corner squircle, given a light rim and a shadow, and written to
web/icons/apps. The gateway artwork also becomes the favicon set and the Apple
touch icon. The settings icons are a colored squircle with a white SF
Symbols-style glyph drawn in this script.

Needs Pillow:  python3 -m pip install Pillow
Then:          python3 gateway/scripts/build-icons.py && python3 gateway/runtime/build-info.py
"""
import base64
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

GATEWAY = Path(__file__).resolve().parents[1]
ART, WEB = GATEWAY / 'art/icons', GATEWAY / 'web'
APPS = ('gateway', 'settings', 'proxy', 'transfer', 'workstation', 'terminal', 'panel', 'adguard')
# Settings icons follow the current macOS System Settings sidebar: a squircle in an
# Apple system colour with a large white SF Symbols-style glyph, drawn on a 24-unit
# grid. Cut-outs use a mask so the tile colour shows through.
W = 'fill="#fff"'
S = 'fill="none" stroke="#fff" stroke-linecap="round" stroke-linejoin="round"'


def gear(teeth=8, outer=10.6, inner=8.3, hole=3.4):
    """SF gearshape.fill: rounded-off teeth and a round hole."""
    import math
    points = []
    for i in range(teeth):
        a = 2 * math.pi * i / teeth
        half, flank = math.pi / teeth * .52, math.pi / teeth * .3
        for angle, radius in ((a - half - flank, inner), (a - half, outer), (a + half, outer), (a + half + flank, inner)):
            points.append((12 + radius * math.sin(angle), 12 - radius * math.cos(angle)))
    ring = 'M' + ' L'.join(f'{x:.2f} {y:.2f}' for x, y in points) + 'Z'
    return (f'<path {W} fill-rule="evenodd" d="{ring} M12 {12 - hole}a{hole} {hole} 0 1 0 0 {2 * hole}a{hole} {hole} 0 1 0 0 {-2 * hole}Z"/>'
            f'<circle cx="12" cy="12" r="{inner - 1.2}" fill="none" stroke="#fff" stroke-width="2.4"/>')


def flower(petals=7):
    """SF camera.macro, as in the Wallpaper pane: outlined petals round a centre."""
    shapes = ''.join(f'<ellipse cx="12" cy="7.1" rx="2.9" ry="4.6" transform="rotate({360 * i / petals:.1f} 12 12)"/>' for i in range(petals))
    return f'<g {S} stroke-width="1.45">{shapes}<circle cx="12" cy="12" r="2.1"/></g>'


def cutout(name, solid, cut):
    """A white shape with a stroked cut-out, as in shield.checkmark.fill."""
    return (f'<mask id="{name}" maskUnits="userSpaceOnUse" x="0" y="0" width="24" height="24"><g fill="#fff">{solid}</g>'
            f'<g fill="none" stroke="#000" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round">{cut}</g></mask>'
            f'<rect width="24" height="24" fill="#fff" mask="url(#{name})"/>')


GLYPHS = {
    'gear': gear(),
    'branch': (f'<g {S} stroke-width="2.3"><path d="M12 21v-6.5L6.2 8.2M12 14.5l5.8-6.3"/></g>'
               f'<path {W} d="M3.6 3.2h6.2L4.3 9.4ZM20.4 3.2h-6.2l5.5 6.2Z" stroke="#fff" stroke-width="1.2" stroke-linejoin="round"/>'),
    'pin': (f'<path {W} fill-rule="evenodd" d="M12 2.2c-4.4 0-7.6 3.3-7.6 7.6 0 5.4 6.2 11 6.9 11.6.4.3 1 .3 1.4 0 .7-.6 6.9-6.2 6.9-11.6 0-4.3-3.2-7.6-7.6-7.6Z'
            'M12 6.6a3.1 3.1 0 1 1 0 6.2 3.1 3.1 0 1 1 0-6.2Z"/>'),
    'globe': (f'<g {S} stroke-width="1.6"><circle cx="12" cy="12" r="9.4"/><ellipse cx="12" cy="12" rx="4.1" ry="9.4"/>'
              '<path d="M2.6 12h18.8M4.1 7h15.8M4.1 17h15.8M12 2.6v18.8"/></g>'),
    'devices': (f'<path {W} fill-rule="evenodd" d="M3.4 5.2h11.2a1.6 1.6 0 0 1 1.6 1.6v8.4H1.8V6.8a1.6 1.6 0 0 1 1.6-1.6ZM3.6 7v6.4h10.8V7Z"/>'
                f'<rect x="0.6" y="16" width="16.6" height="2.4" rx="1.2" {W}/>'
                f'<path {W} fill-rule="evenodd" d="M18.6 9.2h3.2a1.6 1.6 0 0 1 1.6 1.6v8.4a1.6 1.6 0 0 1-1.6 1.6h-3.2a1.6 1.6 0 0 1-1.6-1.6v-8.4a1.6 1.6 0 0 1 1.6-1.6ZM18.6 11v7.6h3.2V11Z"/>'),
    'shield': cutout('shield', '<path d="M12 1.8 3.8 5.1v6c0 5.3 3.5 9.6 8.2 11.1 4.7-1.5 8.2-5.8 8.2-11.1v-6Z"/>', '<path d="m8.2 12.1 2.7 2.7 5.1-5.5"/>'),
    'dock': (f'<rect x="2.6" y="4.4" width="18.8" height="15.2" rx="3" {S} stroke-width="1.9"/>'
             f'<rect x="6.2" y="14.2" width="11.6" height="2.4" rx="1.2" {W}/>'),
    'flower': flower(),
    'lock': (f'<path {S} stroke-width="2.3" d="M7.6 11V7.9a4.4 4.4 0 0 1 8.8 0V11"/>'
             f'<rect x="4.4" y="10.2" width="15.2" height="11.6" rx="2.6" {W}/>'),
    'download': cutout('download', '<circle cx="12" cy="12" r="10"/>', '<path d="M12 6.6v9.4M7.8 12.1 12 16.2l4.2-4.1"/>'),
    'backup': (f'<g {S} stroke-width="2"><path d="M4.2 13.2A8 8 0 1 0 6.6 6.1"/><path d="M12 7.7V12l3 2"/></g>'
               f'<path {W} d="M3.4 3.6 9 4.6 4.4 9.2Z" stroke="#fff" stroke-width="1" stroke-linejoin="round"/>'),
    'code': f'<g {S} stroke-width="2.3"><path d="m7.4 7.2-4.8 4.8 4.8 4.8M16.6 7.2l4.8 4.8-4.8 4.8M13.6 4.6l-3.2 14.8"/></g>',
    'gateway': (f'<path {W} d="M3.6 21V11.2a8.4 8.4 0 0 1 16.8 0V21h-4.2v-9.6a4.2 4.2 0 0 0-8.4 0V21Z"/>'),
}
SETTINGS = {  # file: (glyph, top colour, bottom colour), close to Apple's system colours
    'general': ('gear', '#a2a2a7', '#77777c'),
    'proxy': ('branch', '#2f95ff', '#0a6ee6'),
    'routes': ('pin', '#ffaa33', '#ff8800'),
    'dns': ('globe', '#2f95ff', '#0a6ee6'),
    'tailscale': ('devices', '#7a78f0', '#5553d6'),
    'adguard': ('shield', '#4ad66d', '#28b24b'),
    'desktop': ('dock', '#3a3a3c', '#111113'),
    'appearance': ('flower', '#33c8ec', '#11a7d4'),
    'account': ('lock', '#ff5a52', '#ec3127'),
    'updates': ('download', '#c174ee', '#9f45d4'),
    'backup': ('backup', '#ffd426', '#f5b000'),
    'source': ('code', '#5a5a5e', '#2c2c2e'),
    'gateway': ('gateway', '#2f95ff', '#0a6ee6'),
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
            '<linearGradient id="rim" x1="16" y1="0" x2="16" y2="32" gradientUnits="userSpaceOnUse"><stop stop-color="#fff" stop-opacity=".42"/><stop offset=".5" stop-color="#fff" stop-opacity=".08"/><stop offset="1" stop-color="#fff" stop-opacity=".2"/></linearGradient>'
            f'</defs><path d="{shape}" fill="url(#bg)"/><path d="{squircle_path(.3, .3, 31.4, 31.4, 31.4 * RATIO)}" stroke="url(#rim)" stroke-width=".6"/>'
            f'<g transform="translate(5.6 5.6) scale(.8667)">{glyph}</g></svg>\n')


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
    (WEB / 'icons/settings').mkdir(exist_ok=True)
    for name, (glyph, top, bottom) in SETTINGS.items():
        (WEB / f'icons/settings/{name}.svg').write_text(settings_icon(GLYPHS[glyph], top, bottom))


if __name__ == '__main__':
    main()
