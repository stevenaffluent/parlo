"""The Parlo logo, "Waveform p": rounded voice bars whose heights trace a lowercase p.

Drawn on a 256-unit grid; web/logo.svg uses the same coordinates. Rendered 4x larger and scaled
down so small sizes (tray, taskbar) stay smooth.
"""
import math

from PIL import Image, ImageDraw

TILE = (194, 65, 12)  # the app's --accent-strong
TILE_REC = (200, 40, 40)  # while recording
WHITE = (255, 255, 255)
BAR_W = 18
STEM = (66, 52, 208)  # x, top, bottom: the stem drops below the bowl like a p
BOWL = (132, 112, 62)  # centre x, centre y, radius
BOWL_BARS = (92, 116, 140, 164, 188)


def bars():
    """(x, top, bottom) of every bar, in grid units."""
    cx, cy, r = BOWL
    out = [STEM]
    for x in BOWL_BARS:
        h = math.sqrt(max(r * r - (x - cx) ** 2, 0))
        out.append((x, cy - h, cy + h))
    return out


def make_icon(size=64, recording=False):
    px = max(256, size) * 4
    k = px / 256
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, px - 1, px - 1], radius=round(60 * k), fill=TILE_REC if recording else TILE)
    for x, top, bottom in bars():
        d.rounded_rectangle([(x - BAR_W / 2) * k, top * k, (x + BAR_W / 2) * k, bottom * k],
                            radius=BAR_W / 2 * k, fill=WHITE)
    return img.resize((size, size), Image.LANCZOS)


def save_ico(path):
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    imgs = [make_icon(n) for n in sizes]
    imgs[-1].save(str(path), format="ICO", sizes=[(n, n) for n in sizes], append_images=imgs[:-1])


def svg():
    rects = "".join(f'<rect x="{x - BAR_W / 2:g}" y="{top:.1f}" width="{BAR_W}" height="{bottom - top:.1f}" rx="{BAR_W / 2:g}"/>'
                    for x, top, bottom in bars())
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">'
            '<rect width="256" height="256" rx="60" fill="#C2410C"/>'
            f'<g fill="#fff">{rects}</g></svg>\n')


if __name__ == "__main__":  # python icon.py web/logo.svg  -> regenerate the vector logo from the same geometry
    import sys

    open(sys.argv[1], "w", encoding="utf-8").write(svg())
