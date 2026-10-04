"""Regenerate the launcher icon, presplash and Play listing artwork.

    python tools/make_store_art.py

Writes:

* ``data/icon.png``        512x512 launcher icon (Play requires 512x512 PNG)
* ``data/presplash.jpg``   480x800 shown while the activity starts
* ``store/feature-graphic.png``  1024x500, uploaded in Play Console only

``buildozer.spec`` points at the first two; ``verify_packaging.py`` fails the
build if the icon is not exactly 512x512, so overwrite the files rather than
editing the spec.  Needs Pillow.
"""

import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data")
STORE = os.path.join(ROOT, "store")
for _path in (OUT, STORE):
    os.makedirs(_path, exist_ok=True)

FONT = next(
    (p for p in (
        r"C:\Windows\Fonts\bahnschrift.ttf",
        r"C:\Windows\Fonts\segoeuib.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ) if os.path.exists(p)),
    None,
)

NAVY_TOP = (10, 12, 34)
NAVY_BOT = (22, 34, 74)
BODY = (230, 237, 248)
WING = (185, 200, 222)
COCKPIT = (90, 200, 250)
GLOW = (255, 183, 77)
EDGE = (8, 10, 26)


def gradient(w, h, top, bottom):
    col = Image.new("RGB", (1, h))
    px = col.load()
    for y in range(h):
        t = y / max(1, h - 1)
        px[0, y] = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
    return col.resize((w, h), Image.BILINEAR)


def stars(img, n, seed, lo=1, hi=3):
    rnd = random.Random(seed)
    w, h = img.size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for _ in range(n):
        x = rnd.uniform(0, w)
        y = rnd.uniform(0, h)
        r = rnd.uniform(lo, hi)
        a = rnd.randint(70, 235)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, a))
    return Image.alpha_composite(img.convert("RGBA"), layer)


def jet_polygons():
    """Jet silhouette in a 512x512 design space, nose up."""
    fuselage = [(256, 76), (273, 208), (278, 402), (234, 402), (239, 208)]
    wing_l = [(241, 240), (112, 368), (176, 404), (248, 344)]
    wing_r = [(271, 240), (400, 368), (336, 404), (264, 344)]
    stab_l = [(240, 364), (196, 424), (238, 430)]
    stab_r = [(272, 364), (316, 424), (274, 430)]
    pod_l = [(238, 386), (250, 386), (250, 420), (238, 420)]
    pod_r = [(262, 386), (274, 386), (274, 420), (262, 420)]
    return [
        (wing_l, WING), (wing_r, WING),
        (stab_l, WING), (stab_r, WING),
        (fuselage, BODY),
        (pod_l, EDGE), (pod_r, EDGE),
    ]


def draw_jet(d, cx, cy, scale):
    for pts, fill in jet_polygons():
        sp = [(cx + (x - 256) * scale, cy + (y - 256) * scale) for x, y in pts]
        d.polygon(sp, fill=fill, outline=EDGE, width=max(2, int(4 * scale)))
    # cockpit
    ck = (cx, cy - 256 * scale + 142 * scale)
    rx, ry = 15 * scale, 42 * scale
    d.ellipse([ck[0] - rx, ck[1] - ry, ck[0] + rx, ck[1] + ry],
              fill=COCKPIT, outline=EDGE, width=max(2, int(4 * scale)))
    # engine glow
    for ox in (-9, 9):
        gx = cx + ox * scale
        gy = cy + (420 - 256) * scale
        r = 17 * scale
        d.ellipse([gx - r, gy - r, gx + r, gy + r], fill=GLOW)


def glow_pass(img, cx, cy, scale, sigma):
    """Soft cyan bloom behind the jet."""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for pts, _ in jet_polygons():
        sp = [(cx + (x - 256) * scale, cy + (y - 256) * scale) for x, y in pts]
        d.polygon(sp, fill=(90, 200, 250, 255))
    layer = layer.filter(ImageFilter.GaussianBlur(sigma))
    return Image.alpha_composite(img, layer)


def font(size):
    """The chosen TTF where one exists, otherwise PIL bitmap font."""
    if FONT:
        return ImageFont.truetype(FONT, size)
    return ImageFont.load_default()


def fit_font(text, px, max_w):
    size = px
    while size > 8:
        f = font(size)
        b = f.getbbox(text)
        if (b[2] - b[0]) <= max_w:
            return f
        size -= 4
    return font(8)


def centered_text(d, xy, text, font, fill):
    b = font.getbbox(text)
    x, y = xy
    d.text((x - (b[2] - b[0]) / 2 - b[0], y), text, font=font, fill=fill)
    return b[3]


def make_icon():
    S = 4
    W = 512 * S
    cx = cy = W / 2
    img = gradient(W, W, NAVY_TOP, NAVY_BOT).convert("RGBA")
    img = stars(img, 90, 7, 1.4 * S, 3.4 * S)
    img = glow_pass(img, cx, cy, S, 40 * S)
    d = ImageDraw.Draw(img)
    draw_jet(d, cx, cy, S)
    out = img.resize((512, 512), Image.LANCZOS)
    p = os.path.join(OUT, "icon.png")
    out.convert("RGB").save(p, "PNG", optimize=True)
    return p, out.size


def make_presplash():
    S = 3
    W, H = 480 * S, 800 * S
    cx, cy, sc = W / 2, H * 0.27, 2.2
    img = gradient(W, H, NAVY_TOP, NAVY_BOT).convert("RGBA")
    img = stars(img, 120, 11, 1.1 * S, 2.6 * S)
    img = glow_pass(img, cx, cy, sc, 40)
    d = ImageDraw.Draw(img)
    draw_jet(d, cx, cy, sc)

    title = "SKY STRIKERS"
    f = fit_font(title, 78 * S, int(W * 0.86))
    ty = int(H * 0.56)
    bh = centered_text(d, (W / 2 + 3 * S, ty + 3 * S), title, f, (0, 0, 0, 170))
    centered_text(d, (W / 2, ty), title, f, (255, 255, 255, 255))

    tag = "TAKE THE SKIES"
    f2 = fit_font(tag, 30 * S, int(W * 0.72))
    centered_text(d, (W / 2, ty + bh + int(24 * S)), tag, f2, COCKPIT)

    y = int(H * 0.86)
    lw = int(W * 0.34)
    d.rectangle([(W - lw) / 2, y, (W + lw) / 2, y + 3 * S], fill=(255, 255, 255, 60))
    d.rectangle([(W - lw) / 2, y, (W - lw) / 2 + lw * 0.62, y + 3 * S], fill=COCKPIT)

    out = img.resize((480, 800), Image.LANCZOS)
    p = os.path.join(OUT, "presplash.jpg")
    out.convert("RGB").save(p, "JPEG", quality=86, optimize=True, progressive=True)
    return p, out.size


def make_feature_graphic():
    """Play store listing feature graphic - 1024x500."""
    S = 2
    W, H = 1024 * S, 500 * S
    cx, cy, sc = W * 0.22, H / 2, 1.55 * S
    img = gradient(W, H, NAVY_TOP, NAVY_BOT).convert("RGBA")
    img = stars(img, 150, 23, 1.2 * S, 2.8 * S)
    img = glow_pass(img, cx, cy, sc, 42 * S)
    d = ImageDraw.Draw(img)
    draw_jet(d, cx, cy, sc)

    title = "SKY STRIKERS"
    f = fit_font(title, 96 * S, int(W * 0.46))
    ty = int(H * 0.30)
    bh = centered_text(d, (W * 0.655 + 3 * S, ty + 3 * S), title, f,
                       (0, 0, 0, 170))
    centered_text(d, (W * 0.655, ty), title, f, (255, 255, 255, 255))

    tag = "TAKE THE SKIES"
    f2 = fit_font(tag, 40 * S, int(W * 0.34))
    centered_text(d, (W * 0.655, ty + bh + int(30 * S)), tag, f2, COCKPIT)

    out = img.resize((1024, 500), Image.LANCZOS)
    p = os.path.join(STORE, "feature-graphic.png")
    out.convert("RGB").save(p, "PNG", optimize=True)
    return p, out.size


if __name__ == "__main__":
    for fn in (make_icon, make_presplash, make_feature_graphic):
        path, size = fn()
        print(f"{path}  {size}  {os.path.getsize(path)} bytes")
